"""How a goal gets hit, and what the AI employee is learning along the way.

Stored on the goal (Campaign.approach):

  model        the goal broken into its funnel, e.g. contacts -> replies -> meetings, with the
               current number and a benchmark for each stage, and which stage is the bottleneck.
               Every session's plan has to work on the bottleneck.
  approaches   the ways it will pursue the goal: the obvious ones and creative ones (an X thread,
               a short video, a community, a free tool...), each with its status
               (planned, testing, working, dropped).
  experiments  one change at a time against a baseline, judged after enough attempts, then kept
               or dropped.
  learnings    what worked and what didn't, with the evidence; every future session sees them.

It's made when a goal is about to start (shown to people before they turn it on), and the
strategist updates it at the start of every session. People see a short update whenever there
is something new: what was measured, what was learned, and what's changing.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from app.agent.llm import MeteredClaude
from app.agent.playbook import TOOL_CHOICES
from app.catalog import TOOLS
from app.models import Campaign, utcnow

log = logging.getLogger(__name__)

MAX_STAGES = 5
MAX_APPROACHES = 7
MAX_LEARNINGS = 12
MAX_EXPERIMENTS = 10
STATUSES = ("planned", "testing", "working", "dropped")

SYSTEM = """You design how an AI employee will hit a business goal. It researches, builds lists, \
writes, designs, sends, posts and uses the company's apps, and asks a person before anything public, \
outgoing or paid. Think like the best person for this job, not a template.

1. The model: break the goal's number into the 2-5 stages that produce it, as a funnel, e.g. for \
meetings: "Prospects contacted" -> "Replies" -> "Meetings booked"; for signups: "Visitors" -> \
"Signups". For each stage give a realistic benchmark for this kind of company (e.g. "5-10% reply \
rate"). Name the stage most likely to be the bottleneck at the start, and why.
2. The approaches: 4-7 ways to pursue it, best first. Include the obvious ones done well, AND at \
least two creative ones that fit this goal and audience: e.g. an X or LinkedIn thread series, a \
short demo or explainer video (script and storyboard, made with a connected video tool), a free \
calculator or template, a webinar, a community or podcast appearance, a partnership, a teardown of \
a well-known example, user-generated content, a giveaway. No spam, fake engagement or misleading \
claims. For each: what it does in one line, why it fits, the main tool, and which milestone it \
belongs to when the goal has milestones (else 1).
3. The first experiment worth running, as a hypothesis with the change and how many attempts to \
judge it on.

The owner reads this before turning it on, so write for a busy person, in plain words: stage names \
of 1-3 words; the bottleneck's "why" in one short sentence; each approach named in under 6 words and \
described in under 15 words, saying what it does for them. No jargon or acronyms (say "bid \
comparison", not "TBE")."""


def schema() -> dict:
    stage = {"type": "object", "properties": {
        "name": {"type": "string"}, "benchmark": {"type": "string", "description": "e.g. '5-10% of contacts reply'"},
        "unit": {"type": "string", "description": "e.g. 'a week'"}},
        "required": ["name", "benchmark", "unit"], "additionalProperties": False}
    approach = {"type": "object", "properties": {
        "name": {"type": "string", "description": "Under 6 words, e.g. 'Founder-led X thread series'"},
        "what": {"type": "string", "description": "What it does for them, under 15 plain words"},
        "why": {"type": "string"}, "creative": {"type": "boolean"},
        "tool": {"type": "string", "enum": TOOL_CHOICES}, "milestone": {"type": "integer"}},
        "required": ["name", "what", "why", "creative", "tool", "milestone"], "additionalProperties": False}
    return {"type": "json_schema", "schema": {"type": "object", "properties": {
        "stages": {"type": "array", "items": stage},
        "bottleneck": {"type": "string"}, "bottleneck_why": {"type": "string"},
        "approaches": {"type": "array", "items": approach},
        "experiment": {"type": "object", "properties": {
            "hypothesis": {"type": "string"}, "change": {"type": "string"}, "judge_after": {"type": "string"}},
            "required": ["hypothesis", "change", "judge_after"], "additionalProperties": False}},
        "required": ["stages", "bottleneck", "bottleneck_why", "approaches", "experiment"], "additionalProperties": False}}


def _id() -> str:
    return uuid.uuid4().hex[:8]


def tidy(data: dict, c: Campaign) -> dict:
    stages = [{"name": str(x.get("name", ""))[:60], "benchmark": str(x.get("benchmark", ""))[:80],
               "unit": str(x.get("unit", ""))[:30], "now": None}
              for x in data.get("stages") or [] if x.get("name")][:MAX_STAGES]
    if not stages:
        stages = [{"name": c.primary_metric or "Results", "benchmark": "", "unit": "", "now": None}]
    names = [s["name"] for s in stages]
    bottleneck = data.get("bottleneck") if data.get("bottleneck") in names else names[0]
    approaches = [{"id": _id(), "name": str(x.get("name", ""))[:60], "what": str(x.get("what", ""))[:200],
                   "why": str(x.get("why", ""))[:200], "creative": bool(x.get("creative")),
                   "tool": x.get("tool") if x.get("tool") in TOOL_CHOICES else "none",
                   "milestone": max(int(x.get("milestone") or 1), 1), "status": "planned"}
                  for x in data.get("approaches") or [] if x.get("name")][:MAX_APPROACHES]
    exp = data.get("experiment") or {}
    experiments = [{"id": _id(), "hypothesis": exp["hypothesis"][:200], "change": str(exp.get("change", ""))[:200],
                    "judge_after": str(exp.get("judge_after", ""))[:80], "status": "planned", "result": "",
                    "started": None, "ended": None}] if exp.get("hypothesis") else []
    return {"model": {"stages": stages, "bottleneck": bottleneck, "why": str(data.get("bottleneck_why", ""))[:240]},
            "approaches": approaches, "experiments": experiments, "learnings": [], "updates": 0,
            "made": utcnow().isoformat()}


def default(c: Campaign) -> dict:
    """Without a Claude key: a plain funnel and the plan's own steps as approaches."""
    steps = (c.playbook or {}).get("steps") or []
    return tidy({"stages": [{"name": "Work done", "benchmark": "", "unit": "a week"},
                            {"name": c.primary_metric or "Results", "benchmark": "", "unit": "a week"}],
                 "bottleneck": "Work done", "bottleneck_why": "Nothing measured yet.",
                 "approaches": [{"name": st["text"][:60], "what": st["text"], "why": "", "creative": False,
                                 "tool": st.get("tool", "none"), "milestone": 1} for st in steps[:5]]}, c)


async def generate(claude: MeteredClaude, c: Campaign, milestones: list[dict] | None = None) -> dict:
    """Charged to the goal's budget (a few cents)."""
    tools = ", ".join(f"{k} ({t.label})" for k, t in TOOLS.items())
    steps = "\n".join(f"- {st['text']}" for st in (c.playbook or {}).get("steps") or [])
    stones = "\n".join(f"{i}. {m['name']} ({m['weeks']:g} weeks): {m.get('outcome', '')}"
                       for i, m in enumerate(milestones or [], 1))
    prompt = (f"Goal: {c.name}\n{c.goal_description}\nCounts when: {c.done_when or '(not given)'}\n"
              f"Number: {c.primary_metric}" + (f" (target {c.target_value:g})" if c.target_value else "") + "\n"
              f"Channels people suggested: {', '.join(c.channels) if c.channels else 'any'}\n"
              f"Company context:\n{(c.context or '(none)')[:3000]}\n\n"
              f"The plan people agreed to:\n{steps or '(none yet)'}\n\n"
              + (f"Milestones:\n{stones}\n\n" if stones else "")
              + f"Tools available: {tools}.")
    result = await claude.create(campaign_id=c.id, run_id=None, purpose="how this goal gets hit", role="planner",
                                 system=SYSTEM, messages=[{"role": "user", "content": prompt}], max_tokens=6000,
                                 output_format=schema())
    text = "\n".join(b.get("text", "") for b in result.content if b.get("type") == "text")
    try:
        return tidy(json.loads(text), c)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return default(c)


# --- every session: the strategist's updates ----------------------------------------------------

def plan_fields(approach: dict | None) -> dict:
    """What the strategist returns each session, on top of its plan (merged into its schema)."""
    names = [s["name"] for s in ((approach or {}).get("model") or {}).get("stages") or []] or ["Results"]
    ap_names = [a["name"] for a in (approach or {}).get("approaches") or []] or [""]
    return {
        "stages": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string", "enum": names}, "now": {"anyOf": [{"type": "number"}, {"type": "null"}]}},
            "required": ["name", "now"], "additionalProperties": False}},
        "bottleneck": {"type": "string", "enum": names},
        "bottleneck_why": {"type": "string"},
        "focus": {"type": "array", "items": {"type": "string", "enum": ap_names},
                  "description": "The approaches this session works on"},
        "approach_status": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string", "enum": ap_names}, "status": {"type": "string", "enum": list(STATUSES)}},
            "required": ["name", "status"], "additionalProperties": False}},
        "new_approach": {"anyOf": [{"type": "null"}, {"type": "object", "properties": {
            "name": {"type": "string"}, "what": {"type": "string"}, "why": {"type": "string"},
            "creative": {"type": "boolean"}, "tool": {"type": "string", "enum": TOOL_CHOICES}},
            "required": ["name", "what", "why", "creative", "tool"], "additionalProperties": False}]},
        "experiment": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["none", "start", "keep", "drop"]},
            "hypothesis": {"type": "string"}, "change": {"type": "string"}, "judge_after": {"type": "string"},
            "result": {"type": "string", "description": "For keep or drop: what the numbers showed"}},
            "required": ["action", "hypothesis", "change", "judge_after", "result"], "additionalProperties": False},
        "learnings": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "evidence": {"type": "string"}},
            "required": ["text", "evidence"], "additionalProperties": False}},
        "update": {"type": "object", "properties": {
            "measured": {"type": "string"}, "learned": {"type": "string"}, "changing": {"type": "string"}},
            "required": ["measured", "learned", "changing"], "additionalProperties": False},
    }


PLAN_GUIDANCE = """Also, every session:
- stages: the latest number for each stage of the funnel (null if unknown); bottleneck: the stage \
holding the goal back now, and why. The plan must work on the bottleneck first.
- focus: the approaches this session works on. Keep the obvious ones going, and give the creative \
ones a real try when the obvious ones plateau. approach_status: change an approach's status when \
the numbers say so (testing, working, dropped). new_approach: a better idea you've found, or null.
- experiment: one change at a time. "start" a new one (hypothesis, the change, judged after how many \
attempts) only when none is running; "keep" or "drop" the running one once it has enough attempts, \
with the result in numbers; otherwise "none".
- learnings: up to 2 new things you're now confident about, each with its evidence. Not guesses.
- update: a short note for the team, like a good employee's, only when there's something new since \
the last one (otherwise all three empty): measured (the numbers that moved), learned (what that \
tells us), changing (what you'll do differently). One sentence each, plain words, real numbers."""


def apply(c: Campaign, data: dict, now: datetime | None = None) -> dict | None:
    """Apply the strategist's session output to the goal. Returns the update to post, if any."""
    a = dict(c.approach or {})
    if not a:
        return None
    now = now or utcnow()
    model = dict(a.get("model") or {})
    stages = [dict(s) for s in model.get("stages") or []]
    for x in data.get("stages") or []:
        for s in stages:
            if s["name"] == x.get("name") and isinstance(x.get("now"), (int, float)):
                s["now"] = float(x["now"])
    model["stages"] = stages
    if data.get("bottleneck") in [s["name"] for s in stages]:
        if data["bottleneck"] != model.get("bottleneck"):
            model["moved_at"] = now.isoformat()
        model["bottleneck"] = data["bottleneck"]
        model["why"] = str(data.get("bottleneck_why", ""))[:240] or model.get("why", "")
    a["model"] = model

    approaches = [dict(x) for x in a.get("approaches") or []]
    focus = set(data.get("focus") or [])
    for x in approaches:
        x["focus"] = x["name"] in focus
        if x["focus"] and x.get("status") == "planned":
            x["status"] = "testing"
    for x in data.get("approach_status") or []:
        for ap in approaches:
            if ap["name"] == x.get("name") and x.get("status") in STATUSES:
                ap["status"] = x["status"]
    new = data.get("new_approach")
    if new and new.get("name") and all(ap["name"] != new["name"] for ap in approaches) and len(approaches) < MAX_APPROACHES + 3:
        approaches.append({"id": _id(), "name": new["name"][:60], "what": str(new.get("what", ""))[:200],
                           "why": str(new.get("why", ""))[:200], "creative": bool(new.get("creative")),
                           "tool": new.get("tool") if new.get("tool") in TOOL_CHOICES else "none",
                           "milestone": 1, "status": "testing", "focus": True, "added": now.isoformat()})
    a["approaches"] = approaches

    experiments = [dict(x) for x in a.get("experiments") or []]
    running = next((x for x in experiments if x["status"] == "running"), None)
    exp = data.get("experiment") or {}
    act = exp.get("action")
    if act == "start" and not running:
        waiting = next((x for x in experiments if x["status"] == "planned"), None)
        if waiting and not exp.get("hypothesis"):
            waiting.update(status="running", started=now.isoformat())
        elif exp.get("hypothesis"):
            experiments = [x for x in experiments if x["status"] != "planned"]
            experiments.append({"id": _id(), "hypothesis": exp["hypothesis"][:200], "change": str(exp.get("change", ""))[:200],
                                "judge_after": str(exp.get("judge_after", ""))[:80], "status": "running", "result": "",
                                "started": now.isoformat(), "ended": None})
    elif act in ("keep", "drop") and running:
        running.update(status="kept" if act == "keep" else "dropped", result=str(exp.get("result", ""))[:240],
                       ended=now.isoformat())
    a["experiments"] = experiments[-MAX_EXPERIMENTS:]

    learnings = list(a.get("learnings") or [])
    for x in (data.get("learnings") or [])[:2]:
        if x.get("text") and all(x["text"] != l["text"] for l in learnings):
            learnings.append({"text": x["text"][:200], "evidence": str(x.get("evidence", ""))[:200], "at": now.isoformat()})
    a["learnings"] = learnings[-MAX_LEARNINGS:]

    update = data.get("update") or {}
    posted = None
    if any((update.get(k) or "").strip() for k in ("measured", "learned", "changing")):
        posted = {k: (update.get(k) or "").strip()[:300] for k in ("measured", "learned", "changing")}
        a["updates"] = int(a.get("updates") or 0) + 1
        a["last_update_at"] = now.isoformat()
    c.approach = a
    return posted


def brief_text(approach: dict | None, pace_text: str = "") -> str:
    """For the session brief: how the goal gets hit, the pace, approaches, experiments, learnings."""
    a = approach or {}
    lines: list[str] = []
    model = a.get("model") or {}
    if model.get("stages"):
        lines += ["", "## How this goal gets hit (work on the bottleneck first)"]
        for s in model["stages"]:
            now = f"{s['now']:g}" if isinstance(s.get("now"), (int, float)) else "not measured yet"
            mark = "  <- bottleneck" if s["name"] == model.get("bottleneck") else ""
            lines.append(f"- {s['name']}: {now}{' ' + s['unit'] if s.get('unit') else ''}"
                         f"{' (benchmark: ' + s['benchmark'] + ')' if s.get('benchmark') else ''}{mark}")
        if model.get("why"):
            lines.append(f"Why it's the bottleneck: {model['why']}")
    if pace_text:
        lines += ["", "## Pace", pace_text]
    if a.get("approaches"):
        lines += ["", "## Approaches (status)"]
        lines += [f"- {x['name']} [{x.get('status', 'planned')}{', creative' if x.get('creative') else ''}]: {x['what']}"
                  for x in a["approaches"]]
    exps = a.get("experiments") or []
    if exps:
        lines += ["", "## Experiments"]
        for x in exps[-4:]:
            lines.append(f"- [{x['status']}] {x['hypothesis']} (change: {x['change']}; judge after {x['judge_after']})"
                         + (f" Result: {x['result']}" if x.get("result") else ""))
    if a.get("learnings"):
        lines += ["", "## What we've learned (keep doing what works)"]
        lines += [f"- {x['text']} ({x['evidence']})" for x in a["learnings"]]
    return "\n".join(lines)
