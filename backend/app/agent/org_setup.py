"""First-run setup: learn what the company does, then set up its AI team.

    1. website   read the home page and a few telling pages (about, pricing, customers, careers)
    2. research  web research on the company: funding, team, customers, news, competitors
    3. plan      decide which functions matter now, and the few goals each should pursue
    4. create    departments + AI employees, with the goals saved as drafts to review and start
    5. scan      what the company is missing today (public signals), each gap tied to a goal

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
from app.agent import opportunities, packs
from app.agent.playbook import OUTREACH_KNOWHOW, STEP_GUIDANCE, default_key_results, step_schema, tidy_steps
from app.services import activity, estimate, targets
from app.services.website import read_site

log = logging.getLogger(__name__)

MAX_GOALS_PER_DEPARTMENT = 3
MAX_AGENTS_PER_DEPARTMENT = 3
# How big a team fits a company: set from headcount, revenue and funding found by the research.
SIZES: dict[str, dict] = {
    "tiny": {"label": "1-10 people", "departments": 4, "agents": 6, "goals": 8},
    "small": {"label": "11-50 people", "departments": 6, "agents": 9, "goals": 12},
    "mid": {"label": "51-250 people", "departments": 8, "agents": 13, "goals": 16},
    "large": {"label": "250+ people", "departments": 10, "agents": 18, "goals": 20},
}
DEFAULT_SIZE = "small"
MAX_DEPARTMENTS = SIZES[DEFAULT_SIZE]["departments"]
MAX_GOALS = SIZES[DEFAULT_SIZE]["goals"]
MAX_LATER = 4
MAX_SEARCHES = 8
MAX_CONTINUATIONS = 4
CYCLE_CHOICES = [1, 3, 6, 12, 24, 48]

# What a setup run does, by mode:
#   start    first-time onboarding: learn about the company, then find what it's missing out on
#            (each finding comes with the goal that fixes it)
#   goals    "Suggest more goals": goals for each function, from what we already know
#   more     "Find more opportunities": look again, skipping what was already found
#   include  add specific functions (with their goals), from what we already know
STEPS: dict[str, list[tuple[str, str]]] = {
    "start": [("website", "Reading your website"),
              ("research", "Researching the company on the web"),
              ("profile", "Understanding what you sell and who buys it"),
              ("scan", "Finding what you're missing out on")],
    "goals": [("plan", "Working out goals for each function"),
              ("create", "Setting up the suggested goals")],
    "more": [("website", "Reading your website again"),
             ("scan", "Looking for new opportunities")],
    "include": [("plan", "Working out goals for these functions"),
                ("create", "Setting up the goals")],
}
MODES = tuple(STEPS)


def initial_steps(mode: str = "start") -> list[dict]:
    return [{"key": k, "label": label, "status": "pending", "detail": ""} for k, label in STEPS.get(mode, STEPS["start"])]


def mode_of(plan: dict | None) -> str:
    plan = plan or {}
    return plan.get("mode") or ("include" if plan.get("include") else "start")


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
- Team: approximate headcount (team page, LinkedIn, job boards), founders and their backgrounds, open roles (what they are hiring for says a lot).
- Size and money: headcount, revenue or ARR (reported or estimated, say which), total funding and last round.
- Traction: named customers, users, revenue or growth signals, launches.
- Back office: signs of finance, people, IT/security and legal needs (enterprise customers asking for security reviews, SOC 2 or ISO pages, many open roles, several countries, regulated industry).
- Go-to-market today: which channels they visibly use (outbound, content, community, ads, partners, marketplaces, events).
- Recent news from the last 12 months, with dates.
- Competitors and how they position against them.
- Signals about current priorities and challenges.

End with a "Sources:" list of the URLs you relied on."""

PLAN_SYSTEM = """You design the AI team for a company that uses Oton.

Oton AI employees each belong to a department and work autonomously toward goals with a \
countable finish line and a budget. They can: research the web; build and enrich lists of \
companies, people and contacts; write and send emails and LinkedIn/X messages; publish posts, \
articles and replies; take part in communities; apply to directories, programs, awards and \
podcasts; book meetings onto a calendar; run small ad budgets; fill in forms; and use the \
company's connected apps (CRM, email, analytics, docs) or a browser. They ask the person \
they report to before anything public, outgoing or paid. They cannot write or ship product \
code without review, sign contracts, make hiring or legal decisions, move money beyond an approved \
budget, or do physical work.

For software products they can also do product and engineering work, once the company connects \
its tools: a Product AI employee watches product analytics, a read-only database, the market and \
competitors; explains sudden metric changes; and writes and prioritises PRDs. An Engineering AI \
employee reads the code on GitHub, implements small, well-scoped changes (often from approved \
PRDs or open issues) as pull requests, and asks an engineer to review and merge.

AI employee roles you can staff, by team (use the role key; personalise each one's name, focus, \
objective and goals for this company):
{catalog}

Choose functions and goals that fit THIS company at its CURRENT size and stage:
- First size the company and set profile.size. Weigh headcount and revenue (real operations) \
above funding alone:
{sizes}
  profile.size_reason says why in a few words ("~30 people, $12M Series A, 6 open roles").
- Then pick functions, most important first, never more than the size allows, and fewer when an \
AI employee has nothing valuable to do there yet. Tiny companies: almost all growth (sales, \
marketing, product; fundraising if raising). Small: add People & Hiring when several roles are \
open, Finance once there is recurring revenue, Customer Success once there are customers to keep. \
Mid and large: Finance, People & Hiring, IT & Security and Legal & Compliance usually earn a \
place (IT & Security early if they sell to enterprises that send security questionnaires). \
For a software company, include Product (and Engineering, if they build in-house) unless growth \
work clearly matters far more right now; their goals look like "Weekly metrics and competitor \
brief", "Explain the drop in activation", "3 prioritised PRDs for the top user problems", "Ship \
3 small fixes from open issues as PRs". Back-office goals look like "Chase the 14 overdue \
invoices", "Monthly burn and runway report", "Answer the 3 open security questionnaires", \
"Summarise and flag risks in the 10 contracts up for renewal", "Shortlist 20 candidates for the \
AE role".
- Staff each function with 1 to {max_agents} AI employees (usually 1 or 2), each one role from the \
catalog (or "custom" for something it doesn't cover), within the size's limit. Name each for its \
job ("Outbound Agent", "SEO Agent"). Start from the template you're given for this type of company: \
keep what fits, drop what doesn't, and add roles it misses.
- 1 to {max_per_dept} goals per function (2 is typical), within the size's goal limit. Fewer, \
sharper goals beat many. No two goals should overlap.
- later lists up to {max_later} functions you left out that will matter as the company grows, \
each with when, in a few words ("once you have recurring revenue", "when enterprise customers \
ask for SOC 2"). Leave out functions that will never matter here.
- Goals are ongoing, like the goals of a person on that team: the name says what they keep \
working on, never a number or a deadline ("Book demos with logistics ops leaders", not "Book \
15 demos"). What to reach and by when is the target: target_value for target_period, usually a \
week to start (goals start with a one-week budget), or a month when a week is too short to see \
results. The AI employee will propose bigger or different targets as it learns.
- Make every goal specific to this company: name their real customer, product, market and \
channels. done_when says what counts as one result, and must be checkable ("Meeting held on \
calendar with a Head of Ops at a 50-500 person logistics company"); primary_metric is short \
("meetings held"), and the target is realistic for the period.
- first_week says what the company will concretely have after the first week of work, in one \
sentence a busy founder would be glad to read, e.g. "A list of 40 procurement leads at EPC \
contractors with verified emails, and a personal first email drafted for each, waiting for your \
OK". It must be realistic for one week. Goals start with a one-week budget so people can see \
this before committing more.
- objective (per AI employee) is its objective, like an employee's OKR objective: one \
short sentence on what it is there to achieve for this company, e.g. "Fill the pipeline with EPC \
procurement leads ready to pilot Oton".
- key_results (per goal) are 2 or 3 short, measurable outcomes for the first period that show \
the goal is on track, e.g. "8 discovery calls held", "150 qualified procurement contacts", "Reply \
rate above 8%". The first should be the target.
- start_here is true for the 2 or 3 goals in total (across all functions) that would show value \
fastest and matter most right now, false for the rest.
- cycle_hours is how often it works on the goal: usually 12 or 24; 6 only when it must answer \
replies quickly.
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
description over older web sources.
- In anything written for people (why, first_week, objectives, goal names and descriptions), \
don't call it an AI employee, agent or lead: talk about the goal and say Oton does the work."""

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

Starting template for this type of company:
<template>
{template}
</template>

{task}"""

FULL_TASK = "Design their AI team: the profile, the functions, and the first goals for each."
GOALS_TASK = ("Suggest the goals worth setting up now, grouped by function (the profile is already known: "
              "repeat it as it is). The company already has these goals: {goals}. Don't repeat them or close "
              "variations; suggest what's missing. Use the functions it has ({existing}) and add a function only "
              "when a goal clearly needs it.")
ADD_TASK = ("The team already has: {existing}. The founders asked to add these functions now: {include}. "
            "Plan ONLY these functions, with their first goals; return an empty later list.")


def sizes_text() -> str:
    return "\n".join(f"  {k} = {v['label']}: up to {v['departments']} functions, {v['agents']} AI employees and "
                     f"{v['goals']} goals." for k, v in SIZES.items())


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
            "target_period": {"type": "string", "enum": ["week", "month", "quarter"]},
            "category": {"type": "string", "enum": list(CATEGORY_KEYS)},
            "use_case": {"type": "string"},
            "cycle_hours": {"type": "number"},
            "duration_days": {"type": "number"},
            "paid_spend_usd": {"type": "number"},
            "steps": {"type": "array", "items": step_schema()},
            "channels": string_list,
            "why": {"type": "string"},
            "first_week": {"type": "string"},
            "start_here": {"type": "boolean"},
            "key_results": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["target_period", "first_week", "start_here", "key_results", "name", "goal_description", "done_when", "primary_metric", "target_value", "category",
                     "use_case", "cycle_hours", "duration_days", "paid_spend_usd", "steps", "channels", "why"],
        "additionalProperties": False,
    }
    agent = {
        "type": "object",
        "properties": {
            "role": {"type": "string", "enum": list(packs.ROLES) + ["custom"]},
            "name": {"type": "string", "description": "e.g. Outbound Agent"},
            "title": {"type": "string", "description": "Its focus, 2-4 words"},
            "objective": {"type": "string"},
            "goals": {"type": "array", "items": goal},
        },
        "required": ["role", "name", "title", "objective", "goals"],
        "additionalProperties": False,
    }
    department = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": kinds},
            "name": {"type": "string"},
            "why": {"type": "string"},
            "agents": {"type": "array", "items": agent},
        },
        "required": ["kind", "name", "why", "agents"],
        "additionalProperties": False,
    }
    later = {
        "type": "object",
        "properties": {"kind": {"type": "string", "enum": kinds}, "name": {"type": "string"},
                       "when": {"type": "string", "description": "When it will be worth adding, a few words"}},
        "required": ["kind", "name", "when"],
        "additionalProperties": False,
    }
    profile_fields = ["summary", "offering", "customers", "business_model", "stage", "funding", "revenue", "team",
                      "traction", "size_reason"]
    profile = {
        "type": "object",
        "properties": {**{f: {"type": "string"} for f in profile_fields},
                       "size": {"type": "string", "enum": list(SIZES)},
                       "company_type": {"type": "string", "enum": list(packs.PACKS)},
                       "current_focus": string_list, "challenges": string_list},
        "required": [*profile_fields, "size", "company_type", "current_focus", "challenges"],
        "additionalProperties": False,
    }
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {"profile": profile, "departments": {"type": "array", "items": department},
                           "later": {"type": "array", "items": later}},
            "required": ["profile", "departments", "later"],
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


def include_names(include: list[str]) -> list[str]:
    return [PRESET_NAMES.get(k, k) for k in include]


CLASSIFY_SYSTEM = """You decide which kind of company this is, so Oton can start its AI team \
from the right template. Base it on what the company actually does and how it makes money, from \
the research and website, not on single words. Also judge its size from headcount and revenue \
(funding alone counts for less). Give the reason in one short sentence with the evidence."""


def classify_schema() -> dict:
    return {"type": "json_schema", "schema": {
        "type": "object",
        "properties": {"company_type": {"type": "string", "enum": list(packs.PACKS)},
                       "size": {"type": "string", "enum": list(SIZES)},
                       "reason": {"type": "string"}},
        "required": ["company_type", "size", "reason"],
        "additionalProperties": False,
    }}


async def classify_company(claude: MeteredClaude, setup_id: str | None, name: str, website: str, description: str,
                           research: str, site_text: str, step: str = "plan") -> tuple[str, str, str]:
    """(company type, size, reason), decided by Claude (the fast model; a fraction of a cent).
    Falls back to the general pack if it can't decide."""
    types = "\n".join(f"- {p.key}: {p.label}. {p.description}" for p in packs.PACKS.values())
    sizes = "\n".join(f"- {k}: {v['label']}" for k, v in SIZES.items())
    content = (f"Company: {name}\nWebsite: {website or '(none)'}\nWhat the founders say it does: {description or '(not given)'}\n\n"
               f"Research:\n{(research or '(none)')[:8000]}\n\nWebsite text:\n{(site_text or '(none)')[:4000]}\n\n"
               f"Types:\n{types}\n\nSizes:\n{sizes}")
    try:
        result = await claude.create(campaign_id=None, run_id=None, purpose="setup company type", role="checker",
                                     system=CLASSIFY_SYSTEM, messages=[{"role": "user", "content": content}],
                                     max_tokens=1000, output_format=classify_schema())
        data = json.loads(_texts(result.content))
    except Exception as e:  # noqa: BLE001 - planning can still go ahead from the general template
        log.warning("company type: %s", e)
        return "general", "", ""
    if setup_id:
        await _step(setup_id, step, "running", "", result.cost)
    kind = data.get("company_type") if data.get("company_type") in packs.PACKS else "general"
    size = data.get("size") if data.get("size") in SIZES else ""
    return kind, size, (data.get("reason") or "").strip()[:300]


PROFILE_SYSTEM = """You write a short, factual profile of a company from research and its website, and \
decide which kind of company it is and how big. Base the type on what it actually does and how it \
makes money, not on single words. Judge size from headcount and revenue (funding alone counts for \
less). State facts concisely, "Unknown" where not known; trust the founders' description over \
older web sources. current_focus: what they're pushing on now (2-4 items); challenges: what's in \
their way (2-4 items)."""


def profile_schema() -> dict:
    return {"type": "json_schema", "schema": plan_schema()["schema"]["properties"]["profile"]}


async def profile_company(claude: MeteredClaude, setup_id: str, name: str, website: str, description: str,
                          research: str, site_text: str) -> dict:
    """What the company sells, to whom, its stage, type and size (no goals: those come from findings)."""
    types = "\n".join(f"- {p.key}: {p.label}. {p.description}" for p in packs.PACKS.values())
    content = (f"Company: {name}\nWebsite: {website or '(none)'}\nWhat the founders say it does: {description or '(not given)'}\n\n"
               f"Research:\n{(research or '(none)')[:12000]}\n\nWebsite text:\n{(site_text or '(none)')[:8000]}\n\n"
               f"Types:\n{types}\n\nSizes:\n{sizes_text()}")
    result = await claude.create(campaign_id=None, run_id=None, purpose="setup profile", role="worker",
                                 system=PROFILE_SYSTEM, messages=[{"role": "user", "content": content}],
                                 max_tokens=4000, output_format=profile_schema())
    try:
        data = json.loads(_texts(result.content) or "{}")
    except json.JSONDecodeError:
        data = {}
    kind = data.get("company_type") if data.get("company_type") in packs.PACKS else "general"
    profile = {**data, "company_type": kind, "pack_label": packs.PACKS[kind].label,
               "size": data.get("size") if data.get("size") in SIZES else DEFAULT_SIZE}
    await _step(setup_id, "profile", "done", f"{packs.PACKS[kind].label} · {SIZES[profile['size']]['label']}", result.cost)
    return profile


async def plan_team(claude: MeteredClaude, setup_id: str, name: str, website: str, description: str,
                    research: str, site_text: str, include: list[str] | None = None,
                    existing: list[str] | None = None, template: str = "", task: str = "") -> dict:
    task = task or (ADD_TASK.format(existing=", ".join(existing or []) or "nothing yet",
                                    include=", ".join(include_names(include))) if include else FULL_TASK)
    result = await claude.create(
        campaign_id=None, run_id=None, purpose="setup plan", role="planner",
        system=PLAN_SYSTEM.format(sizes=sizes_text(), max_per_dept=MAX_GOALS_PER_DEPARTMENT, max_later=MAX_LATER,
                                  max_agents=MAX_AGENTS_PER_DEPARTMENT, step_guidance=STEP_GUIDANCE,
                                  catalog=packs.catalog_text())
               + "\n\nFor goals that reach people one to one:\n" + OUTREACH_KNOWHOW,
        messages=[{"role": "user", "content": PLAN_TASK.format(
            name=name, website=website or "(none given)", description=description or "(not given)",
            research=research or "(no research available)", site=(site_text or "(not available)")[:12000],
            task=task, template=template or packs.pack_brief("general", []))}],
        max_tokens=16000, output_format=plan_schema(),
    )
    if result.stop_reason == "refusal":
        raise RuntimeError("Claude declined to plan this company's team.")
    raw = _texts(result.content)
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError("The team plan came back incomplete. Try again.") from e
    plan = tidy_plan(plan, include=include)
    n_goals = sum(len(d["goals"]) for d in plan["departments"])
    await _step(setup_id, "plan", "done", f"{len(plan['departments'])} functions, {n_goals} goals", result.cost)
    return plan


def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, v))


def _tidy_goal(g: dict) -> dict | None:
    title = (g.get("name") or g.get("goal_description") or "").strip()
    if not title or not (g.get("goal_description") or "").strip():
        return None
    target = g.get("target_value")
    target = float(target) if isinstance(target, (int, float)) and target > 0 else None
    cycle = _clamp(g.get("cycle_hours"), 1, 48, 6)
    return {
        "name": title[:200],
        "goal_description": g["goal_description"].strip(),
        "done_when": (g.get("done_when") or "").strip(),
        "primary_metric": (g.get("primary_metric") or "results").strip()[:120],
        "target_value": target,
        "target_period": g.get("target_period") if g.get("target_period") in ("week", "month", "quarter") else "week",
        "category": g.get("category") if g.get("category") in CATEGORY_KEYS else "",
        "use_case": (g.get("use_case") or "").strip()[:120],
        "cycle_hours": float(min(CYCLE_CHOICES, key=lambda c: abs(c - cycle))),
        "duration_days": round(_clamp(g.get("duration_days"), 7, 90, 30)),
        "paid_spend_usd": round(_clamp(g.get("paid_spend_usd"), 0, 5000, 0), 2),
        "steps": tidy_steps(g.get("steps")),
        "channels": [str(c)[:60] for c in (g.get("channels") or [])][:8],
        "why": (g.get("why") or "").strip(),
        "first_week": (g.get("first_week") or "").strip(),
        "key_results": [str(k).strip()[:160] for k in (g.get("key_results") or []) if str(k).strip()][:3],
        "start_here": bool(g.get("start_here")),
    }


def tidy_plan(plan: dict, include: list[str] | None = None) -> dict:
    """Enforce the limits the prompt asks for: a team that fits the company's size, a few AI
    employees per function, few goals, sane numbers. With include, keep only the functions people
    asked to add. Each function comes back with its AI employees (each with its goals), plus the
    function's goals listed together for display."""
    profile = dict(plan.get("profile") or {})
    profile["size"] = profile.get("size") if profile.get("size") in SIZES else DEFAULT_SIZE
    if profile.get("company_type") not in packs.PACKS:
        profile.pop("company_type", None)
    limits = SIZES[profile["size"]]
    max_departments, max_agents, max_goals = limits["departments"], limits["agents"], limits["goals"]
    wanted = {x.lower() for x in (include or [])} | {x.lower() for x in include_names(include or [])}
    if include:
        max_departments, max_goals = len(include), MAX_GOALS_PER_DEPARTMENT * len(include)
        max_agents = MAX_AGENTS_PER_DEPARTMENT * len(include)
    departments, seen_names, seen_goals, total_goals, total_agents = [], set(), set(), 0, 0
    for d in plan.get("departments") or []:
        kind = d.get("kind") if d.get("kind") in PRESET_NAMES else ""
        name = (d.get("name") or PRESET_NAMES.get(kind, "")).strip()[:120] or "General"
        if name.lower() in seen_names:
            continue
        if include and kind not in wanted and name.lower() not in wanted:
            continue
        # Older plans (and simple ones) have one AI employee per function, with the goals on the function.
        specs = d.get("agents") if isinstance(d.get("agents"), list) else [
            {"role": "", "name": "", "title": d.get("agent_title") or "", "objective": d.get("objective") or "",
             "goals": d.get("goals") or []}]
        agents, dept_goals = [], 0
        for a in specs:
            if len(agents) >= MAX_AGENTS_PER_DEPARTMENT or total_agents >= max_agents:
                break
            goals = []
            for g in a.get("goals") or []:
                if dept_goals >= MAX_GOALS_PER_DEPARTMENT or total_goals >= max_goals:
                    break
                tidy = _tidy_goal(g)
                if not tidy or tidy["name"].lower() in seen_goals:
                    continue
                goals.append(tidy)
                seen_goals.add(tidy["name"].lower())
                dept_goals += 1
                total_goals += 1
            if not goals:
                continue
            role = a.get("role") if a.get("role") in packs.ROLES else ""
            agents.append({"role": role, "name": (a.get("name") or "").strip()[:120],
                           "title": (a.get("title") or "").strip()[:160] or (packs.ROLES[role].title if role else ""),
                           "objective": (a.get("objective") or "").strip()[:400], "goals": goals})
            total_agents += 1
        if not agents:
            continue
        seen_names.add(name.lower())
        departments.append({"kind": kind, "name": name, "why": (d.get("why") or "").strip(), "agents": agents,
                            # for display (setup page) and older readers
                            "agent_title": agents[0]["title"], "objective": agents[0]["objective"],
                            "goals": [g for a in agents for g in a["goals"]]})
        if len(departments) >= max_departments:
            break
    # Two or three goals to start with: the planner's picks, else the first goal of the top functions.
    goals = [g for d in departments for g in d["goals"]]
    picked = [g for g in goals if g["start_here"]][:3]
    if not picked:
        picked = [d["goals"][0] for d in departments[:2]]
    for g in goals:
        g["start_here"] = any(g is p for p in picked)
    later, taken = [], {n.lower() for n in seen_names} | {d["kind"] for d in departments if d["kind"]}
    for x in plan.get("later") or []:
        kind = x.get("kind") if x.get("kind") in PRESET_NAMES else ""
        name = (x.get("name") or PRESET_NAMES.get(kind, "")).strip()[:120]
        if not name or name.lower() in taken or (kind and kind in taken) or include:
            continue
        taken.add(name.lower())
        later.append({"kind": kind, "name": name, "when": (x.get("when") or "").strip()[:160]})
        if len(later) >= MAX_LATER:
            break
    return {"profile": profile, "departments": departments, "later": later}


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
    lines.append("(From Oton's setup research. Correct anything that's wrong.)")
    return "\n".join(lines)


async def create_team(setup_id: str | None, org_id: str, requested_by: str | None, plan: dict) -> dict:
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
        by_kind: dict[str, Agent] = {}
        for d in plan["departments"]:
            dept = next((x for x in existing if (d["kind"] and x.kind == d["kind"]) or x.name.lower() == d["name"].lower()), None)
            if dept is None:
                dept = await add_department(s, org_id, d["name"], d["kind"], members=admins)
                existing.append(dept)
                created["departments"].append(dept.id)
            staff = list((await s.execute(select(Agent).where(Agent.department_id == dept.id)
                                          .order_by(Agent.created_at))).scalars())
            fresh = dept.id in created["departments"]
            specs = d.get("agents") or [{"role": "", "name": "", "title": d.get("agent_title", ""),
                                          "objective": d.get("objective", ""), "goals": d["goals"]}]
            for i, spec in enumerate(specs):
                agent = await _staff(s, org_id, dept, staff, i, spec, fresh)
                created["agents"].append(agent.id)
                by_kind.setdefault(d["kind"] or d["name"].lower(), agent)
                if spec.get("role"):
                    by_kind.setdefault("role:" + spec["role"], agent)
                await _add_goals(s, org_id, requested_by, agent, spec["goals"], goal_names, context, created)
        await s.flush()
    # Product hands its PRDs to Engineering, after the person it reports to approves them.
    async with session_scope() as s:
        pm = by_kind.get("role:pm") or by_kind.get("product")
        eng = by_kind.get("role:engineer") or by_kind.get("engineering")
        if pm and eng:
            product = await s.get(Agent, pm.id)
            if not product.handoff_to_agent_id:
                product.handoff_to_agent_id = eng.id
                product.handoff_review = True
    if setup_id:
        await _step(setup_id, "create", "done",
                    f"{len(created['goals'])} goal{'s' if len(created['goals']) != 1 else ''} ready to review")
    return created


async def _staff(s, org_id: str, dept: Department, staff: list[Agent], i: int, spec: dict, fresh: bool) -> Agent:
    """The AI employee for one spec: the department's existing one (by role, name or position) or a
    new hire. A department set up just now gets the plan's names; existing ones keep theirs."""
    agent = next((a for a in staff if spec.get("role") and a.role_key == spec["role"]), None) \
        or next((a for a in staff if spec.get("name") and a.name.lower() == spec["name"].lower()), None)
    if agent is None and i < len(staff) and not staff[i].role_key and (i == 0 or fresh):
        agent = staff[i]
    if agent is None:
        agent = Agent(org_id=org_id, department_id=dept.id, name=spec.get("name") or f"{dept.name} Agent {len(staff) + 1}")
        s.add(agent)
        await s.flush()
        staff.append(agent)
    elif fresh and spec.get("name"):
        agent.name = spec["name"]
    if spec.get("role") and not agent.role_key:
        agent.role_key = spec["role"]
    if spec.get("title") and not agent.title:
        agent.title = spec["title"]
    if spec.get("objective") and not agent.objective:
        agent.objective = spec["objective"]
    return agent


async def _add_goals(s, org_id: str, requested_by: str | None, agent: Agent, goals: list[dict], goal_names: set[str],
                     context: str, created: dict) -> None:
    for g in goals:
        if g["name"].lower() in goal_names:
            continue
        goal_names.add(g["name"].lower())
        c = Campaign(
            org_id=org_id, owner_id=requested_by, agent_id=agent.id, name=g["name"],
            goal_type=CATEGORY_KEYS.get(g["category"], "custom"), goal_description=g["goal_description"],
            primary_metric=g["primary_metric"], target_value=g["target_value"], done_when=g["done_when"],
            category=g["category"], use_case=g["use_case"], context=context, channels=g["channels"],
            budget_total=Decimal(str(g["budget_usd"])), cycle_hours=g["cycle_hours"],
            origin="setup", suggested_reason=g["why"], first_deliverable=g.get("first_week", ""),
            key_results=g.get("key_results") or default_key_results(g["primary_metric"], g["target_value"]),
            budget_basis={**g["budget_basis"], "chosen_usd": g["budget_usd"]},
            playbook={"steps": g["steps"], "source": "setup"} if g["steps"] else None,
        )
        targets.plan_first(c, g["target_value"], g.get("target_period", "week"), set_by="setup")
        s.add(c)
        await s.flush()
        await activity.log(s, c.id, "system", "Suggested by setup research",
                           details={"why": g["why"]} if g["why"] else None, status="info")
        created["goals"].append(c.id)


async def _earlier_research(s, org: Organization, setup_id: str) -> str:
    """What earlier setups learned (for runs that don't research again)."""
    research = (await s.execute(
        select(OrgSetup.research).where(OrgSetup.org_id == org.id, OrgSetup.id != setup_id,
                                        OrgSetup.research.is_not(None), OrgSetup.research != "")
        .order_by(OrgSetup.created_at.desc()).limit(1))).scalar_one_or_none() or ""
    if not research and org.profile:
        research = json.dumps({k: v for k, v in org.profile.items() if k not in ("sources", "later", "opportunities")})
    return research


async def _read_website(setup_id: str, website: str) -> str:
    if not website:
        await _step(setup_id, "website", "skipped", "No website given")
        return ""
    await _step(setup_id, "website", "running")
    reading = await read_site(website)
    if reading.pages:
        await _step(setup_id, "website", "done",
                    f"Read {len(reading.pages)} page{'s' if len(reading.pages) != 1 else ''} on {reading.domain}")
    else:
        await _step(setup_id, "website", "failed", reading.error or "Couldn't read the website")
    return reading.as_text()


async def run_org_setup(setup_id: str, claude: MeteredClaude | None = None) -> None:
    claude = claude or MeteredClaude()
    async with session_scope() as s:
        setup = await s.get(OrgSetup, setup_id)
        org = await s.get(Organization, setup.org_id)
        org_id, requested_by = org.id, setup.requested_by
        name, website, description = org.name, org.website, org.description
        mode = mode_of(setup.plan)
        setup.steps = setup.steps or initial_steps(mode)
        setup.error = None
        include = list((setup.plan or {}).get("include") or [])
        org_profile = dict(org.profile or {})
        earlier_research = await _earlier_research(s, org, setup_id) if mode != "start" else ""
        existing = [n for (n,) in (await s.execute(
            select(Department.name).where(Department.org_id == org_id).order_by(Department.created_at))).all()]
        goal_names = [n for (n,) in (await s.execute(select(Campaign.name).where(Campaign.org_id == org_id)
                                                     .order_by(Campaign.created_at))).all()]
    current = STEPS[mode][0][0]
    created: dict = {"departments": [], "agents": [], "goals": []}
    try:
        if mode == "start":
            created = await _start(claude, setup_id, org_id, requested_by, name, website, description)
        elif mode == "more":
            current = "website"
            site_text = await _read_website(setup_id, website)
            current = "scan"
            await _step(setup_id, "scan", "running")
            found = await opportunities.scan(claude, org_id, requested_by, earlier_research, site_text, more=True)
            n = found.get("new", len(found["findings"]))
            await _step(setup_id, "scan", "done",
                        (f"Ran {found['ran']} more checks · " if found.get("ran") else "")
                        + (f"{n} new opportunit{'ies' if n != 1 else 'y'}" if n else "nothing new stood out this time"),
                        found["cost"])
            created["goals"] = found.get("goals") or []
        else:  # goals / include: plan goals per function from what we know, then set them up
            current = "plan"
            await _step(setup_id, "plan", "running")
            known_type = org_profile.get("company_type")
            if known_type in packs.PACKS:
                pack_key, size_guess, reason = known_type, org_profile.get("size", ""), ""
            else:
                pack_key, size_guess, reason = await classify_company(claude, setup_id, name, website, description,
                                                                      earlier_research, "")
            task = GOALS_TASK.format(goals="; ".join(goal_names[:60]) or "none yet",
                                     existing=", ".join(existing) or "none yet") if mode == "goals" else ""
            plan = await plan_team(claude, setup_id, name, website, description, earlier_research, "",
                                   include=include or None, existing=existing,
                                   template=packs.pack_brief(pack_key, reason, size_guess), task=task)
            if not plan["departments"]:
                raise RuntimeError("Couldn't work out any goals to suggest. Add a few words about what you do and try again.")
            async with session_scope() as s:
                per, basis, n = await estimate.session_cost(s, org_id)
            for d in plan["departments"]:  # budget = sessions x cost per session + paid spend
                for g in d["goals"]:
                    g["budget_basis"] = estimate.starter(per, g["cycle_hours"], g["duration_days"], g["paid_spend_usd"], basis, n)
                    g["budget_usd"] = g["budget_basis"]["suggested_usd"]
            async with session_scope() as s:
                (await s.get(OrgSetup, setup_id)).plan = {**plan, "include": include, "mode": mode}
                org = await s.get(Organization, org_id)
                # The profile stays; what was just added is no longer "later".
                added = {d["kind"] for d in plan["departments"] if d["kind"]} | {d["name"].lower() for d in plan["departments"]}
                added |= set(include) | {x.lower() for x in include_names(include)}
                later = [x for x in (org.profile or {}).get("later") or [] if x["kind"] not in added and x["name"].lower() not in added]
                if mode == "goals":
                    later += [x for x in plan.get("later") or [] if x["kind"] not in {y["kind"] for y in later}]
                org.profile = {**(org.profile or {}), "later": later}
                if not (org.profile or {}).get("company_type"):
                    org.profile = {**org.profile, "company_type": pack_key, "pack_label": packs.PACKS[pack_key].label}
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
        async with session_scope() as s:  # the step that was running is the one that failed
            running = next((x["key"] for x in (await s.get(OrgSetup, setup_id)).steps or [] if x["status"] == "running"), None)
        await _step(setup_id, running or current, "failed")
        async with session_scope() as s:
            setup = await s.get(OrgSetup, setup_id)
            setup.status = "failed"
            setup.error = str(e)[:1000] or type(e).__name__
            setup.locked_by = None


async def _start(claude: MeteredClaude, setup_id: str, org_id: str, requested_by: str | None, name: str,
                 website: str, description: str) -> dict:
    """Onboarding: read the site, research, profile, then find what the company is missing out on.
    Goals come from the findings (each finding has the goal that fixes it); "Suggest more goals" on
    the Team page plans goals per function later, from this research."""
    site_text = await _read_website(setup_id, website)

    # Research. Setup can still go on from the website and description if this fails.
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

    await _step(setup_id, "profile", "running")
    profile = await profile_company(claude, setup_id, name, website, description, research, site_text)
    async with session_scope() as s:
        org = await s.get(Organization, org_id)
        keep = {k: v for k, v in (org.profile or {}).items() if k in ("opportunities", "later")}
        org.profile = {**keep, **profile, "sources": sources, "researched_at": utcnow().isoformat()}
        (await s.get(OrgSetup, setup_id)).plan = {"mode": "start", "profile": profile}

    await _step(setup_id, "scan", "running")
    found = await opportunities.scan(claude, org_id, requested_by, research, site_text)
    n = len(found["findings"])
    ran = f"Ran {found['ran']} checks plus measurements · " if found.get("ran") else ""
    await _step(setup_id, "scan", "done",
                ran + (f"{n} thing{'s' if n != 1 else ''} you could do better" if n else "nothing big stood out"),
                found["cost"])
    return {"departments": [], "agents": [], "goals": await _goals_added(org_id)}


async def _goals_added(org_id: str) -> list[str]:
    async with session_scope() as s:
        org = await s.get(Organization, org_id)
        return list(((org.profile or {}).get("opportunities") or {}).get("goals_added") or [])


async def build_starter_team(org_id: str, requested_by: str | None) -> dict:
    """Without a personalised plan (no Claude key, or planning failed): a starter team from the pack
    for the type of company Claude decided on during setup, else the general pack. Templates, not
    personalised; people edit them, or research the company again to personalise."""
    async with session_scope() as s:
        org = await s.get(Organization, org_id)
        known = (org.profile or {}).get("company_type")
        pack_key = known if known in packs.PACKS else "general"
        per, basis, n = await estimate.session_cost(s, org_id)
    plan = tidy_plan(packs.starter_plan(pack_key, "tiny"))
    for d in plan["departments"]:
        for g in d["goals"]:
            g["budget_basis"] = estimate.starter(per, g["cycle_hours"], g["duration_days"], g["paid_spend_usd"], basis, n)
            g["budget_usd"] = g["budget_basis"]["suggested_usd"]
            g["why"] = g["why"] or f"A usual starting point for a {packs.PACKS[pack_key].label.lower()}."
    created = await create_team(None, org_id, requested_by, plan)
    async with session_scope() as s:
        org = await s.get(Organization, org_id)
        org.profile = {**(org.profile or {}), "company_type": pack_key, "pack_label": packs.PACKS[pack_key].label,
                       "later": plan["later"], "summary": (org.profile or {}).get("summary") or org.description}
    return {"company_type": pack_key, **created}


async def org_needs_basic_team(org_id: str) -> bool:
    async with session_scope() as s:
        n = (await s.execute(select(func.count()).select_from(Department).where(Department.org_id == org_id))).scalar_one()
        return n == 0
