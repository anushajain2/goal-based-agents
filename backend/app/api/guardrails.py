"""Excluded actions (hard blocks + free-text rules) and standing permissions.

Each can be set on one goal, on a department (every goal its AI employees work on), or on the
whole organization. Organization-wide ones need an admin; department ones need someone in that
department; goal ones need someone who can manage the goal.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import grant_json
from app.db import get_session
from app.models import Agent, Campaign, Department, ExclusionRule, PermissionGrant, utcnow
from app.org import Member, current_member, get_goal, goal_department, require_admin
from app.services import activity
from app.services.events import notify
from app.services.policy import ACTION_TYPES
from app.services.rule_check import BUILT_IN_RULES

router = APIRouter(prefix="/api", tags=["guardrails"])


class ExclusionIn(BaseModel):
    campaign_id: str | None = None  # one goal...
    department_id: str | None = None  # ...or a department; neither = the whole organization
    kind: str = Field(pattern="^(action_type|app|site|text)$")
    value: str = Field(min_length=1, max_length=2000)


class GrantIn(BaseModel):
    campaign_id: str | None = None
    department_id: str | None = None
    action_type: str
    scope: str | None = None
    spend_limit_usd: Decimal | None = None


def _level(row) -> str:
    return "goal" if row.campaign_id else "department" if row.department_id else "org"


def _exclusion_json(e: ExclusionRule) -> dict:
    label = ACTION_TYPES[e.value].label if e.kind == "action_type" and e.value in ACTION_TYPES else None
    return {"id": e.id, "campaign_id": e.campaign_id, "department_id": e.department_id, "level": _level(e),
            "kind": e.kind, "value": e.value, "label": label, "created_at": e.created_at.isoformat()}


async def _check_scope(s: AsyncSession, me: Member, campaign_id: str | None, department_id: str | None) -> None:
    """Who may set or remove a rule/permission at this level."""
    if campaign_id:
        await get_goal(s, me, campaign_id, manage=True)
    elif department_id:
        d = await s.get(Department, department_id)
        if not d or d.org_id != me.org_id:
            raise HTTPException(404, "Department not found")
        if not me.in_department(department_id):
            raise HTTPException(403, "Only people in this department (or admins) can change its rules.")
    else:
        require_admin(me)


async def _bump(s: AsyncSession, me: Member, campaign_id: str | None, department_id: str | None, title: str) -> None:
    """Rules changed: running AI employees are told on their next step."""
    q = select(Campaign).where(Campaign.org_id == me.org_id)
    if campaign_id:
        q = q.where(Campaign.id == campaign_id)
    elif department_id:
        q = q.where(Campaign.agent_id.in_(select(Agent.id).where(Agent.department_id == department_id)))
    who = me.user.name or me.user.email
    for c in (await s.execute(q)).scalars():
        c.guardrail_version += 1
        await activity.log(s, c.id, "system", f"{title} (by {who})", status="info")
        await notify(s, c.id, "guardrails")


async def _covering(s: AsyncSession, me: Member, model, campaign_id: str | None, department_id: str | None):
    """Filter: the rows that apply to a goal (its own + its department's + org-wide), to a
    department (its own + org-wide), or every row in the organization."""
    org_wide = and_(model.org_id == me.org_id, model.campaign_id.is_(None), model.department_id.is_(None))
    if campaign_id:
        c = await get_goal(s, me, campaign_id)
        dept = await goal_department(s, c)
        return or_(model.campaign_id == campaign_id,
                   and_(model.campaign_id.is_(None), model.department_id == dept), org_wide)
    if department_id:
        return or_(and_(model.campaign_id.is_(None), model.department_id == department_id), org_wide)
    return model.org_id == me.org_id


@router.get("/guardrails/built-in")
async def built_in():
    return {"rules": BUILT_IN_RULES}


@router.get("/exclusions")
async def list_exclusions(campaign_id: str | None = None, department_id: str | None = None,
                          s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    where = await _covering(s, me, ExclusionRule, campaign_id, department_id)
    rows = (await s.execute(select(ExclusionRule).where(where).order_by(ExclusionRule.created_at))).scalars().all()
    return [_exclusion_json(e) for e in rows]


@router.post("/exclusions")
async def add_exclusion(body: ExclusionIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    if body.kind == "action_type" and body.value not in ACTION_TYPES:
        raise HTTPException(400, f"Unknown action type {body.value}")
    department_id = None if body.campaign_id else body.department_id
    await _check_scope(s, me, body.campaign_id, department_id)
    e = ExclusionRule(org_id=me.org_id, owner_id=me.user.id, campaign_id=body.campaign_id,
                      department_id=department_id, kind=body.kind, value=body.value.strip())
    s.add(e)
    await s.flush()
    shown = ACTION_TYPES[e.value].label if e.kind == "action_type" else e.value
    await _bump(s, me, body.campaign_id, department_id,
                f"Guardrail added: don't {shown}" if e.kind == "action_type" else f"Guardrail added ({e.kind}): {shown}")
    return _exclusion_json(e)


@router.delete("/exclusions/{exclusion_id}")
async def delete_exclusion(exclusion_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    e = await s.get(ExclusionRule, exclusion_id)
    if not e or e.org_id != me.org_id:
        raise HTTPException(404, "Not found")
    await _check_scope(s, me, e.campaign_id, e.department_id)
    campaign_id, department_id, value = e.campaign_id, e.department_id, e.value
    await s.delete(e)
    await _bump(s, me, campaign_id, department_id, f"Guardrail removed: {value}")
    return {"ok": True}


@router.get("/grants")
async def list_grants(campaign_id: str | None = None, department_id: str | None = None,
                      s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    where = await _covering(s, me, PermissionGrant, campaign_id, department_id)
    q = (
        select(PermissionGrant, Campaign.name, Department.name)
        .outerjoin(Campaign, Campaign.id == PermissionGrant.campaign_id)
        .outerjoin(Department, Department.id == PermissionGrant.department_id)
        .where(PermissionGrant.revoked_at.is_(None), where)
    )
    rows = (await s.execute(q.order_by(PermissionGrant.created_at))).all()
    return [{**grant_json(g, goal_name), "department_id": g.department_id, "department_name": dept_name,
             "level": _level(g)} for g, goal_name, dept_name in rows]


@router.post("/grants")
async def add_grant(body: GrantIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    if body.action_type not in ACTION_TYPES:
        raise HTTPException(400, "Unknown action type")
    if body.action_type == "spend_money" and body.spend_limit_usd is None:
        raise HTTPException(400, "A spending permission needs a per-action limit")
    department_id = None if body.campaign_id else body.department_id
    await _check_scope(s, me, body.campaign_id, department_id)
    g = PermissionGrant(org_id=me.org_id, owner_id=me.user.id, granted_by=me.user.id, campaign_id=body.campaign_id,
                        department_id=department_id, action_type=body.action_type, scope=body.scope,
                        spend_limit_usd=body.spend_limit_usd)
    s.add(g)
    await s.flush()
    await _bump(s, me, body.campaign_id, department_id,
                f"Permission added: {ACTION_TYPES[g.action_type].label} without asking")
    return grant_json(g)


@router.delete("/grants/{grant_id}")
async def revoke_grant(grant_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    g = await s.get(PermissionGrant, grant_id)
    if not g or g.revoked_at or g.org_id != me.org_id:
        raise HTTPException(404, "Not found")
    await _check_scope(s, me, g.campaign_id, g.department_id)
    g.revoked_at = utcnow()
    label = ACTION_TYPES[g.action_type].label if g.action_type in ACTION_TYPES else g.action_type
    await _bump(s, me, g.campaign_id, g.department_id, f"Permission revoked: will ask again before \"{label}\"")
    return {"ok": True}
