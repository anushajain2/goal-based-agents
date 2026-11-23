"""Model -> JSON helpers shared by the routers."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    Agent,
    AgentRun,
    Campaign,
    Department,
    MetricSnapshot,
    PermissionGrant,
    UserRequest,
)
from app.services import estimate, ledger
from app.services.policy import ACTION_TYPES


def _f(x):
    return float(x) if x is not None else None


def activity_json(a: Activity, campaign_name: str | None = None) -> dict:
    return {
        "campaign_name": campaign_name,
        "id": a.id, "campaign_id": a.campaign_id, "run_id": a.run_id, "kind": a.kind,
        "action_type": a.action_type, "channel": a.channel, "title": a.title, "status": a.status,
        "cost_usd": _f(a.cost_usd), "details": a.details, "created_at": a.created_at.isoformat(),
    }


def request_json(r: UserRequest, campaign_name: str | None = None) -> dict:
    at = ACTION_TYPES.get(r.action_type) if r.action_type else None
    return {
        "id": r.id, "campaign_id": r.campaign_id, "campaign_name": campaign_name, "run_id": r.run_id,
        "kind": r.kind, "status": r.status, "action_type": r.action_type,
        "action_label": at.label if at else None, "scope": r.scope, "title": r.title, "rationale": r.rationale,
        "preview": r.preview, "est_spend_usd": _f(r.est_spend_usd), "decision_note": r.decision_note,
        "edited_fields": r.edited_fields, "remember": r.remember,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None, "created_at": r.created_at.isoformat(),
    }


def grant_json(g: PermissionGrant, campaign_name: str | None = None) -> dict:
    at = ACTION_TYPES.get(g.action_type)
    return {
        "id": g.id, "campaign_id": g.campaign_id, "campaign_name": campaign_name, "action_type": g.action_type,
        "action_label": at.label if at else g.action_type, "scope": g.scope,
        "spend_limit_usd": _f(g.spend_limit_usd), "created_at": g.created_at.isoformat(),
    }


async def results_for(s: AsyncSession, c: Campaign) -> dict:
    """Progress on the primary metric: first reading -> latest reading."""
    q = select(MetricSnapshot).where(
        MetricSnapshot.campaign_id == c.id, func.lower(MetricSnapshot.metric) == c.primary_metric.lower()
    )
    first = (await s.execute(q.order_by(MetricSnapshot.recorded_at.asc()).limit(1))).scalar_one_or_none()
    last = (await s.execute(q.order_by(MetricSnapshot.recorded_at.desc()).limit(1))).scalar_one_or_none()
    if not first or not last:
        return {"baseline": None, "current": None, "results": None}
    return {"baseline": first.value, "current": last.value, "results": last.value - first.value}


async def campaign_json(s: AsyncSession, c: Campaign, full: bool = False, me=None) -> dict:
    budget = (await ledger.budget_state(s, c)).as_dict()
    results = await results_for(s, c)
    pending = (
        await s.execute(
            select(func.count()).select_from(UserRequest)
            .where(UserRequest.campaign_id == c.id, UserRequest.status == "pending")
        )
    ).scalar_one()
    current_run = (
        await s.execute(
            select(AgentRun).where(AgentRun.campaign_id == c.id).order_by(AgentRun.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    actions_taken = (
        await s.execute(
            select(func.count()).select_from(Activity)
            .where(Activity.campaign_id == c.id, Activity.kind == "action", Activity.status == "done")
        )
    ).scalar_one()
    last = (
        await s.execute(
            select(Activity).where(Activity.campaign_id == c.id, Activity.kind.notin_(["system", "metric"]))
            .order_by(Activity.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    agent = await s.get(Agent, c.agent_id) if c.agent_id else None
    dept = await s.get(Department, agent.department_id) if agent else None
    r = results["results"]
    data = {
        "agent": {"id": agent.id, "name": agent.name, "title": agent.title} if agent else None,
        "department": {"id": dept.id, "name": dept.name} if dept else None,
        "can_manage": me.in_department(dept.id if dept else None) if me is not None else None,
        "id": c.id, "name": c.name, "goal_type": c.goal_type, "goal_description": c.goal_description,
        "primary_metric": c.primary_metric, "target_value": c.target_value, "status": c.status,
        "done_when": c.done_when, "category": c.category, "use_case": c.use_case, "client_name": c.client_name,
        "origin": c.origin or "", "suggested_reason": c.suggested_reason or "",
        "first_deliverable": c.first_deliverable or "",
        "key_results": c.key_results or [],
        "budget_basis": c.budget_basis, "has_playbook": bool(c.playbook),
        "actions_taken": actions_taken,
        "last_activity": {"title": last.title, "kind": last.kind, "at": last.created_at.isoformat()} if last else None,
        "channels": c.channels, "budget": budget, "results": results,
        "cost_per_result": (budget["spent"] / r) if r and r > 0 else None,
        "pending_requests": pending, "cycles_completed": c.cycles_completed,
        "next_cycle_at": c.next_cycle_at.isoformat() if c.next_cycle_at else None,
        "end_date": c.end_date.isoformat() if c.end_date else None,
        "daily_cap": _f(c.daily_cap), "budget_total": _f(c.budget_total), "cycle_hours": c.cycle_hours,
        "current_run": {
            "id": current_run.id, "status": current_run.status, "cycle_number": current_run.cycle_number,
            "summary": current_run.summary, "error": current_run.error,
        } if current_run else None,
        "created_at": c.created_at.isoformat(),
    }
    if full:
        data["context"] = c.context
        data["strategy"] = c.strategy
        data["playbook"] = c.playbook
        data["pace"] = await estimate.pace(s, c, Decimal(str(budget["remaining"])))
        metrics = (
            await s.execute(
                select(MetricSnapshot).where(MetricSnapshot.campaign_id == c.id)
                .order_by(MetricSnapshot.recorded_at.asc()).limit(500)
            )
        ).scalars()
        data["metrics"] = [
            {"metric": m.metric, "value": m.value, "source": m.source, "note": m.note,
             "recorded_at": m.recorded_at.isoformat()} for m in metrics
        ]
    return data
