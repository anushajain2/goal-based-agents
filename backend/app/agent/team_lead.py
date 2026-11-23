"""The AI team lead: one per team, always thinking about how the team's goals could do better.

Every few days (and whenever someone asks) it reviews the team's goals the way a good manager
would: what each AI employee aims for, how past periods went, what the sessions found, and what
the money bought. It then proposes a few changes: a new goal, a new target, pausing what isn't
working, or restarting something paused. Each proposal goes to Needs you with its reasoning,
routed like the AI employee's own requests; nothing changes until a person approves.

It doesn't do the work itself and has no goal of its own. Its Claude usage is paid by the
organization (like setup research), with a monthly cap per team.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.agent.llm import MeteredClaude
from app.agent.org_setup import company_context
from app.db import session_scope
from app.models import (
    Agent,
    AgentRun,
    Campaign,
    CampaignStatus,
    Department,
    LeadReview,
    Organization,
    RequestKind,
    RequestStatus,
    UserRequest,
    utcnow,
)
from app.org import approvers
from app.services import activity, estimate, ledger, targets
from app.services.events import notify
from app.services.mailer import send_approval_needed

log = logging.getLogger(__name__)

MAX_PROPOSALS = 3
CHANGE_TYPES = ["new_goal", "target", "pause", "resume"]


def lead_name(dept: Department) -> str:
    return f"{dept.name} Lead"


def month_start():
    now = utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def spent_this_month(s, department_id: str) -> Decimal:
    total = (await s.execute(select(func.coalesce(func.sum(LeadReview.cost_usd), 0)).where(
        LeadReview.department_id == department_id, LeadReview.created_at >= month_start()))).scalar_one()
    return Decimal(str(total))


SYSTEM = """You are the AI team lead of the {team} team at {org}. You don't do the work yourself: \
AI employees on your team each own ongoing goals, with a target for the current week, month or \
quarter. Your job is to keep making the team better at what matters most for the company now, \
like a thoughtful manager in a weekly review.

Look at each goal's results against its targets, what its sessions found, and what it costs. Then \
propose at most {max} changes, only where they clearly help:
- new_goal: something important the team isn't working on yet (from the company's focus, gaps you \
see, or what a goal's results suggest). Ongoing goals are named like a person's goal, without \
numbers ("Win back churned customers"); the number goes in the target. Give it to the AI employee \
on the team who fits best (agent_id).
- target: a better target for a goal (raise it when it's being hit easily, lower it or change the \
period when it's out of reach or too noisy to judge).
- pause: a goal that keeps missing and isn't worth its budget, or no longer fits the focus.
- resume: a paused goal worth restarting.
Don't propose what is already waiting for a decision, and don't change a goal that started in the \
last few days unless something is clearly wrong. No changes is a fine answer when the team is on \
track. Every reasoning is two or three plain sentences with the numbers behind it. The summary is \
two or three sentences on how the team is doing."""

TASK = """Company:
{company}

Team: {team}
AI employees:
{agents}

Goals:
{goals}

Waiting for a decision already:
{pending}

Review the team and propose changes (or none)."""


def schema() -> dict:
    new_goal = {
        "type": "object",
        "properties": {
            "name": {"type": "string"}, "goal_description": {"type": "string"},
            "primary_metric": {"type": "string"}, "done_when": {"type": "string"},
            "target_value": {"type": "number"}, "target_period": {"type": "string", "enum": ["week", "month", "quarter"]},
            "first_week": {"type": "string"}, "key_results": {"type": "array", "items": {"type": "string"}},
            "agent_id": {"type": "string"},
        },
        "required": ["name", "goal_description", "primary_metric", "done_when", "target_value", "target_period",
                     "first_week", "key_results", "agent_id"],
        "additionalProperties": False,
    }
    proposal = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": CHANGE_TYPES},
            "goal_id": {"type": "string", "description": "The goal it changes; empty for new_goal"},
            "reasoning": {"type": "string"},
            "target": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "period": {"anyOf": [{"type": "string", "enum": ["week", "month", "quarter"]}, {"type": "null"}]},
            "new_goal": {"anyOf": [new_goal, {"type": "null"}]},
        },
        "required": ["type", "goal_id", "reasoning", "target", "period", "new_goal"],
        "additionalProperties": False,
    }
    return {"type": "json_schema", "schema": {
        "type": "object",
        "properties": {"health": {"type": "string", "enum": ["on_track", "mixed", "off_track"]},
                       "summary": {"type": "string"},
                       "proposals": {"type": "array", "items": proposal}},
        "required": ["health", "summary", "proposals"],
        "additionalProperties": False,
    }}


async def _snapshot(s, dept: Department) -> tuple[str, list[Agent], dict[str, Campaign], set[str]]:
    org = await s.get(Organization, dept.org_id)
    agents = list((await s.execute(select(Agent).where(Agent.department_id == dept.id).order_by(Agent.created_at))).scalars())
    goals = list((await s.execute(select(Campaign).where(Campaign.agent_id.in_([a.id for a in agents] or ["-"]))
                                  .order_by(Campaign.created_at))).scalars())
    pending = {c for (c,) in (await s.execute(select(UserRequest.campaign_id).where(
        UserRequest.campaign_id.in_([g.id for g in goals] or ["-"]), UserRequest.kind == RequestKind.proposal.value,
        UserRequest.status == RequestStatus.pending.value))).all()}
    lines = []
    by_id = {a.id: a for a in agents}
    for g in goals:
        value = await targets.value_now(s, g) if targets.active(g) else None
        t = targets.view(g, value)
        budget = await ledger.budget_state(s, g)
        runs = [r for (r,) in (await s.execute(select(AgentRun.summary).where(
            AgentRun.campaign_id == g.id, AgentRun.summary.is_not(None)).order_by(AgentRun.cycle_number.desc()).limit(3))).all()]
        target = "no target"
        if t and t.get("target"):
            target = f"target {targets.fmt(t['target'])} {g.primary_metric} a {t['period']}"
            if t.get("progress") is not None:
                target += f", {targets.fmt(t['progress'])} so far, {t['days_left']:g} days left"
        history = "; ".join(f"{h['period']}: {targets.fmt(h['result'])}/{targets.fmt(h['target'])} {h['status']}"
                            for h in (t or {}).get("history", []))
        agent = by_id.get(g.agent_id)
        lines.append(
            f"- [{g.id}] {g.name} ({g.status}; {agent.name if agent else 'no AI employee'}): {target}."
            + (f" Past periods: {history}." if history else "")
            + f" Budget ${budget.settled:.2f} of ${budget.total:.2f} used."
            + (f" Started {g.created_at:%Y-%m-%d}." if g.created_at else "")
            + (" Recent sessions: " + " | ".join(r[:300] for r in runs) if runs else "")
        )
    company = company_context(org, org.profile or {})
    agents_text = "\n".join(f"- [{a.id}] {a.name}" + (f" ({a.title})" if a.title else "")
                            + (f": {a.objective}" if a.objective else "") for a in agents) or "(none)"
    pending_text = "\n".join(f"- {g.name}" for g in goals if g.id in pending) or "(nothing)"
    task = TASK.format(company=company, team=dept.name, agents=agents_text, goals="\n".join(lines) or "(no goals yet)",
                       pending=pending_text)
    return task, agents, {g.id: g for g in goals}, pending


def tidy(raw: dict, agents: list[Agent], goals: dict[str, Campaign], pending: set[str]) -> list[dict]:
    out, touched = [], set()
    for p in raw.get("proposals") or []:
        kind = p.get("type")
        reasoning = (p.get("reasoning") or "").strip()
        if kind not in CHANGE_TYPES or not reasoning:
            continue
        if kind == "new_goal":
            ng = p.get("new_goal") or {}
            if not (ng.get("name") or "").strip() or not (ng.get("goal_description") or "").strip():
                continue
            if ng["name"].strip().lower() in {g.name.lower() for g in goals.values()}:
                continue
            agent = next((a for a in agents if a.id == ng.get("agent_id")), agents[0] if agents else None)
            if not agent:
                continue
            out.append({"type": "new_goal", "reasoning": reasoning, "agent_id": agent.id, "new_goal": ng})
        else:
            g = goals.get(p.get("goal_id") or "")
            if not g or g.id in pending or g.id in touched:
                continue
            if kind == "target":
                try:
                    target = float(p.get("target"))
                except (TypeError, ValueError):
                    continue
                if target <= 0 or g.status not in (CampaignStatus.active.value, CampaignStatus.draft.value):
                    continue
                out.append({"type": "target", "goal_id": g.id, "reasoning": reasoning, "target": target,
                            "period": targets.period_of(p.get("period"), "week")})
            elif kind == "pause" and g.status == CampaignStatus.active.value:
                out.append({"type": "pause", "goal_id": g.id, "reasoning": reasoning})
            elif kind == "resume" and g.status == CampaignStatus.paused.value:
                out.append({"type": "resume", "goal_id": g.id, "reasoning": reasoning})
            else:
                continue
            touched.add(g.id)
        if len(out) >= MAX_PROPOSALS:
            break
    return out


async def _propose(s, dept: Department, review: LeadReview, p: dict) -> dict:
    """Turn one proposal into a request in Needs you (and, for a new goal, its draft)."""
    lead = lead_name(dept)
    change = {"type": p["type"], "by": "lead"}
    if p["type"] == "new_goal":
        ng = p["new_goal"]
        org = await s.get(Organization, dept.org_id)
        per, kind, n = await estimate.session_cost(s, dept.org_id)
        basis = estimate.starter(per, 24, estimate.DEFAULT_DAYS, 0, kind, n)
        c = Campaign(
            org_id=dept.org_id, owner_id=review.requested_by, agent_id=p["agent_id"], name=ng["name"].strip()[:200],
            goal_type="custom", goal_description=ng["goal_description"].strip(),
            primary_metric=(ng.get("primary_metric") or "results").strip()[:120], done_when=(ng.get("done_when") or "").strip(),
            context=company_context(org, org.profile or {}), origin="lead", suggested_reason=p["reasoning"],
            first_deliverable=(ng.get("first_week") or "").strip(),
            key_results=[str(k).strip()[:160] for k in ng.get("key_results") or [] if str(k).strip()][:3],
            budget_total=Decimal(str(basis["suggested_usd"])), budget_basis={**basis, "chosen_usd": basis["suggested_usd"]},
            cycle_hours=24,
        )
        targets.plan_first(c, ng.get("target_value"), ng.get("target_period") or "week", why=p["reasoning"], set_by="lead")
        s.add(c)
        await s.flush()
        await activity.log(s, c.id, "system", f"Suggested by {lead}", details={"why": p["reasoning"]}, status="info")
    else:
        c = await s.get(Campaign, p["goal_id"])
        if p["type"] == "target":
            change |= {"target": p["target"], "period": p["period"]}
    title = targets.change_title(c, change)
    current = targets.view(c, await targets.value_now(s, c) if targets.active(c) else None)
    preview = {"change": change, "current": current, "source": "lead", "lead": lead, "review_id": review.id}
    if p["type"] == "target":
        preview |= {"fields": {"target": targets.fmt(p["target"]).replace(",", "")}, "editable": ["target"]}
    if p["type"] == "new_goal":
        preview |= {"budget_usd": float(c.budget_total)}
    req = UserRequest(campaign_id=c.id, kind=RequestKind.proposal.value, title=title[:300], rationale=p["reasoning"],
                      preview=preview, department_id=dept.id)
    s.add(req)
    await s.flush()
    await activity.log(s, c.id, "request", f"{lead} suggested: {title}", status="waiting",
                       details={"request_id": req.id, "review_id": review.id})
    await notify(s, c.id, "request", id=req.id)
    return {"type": p["type"], "goal_id": c.id, "title": title, "reasoning": p["reasoning"], "request_id": req.id}


async def run_review(review_id: str, claude: MeteredClaude | None = None) -> None:
    claude = claude or MeteredClaude()
    async with session_scope() as s:
        review = await s.get(LeadReview, review_id)
        dept = await s.get(Department, review.department_id)
        org = await s.get(Organization, dept.org_id)
        if await spent_this_month(s, dept.id) >= dept.lead_monthly_cap_usd:
            review.status, review.error, review.locked_by = "failed", (
                f"This month's limit for {lead_name(dept)} (${dept.lead_monthly_cap_usd:.2f}) is used up."), None
            return
        task, agents, goals, pending = await _snapshot(s, dept)
        system = SYSTEM.format(team=dept.name, org=org.name, max=MAX_PROPOSALS)
    try:
        result = await claude.create(campaign_id=None, run_id=None, purpose="team lead review", role="planner",
                                     system=system, messages=[{"role": "user", "content": task}], max_tokens=6000,
                                     output_format=schema())
        text = "\n".join(b.get("text", "") for b in result.content if b.get("type") == "text")
        raw = json.loads(text)
    except Exception as e:  # a failed review costs little and is retried next time
        log.exception("team lead review %s failed", review_id)
        async with session_scope() as s:
            review = await s.get(LeadReview, review_id)
            review.status, review.error, review.locked_by = "failed", f"{type(e).__name__}: {e}"[:500], None
        return
    async with session_scope() as s:
        review = await s.get(LeadReview, review_id)
        dept = await s.get(Department, review.department_id)
        task, agents, goals, pending = await _snapshot(s, dept)  # fresh: things may have changed meanwhile
        made = [await _propose(s, dept, review, p) for p in tidy(raw, agents, goals, pending)]
        review.cost_usd = result.cost
        review.health = raw.get("health") if raw.get("health") in ("on_track", "mixed", "off_track") else ""
        review.summary = (raw.get("summary") or "").strip()[:2000]
        review.proposals = made
        review.status, review.locked_by = "done", None
        dept.lead_last_review_at = utcnow()
        emails = [u.email for u in await approvers(s, dept.org_id, dept.id)] if made else []
        first_goal = made[0]["goal_id"] if made else None
        name = lead_name(dept)
    if made:
        await send_approval_needed(emails, name, dept.name,
                                   f"{len(made)} suggestion{'s' if len(made) != 1 else ''} for the {dept.name} team", first_goal)


async def schedule_due_reviews() -> int:
    """Queue a review for each team whose lead is due (and has live goals, and budget left)."""
    created = 0
    async with session_scope() as s:
        now = utcnow()
        for dept in (await s.execute(select(Department).where(Department.lead_enabled.is_(True),
                                                              Department.lead_review_days > 0))).scalars():
            live = (await s.execute(select(Campaign.id).join(Agent, Agent.id == Campaign.agent_id).where(
                Agent.department_id == dept.id, Campaign.status == CampaignStatus.active.value).limit(1))).first()
            if not live:
                continue
            if dept.lead_last_review_at is None:
                dept.lead_last_review_at = now  # the clock starts when the team has live goals
                continue
            if now - dept.lead_last_review_at < timedelta(days=dept.lead_review_days):
                continue
            busy = (await s.execute(select(LeadReview.id).where(LeadReview.department_id == dept.id,
                                                                LeadReview.status.in_(["queued", "running"])))).first()
            if busy or await spent_this_month(s, dept.id) >= dept.lead_monthly_cap_usd:
                continue
            s.add(LeadReview(org_id=dept.org_id, department_id=dept.id))
            dept.lead_last_review_at = now
            created += 1
    return created


def review_json(r: LeadReview) -> dict:
    return {"id": r.id, "status": r.status, "health": r.health, "summary": r.summary, "proposals": r.proposals or [],
            "error": r.error, "cost_usd": float(r.cost_usd or 0), "created_at": r.created_at.isoformat()}
