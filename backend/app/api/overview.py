"""Home-page overview of the AI employee, and the work log across all goals."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import activity_json
from app.db import get_session
from app.models import Activity, Agent, AgentRun, Campaign, LedgerEntry, UserRequest, utcnow
from app.org import Member, current_member, routed_to_me

router = APIRouter(prefix="/api", tags=["overview"])

LIVE_KINDS = ["update", "step", "action", "plan", "request", "blocked"]


@router.get("/overview")
async def overview(department_id: str | None = None, s: AsyncSession = Depends(get_session),
                   me: Member = Depends(current_member)):
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    q = select(Campaign).where(Campaign.org_id == me.org_id)
    if department_id:
        q = q.where(Campaign.agent_id.in_(select(Agent.id).where(Agent.department_id == department_id)))
    campaigns = (await s.execute(q)).scalars().all()
    names = {c.id: c.name for c in campaigns}
    mine = list(names) or ["-"]
    active = [c for c in campaigns if c.status == "active"]

    open_runs = (
        await s.execute(select(AgentRun).where(AgentRun.campaign_id.in_(mine),
                                   AgentRun.status.in_(["queued", "running", "waiting"])))
    ).scalars().all()
    working = [r for r in open_runs if r.status in ("queued", "running")]
    waiting = [r for r in open_runs if r.status == "waiting"]

    # What it is doing right now: the latest entry of a session in progress.
    now_doing = None
    if working:
        latest = (
            await s.execute(
                select(Activity).where(Activity.run_id.in_([r.id for r in working]), Activity.kind.in_(LIVE_KINDS))
                .order_by(Activity.id.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if latest:
            now_doing = activity_json(latest, names.get(latest.campaign_id))

    spent = dict(
        (
            await s.execute(
                select(LedgerEntry.kind, func.coalesce(func.sum(LedgerEntry.amount_usd), 0))
                .where(LedgerEntry.campaign_id.in_(mine), LedgerEntry.status == "settled",
                       LedgerEntry.created_at >= month_start)
                .group_by(LedgerEntry.kind)
            )
        ).all()
    )
    actions_week = (
        await s.execute(
            select(func.count()).select_from(Activity)
            .where(Activity.campaign_id.in_(mine), Activity.kind == "action", Activity.status == "done",
                   Activity.created_at >= week_ago)
        )
    ).scalar_one()
    steps_week = (
        await s.execute(
            select(func.count()).select_from(Activity)
            .where(Activity.campaign_id.in_(mine), Activity.kind.in_(["action", "step"]),
                   Activity.created_at >= week_ago)
        )
    ).scalar_one()
    pending = (
        await s.execute(select(func.count()).select_from(UserRequest)
                        .where(UserRequest.campaign_id.in_(mine), UserRequest.status == "pending",
                               await routed_to_me(s, me)))
    ).scalar_one()
    next_check = min((c.next_cycle_at for c in active if c.next_cycle_at), default=None)

    ai = float(spent.get("ai_usage", 0) or 0)
    other = float(spent.get("spend", 0) or 0)
    return {
        "goals": {"total": len(campaigns), "active": len(active)},
        "working_on": sorted({names[r.campaign_id] for r in working if r.campaign_id in names}),
        "waiting_on_you": pending,
        "waiting_goals": sorted({names[r.campaign_id] for r in waiting if r.campaign_id in names}),
        "now": now_doing,
        "next_check_in": next_check.isoformat() if next_check else None,
        "spend_this_month": {"total": ai + other, "ai_usage": ai, "other": other},
        "budget_total": float(sum(c.budget_total for c in campaigns if c.status != "completed")),
        "actions_this_week": actions_week,
        "steps_this_week": steps_week,
    }


@router.get("/activity")
async def all_activity(
    campaign_id: str | None = None,
    kinds: str | None = None,
    q: str | None = None,
    before_id: int | None = None,
    limit: int = 150,
    s: AsyncSession = Depends(get_session),
    me: Member = Depends(current_member),
    department_id: str | None = None,
    agent_id: str | None = None,
):
    """The work log across goals, newest first."""
    query = (
        select(Activity, Campaign.name)
        .join(Campaign, Campaign.id == Activity.campaign_id)
        .where(Campaign.org_id == me.org_id)
    )
    if agent_id:
        query = query.where(Campaign.agent_id == agent_id)
    if department_id:
        query = query.where(Campaign.agent_id.in_(select(Agent.id).where(Agent.department_id == department_id)))
    if campaign_id:
        query = query.where(Activity.campaign_id == campaign_id)
    if kinds:
        query = query.where(Activity.kind.in_([k for k in kinds.split(",") if k]))
    if q:
        query = query.where(func.lower(Activity.title).contains(q.lower()))
    if before_id is not None:
        query = query.where(Activity.id < before_id)
    rows = (await s.execute(query.order_by(Activity.id.desc()).limit(min(limit, 500)))).all()
    return [activity_json(a, name) for a, name in rows]
