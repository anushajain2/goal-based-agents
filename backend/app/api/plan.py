"""What a goal will do and what it needs before it starts.

    GET  /api/estimate                         budget suggestion for a schedule (sessions x cost)
    POST /api/campaigns/{id}/playbook          the goal's plan of steps (made once, or remade)
    GET  /api/campaigns/{id}/permissions       per kind of action: on its own / heads-up / ask first / never
    PUT  /api/campaigns/{id}/permissions/{t}   change that for this goal
    GET  /api/campaigns/{id}/autonomy          recommended autonomy presets for this goal
    POST /api/campaigns/{id}/autonomy          apply one (with changes), usually when starting the goal
    POST /api/campaigns/{id}/autonomy/flag     "this shouldn't have gone out": that kind asks first again
    GET  /api/campaigns/{id}/readiness         tools to connect + approvals, shown before starting
    POST /api/sites/signed-in                  "I signed in to this site in Oton Chrome"
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import MeteredClaude
from app.agent.playbook import default_playbook, generate_playbook, tools_needed
from app.connectors.composio_hub import hub_for_org
from app.db import get_session
from app.models import (
    Campaign,
    Deliverable,
    Department,
    Integration,
    McpServer,
    RequestKind,
    RequestStatus,
    SiteSignIn,
    UserRequest,
    utcnow,
)
from app.org import Member, approvers, current_member, get_goal, goal_department
from app.services import activity, autonomy, estimate, permissions
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
    goal = await s.get(Campaign, campaign_id)
    krs = book.pop("key_results", None)
    goal.playbook = book
    if krs and not goal.key_results:
        goal.key_results = krs
    return book


# --- how the goal gets hit ------------------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/approach")
async def make_approach(campaign_id: str, remake: bool = False, s: AsyncSession = Depends(get_session),
                        me: Member = Depends(current_member)):
    """The funnel, the bottleneck, the approaches (creative ones too) and the first experiment:
    what people see before they turn a goal on. Made once; a few cents from the goal's budget."""
    from app.agent import approach as goal_approach
    from app.models import Organization

    goal = await get_goal(s, me, campaign_id, manage=remake)
    if goal.approach and not remake:
        return goal.approach
    org = await s.get(Organization, goal.org_id) if goal.org_id else None
    milestones = next((f.get("milestones") for f in (((org.profile or {}) if org else {}).get("opportunities") or {})
                       .get("findings") or [] if any(m.get("goal_id") == goal.id for m in f.get("milestones") or [])), None)
    c = Campaign(id=goal.id, name=goal.name, goal_description=goal.goal_description, done_when=goal.done_when,
                 primary_metric=goal.primary_metric, target_value=goal.target_value, channels=list(goal.channels or []),
                 context=goal.context, playbook=goal.playbook)
    await s.commit()
    claude = MeteredClaude()
    made = None
    if claude.configured:
        try:
            made = await goal_approach.generate(claude, c, milestones)
        except Exception:  # no budget left, API down...: a plain outline is better than nothing
            made = None
    made = made or goal_approach.default(c)
    goal = await s.get(Campaign, campaign_id)
    goal.approach = made
    return made


# --- permissions -------------------------------------------------------------------------------

async def _people(s: AsyncSession, c: Campaign) -> tuple[str | None, list[str]]:
    dept_id = await goal_department(s, c)
    dept = await s.get(Department, dept_id) if dept_id else None
    people = await approvers(s, c.org_id, dept_id, c.agent_id) if c.org_id else []
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
    mode: str = Field(pattern="^(auto|heads_up|ask|never)$")
    spend_limit_usd: float | None = Field(default=None, gt=0)
    daily_cap: int | None = Field(default=None, ge=1, le=1000)


@router.put("/campaigns/{campaign_id}/permissions/{action_type}")
async def set_permission(campaign_id: str, action_type: str, body: ModeIn,
                         s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    c = await get_goal(s, me, campaign_id, manage=True)
    t = ACTION_TYPES.get(action_type)
    if not t:
        raise HTTPException(404, "Unknown kind of action")
    if body.mode == "ask" and t.default == "auto":
        raise HTTPException(400, f'"{t.label}" never changes anything outside Oton, so it doesn\'t need approval.')
    if body.mode == "auto" and action_type == "spend_money" and not body.spend_limit_usd:
        raise HTTPException(400, "Say how much it may spend per action without asking.")
    if body.mode == "heads_up" and action_type == "spend_money":
        raise HTTPException(400, "Spending asks first, or goes ahead under a per-action limit; it has no heads-up.")
    if t.default == "auto":  # only "never" (or back to the default) for things that change nothing outside
        if body.mode == "never":
            await autonomy.set_goal_mode(s, c, action_type, "never", granted_by=me.user.id)
        else:
            await autonomy.clear_goal_setting(s, campaign_id, action_type)
            await s.flush()
    else:
        # Replace this goal's own setting; department and organization settings stay as they are.
        await autonomy.set_goal_mode(
            s, c, action_type, body.mode, daily_cap=body.daily_cap if body.mode in ("auto", "heads_up") else None,
            spend_limit_usd=Decimal(str(body.spend_limit_usd)) if body.spend_limit_usd and body.mode == "auto" else None,
            granted_by=me.user.id)
    current = next(x for x in await permissions.effective(s, campaign_id) if x["key"] == action_type)
    words = {"auto": "does this on its own", "heads_up": "goes ahead after a heads-up", "ask": "asks first",
             "never": "never does this"}
    c.guardrail_version += 1
    who = me.user.name or me.user.email
    cap = f", up to {body.daily_cap} a day" if body.daily_cap and body.mode in ("auto", "heads_up") else ""
    await activity.log(s, campaign_id, "system", f'"{t.label}": {words[body.mode]}{cap} (set by {who})', status="info")
    await notify(s, campaign_id, "guardrails")
    note = None
    if current["mode"] != body.mode and not (t.default == "auto" and body.mode != "never"):
        where = "the whole organization" if current["set_at"] == "org" else "its department"
        note = f'A setting for {where} keeps this at "{words[current["mode"]]}". Change it in Settings → Permissions.'
    return {"permission": current, "note": note}


# --- autonomy ------------------------------------------------------------------------------------

@router.get("/campaigns/{campaign_id}/autonomy")
async def get_autonomy(campaign_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    return await autonomy.recommend(s, await get_goal(s, me, campaign_id))


class Override(BaseModel):
    mode: str = Field(pattern="^(auto|heads_up|ask|never)$")
    daily_cap: int | None = Field(default=None, ge=1, le=1000)


class AutonomyIn(BaseModel):
    preset: str = Field(pattern="^(cautious|balanced|fast)$")
    overrides: dict[str, Override] = Field(default_factory=dict)
    personal: list[str] = Field(default_factory=list, max_length=20)  # tools that are someone's personal profile


@router.post("/campaigns/{campaign_id}/autonomy")
async def set_autonomy(campaign_id: str, body: AutonomyIn, s: AsyncSession = Depends(get_session),
                       me: Member = Depends(current_member)):
    c = await get_goal(s, me, campaign_id, manage=True)
    try:
        await autonomy.apply(s, c, body.preset, overrides={k: v.model_dump(exclude_unset=True) for k, v in body.overrides.items()},
                             personal=body.personal, by=me.user.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {"preset": c.autonomy_preset, "permissions": await permissions.effective(s, campaign_id)}


class FlagIn(BaseModel):
    action_type: str
    note: str | None = Field(default=None, max_length=1000)


@router.post("/campaigns/{campaign_id}/autonomy/flag")
async def flag(campaign_id: str, body: FlagIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    """Something went out that shouldn't have: that kind of action asks first again on this goal."""
    c = await get_goal(s, me, campaign_id, manage=True)
    if body.action_type not in ACTION_TYPES or ACTION_TYPES[body.action_type].default == "auto":
        raise HTTPException(400, "That kind of action doesn't go out on its own.")
    who = me.user.name or me.user.email
    await autonomy.downgrade(s, c, body.action_type, f"{who} flagged one that went out" + (f' ("{body.note}")' if body.note else "") + ".")
    return {"permissions": await permissions.effective(s, campaign_id)}


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
    hub = await hub_for_org(c.org_id, s)
    connected: set[str] = set()
    if hub.enabled:
        try:
            connected = {a["app"] for a in await hub.connected_apps(c.org_id) if (a.get("status") or "").upper() == "ACTIVE"}
        except Exception:  # Composio unreachable: show everything as not connected
            connected = set()
    sites = await signed_in_sites(s, c.org_id)
    linked = {k for (k,) in (await s.execute(select(Integration.kind).where(Integration.org_id == c.org_id))).all()}
    tools = []
    for t in tools_needed(c):
        if t["kind"] in ("github", "postgres"):
            status = "connected" if t["kind"] in linked else "missing"
        else:
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
        "autonomy": await autonomy.recommend(s, c),
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


@router.get("/deliverables")
async def list_deliverables(agent_id: str | None = None, campaign_id: str | None = None, limit: int = 50,
                            s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    """PRDs, analyses and reports AI employees handed in."""
    q = select(Deliverable).where(Deliverable.org_id == me.org_id)
    if agent_id:
        q = q.where(Deliverable.agent_id == agent_id)
    if campaign_id:
        q = q.where(Deliverable.campaign_id == campaign_id)
    rows = (await s.execute(q.order_by(Deliverable.created_at.desc()).limit(min(limit, 200)))).scalars()
    return [{"id": d.id, "kind": d.kind, "title": d.title, "summary": d.summary, "content": d.content, "status": d.status,
             "campaign_id": d.campaign_id, "agent_id": d.agent_id, "handed_to_campaign_id": d.handed_to_campaign_id,
             "created_at": d.created_at.isoformat()} for d in rows]
