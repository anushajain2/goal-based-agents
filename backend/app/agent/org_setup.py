"""First-run setup: learn what the company does, then set up its AI team.

    1. website   read the home page and a few telling pages (about, pricing, customers, careers)
    2. research  web research on the company: funding, team, customers, news, competitors
    3. plan      decide which functions matter now, and the few goals each should pursue
    4. create    departments + AI employees, with the goals saved as drafts to review and start

Runs in the worker (see app/worker.py), so it survives the browser being closed. Progress is
saved after every step for the setup page to show. Goals are drafts: nothing is spent from a
goal budget until someone starts it. The research itself is paid by the organization, not by
any goal, and its cost is shown on the setup page.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.agent.llm import MeteredClaude
from app.db import session_scope
from app.models import Agent, Campaign, Department, Membership, Organization, OrgSetup, Role, utcnow
from app.org import CATEGORY_KEYS, DEPARTMENT_PRESETS, PRESET_NAMES, add_department
from app.agent.playbook import STEP_GUIDANCE, step_schema, tidy_steps
from app.services import activity, estimate
from app.services.website import read_site

log = logging.getLogger(__name__)

MAX_DEPARTMENTS = 6
MAX_GOALS_PER_DEPARTMENT = 3
MAX_GOALS = 12
MAX_SEARCHES = 8
MAX_CONTINUATIONS = 4
CYCLE_CHOICES = [1, 3, 6, 12, 24, 48]

STEPS = [
    ("website", "Reading your website"),
    ("research", "Researching the company on the web"),
    ("plan", "Working out your key functions and goals"),
    ("create", "Setting up your AI employees"),
]


def initial_steps() -> list[dict]:
    return [{"key": k, "label": label, "status": "pending", "detail": ""} for k, label in STEPS]


# --- prompts -----------------------------------------------------------------------------------

RESEARCH_SYSTEM = """You are a meticulous company research analyst. Your brief will be used to \
decide which AI employees a company needs and what they should work on first, so accuracy \
matters more than length.

Use web search. Prefer primary and recent sources: the company's own site and blog, founders' \
posts, press releases, funding announcements and databases, job boards, app/marketplace \
listings, reviews. Many companies share a name: confirm a source is about this company (same \
domain, product or founders) before using it. Early-stage companies often have little public \
information; when you can't find something, write "Unknown" rather than guessing. Where the \
founders' own description disagrees with older web sources, trust the founders and note it."""

RESEARCH_TASK = """Research this company.

Name: {name}
Website: {website}
What the founders say it does: {description}

What their website says (extracted text, may be partial):
<website>
{site}
</website>

Write a factual brief (about 500-900 words) with these sections:
- Identity: confirm which company this is (and anything easily confused with it).
- What they sell, and to whom (ideal customer, industries, company sizes, geographies).
- Business model and pricing.
- Stage and funding: rounds, amounts, dates, investors. Or "bootstrapped" / "Unknown".
- Team: approximate size, founders and their backgrounds, open roles (what they are hiring for says a lot).
- Traction: named customers, users, revenue or growth signals, launches.
- Go-to-market today: which channels they visibly use (outbound, content, community, ads, partners, marketplaces, events).
- Recent news from the last 12 months, with dates.
- Competitors and how they position against them.
- Signals about current priorities and challenges.

End with a "Sources:" list of the URLs you relied on."""

PLAN_SYSTEM = """You design the AI team for a company that uses Autopilot.

Autopilot AI employees each belong to a department and work autonomously toward goals with a \
countable finish line and a budget. They can: research the web; build and enrich lists of \
companies, people and contacts; write and send emails and LinkedIn/X messages; publish posts, \
articles and replies; take part in communities; apply to directories, programs, awards and \
podcasts; book meetings onto a calendar; run small ad budgets; fill in forms; and use the \
company's connected apps (CRM, email, analytics, docs) or a browser. They ask the people in \
their department before anything public, outgoing or paid. They cannot write or ship product \
code, sign contracts, make hiring or legal decisions, move money beyond an approved budget, or \
do physical work.

Choose functions and goals that fit THIS company at its CURRENT stage:
- 3 to {max_departments} functions, most important first. A two-person pre-seed startup does \
not need Finance or Operations agents; a funded company hiring salespeople needs pipeline; an \
agency needs client acquisition and delivery support. Skip a function if there's nothing \
valuable an AI employee could do there yet.
- 1 to {max_per_dept} goals per function (2 is typical), at most {max_goals} in total. Fewer, \
sharper goals beat many. No two goals should overlap.
- Make every goal specific to this company: name their real customer, product, market and \
channels. Each must be something an AI employee can mostly achieve itself in about 30 days, \
with a done_when that can be checked ("Meeting held on calendar with a Head of Ops at a 50-500 \
person logistics company"), a short primary_metric ("meetings held") and a realistic target.
- cycle_hours is how often it works on the goal: 3 to 12 for active outreach, 24 for slower work.
- duration_days is how long the goal should run: usually 30, 14 for quick wins, up to 60.
- paid_spend_usd is money the goal must spend beyond its own AI usage (ad spend, paid listings, \
data purchases): 0 unless the goal clearly needs it. The budget is calculated from these.
- {step_guidance}
- "why" must point at evidence from the research or the founders' description, in one or two \
plain sentences ("You raised a seed round in March and are hiring two AEs, so a steady \
pipeline matters most right now").
- Use a preset department kind when one fits; otherwise use "custom" and give it a clear name \
(e.g. "Client Delivery").
- category must be the closest library category; use_case is a 1-3 word label ("Cold outbound").
- The profile states facts concisely, "Unknown" where not known. Trust the founders' \
description over older web sources."""

PLAN_TASK = """Company: {name}
Website: {website}
What the founders say it does: {description}

Research brief:
<research>
{research}
</research>

What their website says (extracted text, may be partial):
<website>
{site}
</website>

Design their AI team: the profile, the functions, and the first goals for each."""


def plan_schema() -> dict:
    kinds = [k for k, _ in DEPARTMENT_PRESETS] + ["custom"]
    string_list = {"type": "array", "items": {"type": "string"}}
    goal = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Short name, under 60 characters"},
            "goal_description": {"type": "string", "description": "The goal as you'd brief a new hire: who, what, how many"},
            "done_when": {"type": "string"},
            "primary_metric": {"type": "string"},
            "target_value": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "category": {"type": "string", "enum": list(CATEGORY_KEYS)},
            "use_case": {"type": "string"},
            "cycle_hours": {"type": "number"},
            "duration_days": {"type": "number"},
            "paid_spend_usd": {"type": "number"},
            "steps": {"type": "array", "items": step_schema()},
            "channels": string_list,
            "why": {"type": "string"},
        },
        "required": ["name", "goal_description", "done_when", "primary_metric", "target_value", "category",
                     "use_case", "cycle_hours", "duration_days", "paid_spend_usd", "steps", "channels", "why"],
        "additionalProperties": False,
    }
    department = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": kinds},
            "name": {"type": "string"},
            "agent_title": {"type": "string", "description": "The AI employee's focus, 2-4 words"},
            "why": {"type": "string"},
            "goals": {"type": "array", "items": goal},
        },
        "required": ["kind", "name", "agent_title", "why", "goals"],
        "additionalProperties": False,
    }
    profile_fields = ["summary", "offering", "customers", "business_model", "stage", "funding", "team", "traction"]
    profile = {
        "type": "object",
        "properties": {**{f: {"type": "string"} for f in profile_fields},
                       "current_focus": string_list, "challenges": string_list},
        "required": [*profile_fields, "current_focus", "challenges"],
        "additionalProperties": False,
    }
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {"profile": profile, "departments": {"type": "array", "items": department}},
            "required": ["profile", "departments"],
            "additionalProperties": False,
        },
    }


# --- progress ----------------------------------------------------------------------------------

async def _step(setup_id: str, key: str, status: str, detail: str = "", cost: Decimal = Decimal("0")) -> None:
    async with session_scope() as s:
        setup = await s.get(OrgSetup, setup_id)
        steps = [dict(x) for x in setup.steps or initial_steps()]
        for x in steps:
            if x["key"] == key:
                x["status"] = status
                if detail:
                    x["detail"] = detail
        setup.steps = steps
        setup.cost_usd = (setup.cost_usd or Decimal("0")) + cost
        setup.locked_at = utcnow()  # heartbeat for stale-run recovery


def _texts(content: list[dict]) -> str:
    return "\n".join(b.get("text", "") for b in content if b.get("type") == "text").strip()


def _sources(content: list[dict]) -> list[dict]:
    out = []
    for b in content:
        if b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
            for r in b["content"]:
                if isinstance(r, dict) and r.get("url"):
                    out.append({"url": r["url"], "title": r.get("title") or r["url"]})
    return out


def _searches(response: Any) -> int:
    server = getattr(response.usage, "server_tool_use", None)
    return int(getattr(server, "web_search_requests", 0) or 0) if server else 0


# --- the steps ---------------------------------------------------------------------------------

async def research_company(claude: MeteredClaude, setup_id: str, name: str, website: str, description: str,
                           site_text: str) -> tuple[str, list[dict]]:
    task = RESEARCH_TASK.format(name=name, website=website or "(none given)",
                                description=description or "(not given)", site=site_text or "(not available)")
    messages: list[dict] = [{"role": "user", "content": task}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCHES}]
    texts, sources, searches = [], [], 0
    for _ in range(MAX_CONTINUATIONS + 1):
        result = await claude.create(
            campaign_id=None, run_id=None, purpose="setup research", role="worker",
            system=RESEARCH_SYSTEM, messages=messages, tools=tools, max_tokens=16000,
            max_web_searches=MAX_SEARCHES,
        )
        searches += _searches(result.response)
        sources += _sources(result.content)
        texts.append(_texts(result.content))
        await _step(setup_id, "research", "running", f"{searches} web searches so far", result.cost)
        if result.stop_reason != "pause_turn":
            break
        # The server paused its search loop; send the turn back and it carries on.
        messages = [messages[0], {"role": "assistant", "content": result.content}]
    unique, seen = [], set()
    for src in sources:
        if src["url"] not in seen:
            seen.add(src["url"])
            unique.append(src)
    brief = texts[-1] if texts and texts[-1] else "\n\n".join(t for t in texts if t)
    await _step(setup_id, "research", "done", f"{searches} web searches, {len(unique)} sources")
    return brief, unique[:15]


async def plan_team(claude: MeteredClaude, setup_id: str, name: str, website: str, description: str,
                    research: str, site_text: str) -> dict:
    result = await claude.create(
        campaign_id=None, run_id=None, purpose="setup plan", role="planner",
        system=PLAN_SYSTEM.format(max_departments=MAX_DEPARTMENTS, max_per_dept=MAX_GOALS_PER_DEPARTMENT,
                                  max_goals=MAX_GOALS, step_guidance=STEP_GUIDANCE),
        messages=[{"role": "user", "content": PLAN_TASK.format(
            name=name, website=website or "(none given)", description=description or "(not given)",
            research=research or "(no research available)", site=(site_text or "(not available)")[:12000])}],
        max_tokens=16000, output_format=plan_schema(),
    )
    if result.stop_reason == "refusal":
        raise RuntimeError("Claude declined to plan this company's team.")
    raw = _texts(result.content)
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError("The team plan came back incomplete. Try again.") from e
    plan = tidy_plan(plan)
    n_goals = sum(len(d["goals"]) for d in plan["departments"])
    await _step(setup_id, "plan", "done", f"{len(plan['departments'])} functions, {n_goals} goals", result.cost)
    return plan


def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, v))


def tidy_plan(plan: dict) -> dict:
    """Enforce the limits the prompt asks for: few functions, few goals, sane numbers."""
    departments, seen_names, seen_goals, total = [], set(), set(), 0
    for d in plan.get("departments") or []:
        kind = d.get("kind") if d.get("kind") in PRESET_NAMES else ""
        name = (d.get("name") or PRESET_NAMES.get(kind, "")).strip()[:120] or "General"
        if name.lower() in seen_names:
            continue
        goals = []
        for g in d.get("goals") or []:
            title = (g.get("name") or g.get("goal_description") or "").strip()
            if not title or title.lower() in seen_goals or not (g.get("goal_description") or "").strip():
                continue
            if len(goals) >= MAX_GOALS_PER_DEPARTMENT or total >= MAX_GOALS:
                break
            target = g.get("target_value")
            target = float(target) if isinstance(target, (int, float)) and target > 0 else None
            cycle = _clamp(g.get("cycle_hours"), 1, 48, 6)
            goals.append({
                "name": title[:200],
                "goal_description": g["goal_description"].strip(),
                "done_when": (g.get("done_when") or "").strip(),
                "primary_metric": (g.get("primary_metric") or "results").strip()[:120],
                "target_value": target,
                "category": g.get("category") if g.get("category") in CATEGORY_KEYS else "",
                "use_case": (g.get("use_case") or "").strip()[:120],
                "cycle_hours": float(min(CYCLE_CHOICES, key=lambda c: abs(c - cycle))),
                "duration_days": round(_clamp(g.get("duration_days"), 7, 90, 30)),
                "paid_spend_usd": round(_clamp(g.get("paid_spend_usd"), 0, 5000, 0), 2),
                "steps": tidy_steps(g.get("steps")),
                "channels": [str(c)[:60] for c in (g.get("channels") or [])][:8],
                "why": (g.get("why") or "").strip(),
            })
            seen_goals.add(title.lower())
            total += 1
        if not goals:
            continue
        seen_names.add(name.lower())
        departments.append({"kind": kind, "name": name, "agent_title": (d.get("agent_title") or "").strip()[:160],
                            "why": (d.get("why") or "").strip(), "goals": goals})
        if len(departments) >= MAX_DEPARTMENTS:
            break
    profile = plan.get("profile") or {}
    return {"profile": profile, "departments": departments}


def company_context(org: Organization, profile: dict) -> str:
    """The brief every suggested goal starts with (people can edit it per goal)."""
    lines = [f"Company: {org.name}" + (f" ({org.website})" if org.website else "")]
    if org.description:
        lines.append(f"In the founders' words: {org.description}")
    for key, label in [("offering", "What we sell"), ("customers", "Who we sell to"),
                       ("business_model", "Business model"), ("stage", "Stage"), ("traction", "Traction")]:
        value = (profile.get(key) or "").strip()
        if value and value.lower() != "unknown":
            lines.append(f"{label}: {value}")
    if profile.get("current_focus"):
        lines.append("Current focus: " + "; ".join(profile["current_focus"]))
    lines.append("(From Autopilot's setup research. Correct anything that's wrong.)")
    return "\n".join(lines)


async def create_team(setup_id: str, org_id: str, requested_by: str | None, plan: dict) -> dict:
    """Departments, AI employees and draft goals. Reuses departments that already exist."""
    created = {"departments": [], "agents": [], "goals": []}
    async with session_scope() as s:
        org = await s.get(Organization, org_id)
        admins = [u for (u,) in (await s.execute(
            select(Membership.user_id).where(Membership.org_id == org_id,
                                             Membership.role.in_([Role.owner.value, Role.admin.value]))
        )).all()]
        existing = (await s.execute(select(Department).where(Department.org_id == org_id))).scalars().all()
        goal_names = {n.lower() for (n,) in (await s.execute(
            select(Campaign.name).where(Campaign.org_id == org_id))).all()}
        context = company_context(org, plan.get("profile") or {})
        for d in plan["departments"]:
            dept = next((x for x in existing if (d["kind"] and x.kind == d["kind"]) or x.name.lower() == d["name"].lower()), None)
            if dept is None:
                dept = await add_department(s, org_id, d["name"], d["kind"], members=admins)
                existing.append(dept)
                created["departments"].append(dept.id)
            agent = (await s.execute(select(Agent).where(Agent.department_id == dept.id)
                                     .order_by(Agent.created_at).limit(1))).scalar_one_or_none()
            if agent is None:
                agent = Agent(org_id=org_id, department_id=dept.id, name=f"{dept.name} Agent")
                s.add(agent)
                await s.flush()
            if d["agent_title"] and not agent.title:
                agent.title = d["agent_title"]
            created["agents"].append(agent.id)
            for g in d["goals"]:
                if g["name"].lower() in goal_names:
                    continue
                goal_names.add(g["name"].lower())
                c = Campaign(
                    org_id=org_id, owner_id=requested_by, agent_id=agent.id, name=g["name"],
                    goal_type=CATEGORY_KEYS.get(g["category"], "custom"), goal_description=g["goal_description"],
                    primary_metric=g["primary_metric"], target_value=g["target_value"], done_when=g["done_when"],
                    category=g["category"], use_case=g["use_case"], context=context, channels=g["channels"],
                    budget_total=Decimal(str(g["budget_usd"])), cycle_hours=g["cycle_hours"],
                    origin="setup", suggested_reason=g["why"],
                    budget_basis={**g["budget_basis"], "chosen_usd": g["budget_usd"]},
                    playbook={"steps": g["steps"], "source": "setup"} if g["steps"] else None,
                )
                s.add(c)
                await s.flush()
                await activity.log(s, c.id, "system", f"Suggested by setup research for {agent.name}",
                                   details={"why": g["why"]} if g["why"] else None, status="info")
                created["goals"].append(c.id)
    await _step(setup_id, "create", "done",
                f"{len(created['agents'])} AI employees, {len(created['goals'])} goals ready to review")
    return created


async def run_org_setup(setup_id: str, claude: MeteredClaude | None = None) -> None:
    claude = claude or MeteredClaude()
    async with session_scope() as s:
        setup = await s.get(OrgSetup, setup_id)
        org = await s.get(Organization, setup.org_id)
        org_id, requested_by = org.id, setup.requested_by
        name, website, description = org.name, org.website, org.description
        setup.steps = setup.steps or initial_steps()
        setup.error = None
    current = "website"
    try:
        # 1. Website
        site_text = ""
        if website:
            await _step(setup_id, "website", "running")
            reading = await read_site(website)
            site_text = reading.as_text()
            if reading.pages:
                await _step(setup_id, "website", "done",
                            f"Read {len(reading.pages)} page{'s' if len(reading.pages) != 1 else ''} on {reading.domain}")
            else:
                await _step(setup_id, "website", "failed", reading.error or "Couldn't read the website")
        else:
            await _step(setup_id, "website", "skipped", "No website given")

        # 2. Research. Setup can still go on from the website and description if this fails.
        current = "research"
        await _step(setup_id, "research", "running")
        try:
            research, sources = await research_company(claude, setup_id, name, website, description, site_text)
        except Exception as e:
            log.warning("setup research failed: %s", e)
            research, sources = "", []
            await _step(setup_id, "research", "failed", f"Web research didn't work ({type(e).__name__}); "
                                                         "carrying on with what you told us")
            if not site_text and not description:
                raise
        async with session_scope() as s:
            (await s.get(OrgSetup, setup_id)).research = research

        # 3. Plan
        current = "plan"
        await _step(setup_id, "plan", "running")
        plan = await plan_team(claude, setup_id, name, website, description, research, site_text)
        if not plan["departments"]:
            raise RuntimeError("Couldn't work out any functions to set up. Add a few words about what you do and try again.")
        async with session_scope() as s:
            per, basis, n = await estimate.session_cost(s, org_id)
        for d in plan["departments"]:  # budget = sessions x cost per session + paid spend
            for g in d["goals"]:
                g["budget_basis"] = estimate.compute(per, g["cycle_hours"], g["duration_days"], g["paid_spend_usd"], basis, n)
                g["budget_usd"] = g["budget_basis"]["suggested_usd"]
        async with session_scope() as s:
            (await s.get(OrgSetup, setup_id)).plan = plan
            org = await s.get(Organization, org_id)
            org.profile = {**(plan.get("profile") or {}), "sources": sources, "researched_at": utcnow().isoformat()}

        # 4. Create
        current = "create"
        await _step(setup_id, "create", "running")
        created = await create_team(setup_id, org_id, requested_by, plan)
        async with session_scope() as s:
            setup = await s.get(OrgSetup, setup_id)
            setup.created = created
            setup.status = "done"
            setup.locked_by = None
    except Exception as e:
        log.exception("org setup %s failed", setup_id)
        await _step(setup_id, current, "failed")
        async with session_scope() as s:
            setup = await s.get(OrgSetup, setup_id)
            setup.status = "failed"
            setup.error = str(e)[:1000] or type(e).__name__
            setup.locked_by = None


async def org_needs_basic_team(org_id: str) -> bool:
    async with session_scope() as s:
        n = (await s.execute(select(func.count()).select_from(Department).where(Department.org_id == org_id))).scalar_one()
        return n == 0
