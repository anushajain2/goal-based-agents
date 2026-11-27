"""The AI team lead: one per team, always thinking about how the team could do better.

Every few days (and whenever someone asks) it reviews the team the way a good manager would. It
has tools to look around: web search and fetch (the market, competitors, the company's news), the
company's read-only database and GitHub issues when connected, and each goal's full history
(targets, metrics, what sessions found, what they cost). It then proposes a few changes: a new
goal, a new AI employee with its first goal, a new target, pausing what isn't working, or
restarting something paused. Each proposal goes to Needs you with its reasoning, routed like
the team's other requests; nothing changes until a person approves.

It doesn't do the work itself and has no goal of its own. Its Claude usage is paid by the
organization (like setup research), with a monthly cap per team.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.agent import packs
from app.agent.llm import MeteredClaude, usage_org
from app.agent.org_setup import company_context
from app.db import session_scope
from app.models import (
    Activity,
    Agent,
    AgentRun,
    Campaign,
    CampaignStatus,
    Department,
    Integration,
    LeadReview,
    MetricSnapshot,
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
MAX_TURNS = 10  # model calls per review
MAX_WEB = 5  # web searches (and fetches) per call
CHANGE_TYPES = ["new_goal", "new_agent", "target", "pause", "resume"]


def lead_name(dept: Department) -> str:
    return f"{dept.name} Reviewer"


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

Look before you decide, using your tools:
- goal_details for any goal whose numbers need explaining: its metric history, past periods, what \
recent sessions did and found, and what it costs.
- web_search and web_fetch for what's happening outside: the company's own news and site, \
competitors' launches and pricing, the market and trends that matter for this team.
- db_query (read-only SQL) and github_issues when they're available, for the company's own numbers \
and product problems.
Keep it efficient: a handful of well-chosen lookups, not an audit. Then call submit_review once.

Propose at most {max} changes, only where they clearly help:
- new_goal: something important the team isn't working on yet (from the company's focus, gaps you \
see, or what a goal's results suggest). Ongoing goals are named like a person's goal, without \
numbers ("Win back churned customers"); the number goes in the target. Give it to the AI employee \
on the team who fits best (agent_id).
- target: a better target for a goal (raise it when it's being hit easily, lower it or change the \
period when it's out of reach or too noisy to judge).
- new_agent: work that needs its own AI employee (a distinct skill or a lot of work no one on the \
team covers), with its first goal. Give it a short name ("Reviews"), focus and objective.
- pause: a goal that keeps missing and isn't worth its budget, or no longer fits the focus.
- resume: a paused goal worth restarting.
Don't propose what is already waiting for a decision, and don't change a goal that started in the \
last few days unless something is clearly wrong. No changes is a fine answer when the team is on \
track. Every reasoning is two or three plain sentences with the numbers behind it. The summary is \
two or three sentences on how the team is doing.
In anything written for people (summary, reasoning, goal names and descriptions), don't call it an \
AI employee, agent or lead: talk about the goal, say Oton does the work, and call yourself the \
Reviewer. Propose new_agent to people as starting a new goal."""

TASK = """Company:
{company}

Team: {team}
AI employees:
{agents}

Goals:
{goals}

Waiting for a decision already:
{pending}

Roles you could hire for this team (role key: focus): {roles}.

Tools you have: {tools}.

Review the team and propose changes (or none) with submit_review."""


def review_tool() -> dict:
    new_agent = {
        "type": "object",
        "properties": {"role": {"type": "string", "enum": list(packs.ROLES) + ["custom"]},
                       "name": {"type": "string"}, "title": {"type": "string", "description": "Its focus, 2-4 words"},
                       "objective": {"type": "string"}},
        "required": ["role", "name", "title", "objective"],
        "additionalProperties": False,
    }
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
            "new_goal": {"anyOf": [new_goal, {"type": "null"}],
                         "description": "For new_goal and new_agent: the goal (for new_agent, agent_id is ignored)"},
            "new_agent": {"anyOf": [new_agent, {"type": "null"}], "description": "For new_agent only"},
        },
        "required": ["type", "goal_id", "reasoning", "target", "period", "new_goal", "new_agent"],
        "additionalProperties": False,
    }
    return {
        "name": "submit_review",
        "description": "Finish the review: how the team is doing, and the changes you propose (or none).",
        "input_schema": {
            "type": "object",
            "properties": {"health": {"type": "string", "enum": ["on_track", "mixed", "off_track"]},
                           "summary": {"type": "string", "description": "Two or three sentences on how the team is doing."},
                           "proposals": {"type": "array", "items": proposal}},
            "required": ["health", "summary", "proposals"],
        },
    }


def lead_tools(has_db: bool, has_github: bool) -> list[dict]:
    tools: list[dict] = [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_WEB},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": MAX_WEB},
        {"name": "goal_details", "description": "One goal's full picture: targets and past periods, metric history, "
         "what recent work sessions did and found, recent key actions, and spending.",
         "input_schema": {"type": "object", "properties": {"goal_id": {"type": "string"}}, "required": ["goal_id"]}},
    ]
    if has_db:
        tools.append({"name": "db_query", "description": "Run one read-only SQL query (SELECT only, Postgres) on the "
                      "company's database, e.g. signups or activation by week. Returns up to 200 rows.",
                      "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}})
    if has_github:
        tools.append({"name": "github_issues", "description": "List the product's open GitHub issues (title, labels, comments).",
                      "input_schema": {"type": "object", "properties": {}}})
    tools.append(review_tool())
    return tools


async def _snapshot(s, dept: Department, tools: str = "") -> tuple[str, list[Agent], dict[str, Campaign], set[str]]:
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
                       pending=pending_text, tools=tools or "goal_details, web_search, web_fetch",
                       roles="; ".join(f"{r.key}: {r.title}" for r in packs.ROLES.values() if r.kind == dept.kind)
                       or "any role from the catalog that fits, or custom")
    return task, agents, {g.id: g for g in goals}, pending


def tidy(raw: dict, agents: list[Agent], goals: dict[str, Campaign], pending: set[str]) -> list[dict]:
    out, touched = [], set()
    for p in raw.get("proposals") or []:
        kind = p.get("type")
        reasoning = (p.get("reasoning") or "").strip()
        if kind not in CHANGE_TYPES or not reasoning:
            continue
        if kind in ("new_goal", "new_agent"):
            ng = p.get("new_goal") or {}
            if not (ng.get("name") or "").strip() or not (ng.get("goal_description") or "").strip():
                continue
            if ng["name"].strip().lower() in {g.name.lower() for g in goals.values()}:
                continue
            if kind == "new_agent":
                na = p.get("new_agent") or {}
                if not (na.get("name") or "").strip() or any(o["type"] == "new_agent" for o in out):
                    continue  # one new hire per review at most
                out.append({"type": "new_agent", "reasoning": reasoning, "new_goal": ng,
                            "new_agent": {"role": na.get("role") if na.get("role") in packs.ROLES else "",
                                          "name": na["name"].strip()[:120], "title": (na.get("title") or "").strip()[:160],
                                          "objective": (na.get("objective") or "").strip()[:400]}})
            else:
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
    if p["type"] in ("new_goal", "new_agent"):
        ng = p["new_goal"]
        org = await s.get(Organization, dept.org_id)
        per, kind, n = await estimate.session_cost(s, dept.org_id)
        basis = estimate.starter(per, 24, estimate.DEFAULT_DAYS, 0, kind, n)
        c = Campaign(
            org_id=dept.org_id, owner_id=review.requested_by, agent_id=p.get("agent_id"), name=ng["name"].strip()[:200],
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
        await activity.log(s, c.id, "system", f"Suggested by the {lead}", details={"why": p["reasoning"]}, status="info")
    else:
        c = await s.get(Campaign, p["goal_id"])
        if p["type"] == "target":
            change |= {"target": p["target"], "period": p["period"]}
    if p["type"] == "new_agent":
        change |= {"agent": p["new_agent"], "department_id": dept.id}
    title = targets.change_title(c, change)
    current = targets.view(c, await targets.value_now(s, c) if targets.active(c) else None)
    preview = {"change": change, "current": current, "source": "lead", "lead": lead, "review_id": review.id}
    if p["type"] == "target":
        preview |= {"fields": {"target": targets.fmt(p["target"]).replace(",", "")}, "editable": ["target"]}
    if p["type"] in ("new_goal", "new_agent"):
        preview |= {"budget_usd": float(c.budget_total)}
    req = UserRequest(campaign_id=c.id, kind=RequestKind.proposal.value, title=title[:300], rationale=p["reasoning"],
                      preview=preview, department_id=dept.id)
    s.add(req)
    await s.flush()
    await activity.log(s, c.id, "request", f"The {lead} suggested: {title}", status="waiting",
                       details={"request_id": req.id, "review_id": review.id})
    await notify(s, c.id, "request", id=req.id)
    return {"type": p["type"], "goal_id": c.id, "title": title, "reasoning": p["reasoning"], "request_id": req.id}


async def _goal_details(s, dept: Department, goal_id: str) -> str:
    g = await s.get(Campaign, goal_id)
    agent = await s.get(Agent, g.agent_id) if g and g.agent_id else None
    if not g or not agent or agent.department_id != dept.id:
        return "No such goal on this team."
    value = await targets.value_now(s, g) if targets.active(g) else None
    budget = await ledger.budget_state(s, g)
    metrics = (await s.execute(select(MetricSnapshot).where(MetricSnapshot.campaign_id == g.id)
                               .order_by(MetricSnapshot.recorded_at.desc()).limit(15))).scalars().all()
    runs = (await s.execute(select(AgentRun).where(AgentRun.campaign_id == g.id, AgentRun.summary.is_not(None))
                            .order_by(AgentRun.cycle_number.desc()).limit(6))).scalars().all()
    acts = (await s.execute(select(Activity).where(Activity.campaign_id == g.id, Activity.kind.in_(["action", "decision", "blocked"]))
                            .order_by(Activity.id.desc()).limit(15))).scalars().all()
    return json.dumps({
        "goal": g.name, "description": g.goal_description, "status": g.status, "metric": g.primary_metric,
        "what_counts": g.done_when, "target": targets.view(g, value), "strategy": g.strategy[:1500],
        "budget": {"total": float(budget.total), "spent": float(budget.settled)},
        "metric_history": [{"at": m.recorded_at.isoformat()[:16], "value": m.value, "source": m.source} for m in reversed(metrics)],
        "recent_sessions": [{"n": r.cycle_number, "summary": (r.summary or "")[:600]} for r in runs],
        "recent_actions": [f"{a.created_at:%m-%d} [{a.status}] {a.title}"[:200] for a in acts],
    }, default=str)[:12000]


async def _run_tool(dept: Department, name: str, inp: dict, used: list[str]) -> tuple[str, bool]:
    try:
        if name == "goal_details":
            async with session_scope() as s:
                out = await _goal_details(s, dept, str(inp.get("goal_id") or ""))
                g = await s.get(Campaign, str(inp.get("goal_id") or ""))
            used.append(f"Looked into \"{g.name}\"" if g else "Looked into a goal")
            return out, False
        if name == "db_query":
            i = await _integration(dept.org_id, "postgres")
            if not i:
                return "No database is connected.", True
            from app.connectors.database import run_read_only
            from app.services.secrets_box import unseal

            result = await run_read_only(unseal(i.secret_encrypted), str(inp.get("sql") or ""))
            used.append("Queried your database")
            return json.dumps(result, default=str)[:12000], False
        if name == "github_issues":
            i = await _integration(dept.org_id, "github")
            if not i:
                return "No GitHub repository is connected.", True
            from app.connectors.github import GitHub
            from app.services.secrets_box import unseal

            issues = await GitHub(unseal(i.secret_encrypted), i.config["repo"]).list_issues(limit=30)
            used.append("Read open GitHub issues")
            return json.dumps(issues, default=str)[:12000], False
    except Exception as e:  # noqa: BLE001 - the lead sees the error and carries on
        return f"That didn't work: {type(e).__name__}: {e}"[:500], True
    return f"Unknown tool {name}.", True


async def _integration(org_id: str, kind: str) -> Integration | None:
    async with session_scope() as s:
        return (await s.execute(select(Integration).where(Integration.org_id == org_id, Integration.kind == kind)
                                .order_by(Integration.created_at).limit(1))).scalar_one_or_none()


async def _fail(review_id: str, error: str, cost: Decimal = Decimal("0")) -> None:
    async with session_scope() as s:
        review = await s.get(LeadReview, review_id)
        review.status, review.error, review.locked_by = "failed", error[:500], None
        review.cost_usd = cost


async def run_review(review_id: str, claude: MeteredClaude | None = None) -> None:
    claude = claude or MeteredClaude()
    async with session_scope() as s:
        review = await s.get(LeadReview, review_id)
        dept = await s.get(Department, review.department_id)
        org = await s.get(Organization, dept.org_id)
        usage_org.set(dept.org_id)
        left = dept.lead_monthly_cap_usd - await spent_this_month(s, dept.id)
        if left <= 0:
            review.status, review.error, review.locked_by = "failed", (
                f"This month's limit for {lead_name(dept)} (${dept.lead_monthly_cap_usd:.2f}) is used up."), None
            return
        kinds = {k for (k,) in (await s.execute(select(Integration.kind).where(Integration.org_id == dept.org_id))).all()}
        tools = lead_tools("postgres" in kinds, "github" in kinds)
        names = ["goal_details", "web_search", "web_fetch"] + (["db_query"] if "postgres" in kinds else []) \
            + (["github_issues"] if "github" in kinds else [])
        task, agents, goals, pending = await _snapshot(s, dept, tools=", ".join(names))
        system = SYSTEM.format(team=dept.name, org=org.name, max=MAX_PROPOSALS)
        dept_snapshot = Department(id=dept.id, org_id=dept.org_id, name=dept.name)

    messages: list[dict] = [{"role": "user", "content": task}]
    cost, raw, used, sources, nudged = Decimal("0"), None, [], [], False
    try:
        for _ in range(MAX_TURNS):
            result = await claude.create(campaign_id=None, run_id=None, purpose="Reviewer review", task="reviewer",
                                         system=system, messages=messages, tools=tools, max_tokens=8000,
                                         max_web_searches=MAX_WEB)
            cost += result.cost
            messages.append({"role": "assistant", "content": result.content})
            for b in result.content:
                if b.get("type") == "server_tool_use":
                    q = (b.get("input") or {}).get("query") or (b.get("input") or {}).get("url")
                    if q:
                        used.append(("Searched: " if b.get("name") == "web_search" else "Read: ") + str(q)[:150])
                if b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
                    sources += [{"url": r["url"], "title": r.get("title") or r["url"]} for r in b["content"]
                                if isinstance(r, dict) and r.get("url")]
            final = next((b for b in result.content if b.get("type") == "tool_use" and b.get("name") == "submit_review"), None)
            if final:
                raw = final.get("input") or {}
                break
            if result.stop_reason == "pause_turn":
                continue  # the server paused a long search; send the turn back to carry on
            calls = [b for b in result.content if b.get("type") == "tool_use"]
            if calls:
                results = []
                for b in calls:
                    out, err = await _run_tool(dept_snapshot, b["name"], b.get("input") or {}, used)
                    results.append({"type": "tool_result", "tool_use_id": b["id"], "content": out, "is_error": err})
                if cost >= left:
                    results.append({"type": "text", "text": "Budget for this review is nearly used: call submit_review now."})
                messages.append({"role": "user", "content": results})
                continue
            if nudged:
                break
            nudged = True
            messages.append({"role": "user", "content": "Call submit_review with your review now."})
    except Exception as e:  # a failed review costs little and is tried again next time
        log.exception("team lead review %s failed", review_id)
        await _fail(review_id, f"{type(e).__name__}: {e}", cost)
        return
    if raw is None:
        await _fail(review_id, "The review didn't finish. Try again.", cost)
        return

    unique, seen = [], set()
    for src in sources:
        if src["url"] not in seen:
            seen.add(src["url"])
            unique.append(src)
    async with session_scope() as s:
        review = await s.get(LeadReview, review_id)
        dept = await s.get(Department, review.department_id)
        task, agents, goals, pending = await _snapshot(s, dept)  # fresh: things may have changed meanwhile
        made = [await _propose(s, dept, review, p) for p in tidy(raw, agents, goals, pending)]
        review.cost_usd = cost
        review.health = raw.get("health") if raw.get("health") in ("on_track", "mixed", "off_track") else ""
        review.summary = (raw.get("summary") or "").strip()[:2000]
        review.proposals = made
        review.research = {"looked_at": used[:30], "sources": unique[:12]}
        review.status, review.locked_by = "done", None
        dept.lead_last_review_at = utcnow()
        emails = [u.email for u in await approvers(s, dept.org_id, dept.id)] if made else []
        first_goal = made[0]["goal_id"] if made else None
        name = lead_name(dept)
    if made:
        await send_approval_needed(emails, f"The {name}", dept.name,
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
            "research": r.research or {},
            "error": r.error, "cost_usd": float(r.cost_usd or 0), "created_at": r.created_at.isoformat()}
