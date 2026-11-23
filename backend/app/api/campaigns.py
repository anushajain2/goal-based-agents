"""Campaign CRUD, lifecycle (launch / pause / resume / run now) and activity."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import activity_json, campaign_json
from app.db import get_session
from app.models import (
    Activity,
    Agent,
    AgentRun,
    Campaign,
    CampaignStatus,
    ExclusionRule,
    LedgerEntry,
    PermissionGrant,
    RunStatus,
    utcnow,
)
from app.org import Member, current_member, get_goal, pick_agent
from app.services import activity, estimate, targets
from app.services.events import notify
from app.services.policy import ACTION_TYPES

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

GOAL_TEMPLATES = {
    "sales": {"label": "Sell more of my product", "metric": "sales"},
    "followers": {"label": "Grow my followers", "metric": "followers"},
    "traffic": {"label": "Drive website traffic", "metric": "website visits"},
    "leads": {"label": "Get more leads / sign-ups", "metric": "leads"},
    "awareness": {"label": "Build awareness", "metric": "impressions"},
    "custom": {"label": "Something else", "metric": ""},
}


class ExclusionIn(BaseModel):
    kind: str = Field(pattern="^(action_type|app|site|text)$")
    value: str = Field(min_length=1, max_length=2000)


class GrantIn(BaseModel):
    action_type: str
    scope: str | None = None
    spend_limit_usd: Decimal | None = None


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal_type: str = "custom"
    goal_description: str = Field(min_length=1)
    primary_metric: str = Field(min_length=1, max_length=120)
    target_value: float | None = None
    target_period: str = "month"  # the period the target covers: week | month | quarter
    done_when: str = ""
    category: str = ""
    use_case: str = ""
    client_name: str = ""
    context: str = ""
    channels: list[str] = []
    budget_total: Decimal = Field(gt=0)
    daily_cap: Decimal | None = Field(default=None, gt=0)
    end_date: datetime | None = None
    cycle_hours: float = Field(default=6.0, ge=0.5, le=72)
    exclusions: list[ExclusionIn] = []
    grants: list[GrantIn] = []
    launch: bool = False
    agent_id: str | None = None  # the AI employee to give it to (suggested from the category if empty)


class CampaignPatch(BaseModel):
    name: str | None = None
    goal_description: str | None = None
    primary_metric: str | None = None
    target_value: float | None = None
    target_period: str | None = None
    done_when: str | None = None
    client_name: str | None = None
    context: str | None = None
    channels: list[str] | None = None
    budget_total: Decimal | None = Field(default=None, gt=0)
    daily_cap: Decimal | None = None
    end_date: datetime | None = None
    cycle_hours: float | None = Field(default=None, ge=0.5, le=72)
    agent_id: str | None = None  # hand the goal to another AI employee


async def _get(s: AsyncSession, campaign_id: str, me: Member, manage: bool = False) -> Campaign:
    return await get_goal(s, me, campaign_id, manage=manage)


def _who(me: Member) -> str:
    return me.user.name or me.user.email


@router.get("/meta")
async def meta():
    return {
        "goal_templates": GOAL_TEMPLATES,
        "action_types": [
            {"key": a.key, "label": a.label, "description": a.description, "default": a.default}
            for a in ACTION_TYPES.values()
        ],
    }


@router.get("")
async def list_campaigns(agent_id: str | None = None, department_id: str | None = None,
                         s: AsyncSession = Depends(get_session),
                  me: Member = Depends(current_member)):
    q = select(Campaign).where(Campaign.org_id == me.org_id)
    if agent_id:
        q = q.where(Campaign.agent_id == agent_id)
    if department_id:
        q = q.where(Campaign.agent_id.in_(select(Agent.id).where(Agent.department_id == department_id)))
    campaigns = (await s.execute(q.order_by(Campaign.created_at.desc()))).scalars().all()
    return [await campaign_json(s, c, me=me) for c in campaigns]


@router.post("")
async def create_campaign(body: CampaignIn, s: AsyncSession = Depends(get_session),
                  me: Member = Depends(current_member)):
    for g in body.grants:
        if g.action_type not in ACTION_TYPES:
            raise HTTPException(400, f"Unknown action type {g.action_type}")
        if g.action_type == "spend_money" and g.spend_limit_usd is None:
            raise HTTPException(400, "A spending permission needs a per-action limit")
    agent = await s.get(Agent, body.agent_id) if body.agent_id else await pick_agent(s, me.org_id, body.category)
    if not agent or agent.org_id != me.org_id:
        raise HTTPException(400, "Choose an AI employee for this goal (add one under Team first).")
    if not me.in_department(agent.department_id):
        raise HTTPException(403, "You can only give goals to AI employees in your departments.")
    c = Campaign(
        owner_id=me.user.id, org_id=me.org_id, agent_id=agent.id,
        name=body.name, goal_type=body.goal_type, goal_description=body.goal_description,
        primary_metric=body.primary_metric, target_value=body.target_value, context=body.context,
        done_when=body.done_when, category=body.category, use_case=body.use_case, client_name=body.client_name,
        channels=body.channels, budget_total=body.budget_total, daily_cap=body.daily_cap,
        end_date=body.end_date, cycle_hours=body.cycle_hours,
    )
    targets.plan_first(c, body.target_value, body.target_period, set_by="person")
    s.add(c)
    await s.flush()
    await _set_budget_basis(s, c)
    for e in body.exclusions:
        s.add(ExclusionRule(campaign_id=c.id, org_id=me.org_id, owner_id=me.user.id, kind=e.kind, value=e.value.strip()))
    for g in body.grants:
        s.add(PermissionGrant(campaign_id=c.id, org_id=me.org_id, owner_id=me.user.id, granted_by=me.user.id,
                              action_type=g.action_type, scope=g.scope,
                              spend_limit_usd=g.spend_limit_usd))
    await activity.log(s, c.id, "system", f"Goal created by {_who(me)} for {agent.name}", status="info")
    if body.launch:
        await _launch(s, c)
    await s.flush()
    return await campaign_json(s, c, full=True, me=me)


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str, s: AsyncSession = Depends(get_session),
                  me: Member = Depends(current_member)):
    return await campaign_json(s, await _get(s, campaign_id, me), full=True, me=me)


@router.patch("/{campaign_id}")
async def patch_campaign(campaign_id: str, body: CampaignPatch, s: AsyncSession = Depends(get_session),
                  me: Member = Depends(current_member)):
    c = await _get(s, campaign_id, me, manage=True)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("agent_id"):
        agent = await s.get(Agent, changes["agent_id"])
        if not agent or agent.org_id != me.org_id or not me.in_department(agent.department_id):
            raise HTTPException(403, "You can only hand goals to AI employees in your departments.")
    new_target = changes.pop("target_value", None) if "target_value" in changes else None
    new_period = changes.pop("target_period", None)
    for k, v in changes.items():
        setattr(c, k, v)
    if new_target or new_period:
        now_t = targets.current(c)
        value = new_target or (now_t["target"] if now_t else None)
        if value:
            await targets.set_target(s, c, target=value, period=new_period or (now_t["period"] if now_t else "month"),
                                     why=f"Set by {_who(me)}", set_by="person")
        changes |= {"target": value}
    if {"budget_total", "cycle_hours", "end_date"} & set(changes):
        await _set_budget_basis(s, c)
    if "budget_total" in changes and c.status == CampaignStatus.out_of_budget.value:
        c.status = CampaignStatus.paused.value  # the user can resume now that there is budget
    await activity.log(s, c.id, "system", "Goal settings updated: " + ", ".join(changes).replace("_", " "),
                       status="info")
    await notify(s, c.id, "campaign")
    return await campaign_json(s, c, full=True, me=me)


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: str, s: AsyncSession = Depends(get_session),
                  me: Member = Depends(current_member)):
    await s.delete(await _get(s, campaign_id, me, manage=True))
    return {"ok": True}


async def _set_budget_basis(s: AsyncSession, c: Campaign) -> None:
    """Keep the "how this budget compares to the estimate" note in step with the settings."""
    old = c.budget_basis or {}
    paid = float(old.get("paid_spend_usd") or 0)
    if old.get("starter"):  # suggested goals start with a one-week budget; keep it that way
        per, kind, n = await estimate.session_cost(s, c.org_id)
        basis = estimate.starter(per, c.cycle_hours, old.get("full_days") or estimate.DEFAULT_DAYS, 0, kind, n)
    else:
        basis = await estimate.estimate(s, c.org_id, c.cycle_hours, estimate.days_until(c.end_date), paid)
    c.budget_basis = {**basis, "chosen_usd": float(c.budget_total)}


async def _launch(s: AsyncSession, c: Campaign) -> None:
    c.status = CampaignStatus.active.value
    c.next_cycle_at = utcnow()
    await targets.ensure_started(s, c)
    await activity.log(s, c.id, "system", "Started working on this goal", status="info")
    await notify(s, c.id, "campaign")


@router.post("/{campaign_id}/launch")
async def launch(campaign_id: str, s: AsyncSession = Depends(get_session),
                  me: Member = Depends(current_member)):
    c = await _get(s, campaign_id, me, manage=True)
    if c.status not in (CampaignStatus.draft.value, CampaignStatus.paused.value):
        raise HTTPException(400, f"Cannot start a goal that is {c.status}")
    await _launch(s, c)
    return await campaign_json(s, c, me=me)


@router.post("/{campaign_id}/pause")
async def pause(campaign_id: str, s: AsyncSession = Depends(get_session),
                  me: Member = Depends(current_member)):
    c = await _get(s, campaign_id, me, manage=True)
    c.status = CampaignStatus.paused.value
    await activity.log(s, c.id, "system", f"Paused by {_who(me)}", status="info")
    await notify(s, c.id, "campaign")
    return await campaign_json(s, c, me=me)


@router.post("/{campaign_id}/resume")
async def resume(campaign_id: str, s: AsyncSession = Depends(get_session),
                  me: Member = Depends(current_member)):
    c = await _get(s, campaign_id, me, manage=True)
    if c.status == CampaignStatus.completed.value:
        raise HTTPException(400, "This goal has finished")
    c.status = CampaignStatus.active.value
    # Continue an interrupted cycle if there is one, otherwise start a new one now.
    interrupted = (
        await s.execute(
            update(AgentRun)
            .where(AgentRun.campaign_id == c.id, AgentRun.status == RunStatus.stopped.value,
                   AgentRun.summary.is_(None))
            .values(status=RunStatus.queued.value)
            .returning(AgentRun.id)
        )
    ).all()
    if not interrupted and not c.next_cycle_at:
        c.next_cycle_at = utcnow()
    await targets.ensure_started(s, c)
    await activity.log(s, c.id, "system", f"Resumed by {_who(me)}", status="info")
    await notify(s, c.id, "campaign")
    return await campaign_json(s, c, me=me)


@router.post("/{campaign_id}/run-now")
async def run_now(campaign_id: str, s: AsyncSession = Depends(get_session),
                  me: Member = Depends(current_member)):
    c = await _get(s, campaign_id, me, manage=True)
    if c.status != CampaignStatus.active.value:
        raise HTTPException(400, "Start or resume the goal first")
    c.next_cycle_at = utcnow()
    await notify(s, c.id, "campaign")
    return await campaign_json(s, c, me=me)


@router.get("/{campaign_id}/activity")
async def campaign_activity(
    campaign_id: str, after_id: int | None = None, before_id: int | None = None, limit: int = 100,
    s: AsyncSession = Depends(get_session), me: Member = Depends(current_member),
):
    await _get(s, campaign_id, me)
    q = select(Activity).where(Activity.campaign_id == campaign_id)
    if after_id is not None:
        q = q.where(Activity.id > after_id).order_by(Activity.id.asc())
    else:
        if before_id is not None:
            q = q.where(Activity.id < before_id)
        q = q.order_by(Activity.id.desc())
    rows = (await s.execute(q.limit(min(limit, 500)))).scalars().all()
    if after_id is None:
        rows = list(reversed(rows))
    return [activity_json(a) for a in rows]


@router.get("/{campaign_id}/sessions")
async def campaign_sessions(campaign_id: str, s: AsyncSession = Depends(get_session),
                  me: Member = Depends(current_member)):
    """Work sessions (one per optimization cycle) with their cost and step counts."""
    await _get(s, campaign_id, me)
    runs = (
        await s.execute(
            select(AgentRun).where(AgentRun.campaign_id == campaign_id).order_by(AgentRun.cycle_number.desc())
        )
    ).scalars().all()
    if not runs:
        return []
    ids = [r.id for r in runs]
    costs = dict(
        (
            await s.execute(
                select(LedgerEntry.run_id, func.coalesce(func.sum(LedgerEntry.amount_usd), 0))
                .where(LedgerEntry.run_id.in_(ids), LedgerEntry.status.in_(["settled", "reserved"]))
                .group_by(LedgerEntry.run_id)
            )
        ).all()
    )
    counts: dict[str, dict[str, int]] = {}
    for run_id, kind, n in (
        await s.execute(
            select(Activity.run_id, Activity.kind, func.count()).where(Activity.run_id.in_(ids))
            .group_by(Activity.run_id, Activity.kind)
        )
    ).all():
        counts.setdefault(run_id, {})[kind] = n
    return [
        {
            "id": r.id, "number": r.cycle_number, "status": r.status, "summary": r.summary, "error": r.error,
            "started_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat(),
            "cost_usd": float(costs.get(r.id, 0) or 0), "ai_calls": r.model_calls,
            "counts": counts.get(r.id, {}),
        }
        for r in runs
    ]
