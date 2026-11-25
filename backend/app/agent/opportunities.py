"""What the company is missing: a scan of public signals, each finding tied to a goal it can turn on.

Runs at the end of setup. Claude looks at the company's own website and what's public about it
(blog and social posting, reviews, search presence, careers page, press, competitors), finds the
biggest concrete gaps, and links each one to one of the draft goals setup just made, or proposes a
new goal for the right team. Evidence and sources are required; money estimates are ranges with
the assumption behind them, or left out. Company-level only: it never judges individual people.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from sqlalchemy import select

from app.agent.llm import MeteredClaude
from app.catalog import TOOLS
from app.db import session_scope
from app.models import Agent, Campaign, Department, Organization, utcnow
from app.org import DEPARTMENT_PRESETS
from app.services import estimate


log = logging.getLogger(__name__)

MAX_FINDINGS = 8
MAX_WEB = 8
MAX_CONTINUATIONS = 4

# What can be checked from public information, by team. Guidance for Claude, not rules: it picks
# what applies to this company and skips the rest.
CHECKS: list[tuple[str, str]] = [
    ("marketing", "How often they post on LinkedIn, X and their blog, and the traction posts get (dates of the "
                  "latest posts, likes and comments visible in search results); newsletter signup on the site; "
                  "case studies and customer stories; content competitors have that they don't"),
    ("marketing", "Search presence: whether they show up for the obvious searches for what they sell, page titles "
                  "and descriptions, missing comparison or use-case pages, competitors outranking them"),
    ("sales", "How easy it is to buy or book a demo from the site, pricing page clarity, comparison pages against "
              "named competitors, marketplaces or directories where buyers look and they're not listed"),
    ("support", "Public reviews (G2, Capterra, Trustpilot, Google, app stores): rating, count against competitors, "
                "recent unanswered negative reviews, recurring complaints; help centre and docs"),
    ("success", "Whether customers are shown off (logos, testimonials, reviews) and asked for reviews or referrals"),
    ("product", "Release notes or changelog cadence, features competitors advertise that they don't, themes in "
                "reviews that point to product gaps"),
    ("hiring", "Open roles and how long they've been posted, careers page quality, how job ads read, functions a "
               "company of this size and stage usually has but they're hiring for or missing. Company-level only"),
    ("partnerships", "Integrations and partner listings competitors have that they don't"),
    ("pr", "When they were last in the press, a press page, launches or milestones nobody announced"),
    ("community", "Communities, events or groups their customers gather in where they're absent"),
    ("finance", "Public pricing compared with competitors (only if both are public)"),
    ("store", "Product reviews, ratings and photos, shipping and returns clarity, marketplaces they're not on"),
    ("engineering", "Visible website problems: broken pages, outdated content (old copyright year, stale dates), "
                    "missing basics like a status page for a software product"),
]

# Deeper checks once a tool is connected: what the AI employees could then measure for real.
DEEPER: list[tuple[str, str]] = [
    ("hubspot", "Leads and deals nobody followed up, and how long new inbound leads wait for a reply"),
    ("salesforce", "Stalled deals and leads nobody followed up"),
    ("gmail", "Inbound emails from prospects and customers left unanswered"),
    ("linkedin", "Exact posting frequency and engagement on your company page"),
    ("searchconsole", "Searches you almost rank for (page 2) that a few posts could win"),
    ("stripe", "Failed payments that were never recovered, and customers who quietly churned"),
    ("quickbooks", "Overdue invoices nobody chased"),
    ("zendesk", "Slow first replies and tickets waiting too long"),
    ("intercom", "Slow first replies and conversations left open"),
    ("github", "Bugs and pull requests that have been waiting for weeks"),
    ("shopify", "Abandoned checkouts and customers who never bought again"),
]

SYSTEM = """You are a sharp growth and operations analyst. A company just set up its AI team on \
Autopilot. Your job: show them, concretely, what they're missing out on today, so they can turn on \
the AI employees that fix it.

Rules:
- Evidence first. Every finding must say exactly what you saw ("last blog post: March 2025", \
"4.1 stars from 12 G2 reviews; their two main competitors have 180 and 240"). Use web_search and \
web_fetch to check; don't guess. If you couldn't verify something, leave it out.
- Public, company-level information only. Never judge, rank or name individual employees. For \
hiring, talk about roles, functions and how jobs are posted, never about the people already there.
- Money: only give an estimate when you can state a reasonable assumption ("if a weekly post brings \
2-3 inbound leads a month at your price, that's roughly $20k-60k a year in pipeline"). Use ranges. \
Otherwise describe the impact without a number. Never present a guess as a fact.
- Be specific to this company, its stage and its competitors. No generic advice.
- Tone: direct and helpful, not alarming. They should feel "we should fix that", not "we're doomed".
- Pick the biggest {max} gaps at most, most valuable first. Fewer, stronger findings beat many weak ones."""

TASK = """Company: {name}
Website: {website}
What they do: {description}

What setup research found:
{research}

From their website:
{site}

Things you can check from public information (pick what applies; skip what doesn't):
{checks}

Investigate with web_search and web_fetch, then write your notes: for each gap, what you saw, \
where (URLs), why it matters, and any estimate with its assumption."""

STRUCTURE_SYSTEM = """You turn an analyst's notes into findings for a company's dashboard, and tie \
each finding to the goal an AI employee would work on to fix it. Keep only findings the notes back \
with evidence. Prefer linking to one of the company's existing goals (by its id) when it would fix \
the gap; otherwise propose a new goal for the right team. Write plainly and briefly."""

STRUCTURE_TASK = """The analyst's notes:
{notes}

Sources the analyst saw:
{sources}

The company's teams: {teams}

Goals already set up (id: name · team):
{goals}

Tools that could be connected later, for deeper checks (key: what it could show):
{deeper}

Return at most {max} findings, most valuable first, and up to 4 deeper checks that fit this company."""


def findings_schema(goal_schema: dict) -> dict:
    kinds = [k for k, _ in DEPARTMENT_PRESETS] + ["custom"]
    finding = {
        "type": "object",
        "properties": {
            "team_kind": {"type": "string", "enum": kinds},
            "title": {"type": "string", "description": "The gap in a few words, e.g. 'Rare, low-traction LinkedIn posts'"},
            "evidence": {"type": "string", "description": "Exactly what was seen, with numbers and dates"},
            "impact": {"type": "string", "description": "Why it matters for this company, one or two sentences"},
            "estimate": {"type": "string", "description": "A money or volume range, e.g. '$20k-60k a year in pipeline', or ''"},
            "assumption": {"type": "string", "description": "The assumption behind the estimate, or ''"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "source_urls": {"type": "array", "items": {"type": "string"}},
            "goal_id": {"type": "string", "description": "Id of an existing goal that fixes this, or ''"},
            "new_goal": {"anyOf": [goal_schema, {"type": "null"}]},
        },
        "required": ["team_kind", "title", "evidence", "impact", "estimate", "assumption", "confidence",
                     "source_urls", "goal_id", "new_goal"],
        "additionalProperties": False,
    }
    deeper = {
        "type": "object",
        "properties": {"tool": {"type": "string", "enum": [k for k, _ in DEEPER]}, "check": {"type": "string"}},
        "required": ["tool", "check"],
        "additionalProperties": False,
    }
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {"findings": {"type": "array", "items": finding}, "deeper": {"type": "array", "items": deeper}},
            "required": ["findings", "deeper"],
            "additionalProperties": False,
        },
    }


def _texts(content: list[dict]) -> str:
    return "\n".join(b.get("text", "") for b in content if b.get("type") == "text").strip()


def _sources(content: list[dict]) -> list[dict]:
    out = []
    for b in content:
        if b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
            out += [{"url": r["url"], "title": r.get("title") or r["url"]} for r in b["content"]
                    if isinstance(r, dict) and r.get("url")]
        if b.get("type") == "web_fetch_tool_result" and isinstance(b.get("content"), dict):
            url = b["content"].get("url")
            if url:
                out.append({"url": url, "title": url})
    return out


async def investigate(claude: MeteredClaude, name: str, website: str, description: str, research: str,
                      site_text: str) -> tuple[str, list[dict], Decimal]:
    task = TASK.format(name=name, website=website or "(none)", description=description or "(not given)",
                       research=(research or "(none)")[:6000], site=(site_text or "(not available)")[:8000],
                       checks="\n".join(f"- {k}: {text}" for k, text in CHECKS))
    messages: list[dict] = [{"role": "user", "content": task}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_WEB},
             {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": MAX_WEB}]
    texts, sources, cost = [], [], Decimal("0")
    for _ in range(MAX_CONTINUATIONS + 1):
        result = await claude.create(campaign_id=None, run_id=None, purpose="opportunity scan", role="worker",
                                     system=SYSTEM.format(max=MAX_FINDINGS), messages=messages, tools=tools,
                                     max_tokens=12000, max_web_searches=MAX_WEB)
        cost += result.cost
        sources += _sources(result.content)
        texts.append(_texts(result.content))
        if result.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": result.content}]
    notes = texts[-1] if texts and texts[-1] else "\n\n".join(t for t in texts if t)
    seen, unique = set(), []
    for src in sources:
        if src["url"] not in seen:
            seen.add(src["url"])
            unique.append(src)
    return notes, unique, cost


async def scan(claude: MeteredClaude, org_id: str, requested_by: str | None, research: str, site_text: str) -> dict:
    """Find what the company is missing, link each finding to a goal, and save it on the profile.
    Returns {"findings": [...], "deeper": [...], "cost": Decimal}."""
    from app.agent import org_setup  # the goal schema, tidying and goal creation live there

    async with session_scope() as s:
        org = await s.get(Organization, org_id)
        name, website, description = org.name, org.website, org.description
        depts = (await s.execute(select(Department).where(Department.org_id == org_id)
                                 .order_by(Department.created_at))).scalars().all()
        goals = (await s.execute(select(Campaign.id, Campaign.name, Department.name, Department.kind)
                                 .join(Agent, Agent.id == Campaign.agent_id)
                                 .join(Department, Department.id == Agent.department_id)
                                 .where(Campaign.org_id == org_id))).all()
        teams = ", ".join(f"{d.name} ({d.kind or 'custom'})" for d in depts) or "(none yet)"

    notes, sources, cost = await investigate(claude, name, website, description, research, site_text)
    if not notes:
        return {"findings": [], "deeper": [], "cost": cost}

    task = STRUCTURE_TASK.format(
        notes=notes[:12000],
        sources="\n".join(f"- {x['title']}: {x['url']}" for x in sources[:30]) or "(none)",
        teams=teams, max=MAX_FINDINGS,
        goals="\n".join(f"- {gid}: {gname} · {dname}" for gid, gname, dname, _ in goals) or "(none)",
        deeper="\n".join(f"- {k}: {text}" for k, text in DEEPER),
    )
    goal_schema = org_setup.plan_schema()["schema"]["properties"]["departments"]["items"]["properties"][
        "agents"]["items"]["properties"]["goals"]["items"]
    result = await claude.create(campaign_id=None, run_id=None, purpose="opportunity scan", role="worker",
                                 system=STRUCTURE_SYSTEM, messages=[{"role": "user", "content": task}],
                                 max_tokens=8000, output_format=findings_schema(goal_schema))
    cost += result.cost
    raw = json.loads(_texts(result.content) or "{}")

    known = {gid: (gname, dkind) for gid, gname, _, dkind in goals}
    allowed = {x["url"] for x in sources}
    findings, created = [], []
    for f in (raw.get("findings") or [])[:MAX_FINDINGS]:
        if not f.get("title") or not f.get("evidence"):
            continue
        goal_id = f.get("goal_id") if f.get("goal_id") in known else ""
        if not goal_id and f.get("new_goal"):
            goal_id = await _new_goal(org_id, requested_by, f["team_kind"], f["new_goal"], research)
            if goal_id:
                created.append(goal_id)
        urls = [u for u in f.get("source_urls") or [] if isinstance(u, str) and u.startswith("http")]
        findings.append({
            "team_kind": f["team_kind"], "title": f["title"][:120], "evidence": f["evidence"][:600],
            "impact": f.get("impact", "")[:400], "estimate": f.get("estimate", "")[:120],
            "assumption": f.get("assumption", "")[:300], "confidence": f.get("confidence", "medium"),
            # Prefer sources the analyst really saw; keep others only if it saw none.
            "sources": [u for u in urls if u in allowed][:4] or urls[:2],
            "goal_id": goal_id or None,
        })
    deeper = [{"tool": d["tool"], "label": TOOLS[d["tool"]].label if d["tool"] in TOOLS else d["tool"],
               "check": d["check"][:200]} for d in (raw.get("deeper") or [])[:4] if d.get("tool")]
    async with session_scope() as s:
        org = await s.get(Organization, org_id)
        org.profile = {**(org.profile or {}), "opportunities": {
            "findings": findings, "deeper": deeper, "scanned_at": utcnow().isoformat(), "goals_added": created}}
    return {"findings": findings, "deeper": deeper, "cost": cost}


async def _new_goal(org_id: str, requested_by: str | None, team_kind: str, spec: dict, research: str) -> str | None:
    """A draft goal for the team that would fix a gap, on that team's first AI employee. Returns its
    id, or None when the company has no such team (the finding then points at adding the team)."""
    from app.agent import org_setup

    goal = org_setup._tidy_goal(spec)
    if goal is None:
        return None
    async with session_scope() as s:
        dept = (await s.execute(select(Department).where(Department.org_id == org_id, Department.kind == team_kind)
                                .order_by(Department.created_at).limit(1))).scalar_one_or_none()
        if dept is None:
            return None
        agent = (await s.execute(select(Agent).where(Agent.department_id == dept.id)
                                 .order_by(Agent.created_at).limit(1))).scalar_one_or_none()
        if agent is None:
            return None
        org = await s.get(Organization, org_id)
        per, basis, n = await estimate.session_cost(s, org_id)
        goal["budget_basis"] = estimate.starter(per, goal["cycle_hours"], goal["duration_days"],
                                                goal["paid_spend_usd"], basis, n)
        goal["budget_usd"] = goal["budget_basis"]["suggested_usd"]
        names = {x.lower() for (x,) in (await s.execute(select(Campaign.name).where(Campaign.org_id == org_id))).all()}
        created: dict = {"goals": []}
        await org_setup._add_goals(s, org_id, requested_by, agent, [goal], names,
                                   org_setup.company_context(org, org.profile or {}), created)
        return created["goals"][0] if created["goals"] else None
