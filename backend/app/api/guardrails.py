"""Excluded actions (hard blocks + free-text rules) and standing permissions."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import grant_json
from app.auth import current_user
from app.db import get_session
from app.models import Campaign, ExclusionRule, PermissionGrant, User, utcnow
from app.services import activity
from app.services.events import notify
from app.services.policy import ACTION_TYPES
from app.services.rule_check import BUILT_IN_RULES

router = APIRouter(prefix="/api", tags=["guardrails"])


class ExclusionIn(BaseModel):
    campaign_id: str | None = None  # None = all campaigns
    kind: str = Field(pattern="^(action_type|app|site|text)$")
    value: str = Field(min_length=1, max_length=2000)


class GrantIn(BaseModel):
    campaign_id: str | None = None
    action_type: str
    scope: str | None = None
    spend_limit_usd: Decimal | None = None


def _exclusion_json(e: ExclusionRule) -> dict:
    label = ACTION_TYPES[e.value].label if e.kind == "action_type" and e.value in ACTION_TYPES else None
    return {"id": e.id, "campaign_id": e.campaign_id, "kind": e.kind, "value": e.value, "label": label,
            "created_at": e.created_at.isoformat()}


async def _bump(s: AsyncSession, user: User, campaign_id: str | None, title: str) -> None:
    """Guardrails changed: running agents are told on their next step."""
    q = select(Campaign).where(Campaign.owner_id == user.id)
    if campaign_id is not None:
        q = q.where(Campaign.id == campaign_id)
    for c in (await s.execute(q)).scalars():
        c.guardrail_version += 1
        await activity.log(s, c.id, "system", title, status="info")
        await notify(s, c.id, "guardrails")


async def _own_campaign(s: AsyncSession, user: User, campaign_id: str | None) -> None:
    if campaign_id is None:
        return
    c = await s.get(Campaign, campaign_id)
    if not c or c.owner_id != user.id:
        raise HTTPException(404, "Goal not found")


def _mine(model, user: User, campaign_id: str | None):
    """The user's rules: for one goal (plus their all-goals rules), or all of them."""
    if campaign_id:
        return or_(model.campaign_id == campaign_id, and_(model.campaign_id.is_(None), model.owner_id == user.id))
    return model.owner_id == user.id


@router.get("/guardrails/built-in")
async def built_in():
    return {"rules": BUILT_IN_RULES}


@router.get("/exclusions")
async def list_exclusions(campaign_id: str | None = None, s: AsyncSession = Depends(get_session),
                          user: User = Depends(current_user)):
    await _own_campaign(s, user, campaign_id)
    rows = (
        await s.execute(select(ExclusionRule).where(_mine(ExclusionRule, user, campaign_id))
                        .order_by(ExclusionRule.created_at))
    ).scalars().all()
    return [_exclusion_json(e) for e in rows]


@router.post("/exclusions")
async def add_exclusion(body: ExclusionIn, s: AsyncSession = Depends(get_session),
                        user: User = Depends(current_user)):
    if body.kind == "action_type" and body.value not in ACTION_TYPES:
        raise HTTPException(400, f"Unknown action type {body.value}")
    await _own_campaign(s, user, body.campaign_id)
    e = ExclusionRule(campaign_id=body.campaign_id, owner_id=user.id, kind=body.kind, value=body.value.strip())
    s.add(e)
    await s.flush()
    shown = ACTION_TYPES[e.value].label if e.kind == "action_type" else e.value
    await _bump(s, user, body.campaign_id, f"Guardrail added: don't {shown}" if e.kind == "action_type"
                else f"Guardrail added ({e.kind}): {shown}")
    return _exclusion_json(e)


@router.delete("/exclusions/{exclusion_id}")
async def delete_exclusion(exclusion_id: str, s: AsyncSession = Depends(get_session),
                           user: User = Depends(current_user)):
    e = await s.get(ExclusionRule, exclusion_id)
    if not e or e.owner_id != user.id:
        raise HTTPException(404, "Not found")
    campaign_id, value = e.campaign_id, e.value
    await s.delete(e)
    await _bump(s, user, campaign_id, f"Guardrail removed: {value}")
    return {"ok": True}


@router.get("/grants")
async def list_grants(campaign_id: str | None = None, s: AsyncSession = Depends(get_session),
                      user: User = Depends(current_user)):
    await _own_campaign(s, user, campaign_id)
    q = (
        select(PermissionGrant, Campaign.name)
        .outerjoin(Campaign, Campaign.id == PermissionGrant.campaign_id)
        .where(PermissionGrant.revoked_at.is_(None), _mine(PermissionGrant, user, campaign_id))
    )
    rows = (await s.execute(q.order_by(PermissionGrant.created_at))).all()
    return [grant_json(g, name) for g, name in rows]


@router.post("/grants")
async def add_grant(body: GrantIn, s: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    if body.action_type not in ACTION_TYPES:
        raise HTTPException(400, "Unknown action type")
    if body.action_type == "spend_money" and body.spend_limit_usd is None:
        raise HTTPException(400, "A spending permission needs a per-action limit")
    await _own_campaign(s, user, body.campaign_id)
    g = PermissionGrant(campaign_id=body.campaign_id, owner_id=user.id, action_type=body.action_type,
                        scope=body.scope, spend_limit_usd=body.spend_limit_usd)
    s.add(g)
    await s.flush()
    await _bump(s, user, body.campaign_id, f"Permission added: {ACTION_TYPES[g.action_type].label} without asking")
    return grant_json(g)


@router.delete("/grants/{grant_id}")
async def revoke_grant(grant_id: str, s: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    g = await s.get(PermissionGrant, grant_id)
    if not g or g.revoked_at or g.owner_id != user.id:
        raise HTTPException(404, "Not found")
    g.revoked_at = utcnow()
    label = ACTION_TYPES[g.action_type].label if g.action_type in ACTION_TYPES else g.action_type
    await _bump(s, user, g.campaign_id, f"Permission revoked: will ask again before \"{label}\"")
    return {"ok": True}
