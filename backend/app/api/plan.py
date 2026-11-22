"""What a goal will do and what it needs before it starts.

    GET  /api/estimate                         budget suggestion for a schedule (sessions x cost)
    POST /api/campaigns/{id}/playbook          the goal's plan of steps (made once, or remade)
    GET  /api/campaigns/{id}/permissions       per kind of action: on its own / ask first / never
    PUT  /api/campaigns/{id}/permissions/{t}   change that for this goal
    GET  /api/campaigns/{id}/readiness         tools to connect + approvals, shown before starting
    POST /api/sites/signed-in                  "I signed in to this site in Agent Chrome"
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import MeteredClaude
from app.agent.playbook import default_playbook, generate_playbook, tools_needed
from app.connectors.composio_hub import get_hub
from app.db import get_session
from app.models import (
    Campaign,
    Department,
    ExclusionRule,
    McpServer,
    PermissionGrant,
    RequestKind,
    RequestStatus,
    SiteSignIn,
    UserRequest,
    utcnow,
)
from app.org import Member, approvers, current_member, get_goal, goal_department
from app.services import activity, estimate, permissions
from app.services.events import notify
from app.services.policy import ACTION_TYPES, domain_of
from app.services.rule_check import BUILT_IN_RULES
from app.services.website import UnsafeURL, normalize_url

router = APIRouter(prefix="/api", tags=["plan"], dependencies=[Depends(current_member)])


@router.get("/estimate")
async def budget_estimate(cycle_hours: float = 6, days: float = 30, paid_spend_usd: float = 0,
                          s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    return await estimate.estimate(s, me.org_id, cycle_hours, days, paid_spend_usd)


# --- the plan ----------------------------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/playbook")
async def make_playbook(campaign_id: str, remake: bool = False, s: AsyncSession = Depends(get_session),
                        me: Member = Depends(current_member)):
    goal = await get_goal(s, me, campaign_id, manage=remake)
    if goal.playbook and not remake:
        return goal.playbook
    # A detached copy, then let go of the database while Claude thinks.
    c = Campaign(id=goal.id, goal_description=goal.goal_description, done_when=goal.done_when,
                 primary_metric=goal.primary_metric, target_value=goal.target_value,
                 channels=list(goal.channels or []), context=goal.context)
    await s.commit()
    claude = MeteredClaude()
    if claude.configured:
        try:
            book = await generate_playbook(claude, c)
        except Exception:  # no budget left, API down...: an outline is better than nothing
            book = default_playbook(c)
    else:
        book = default_playbook(c)
    (await s.get(Campaign, campaign_id)).playbook = book
    return book


# --- permissions -------------------------------------------------------------------------------

async def _people(s: AsyncSession, c: Campaign) -> tuple[str | None, list[str]]:
    dept_id = await goal_department(s, c)
    dept = await s.get(Department, dept_id) if dept_id else None
    people = await approvers(s, c.org_id, dept_id) if c.org_id else []
    return (dept.name if dept else None), [p.name or p.email for p in people]


@router.get("/campaigns/{campaign_id}/permissions")
async def get_permissions(campaign_id: str, s: AsyncSession = Depends(get_session),
                          me: Member = Depends(current_member)):
    c = await get_goal(s, me, campaign_id)
    dept, people = await _people(s, c)
    return {
        "action_types": await permissions.effective(s, campaign_id),
        "department": dept, "approvers": people,
        "built_in_rules": BUILT_IN_RULES,
        "can_edit": c.org_id is None or me.is_admin or me.in_department(await goal_department(s, c)),
    }


class ModeIn(BaseModel):
    mode: str = Field(pattern="^(auto|ask|never)$")
    spend_limit_usd: float | None = Field(default=None, gt=0)


@router.put("/campaigns/{campaign_id}/permissions/{action_type}")
async def set_permission(campaign_id: str, action_type: str, body: ModeIn,
                         s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    c = await get_goal(s, me, campaign_id, manage=True)
    t = ACTION_TYPES.get(action_type)
    if not t:
        raise HTTPException(404, "Unknown kind of action")
    if body.mode == "ask" and t.default == "auto":
        raise HTTPException(400, f'"{t.label}" never changes anything outside Autopilot, so it doesn\'t need approval.')
    if body.mode == "auto" and action_type == "spend_money" and not body.spend_limit_usd:
        raise HTTPException(400, "Say how much it may spend per action without asking.")
    # Replace this goal's own setting; department and organization settings stay as they are.
    await s.execute(delete(ExclusionRule).where(ExclusionRule.campaign_id == campaign_id,
                                                ExclusionRule.kind == "action_type", ExclusionRule.value == action_type))
    for g in (await s.execute(select(PermissionGrant).where(
            PermissionGrant.campaign_id == campaign_id, PermissionGrant.action_type == action_type,
            PermissionGrant.scope.is_(None), PermissionGrant.revoked_at.is_(None)))).scalars():
        g.revoked_at = utcnow()
    if body.mode == "never":
        s.add(ExclusionRule(campaign_id=campaign_id, org_id=c.org_id, kind="action_type", value=action_type))
    elif body.mode == "auto" and t.default == "ask":
        s.add(PermissionGrant(campaign_id=campaign_id, org_id=c.org_id, action_type=action_type,
                              granted_by=me.user.id,
                              spend_limit_usd=Decimal(str(body.spend_limit_usd)) if body.spend_limit_usd else None))
    await s.flush()
    current = next(x for x in await permissions.effective(s, campaign_id) if x["key"] == action_type)
    words = {"auto": "does this on its own", "ask": "asks first", "never": "never does this"}
    c.guardrail_version += 1
    who = me.user.name or me.user.email
    await activity.log(s, campaign_id, "system", f'"{t.label}": {words[body.mode]} (set by {who})', status="info")
    await notify(s, campaign_id, "guardrails")
    note = None
    if current["mode"] != body.mode:
        where = "the whole organization" if current["set_at"] == "org" else "its department"
        note = f'A setting for {where} keeps this at "{words[current["mode"]]}". Change it in Settings → Permissions.'
    return {"permission": current, "note": note}


# --- before starting ---------------------------------------------------------------------------

async def signed_in_sites(s: AsyncSession, org_id: str) -> set[str]:
    sites = {domain_of(x) for (x,) in (await s.execute(
        select(SiteSignIn.site).where(SiteSignIn.org_id == org_id))).all()}
    sites |= {domain_of(x) for (x,) in (await s.execute(
        select(UserRequest.scope).join(Campaign, Campaign.id == UserRequest.campaign_id)
        .where(Campaign.org_id == org_id, UserRequest.kind == RequestKind.login.value,
               UserRequest.status == RequestStatus.approved.value))).all() if x}
    return sites


@router.get("/campaigns/{campaign_id}/readiness")
async def readiness(campaign_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    c = await get_goal(s, me, campaign_id)
    hub = get_hub()
    connected: set[str] = set()
    if hub.enabled:
        try:
            connected = {a["app"] for a in await hub.connected_apps(c.org_id) if (a.get("status") or "").upper() == "ACTIVE"}
        except Exception:  # Composio unreachable: show everything as not connected
            connected = set()
    sites = await signed_in_sites(s, c.org_id)
    tools = []
    for t in tools_needed(c):
        status = ("connected" if t["app"] and t["app"] in connected
                  else "signed_in" if t["site"] and domain_of(t["site"]) in sites else "missing")
        tools.append({**t, "status": status, "can_connect_app": bool(hub.enabled and t["app"])})
    servers = (await s.execute(select(McpServer).where(McpServer.org_id == c.org_id)
                               .order_by(McpServer.created_at))).scalars().all()
    dept, people = await _people(s, c)
    return {
        "tools": tools,
        "composio_enabled": hub.enabled,
        "mcp_servers": [{"id": m.id, "name": m.name, "tools": len(m.tools or []), "error": m.last_error} for m in servers],
        "permissions": await permissions.effective(s, campaign_id),
        "department": dept, "approvers": people,
        "playbook": c.playbook,
    }


class SiteIn(BaseModel):
    site: str = Field(min_length=3, max_length=300)


@router.post("/sites/signed-in")
async def mark_signed_in(body: SiteIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    try:
        site = domain_of(normalize_url(body.site))
    except UnsafeURL as e:
        raise HTTPException(400, str(e)) from e
    exists = (await s.execute(select(func.count()).select_from(SiteSignIn).where(
        SiteSignIn.org_id == me.org_id, SiteSignIn.site == site))).scalar_one()
    if exists:
        await s.execute(SiteSignIn.__table__.update().where(SiteSignIn.org_id == me.org_id, SiteSignIn.site == site)
                        .values(signed_in_at=utcnow(), user_id=me.user.id))
    else:
        s.add(SiteSignIn(org_id=me.org_id, site=site, user_id=me.user.id))
    return {"site": site}
