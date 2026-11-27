"""What the company is missing: checks on public signals, each finding tied to goals it can turn on.

Runs at the end of setup:
  1. pick       from the catalog (checks.py), narrowed by the company's type, Claude picks the
                checks most worth running, writes the searches a customer would type (never the
                company's name) and names the main competitors
  2. measure    runs those searches for real and records where the company ranks against its
                competitors; asks an AI assistant the same questions and records who it recommends
  3. look       reads public pages for the other picked checks (site, reviews, jobs, directories)
  4. findings   the biggest gaps, with evidence and sources, each tied to a goal. When fixing a
                gap fully costs more than about $100 (SEO, ads, PR...), it comes as milestones:
                a first step people can turn on now with its own price and outcome, and the
                later steps with theirs, so nobody has to commit to the whole amount up front

Costs are worked out the same way as every goal budget (AI work sessions over the milestone's
length, plus any real spend such as ads, tools or freelancers, itemised). Company-level only: it
never judges individual people.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import select

from app.agent import checks as catalog
from app.agent.playbook import OUTREACH_KNOWHOW
from app.agent.llm import MeteredClaude, usage_org
from app.catalog import TOOLS
from app.db import session_scope
from app.models import Agent, Campaign, Department, Membership, Organization, Role, utcnow
from app.org import DEPARTMENT_PRESETS, PRESET_NAMES, add_department, default_agent_name
from app.services import estimate, presence

log = logging.getLogger(__name__)

# The budget for one scan. Fewer checks, chosen carefully and run deeply: Claude scores every check
# that fits the company and runs the few most likely to show a big, fixable gap. Measurements
# (Google, AI assistants, the website scorecard) always run alongside.
SHOW = 6  # findings shown
CANDIDATES = 8  # findings asked for, ranked by how much the company will want to fix each
MAX_CHECKS = 7  # the core checks for early companies plus Claude's strongest picks
MIN_SCORE = 3  # a check Claude scores lower than this (1-5) isn't worth running
WEB_PER_CHECK = 5  # searches and page reads for each check
STRONG = 3  # a finding outside sales and marketing makes the five only if it's at least this strong
MAX_QUERIES = 3
MAX_COMPETITORS = 2
MAX_WEB = 8
MAX_CONTINUATIONS = 4
MILESTONES_ABOVE_USD = 100  # fixing it fully costs more than this: offer it in steps
MAX_MILESTONE_DAYS = 365

# --- 1. pick ------------------------------------------------------------------------------------

PICK_SYSTEM = """You plan a short, sharp check of a company. Most companies we check are small and \
early, and what they need most is customers. The question behind every check: where will this \
company's next 10 customers come from, and what's in the way? Find the few gaps that will make its \
founders say "we need to fix that now" and turn a goal on to fix it.

From the candidate checks, score each 1-5 on how likely it is, for THIS company, to show something \
big, specific and measurable that leads to customers soon (within about 90 days) once fixed. Score \
highest, in this order of value for an early company:
1. buyers to talk to now: people publicly asking for what it sells, competitors' unhappy customers, \
named companies with a fresh buying trigger, open briefs or tenders;
2. why buyers don't choose it: an unclear home page, no customer proof, no trust or security answers \
for big buyers, friction booking a call or buying;
3. where competitors win attention and deals: social media (company and founders), a launch video, \
comparison searches, directories buyers check;
4. being ready to reach out: email that lands in inboxes, a way to book a call.
Search and AI-assistant ranking for broad searches is slow and costly: score it high only for local \
businesses, agencies, online stores, or when the market clearly searches for this. Website hygiene, \
grants, hiring and legal pages rarely bring customers: score them low unless the research shows \
something serious. Use what you know: what it sells, who buys it, its stage and the research. A \
check that would probably come back "fine", or vague, scores low. Pick the strongest, not for \
variety. Say in a few words why, and the headline you expect.

Then write the searches a real customer would type when looking for what this company sells. Never \
include the company's own name or brand in a search: we want to know if customers who don't know \
them yet find them. Mix a broad search with more specific ones (by use case, industry or location), \
in the language its customers use. Name its 2 closest competitors with their website domains. List \
the markets where its customers are (up to 3, most important first) with Google's country code and \
the language people search in there. If it serves customers in particular cities (a clinic, an \
installer, a restaurant, a local agency or shop), give the search a local customer would type \
without the city (e.g. "emergency plumber") and up to 3 cities; otherwise leave local empty."""

PICK_TASK = """Company: {name} ({website})
What they do: {description}

What research found:
{research}

Candidate checks:
{checks}

Score every candidate, write {max_queries} customer searches, name the 2 closest competitors and list the markets."""


def pick_schema(keys: list[str]) -> dict:
    return {"type": "json_schema", "schema": {
        "type": "object",
        "properties": {
            "checks": {"type": "array", "items": {
                "type": "object",
                "properties": {"key": {"type": "string", "enum": keys},
                               "score": {"type": "integer", "description": "1-5: how likely a big, fixable, measurable gap"},
                               "why": {"type": "string"}, "expect": {"type": "string", "description": "The headline you expect"}},
                "required": ["key", "score", "why", "expect"], "additionalProperties": False}},
            "queries": {"type": "array", "items": {
                "type": "object",
                "properties": {"query": {"type": "string"},
                               "intent": {"type": "string", "description": "Who searches this and why, a few words"}},
                "required": ["query", "intent"], "additionalProperties": False}},
            "competitors": {"type": "array", "items": {
                "type": "object", "properties": {"name": {"type": "string"}, "domain": {"type": "string"}},
                "required": ["name", "domain"], "additionalProperties": False}},
            "markets": {"type": "array", "items": {
                "type": "object",
                "properties": {"country": {"type": "string", "description": "Country name in English, e.g. Germany"},
                               "gl": {"type": "string", "description": "Google country code, e.g. de"},
                               "hl": {"type": "string", "description": "Search language code, e.g. de"}},
                "required": ["country", "gl", "hl"], "additionalProperties": False}},
            "local": {"type": "object",
                      "properties": {"query": {"type": "string"}, "cities": {"type": "array", "items": {"type": "string"}}},
                      "required": ["query", "cities"], "additionalProperties": False},
        },
        "required": ["checks", "queries", "competitors", "markets", "local"], "additionalProperties": False}}


# --- 2. measure ---------------------------------------------------------------------------------

SEARCH_SYSTEM = "You run web searches exactly as asked and report nothing else."
SEARCH_TASK = """Run each of these web searches once, with exactly this text, in this order. Don't \
run any other searches. When all are done, reply "done".

{queries}"""

AI_SYSTEM = """You are a helpful AI assistant. A person asks you each question below. Answer from \
your own knowledge, as you would for anyone: recommend the companies or products you'd actually \
suggest, best first, up to 5 each, with their website domains when you know them."""


def ai_schema() -> dict:
    rec = {"type": "object", "properties": {"name": {"type": "string"}, "domain": {"type": "string"}},
           "required": ["name", "domain"], "additionalProperties": False}
    answer = {"type": "object", "properties": {"query": {"type": "string"}, "recommendations": {"type": "array", "items": rec}},
              "required": ["query", "recommendations"], "additionalProperties": False}
    return {"type": "json_schema", "schema": {"type": "object", "properties": {"answers": {"type": "array", "items": answer}},
                                              "required": ["answers"], "additionalProperties": False}}


def host(url_or_domain: str) -> str:
    raw = (url_or_domain or "").strip().lower()
    if not raw:
        return ""
    netloc = urlparse(raw if "://" in raw else "https://" + raw).netloc
    return netloc.split(":")[0].removeprefix("www.")


def _same_site(a: str, b: str) -> bool:
    """example.com matches blog.example.com and example.com/uk."""
    return bool(a and b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


def _norm(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lower().strip('"'))


async def search_visibility(claude: MeteredClaude, queries: list[dict], mine: str,
                            competitors: list[dict]) -> tuple[list[dict], Decimal]:
    """Runs the searches and records where the company ranks, and which competitors show up."""
    text = "\n".join(f"{i + 1}. {q['query']}" for i, q in enumerate(queries))
    messages: list[dict] = [{"role": "user", "content": SEARCH_TASK.format(queries=text)}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": len(queries)}]
    asked: dict[str, str] = {}  # search tool call id -> the query it ran
    results: dict[str, list[dict]] = {}
    cost = Decimal("0")
    for _ in range(MAX_CONTINUATIONS + 1):
        result = await claude.create(campaign_id=None, run_id=None, purpose="search visibility", task="search_ranking",
                                     system=SEARCH_SYSTEM, messages=messages, tools=tools, max_tokens=2000,
                                     max_web_searches=len(queries))
        cost += result.cost
        for b in result.content:
            if b.get("type") == "server_tool_use" and b.get("name") == "web_search":
                asked[b.get("id", "")] = (b.get("input") or {}).get("query", "")
            if b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
                results[b.get("tool_use_id", "")] = [r for r in b["content"] if isinstance(r, dict) and r.get("url")]
        if result.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": result.content}]

    ran = [(asked.get(k, ""), v) for k, v in results.items()]
    out = []
    for i, q in enumerate(queries):
        found = next((v for a, v in ran if _norm(a) == _norm(q["query"])), None)
        if found is None and i < len(ran):  # the search tool reworded it slightly: go by order
            found = ran[i][1]
        if found is None:
            continue
        rows, rank = [], None
        for pos, r in enumerate(found, start=1):
            d = host(r["url"])
            who = "you" if _same_site(d, mine) else next(
                (c["name"] for c in competitors if _same_site(d, host(c["domain"]))), "")
            if who == "you" and rank is None:
                rank = pos
            rows.append({"title": (r.get("title") or d)[:120], "url": r["url"], "domain": d, "who": who})
        ahead = []
        for row in rows[: (rank - 1) if rank else len(rows)]:
            if row["who"] and row["who"] != "you" and row["who"] not in ahead:
                ahead.append(row["who"])
        out.append({"query": q["query"], "intent": q.get("intent", ""), "market": "Web", "rank": rank, "checked": len(rows),
                    "results": rows[:6], "competitors_ahead": ahead, "source": "web"})
    return out, cost


async def ai_answers(claude: MeteredClaude, queries: list[dict], name: str, mine: str,
                     competitors: list[dict]) -> tuple[list[dict], Decimal]:
    """What an AI assistant recommends for the same questions, and whether the company is in it."""
    asked = "\n".join(f"- {q['query']}" for q in queries)
    result = await claude.create(campaign_id=None, run_id=None, purpose="AI answer visibility", task="ai_recommend",
                                 system=AI_SYSTEM, messages=[{"role": "user", "content": asked}], max_tokens=3000,
                                 output_format=ai_schema())
    raw = json.loads(_texts(result.content) or "{}")
    by_query = {_norm(a.get("query", "")): a.get("recommendations") or [] for a in raw.get("answers") or []}
    answers = list(raw.get("answers") or [])
    out = []
    for i, q in enumerate(queries):
        recs = by_query.get(_norm(q["query"]))
        if recs is None:
            recs = (answers[i].get("recommendations") or []) if i < len(answers) else []
        rank, names = None, []
        for pos, r in enumerate(recs[:5], start=1):
            is_me = _same_site(host(r.get("domain", "")), mine) or _norm(r.get("name", "")) == _norm(name)
            if is_me and rank is None:
                rank = pos
            names.append({"name": r.get("name", "")[:80], "domain": host(r.get("domain", "")), "you": is_me,
                          "competitor": any(_same_site(host(r.get("domain", "")), host(c["domain"])) for c in competitors)})
        out.append({"assistant": "Claude", "query": q["query"], "rank": rank, "recommended": names})
    return out, result.cost


# --- 3. look ------------------------------------------------------------------------------------

LOOK_SYSTEM = """You are a sharp growth analyst running one check on a company, to show it \
something it's missing out on, concretely enough that it wants to turn a goal on to fix it.

Rules:
- Follow the steps. Use web_search and web_fetch to see for yourself; don't guess. Measure the \
number the check is about for the company and for each competitor named.
- Evidence first: say exactly what you saw, with numbers, dates and URLs ("12 reviews on G2 at \
4.1; Routeco has 240 at 4.6"). If you couldn't verify something, say so instead of guessing.
- Public information only. Founders' public posts about their company may be counted and compared; \
never judge, rank or name other individual employees. People who post publicly asking for help or \
reviewing a product may be quoted from what they posted.
- If the company turns out to be doing well on this, say that plainly: a clear "no gap" is useful."""

LOOK_TASK = """Company: {name} ({website})
What they do: {description}
Closest competitors: {competitors}

What setup research found:
{research}

What was measured (use these numbers; don't re-measure them):
{measured}

The check: {title}
The number it's about: {metric}
Steps:
{steps}

Write your notes. End with a line "RESULT:" giving the number for the company and for each \
competitor, and the single most striking fact you found."""


# --- 3b. social media, read from public posts --------------------------------------------------------

SOCIAL_KEYS = {"social_performance", "launch_video"}
SOCIAL_USES = 14  # searches and page reads for the whole social read
SOCIAL_SYSTEM = """You measure a company's social media next to its competitors by reading public \
posts: LinkedIn and X, for each company's own account and its founders' personal accounts.

How:
- Start from the profiles each company's website links to (given). Find the founders (the company's \
site, its LinkedIn page, news) and their LinkedIn and X profiles.
- For each account, count the posts from the last 30 days and add up likes (reactions) and comments \
(replies) on them. Read public posts: search for them (e.g. site:linkedin.com/posts "<company>"; \
site:x.com <handle>) and open the posts and profile pages you can. Count only what you saw; if an \
account's posts can't be read, give null rather than a guess, and say why in the note. coverage says \
how much you saw: "verified" (you saw the account's posts for the whole 30 days), "partial" (some \
posts or some days only: the counts are a floor) or "blocked" (you couldn't see its posts; counts null).
- Also look at the first page of each company's own accounts (and its YouTube or Product Hunt page if \
linked) for a launch, demo or explainer video, and note its views or engagement when shown.
- Public information only. Founders' public posts about their company may be counted; never judge \
or rank other individual employees."""


def social_schema() -> dict:
    account = {"type": "object", "properties": {
        "company": {"type": "string", "description": "Which company the account belongs to, exactly as given"},
        "who": {"type": "string", "enum": ["company", "founder"]},
        "name": {"type": "string", "description": "The account name, e.g. the company or the founder's name"},
        "platform": {"type": "string", "enum": ["linkedin", "x"]},
        "url": {"type": "string"},
        "coverage": {"type": "string", "enum": ["verified", "partial", "blocked"]},
        "posts_30d": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "engagement_30d": {"anyOf": [{"type": "integer"}, {"type": "null"}],
                           "description": "Likes/reactions plus comments/replies on those posts"},
        "note": {"type": "string"}},
        "required": ["company", "who", "name", "platform", "url", "coverage", "posts_30d", "engagement_30d", "note"],
        "additionalProperties": False}
    video = {"type": "object", "properties": {
        "company": {"type": "string"}, "found": {"type": "boolean"}, "where": {"type": "string"},
        "url": {"type": "string"}, "views_or_engagement": {"type": "string"}},
        "required": ["company", "found", "where", "url", "views_or_engagement"], "additionalProperties": False}
    return {"type": "json_schema", "schema": {"type": "object", "properties": {
        "accounts": {"type": "array", "items": account}, "videos": {"type": "array", "items": video}},
        "required": ["accounts", "videos"], "additionalProperties": False}}


async def read_social(claude: MeteredClaude, name: str, website: str, competitors: list[dict],
                      sites: dict) -> tuple[dict, Decimal]:
    """Posts and engagement in the last 30 days, and launch videos, for the company and competitors."""
    companies = [(name, host(website))] + [(c["name"], host(c["domain"])) for c in competitors]
    lines = []
    for n, d in companies:
        so = (sites.get(d) or {}).get("socials") or {}
        vids = (sites.get(d) or {}).get("videos")
        lines.append(f"- {n} ({d or 'no website'}): profiles linked from its site: "
                     + (", ".join(f"{k} {v}" for k, v in so.items()) or "none found")
                     + (f"; video on its home page: {', '.join(vids) or 'none'}" if vids is not None else ""))
    task = (f"Today is {utcnow().date().isoformat()}. Measure these companies' last 30 days on LinkedIn and X, "
            f"company accounts and founders:\n" + "\n".join(lines))
    messages: list[dict] = [{"role": "user", "content": task}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": SOCIAL_USES},
             {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": SOCIAL_USES}]
    cost = Decimal("0")
    for _ in range(MAX_CONTINUATIONS + 1):
        result = await claude.create(campaign_id=None, run_id=None, purpose="opportunity scan", task="social_read",
                                     system=SOCIAL_SYSTEM, messages=messages, tools=tools, max_tokens=6000,
                                     max_web_searches=SOCIAL_USES, output_format=social_schema())
        cost += result.cost
        if result.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": result.content}]
    try:
        data = json.loads(_texts(result.content) or "{}")
    except ValueError:
        data = {}
    return {"accounts": data.get("accounts") or [], "videos": data.get("videos") or []}, cost


def social_rows(social: dict, name: str, competitors: list[dict]) -> list[dict]:
    """Scorecard rows: you vs competitors on LinkedIn, X, founders, and launch videos."""
    names = [name] + [c["name"] for c in competitors]
    # An account that couldn't be read has no numbers, whatever came back.
    accounts = [{**a, "posts_30d": None, "engagement_30d": None} if a.get("coverage") == "blocked" else a
                for a in social.get("accounts") or []]
    note = "Read from public posts by AI; approximate"

    def fmt(a: dict | None) -> str | None:
        if not a:
            return None
        if a.get("posts_30d") is None or a.get("coverage") == "blocked":
            return "Couldn't read"
        eng = a.get("engagement_30d")
        shown = f"{a['posts_30d']} posts" + (f" · {eng:,} likes and comments" if eng is not None else "")
        return shown + (" (at least: only partly visible)" if a.get("coverage") == "partial" else "")

    def find(company: str, who: str, platform: str) -> list[dict]:
        return [a for a in accounts if a.get("company", "").lower() == company.lower() and a.get("who") == who
                and a.get("platform") == platform]

    def verdict(me: dict | None, them: list[dict]) -> str:
        best = max((t for t in them if t and t.get("posts_30d") is not None), default=None,
                   key=lambda t: (t.get("engagement_30d") or 0, t.get("posts_30d") or 0))
        if not me or me.get("posts_30d") is None:
            return "bad" if best else "ok"
        if not best:
            return "good"
        if (me["posts_30d"] or 0) * 2 < (best["posts_30d"] or 0) or (me.get("engagement_30d") or 0) * 3 < (best.get("engagement_30d") or 0):
            return "bad"
        return "good" if (me.get("engagement_30d") or 0) >= (best.get("engagement_30d") or 0) else "ok"

    rows = []
    for platform, label in (("linkedin", "LinkedIn page, last 30 days"), ("x", "X account, last 30 days")):
        mine = (find(name, "company", platform) or [None])[0]
        theirs = [(n, (find(n, "company", platform) or [None])[0]) for n in names[1:]]
        if not mine and not any(a for _, a in theirs):
            continue
        rows.append({"key": f"social_{platform}", "label": label, "team": "marketing",
                     "you": {"display": fmt(mine) or "No account found", "status": verdict(mine, [a for _, a in theirs])},
                     "others": [{"name": n, "display": fmt(a)} for n, a in theirs if a], "note": note})

    def founders(company: str) -> dict | None:
        fs = [a for a in accounts if a.get("company", "").lower() == company.lower() and a.get("who") == "founder"
              and a.get("posts_30d") is not None]
        if not fs:
            return None
        return {"posts_30d": sum(a["posts_30d"] for a in fs), "engagement_30d": sum(a.get("engagement_30d") or 0 for a in fs),
                "who": ", ".join(sorted({a["name"] for a in fs}))}
    mine_f = founders(name)
    theirs_f = [(n, founders(n)) for n in names[1:]]
    if mine_f or any(f for _, f in theirs_f):
        rows.append({"key": "social_founders", "label": "Founders' posts, last 30 days", "team": "marketing",
                     "you": {"display": (fmt(mine_f) + f" ({mine_f['who']})") if mine_f else "None found",
                             "status": verdict(mine_f, [f for _, f in theirs_f])},
                     "others": [{"name": n, "display": fmt(f) + f" ({f['who']})"} for n, f in theirs_f if f], "note": note})

    videos = {v.get("company", "").lower(): v for v in social.get("videos") or []}
    if videos:
        def vid(n):
            v = videos.get(n.lower())
            if not v:
                return None
            if not v.get("found"):
                return "None found"
            return " · ".join(x for x in (v.get("where"), v.get("views_or_engagement")) if x) or "Yes"
        mine_v = vid(name)
        rows.append({"key": "launch_video", "label": "Launch or demo video", "team": "marketing",
                     "you": {"display": mine_v or "None found",
                             "status": "good" if (videos.get(name.lower()) or {}).get("found")
                             else "bad" if any((videos.get(n.lower()) or {}).get("found") for n in names[1:]) else "ok"},
                     "others": [{"name": n, "display": vid(n)} for n in names[1:] if vid(n)],
                     "note": "Home page, YouTube, LinkedIn, X and Product Hunt (first page of each)"})
    return rows


# --- 4. findings ---------------------------------------------------------------------------------

STRUCTURE_SYSTEM = """You turn an analyst's measurements and notes into the few findings that \
will make a company want to turn on an AI employee, and tie each to the goal that fixes it.

What makes a finding worth showing: it's big, specific and surprising; it's measured next to \
competitors; it ends in a number the company cares about (customers, revenue, reputation, risk, \
cash); and an AI employee can clearly move that number. Rank by how much they'll want to fix it, \
and score that 1-5 ("pull"). Drop anything vague, generic or minor, even if it's true.

- Keep only findings backed by evidence. Use the measured search and AI-answer results exactly as \
given; never change a rank or invent one.
- Each finding has its number: what it's called, where they are now, and a realistic goal (e.g. \
"negative reviews answered: 2 of 9 now, 9 of 9 goal"; "page-1 searches: 1 of 6 now, 4 of 6 goal").
- Say what it costs them in customers: buyers missed, meetings or deals not won, people asking who \
never heard back. Prefer findings that lead to customers soon over slow or cosmetic ones.
- A missing launch or demo video: the fix is a goal whose first result is a 20-second launch video \
made from their website (story, motion, music and share copy), then the posts that launch it on \
LinkedIn and X; posting waits for their OK.
- Social media: give the numbers side by side (posts and likes + comments in the last 30 days, for \
the company page and the founders), and make the goal about posting better content more often to \
win engagement and inbound deals.
- Search ranking: only make a finding about it when the measured searches show real demand (more \
than about 100 a month) or the company is local, an agency or an online store. Search and AI-assistant \
visibility (Google, ChatGPT, Perplexity, Gemini) together get one finding at most.
- Cover the checks that were run: one finding for each check that found a real gap, before a second \
finding on anything. For an early company, getting in front of buyers (people asking, social \
media, a launch video, comparisons, a clear home page) matters more than search or AI rankings.
- No analytics on the website (in the measurements) is a quick finding: they can't see which \
channel brings visitors and customers, so they can't double down on what works. The fix is setting \
up analytics with sign-up/booking events and a weekly channel report.
- Write plainly and briefly; direct and helpful, not alarming. People skim these: the title says the \
gap in a few words; the points are 2-4 short facts (who, what, how many, when), not a paragraph; \
"impact" says in one or two plain sentences why it matters to their business (lost deals, revenue, \
risk), connecting the facts to what they sell.
- Money: only give an estimate of what the gap costs them when you can state a reasonable \
assumption, as a range. Never present a guess as a fact.
- Fixing it: if an existing goal would fix the gap, link it by id. Otherwise propose the work.
  When fully fixing it is a big job that would cost more than about ${threshold} (for example SEO \
or AI-answer visibility for competitive searches, paid ads, PR, a marketplace launch), split it \
into 2-3 milestones: a first step that's cheap and quick with a concrete outcome they'll see (e.g. \
"page 1 for 3 long-tail searches in 6 weeks"), then bigger steps up to the full result (e.g. "top 3 \
for the main search in 6 months"). Each milestone is a goal for the right team, with how often the \
AI employee works on it, how many weeks, how many work sessions it really needs (one-off setup \
work like DNS records, a profile or a page takes a few sessions, not weeks of them), and any real \
money it needs beyond the AI's own work \
(ads, tools, freelancers, directory fees, PR distribution), itemised with realistic prices. Don't \
pad: if no extra spend is needed, list none.
  Smaller fixes get a single new goal and no milestones.
- A goal's steps are what a skilled person would actually do to hit that goal.
- In anything written for people, don't call it an AI employee, agent or lead: talk about the goal \
and say Oton does the work."""

STRUCTURE_TASK = """Measured: where {name} ({domain}) shows up for what customers search
{visibility}

Measured: its website, domain and presence next to competitors
{measured}

The analyst's notes:
{notes}

Sources the analyst saw:
{sources}

The company's teams: {teams}

Goals already set up (id: name · team):
{goals}

Checks that ran (key: title): {checks}

Return at most {max} findings, ranked by pull. If there's a strong one for a team outside sales \
and marketing (for example email that lands in spam, a slow site, bad reviews nobody answered, \
funding they qualify for), include it; don't include a weak one just for variety."""


def findings_schema(goal_schema: dict, check_keys: list[str]) -> dict:
    # The goal is defined once and referenced twice: written out in both places, the API rejects
    # the schema ("compiled grammar is too large") and every scan fails at this last step.
    goal = {"$ref": "#/$defs/goal"}
    kinds = [k for k, _ in DEPARTMENT_PRESETS] + ["custom"]
    milestone = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "e.g. 'Page 1 for 3 long-tail searches'"},
            "outcome": {"type": "string", "description": "What they'll have at the end, concretely"},
            "weeks": {"type": "number"},
            "sessions": {"type": "integer", "description": (
                "Work sessions this step really needs. One-off jobs (DNS records, a profile, a page or two, "
                "a video) need 1-6; ongoing work (posting, outreach, SEO) needs one per cycle over the weeks")},
            "paid_items": {"type": "array", "items": {
                "type": "object", "properties": {"item": {"type": "string"}, "usd": {"type": "number"}},
                "required": ["item", "usd"], "additionalProperties": False}},
            "goal": goal,
        },
        "required": ["name", "outcome", "weeks", "sessions", "paid_items", "goal"],
        "additionalProperties": False,
    }
    finding = {
        "type": "object",
        "properties": {
            "check": {"type": "string", "enum": check_keys + [""]},
            "team_kind": {"type": "string", "enum": kinds},
            "title": {"type": "string", "description": "The gap in a few words"},
            "evidence": {"type": "string", "description": "What was seen, in one short sentence"},
            "points": {"type": "array", "items": {"type": "string"},
                       "description": "2-4 short bullets of exactly what was seen (names, numbers, dates), "
                                      "each under 18 words"},
            "impact": {"type": "string", "description": "Why this matters for this company's business: one or two "
                                                        "plain sentences, under 35 words"},
            "estimate": {"type": "string", "description": "What the gap costs them, as a range, or ''"},
            "assumption": {"type": "string", "description": "The assumption behind the estimate, or ''"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "metric_name": {"type": "string", "description": "The number, e.g. 'Negative reviews answered'"},
            "metric_now": {"type": "string", "description": "Where they are, e.g. '2 of 9'"},
            "metric_goal": {"type": "string", "description": "A realistic goal, e.g. '9 of 9'"},
            "pull": {"type": "integer", "description": "1-5: how much they'll want to fix it"},
            "source_urls": {"type": "array", "items": {"type": "string"}},
            "goal_id": {"type": "string", "description": "Id of an existing goal that fixes this, or ''"},
            "new_goal": {"anyOf": [goal, {"type": "null"}]},
            "milestones": {"type": "array", "items": milestone},
        },
        "required": ["check", "team_kind", "title", "evidence", "points", "impact", "estimate", "assumption", "confidence",
                     "metric_name", "metric_now", "metric_goal", "pull",
                     "source_urls", "goal_id", "new_goal", "milestones"],
        "additionalProperties": False,
    }
    return {"type": "json_schema", "schema": {
        "type": "object", "properties": {"findings": {"type": "array", "items": finding}},
        "required": ["findings"], "additionalProperties": False, "$defs": {"goal": goal_schema}}}


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


def visibility_text(search: list[dict], ai: list[dict]) -> str:
    if not search and not ai:
        return "(not measured)"
    lines = []
    for s in search:
        where = f"rank {s['rank']} of {s['checked']} results" if s["rank"] else f"not in the top {s['checked']} results"
        top = ", ".join(f"{r['domain']}{' (' + r['who'] + ')' if r['who'] else ''}" for r in s["results"][:5])
        ov = s.get("ai_overview")
        ai_text = (" AI Overview " + ("mentions you" if ov.get("mentioned") else "doesn't mention you")) if ov else ""
        lines.append(f"- {'Google ' + s['market'] if s.get('source') == 'google' else 'Web search'} \"{s['query']}\": {where}. Top results: {top}.{ai_text}")
    for a in ai:
        where = f"recommended #{a['rank']}" if a["rank"] else "not recommended"
        names = ", ".join(r["name"] for r in a["recommended"]) or "nobody"
        lines.append(f"- {a.get('assistant', 'AI assistant')} asked \"{a['query']}\": {where}. Recommended: {names}")
    return "\n".join(lines)


def highlights(search: list[dict], ai: list[dict]) -> list[str]:
    """The few results most worth pointing out, in plain words."""
    out: list[str] = []
    by_query: dict[str, list[dict]] = {}
    for row in search:
        by_query.setdefault(row["query"], []).append(row)
    for q, rows in by_query.items():
        ranked = [r for r in rows if r["rank"]]
        missing = [r for r in rows if not r["rank"]]
        names_a_market = any(r["market"].lower() in q.lower() for r in rows)  # "... netherlands" is meant for one country
        if ranked and missing and len(rows) > 1 and not names_a_market:
            best = min(ranked, key=lambda r: r["rank"])
            miss = missing[0]
            leader = (miss["competitors_ahead"] or [""])[0]
            out.append(f"You're #{best['rank']} in {best['market']} for \"{q}\" but not in the top {miss['checked']} in "
                       f"{miss['market']}" + (f", where {leader} leads." if leader else "."))
        elif rows and not ranked:
            leaders = {r["competitors_ahead"][0] for r in rows if r["competitors_ahead"]}
            where = rows[0]["market"] if len(rows) == 1 else f"all {len(rows)} countries checked"
            out.append(f"Not in the top results for \"{q}\" in {where}" + (f"; {', '.join(sorted(leaders))} rank there." if leaders else "."))
    by_q_ai: dict[str, list[dict]] = {}
    for a in ai:
        by_q_ai.setdefault(a["query"], []).append(a)
    for q, answers in by_q_ai.items():
        if len(answers) > 1 and not any(a["rank"] for a in answers):
            named = sorted({r["name"] for a in answers for r in a["recommended"] if r.get("competitor")})
            out.append(f"None of the {len(answers)} AI assistants asked recommend you for \"{q}\""
                       + (f"; they suggest {', '.join(named)}." if named else "."))
    return out[:3]


async def look(claude: MeteredClaude, name: str, website: str, description: str, research: str, site_text: str,
               picked: list[catalog.Check], competitors: list[dict], measured: str = "") -> tuple[str, list[dict], Decimal]:
    """Each chosen check as its own focused investigation, run in parallel."""
    web_checks = [c for c in picked if c.method == "web"]
    if not web_checks:
        return "", [], Decimal("0")

    async def one(c: catalog.Check) -> tuple[str, list[dict], Decimal]:
        task = LOOK_TASK.format(
            name=name, website=website or "(none)", description=description or "(not given)",
            competitors=", ".join(f"{x['name']} ({x['domain']})" for x in competitors) or "(find the closest 2)",
            research=(research or "(none)")[:4000], measured=(measured or "(nothing measured)")[:4000],
            title=c.title, metric=c.metric,
            steps="\n".join(f"{i}. {st}" for i, st in enumerate(c.steps, 1)))
        messages: list[dict] = [{"role": "user", "content": task}]
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": WEB_PER_CHECK},
                 {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": WEB_PER_CHECK}]
        texts, sources, cost = [], [], Decimal("0")
        for _ in range(MAX_CONTINUATIONS + 1):
            result = await claude.create(campaign_id=None, run_id=None, purpose="opportunity scan", task="check_investigation",
                                         system=LOOK_SYSTEM, messages=messages, tools=tools, max_tokens=6000,
                                         max_web_searches=WEB_PER_CHECK)
            cost += result.cost
            sources += _sources(result.content)
            texts.append(_texts(result.content))
            if result.stop_reason != "pause_turn":
                break
            messages = [messages[0], {"role": "assistant", "content": result.content}]
        notes = texts[-1] if texts and texts[-1] else "\n\n".join(t for t in texts if t)
        return f"## {c.title} ({c.key})\n{notes}", sources, cost

    done = await asyncio.gather(*[one(c) for c in web_checks], return_exceptions=True)
    notes, sources, cost = [], [], Decimal("0")
    for c, r in zip(web_checks, done):
        if isinstance(r, Exception):
            log.warning("check %s failed: %s", c.key, r)
            continue
        notes.append(r[0])
        sources += r[1]
        cost += r[2]
    if not notes and done and all(isinstance(r, Exception) for r in done):
        raise done[0]
    return "\n\n".join(notes), sources, cost


async def scan(claude: MeteredClaude, org_id: str, requested_by: str | None, research: str, site_text: str,
               more: bool = False) -> dict:
    """Run the checks, save the findings on the profile, and return {"findings", "ran", "cost"}.

    more=True ("Find more opportunities"): run checks that haven't run yet, skip what was already
    found, and add the new findings to the earlier ones (returns "new" and the new "goals")."""
    from app.agent import org_setup  # the goal schema, tidying and goal creation live there

    usage_org.set(org_id)

    async with session_scope() as s:
        org = await s.get(Organization, org_id)
        name, website, description = org.name, org.website, org.description
        pack_key = (org.profile or {}).get("company_type")
        size = (org.profile or {}).get("size")
        depts = (await s.execute(select(Department).where(Department.org_id == org_id)
                                 .order_by(Department.created_at))).scalars().all()
        goals = (await s.execute(select(Campaign.id, Campaign.name, Department.name)
                                 .join(Agent, Agent.id == Campaign.agent_id)
                                 .join(Department, Department.id == Agent.department_id)
                                 .where(Campaign.org_id == org_id))).all()
        teams = ", ".join(f"{d.name} ({d.kind or 'custom'})" for d in depts) or "(none yet)"
        per, basis, n = await estimate.session_cost(s, org_id)
        before = dict((org.profile or {}).get("opportunities") or {}) if more else {}
    ran_before = {c.get("key") for c in before.get("checks") or []}
    found_before = [f.get("title", "") for f in before.get("findings") or [] if f.get("title")]
    mine = host(website)
    cost = Decimal("0")

    # 1. Pick the checks for this company, its customers' searches and its competitors.
    options = catalog.runnable(pack_key)
    if more:  # checks that haven't run yet (all of them again once every one has)
        options = [c for c in options if c.key not in ran_before] or options
    result = await claude.create(
        campaign_id=None, run_id=None, purpose="opportunity scan", task="pick_checks", system=PICK_SYSTEM,
        messages=[{"role": "user", "content": PICK_TASK.format(
            name=name, website=website or "(none)", description=description or "(not given)",
            research=(research or "(none)")[:6000], max_queries=MAX_QUERIES,
            checks="\n".join(f"- {c.key}: {c.title}. Looks at: {c.how}. Number: {c.metric}. "
                             f"Example headline: \"{c.example}\"" for c in options))}],
        max_tokens=3000, output_format=pick_schema([c.key for c in options]))
    cost += result.cost
    plan = json.loads(_texts(result.content) or "{}")
    allowed_keys = {c.key for c in options}
    chosen, seen = [], set()
    for x in plan.get("checks") or []:  # one entry per check, in Claude's order
        if isinstance(x, dict) and x.get("key") in allowed_keys and x["key"] not in seen:
            seen.add(x["key"])
            chosen.append(x)
    chosen = sorted(chosen, key=lambda x: -int(x.get("score") or 0))  # stable: ties keep Claude's order
    # The core checks always run for early companies; Claude's strongest picks fill the rest.
    must = [k for k in catalog.core(pack_key, size) if k in allowed_keys]
    by_key = {x["key"]: x for x in chosen}
    core_picks = [by_key.get(k) or {"key": k, "score": 5, "why": "Checked for every early company", "expect": ""} for k in must]
    extra = [x for x in chosen if x["key"] not in must and int(x.get("score") or 0) >= MIN_SCORE]
    chosen = (core_picks + extra)[:max(MAX_CHECKS, len(core_picks))] or chosen[:2]
    picked = [catalog.BY_KEY[x["key"]] for x in chosen]
    reasons = {x["key"]: {"why": str(x.get("why", ""))[:200], "expect": str(x.get("expect", ""))[:200],
                          "score": int(x.get("score") or 0)} for x in chosen}
    name_words = {w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) > 2}
    queries = [q for q in plan.get("queries") or []
               if q.get("query") and not (name_words & set(re.findall(r"[a-z0-9]+", q["query"].lower())))][:MAX_QUERIES]
    competitors = [c for c in plan.get("competitors") or [] if c.get("name") and host(c.get("domain", ""))
                   and not _same_site(host(c["domain"]), mine)][:MAX_COMPETITORS]

    markets = [{"label": m["country"][:40], "gl": m["gl"].lower()[:2], "hl": m["hl"].lower()[:5]}
               for m in plan.get("markets") or [] if m.get("country") and m.get("gl") and m.get("hl")][:3 if size in ("mid", "large") else 2] \
        or [{"label": "United States", "gl": "us", "hl": "en"}]
    local = plan.get("local") or {}
    local = {"query": local.get("query", "")[:80], "cities": [c for c in local.get("cities") or [] if c][:3],
             "gl": markets[0]["gl"], "hl": markets[0]["hl"]} if local.get("query") and local.get("cities") else None

    picked_keys = {c.key for c in picked}

    # 2. Measure: real Google results by country (Claude's web search when Google isn't set up),
    #    what AI assistants recommend, and the website, domain and presence against competitors.
    async def claude_search():
        if not queries or presence.google.enabled() or not any(c.method == "search" for c in picked):
            return [], Decimal("0")
        try:
            return await search_visibility(claude, queries, mine, competitors)
        except Exception as e:
            log.warning("search visibility check failed: %s", e)
            return [], Decimal("0")

    async def claude_answers():
        if not queries or not any(c.method == "ai" for c in picked):
            return [], Decimal("0")
        try:
            return await ai_answers(claude, queries, name, mine, competitors)
        except Exception as e:
            log.warning("AI answer check failed: %s", e)
            return [], Decimal("0")

    async def measured():
        try:
            # Search rankings and AI-assistant answers only when a check needs them: measured
            # every time, their hard numbers would crowd out everything else.
            return await presence.measure(name, website or "", competitors, queries, markets, local,
                                          rankings=bool(SEARCH_KEYS & picked_keys), ask_assistants="ai_answers" in picked_keys)
        except Exception as e:
            log.warning("market measurements failed: %s", e)
            return {}

    (web, c1), (ai, c2), m = await asyncio.gather(claude_search(), claude_answers(), measured())
    cost += c1 + c2 + presence.cost(m.get("calls") or {})
    search = m.get("google") or web
    ai = ai + (m.get("assistants") or [])
    rows = presence.scorecard(m) if m else []
    if SOCIAL_KEYS & {c.key for c in picked}:
        try:
            social, c_social = await read_social(claude, name, website or "", competitors, m.get("sites") or {})
            cost += c_social
            rows += social_rows(social, name, competitors)
        except Exception as e:  # the rest of the scan still runs
            log.warning("reading social media failed: %s", e)
    measured_text = presence.summary(m, rows) if m else presence.summary({}, rows)

    # 3. Look at public pages for the rest.
    try:
        notes, sources, c3 = await look(claude, name, website, description, research, site_text, picked, competitors,
                                        measured_text)
        cost += c3
    except Exception as e:  # the measurements can still make findings
        log.warning("reading public pages failed: %s", e)
        notes, sources = "", []
    if not notes and not search and not ai and not rows:
        return {"findings": [], "ran": len(picked), "cost": cost}

    # 4. Findings, each tied to goals; big fixes in milestones with their prices.
    seen, unique = set(), []
    for src in sources + [{"url": r["url"], "title": r["title"]} for s_ in search for r in s_["results"]]:
        if src["url"] not in seen:
            seen.add(src["url"])
            unique.append(src)
    goal_schema = org_setup.plan_schema()["schema"]["properties"]["departments"]["items"]["properties"][
        "agents"]["items"]["properties"]["goals"]["items"]
    task = STRUCTURE_TASK.format(
        name=name, domain=mine or "(no website)", visibility=visibility_text(search, ai), measured=measured_text or "(nothing measured)", notes=(notes or "(none)")[:12000],
        sources="\n".join(f"- {x['title']}: {x['url']}" for x in unique[:30]) or "(none)", teams=teams, max=CANDIDATES,
        goals="\n".join(f"- {gid}: {gname} · {dname}" for gid, gname, dname in goals) or "(none)",
        checks=", ".join(f"{c.key}: {c.title}" for c in picked) or "(none)")
    if found_before:
        task += ("\n\nAlready found and shown to them (don't repeat these or variations of them; find different "
                 "gaps):\n" + "\n".join(f"- {t}" for t in found_before[:40]))
    result = await claude.create(campaign_id=None, run_id=None, purpose="opportunity scan", task="findings",
                                 system=STRUCTURE_SYSTEM.format(threshold=MILESTONES_ABOVE_USD)
                                 + "\n\nFor fixes that reach people one to one (buyers with a trigger, people asking, "
                                   "competitors' unhappy customers):\n" + OUTREACH_KNOWHOW,
                                 messages=[{"role": "user", "content": task}], max_tokens=12000,
                                 output_format=findings_schema(goal_schema, [c.key for c in picked]))
    cost += result.cost
    raw = json.loads(_texts(result.content) or "{}")

    known = {gid for gid, _, _ in goals}
    allowed = {x["url"] for x in unique}
    findings, created = [], []
    scanned_at = utcnow().isoformat()
    seen_titles = {_norm_title(t) for t in found_before}  # "find more": nothing that repeats an earlier finding
    for f in balanced([f for f in raw.get("findings") or [] if f.get("title") and f.get("evidence")
                       and _norm_title(f["title"]) not in seen_titles]):
        goal_id = f.get("goal_id") if f.get("goal_id") in known else ""
        steps = _milestones(f.get("milestones") or [], per, basis, n, org_setup)
        if steps:
            # Step 1 is ready to turn on now; later steps become goals when someone asks for them.
            first = await create_goal(org_id, requested_by, f["team_kind"], steps[0]["spec"])
            steps[0]["goal_id"] = first
            if first:
                created.append(first)
                goal_id = goal_id or first
        elif not goal_id and f.get("new_goal"):
            goal = org_setup._tidy_goal(f["new_goal"])
            if goal:
                goal["budget_basis"] = estimate.starter(per, goal["cycle_hours"], goal["duration_days"],
                                                        goal["paid_spend_usd"], basis, n)
                goal["budget_usd"] = goal["budget_basis"]["suggested_usd"]
                goal_id = await create_goal(org_id, requested_by, f["team_kind"], goal) or ""
                if goal_id:
                    created.append(goal_id)
        urls = [u for u in f.get("source_urls") or [] if isinstance(u, str) and u.startswith("http")]
        findings.append({
            "check": f.get("check") or "", "team_kind": f["team_kind"], "title": f["title"][:120], "found_at": scanned_at,
            "evidence": f["evidence"][:600], "impact": f.get("impact", "")[:400],
            "points": [str(x)[:200] for x in f.get("points") or [] if str(x).strip()][:4],
            "estimate": f.get("estimate", "")[:120], "assumption": f.get("assumption", "")[:300],
            "confidence": f.get("confidence", "medium"),
            "metric_name": str(f.get("metric_name", ""))[:80], "metric_now": str(f.get("metric_now", ""))[:40],
            "metric_goal": str(f.get("metric_goal", ""))[:40], "pull": int(f.get("pull") or 3),
            "sources": [u for u in urls if u in allowed][:4] or urls[:2],  # prefer sources really seen
            "goal_id": goal_id or None,
            "milestones": steps,
            "total_usd": round(sum(m["total_usd"] for m in steps), 2) if steps else None,
        })
    fresh = {
        "findings": findings, "unlock": catalog.unlockable(pack_key), "scanned_at": scanned_at,
        "goals_added": created,
        "checks": [{"key": c.key, "title": c.title, "method": c.method, "team": c.team, **reasons.get(c.key, {})}
                   for c in picked],
        "visibility": {"domain": mine, "competitors": competitors, "markets": [x["label"] for x in markets],
                       "source": "google" if m.get("google") else "web", "search": search, "ai": ai,
                       "local": m.get("local") or [], "highlights": highlights(search, ai)},
        "scorecard": rows,
    }
    async with session_scope() as s:
        org = await s.get(Organization, org_id)
        old = dict((org.profile or {}).get("opportunities") or {}) if more else {}
        if old:
            vis = fresh["visibility"]
            rows_by_key = {r.get("key"): r for r in old.get("scorecard") or []}
            rows_by_key.update({r.get("key"): r for r in rows})
            fresh = {**fresh,
                     "findings": (old.get("findings") or []) + findings,
                     "goals_added": (old.get("goals_added") or []) + created,
                     "checks": (old.get("checks") or []) + fresh["checks"],
                     "visibility": vis if (vis["search"] or vis["ai"]) else old.get("visibility") or vis,
                     "scorecard": list(rows_by_key.values()),
                     "rounds": int(old.get("rounds") or 1) + 1}
        org.profile = {**(org.profile or {}), "opportunities": fresh}
    return {"findings": findings, "ran": len(picked), "cost": cost, "new": len(findings), "goals": created}


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()




SEARCH_KEYS = {"search_rank", "comparison_searches", "content_gaps"}
VISIBILITY = {"search_rank", "ai_answers", "content_gaps"}  # one finding between them, at most
_VISIBILITY_WORDS = re.compile(r"chatgpt|perplexity|gemini|claude|ai assistant|ai answer|ai overview|google rank|search rank"
                               r"|page 1|first page of google", re.I)


def _theme(f: dict) -> str:
    key = f.get("check") or ""
    if key in VISIBILITY or (key not in catalog.BY_KEY and _VISIBILITY_WORDS.search(f.get("title") or "")):
        return "visibility"
    return key or (f.get("title") or "").lower()


def balanced(found: list[dict]) -> list[dict]:
    """The SHOW findings the company will most want to fix, one per check (and one about search and
    AI-assistant visibility at most). One outside sales and marketing joins only if it's strong
    (pull >= STRONG); a weak one is never added for variety."""
    ranked, themes = [], set()
    for f in sorted(found, key=lambda f: -int(f.get("pull") or 3)):  # stable: Claude's order breaks ties
        if _theme(f) not in themes:
            themes.add(_theme(f))
            ranked.append(f)
    top = ranked[:SHOW]
    if top and all(f.get("team_kind") in catalog.GTM for f in top):
        other = next((f for f in ranked[SHOW:] if f.get("team_kind") not in catalog.GTM
                      and int(f.get("pull") or 0) >= STRONG), None)
        if other:
            top = top[:-1] + [other]
    return top


def _milestones(raw: list[dict], per: float, basis: str, n: int, org_setup) -> list[dict]:
    """Each milestone with its price: AI work sessions over its length plus the itemised spend."""
    out = []
    for m in raw[:3]:
        goal = org_setup._tidy_goal(m.get("goal") or {})
        if goal is None or not m.get("name"):
            continue
        days = round(min(max(float(m.get("weeks") or 4) * 7, 7), MAX_MILESTONE_DAYS))
        items = [{"item": str(i.get("item", ""))[:80], "usd": round(max(float(i.get("usd") or 0), 0), 2)}
                 for i in m.get("paid_items") or [] if i.get("item")][:6]
        paid = sum(i["usd"] for i in items)
        budget = estimate.compute(per, goal["cycle_hours"], days, paid, basis, n,
                                  max_sessions=int(m.get("sessions") or 0) or None)
        goal.update(duration_days=days, paid_spend_usd=paid, budget_basis={**budget, "milestone": True},
                    budget_usd=budget["suggested_usd"])
        out.append({"name": m["name"][:120], "outcome": (m.get("outcome") or "")[:300], "weeks": round(days / 7, 1),
                    "ai_usd": budget["ai_usd"], "paid_usd": round(paid, 2), "paid_items": items,
                    "total_usd": budget["suggested_usd"], "goal_id": None, "spec": goal,
                    "does": [st["text"] for st in goal.get("steps") or []][:4]})
    if len(out) > 1 and sum(m["total_usd"] for m in out) <= MILESTONES_ABOVE_USD:
        out = out[:1]  # small enough to do in one go
    return out


# When a company doesn't have the team a fix belongs to, the closest team that can do the work.
CLOSEST: dict[str, list[str]] = {
    "it": ["engineering", "operations"], "legal": ["operations", "exec"], "finance": ["operations", "exec"],
    "support": ["success"], "success": ["support"], "product": ["engineering"], "hiring": ["exec", "operations"],
    "store": ["marketing"], "pr": ["marketing"], "community": ["marketing"], "partnerships": ["sales"],
}


async def create_goal(org_id: str, requested_by: str | None, team_kind: str, goal: dict, s=None) -> str | None:
    """A draft goal in the function that fixes a gap (the closest one the company has, else that
    function is added). Uses `s` when given (a request's session), else its own."""
    if s is None:
        async with session_scope() as own:
            return await create_goal(org_id, requested_by, team_kind, goal, own)
    from app.agent import org_setup

    dept = None
    for kind in [team_kind] + CLOSEST.get(team_kind, []):  # the right team, else the closest one the company has
        dept = (await s.execute(select(Department).where(Department.org_id == org_id, Department.kind == kind)
                                .order_by(Department.created_at).limit(1))).scalar_one_or_none()
        if dept is not None:
            break
    if dept is None:  # goals come first now: the function is just how goals are grouped, so add it
        admins = [u for (u,) in (await s.execute(
            select(Membership.user_id).where(Membership.org_id == org_id,
                                             Membership.role.in_([Role.owner.value, Role.admin.value])))).all()]
        kind = team_kind if team_kind in PRESET_NAMES else "exec"
        dept = await add_department(s, org_id, PRESET_NAMES[kind], kind, members=admins)
    agent = (await s.execute(select(Agent).where(Agent.department_id == dept.id)
                             .order_by(Agent.created_at).limit(1))).scalar_one_or_none()
    if agent is None:
        agent = Agent(org_id=org_id, department_id=dept.id, name=default_agent_name(dept.name))
        s.add(agent)
        await s.flush()
    org = await s.get(Organization, org_id)
    names = {x.lower() for (x,) in (await s.execute(select(Campaign.name).where(Campaign.org_id == org_id))).all()}
    created: dict = {"goals": []}
    await org_setup._add_goals(s, org_id, requested_by, agent, [goal], names,
                               org_setup.company_context(org, org.profile or {}), created)
    return created["goals"][0] if created["goals"] else None


async def milestone_goal(s, org_id: str, requested_by: str | None, finding: int, step: int) -> str | None:
    """Turn a later milestone into a draft goal (when someone wants to go further), in session `s`."""
    org = await s.get(Organization, org_id)
    opp = dict((org.profile or {}).get("opportunities") or {})
    items = [dict(x) for x in opp.get("findings") or []]
    if not (0 <= finding < len(items)) or not (0 <= step < len(items[finding].get("milestones") or [])):
        return None
    steps = [dict(x) for x in items[finding]["milestones"]]
    m = steps[step]
    if m.get("goal_id") and await s.get(Campaign, m["goal_id"]) is not None:
        return m["goal_id"]
    goal_id = await create_goal(org_id, requested_by, items[finding]["team_kind"], dict(m["spec"]), s)
    if goal_id:
        steps[step]["goal_id"] = goal_id
        items[finding] = {**items[finding], "milestones": steps}
        org.profile = {**(org.profile or {}), "opportunities": {**opp, "findings": items}}
    return goal_id


async def unlock_goal(s, org_id: str, requested_by: str | None, check_key: str) -> str | None:
    """"Connect to unlock": a draft goal for the team's AI employee that runs a check on the company's
    own data. Starting it connects the tool. Returns the goal (an existing one with the same name if
    there is one), or None when the company has no such team."""
    from app.agent import org_setup

    c = catalog.BY_KEY.get(check_key)
    if c is None or c.method != "tool" or not c.goal:
        return None
    existing = (await s.execute(select(Campaign.id).where(Campaign.org_id == org_id, Campaign.name == c.goal))).scalar_one_or_none()
    if existing:
        return existing
    label = TOOLS[c.tool].label if c.tool in TOOLS else c.tool
    goal = org_setup._tidy_goal({
        "name": c.goal, "goal_description": c.goal_how + ".", "done_when": "The list is done and the top items are fixed",
        "primary_metric": "items fixed", "target_value": None, "target_period": "week", "category": "", "use_case": c.title,
        "cycle_hours": 24, "duration_days": 30, "paid_spend_usd": 0, "channels": [label],
        "steps": [{"text": f"Read {label} and find: {c.how.lower()}", "action_type": "read_data", "tool": c.tool},
                  {"text": "Write a short report: what was found and what to fix first", "action_type": "create_draft", "tool": "none"},
                  {"text": "Fix or follow up on each, after your OK", "action_type": "other_write", "tool": c.tool}],
        "why": f"Connecting {label} lets Oton check this on your own data.",
        "first_week": f"A list of {c.title.lower()}, with what to do about each", "start_here": False, "key_results": []})
    if goal is None:
        return None
    per, basis, n = await estimate.session_cost(s, org_id)
    goal["budget_basis"] = estimate.starter(per, goal["cycle_hours"], goal["duration_days"], 0, basis, n)
    goal["budget_usd"] = goal["budget_basis"]["suggested_usd"]
    return await create_goal(org_id, requested_by, c.team, goal, s)
