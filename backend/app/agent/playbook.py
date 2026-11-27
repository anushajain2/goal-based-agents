"""A goal's plan, in plain steps people can read before they start it.

Each step names the riskiest kind of action it involves (see services/policy.ACTION_TYPES)
and the main tool it uses. The kind of action is what decides, live, whether that step
happens on its own or waits for someone's approval, so the plan people see always matches
what the policy engine will actually enforce.
"""

from __future__ import annotations

import json
import logging
import re

from app.agent.llm import MeteredClaude
from app.catalog import CHANNEL_TOOLS, TOOLS, tool_for
from app.models import Campaign
from app.services.policy import ACTION_TYPES, READ_ONLY

log = logging.getLogger(__name__)

MAX_STEPS = 7
TOOL_CHOICES = list(TOOLS) + ["web", "none"]


def step_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "One plain sentence: what it does in this step"},
            "action_type": {"type": "string", "enum": list(ACTION_TYPES)},
            "tool": {"type": "string", "enum": TOOL_CHOICES},
        },
        "required": ["text", "action_type", "tool"],
        "additionalProperties": False,
    }


STEP_GUIDANCE = """Steps: 3 to 6 plain-English steps, in order, saying how Oton will \
pursue the goal: what a skilled person would actually do to hit it. Keep preparing and doing apart, so approval points are obvious: "Write a \
personalised first email to each person" (create_draft) comes before "Send each email" \
(send_message). action_type is the riskiest kind of action in the step: research, read_data, \
create_draft and propose_code happen on their own; engage (likes, follows), reply (replies and \
comments), publish_post, publish_article, send_message, modify_account, delete_content, \
spend_money, merge_content (small content-only pull requests), merge_code and other_write go \
through the goal's permissions (asking first unless the team allowed more). \
tool is the main tool the step uses: a listed tool, "web" for web research and browsing, or \
"none"."""


# What a good founder or SDR knows about reaching people one to one. Given to the plan, the steps
# and every work session of an outreach goal (see is_outreach): know-how, not rules.
OUTREACH_KNOWHOW = """How good outreach works (use what fits this goal and audience):
- Open with something specific and useful about them, not about you: a finding about their company, \
a trigger you noticed (funding, a new hire, a launch), a sharp observation about their market. End \
with one small ask ("Want the full list?"), not a pitch.
- Warm up where they're active: a genuinely useful reply or comment on a recent post, a day or two \
before the message, so your name isn't new.
- Use the channel they actually use: LinkedIn for most B2B buyers (a connection request with a short \
personal note, the message once they accept); email for volume and as the second touch; X DMs for \
people active on X, after a reply; Instagram mainly for consumer brands and shops.
- Sequence: warm-up, first message, one follow-up 3-5 days later on another channel that adds \
something new, then stop. Two unanswered messages is the limit.
- Protect the sender: cold email goes from a separate domain set up for outreach (SPF, DKIM, \
DMARC) and warmed up gradually before volume; stay well within LinkedIn's weekly connection limits; \
start small and grow as replies come in.
- Learn by channel: for each person note the channel and the opener used; keep the totals (sent, \
replies, meetings) by channel and opener with record_channel_results, and double down on what books \
calls."""

_OUTREACH_WORDS = re.compile(r"outbound|outreach|prospect|meetings?|demos?|discovery calls?|replies|intro|"
                             r"new clients?|client acquisition|cold|leads?\b|book(ed|ing)? calls?", re.I)


def is_outreach(c: Campaign) -> bool:
    """Whether a goal is about reaching people one to one (cold or warm outreach)."""
    steps = (c.playbook or {}).get("steps") or []
    if any(st.get("action_type") == "send_message" for st in steps):
        return True
    text = " ".join(str(x or "") for x in (c.name, c.use_case, c.primary_metric, c.category))
    return bool(_OUTREACH_WORDS.search(text))


def default_key_results(metric: str, target: float | None) -> list[str]:
    return [f"{target:g} {metric}" if target else f"Grow {metric}"]


def tidy_key_results(krs: list | None) -> list[str]:
    return [str(k).strip()[:160] for k in (krs or []) if str(k).strip()][:3]


def tidy_steps(steps: list[dict] | None) -> list[dict]:
    out = []
    for st in steps or []:
        text = (st.get("text") or "").strip()
        if not text:
            continue
        action_type = st.get("action_type") if st.get("action_type") in ACTION_TYPES else "other_write"
        tool = st.get("tool") if st.get("tool") in TOOL_CHOICES else "none"
        out.append({"text": text[:300], "action_type": action_type, "tool": tool})
        if len(out) >= MAX_STEPS:
            break
    return out


def default_playbook(c: Campaign) -> dict:
    """Used without a Claude key: a sensible outline from the goal's channels."""
    tools = [t.key for t in (tool_for(ch) for ch in c.channels or []) if t]
    main = tools[0] if tools else "gmail"
    outreach = is_outreach(c) or main in ("gmail", "outlook")
    if outreach:
        steps = [
            {"text": "Get the sending basics ready: a separate outreach domain with email authentication, warmed up, "
                     "and a booking link", "action_type": "modify_account", "tool": "web"},
            {"text": "Find people who fit, each with something specific about them (a trigger, a finding)",
             "action_type": "research", "tool": "web"},
            {"text": "Warm up with a useful reply or comment on a recent post", "action_type": "reply", "tool": "linkedin"},
            {"text": "Write a short first message that leads with that specific thing", "action_type": "create_draft", "tool": main},
            {"text": "Send it on the channel they use, then one follow-up on another channel, then stop",
             "action_type": "send_message", "tool": main},
            {"text": f"Book calls and record {c.primary_metric} by channel and opener", "action_type": "read_data", "tool": main},
        ]
        return {"steps": steps, "source": "default", "key_results": default_key_results(c.primary_metric, c.target_value)}
    steps = [
        {"text": f"Research who and what matters for: {c.goal_description[:120]}", "action_type": "research", "tool": "web"},
        {"text": "Build a list of the best people, companies or places to focus on", "action_type": "research", "tool": "web"},
        {"text": "Write the messages or posts, tailored to each one", "action_type": "create_draft", "tool": main},
        {"text": "Send or publish them, one by one", "action_type": "send_message" if outreach else "publish_post", "tool": main},
        {"text": f"Follow up and count {c.primary_metric}", "action_type": "send_message" if outreach else "read_data", "tool": main},
    ]
    return {"steps": steps, "source": "default", "key_results": default_key_results(c.primary_metric, c.target_value)}


async def generate_playbook(claude: MeteredClaude, c: Campaign) -> dict:
    """Ask Claude for the plan of one goal (charged to that goal's budget; a few cents)."""
    tools_list = ", ".join(f"{k} ({t.label})" for k, t in TOOLS.items())
    prompt = (
        f"Goal: {c.goal_description}\n"
        f"Counts as done when: {c.done_when or '(not given)'}\n"
        f"Progress measured as: {c.primary_metric}" + (f" (target {c.target_value:g})" if c.target_value else "") + "\n"
        f"Preferred channels: {', '.join(c.channels) if c.channels else 'any'}\n"
        f"Context:\n{(c.context or '(none)')[:3000]}\n\n"
        f"Tools available: {tools_list}.\n\n{STEP_GUIDANCE}\n\n"
        + (f"{OUTREACH_KNOWHOW}\n\n" if is_outreach(c) else "")
        + "Also give 2 or 3 key_results: short, measurable "
        "outcomes that show the goal is on track (the first is the goal's own target), e.g. '8 discovery calls held'."
    )
    result = await claude.create(
        campaign_id=c.id, run_id=None, purpose="plan of action", task="goal_steps",
        system="You plan how Oton will achieve a business goal. It researches, builds lists, "
               "writes, sends, posts and uses the company's apps, and asks a person before anything public, "
               "outgoing or paid. Be concrete and brief. In the steps, don't call it an AI employee, agent or "
               "lead: talk about the goal and say Oton does the work.",
        messages=[{"role": "user", "content": prompt}], max_tokens=4000,
        output_format={"type": "json_schema", "schema": {
            "type": "object", "properties": {"steps": {"type": "array", "items": step_schema()},
                                             "key_results": {"type": "array", "items": {"type": "string"}}},
            "required": ["steps", "key_results"], "additionalProperties": False}},
    )
    text = "\n".join(b.get("text", "") for b in result.content if b.get("type") == "text")
    try:
        data = json.loads(text)
        steps, krs = tidy_steps(data.get("steps")), tidy_key_results(data.get("key_results"))
    except (json.JSONDecodeError, AttributeError):
        steps, krs = [], []
    if not steps:
        return default_playbook(c)
    return {"steps": steps, "source": "generated", "key_results": krs or default_key_results(c.primary_metric, c.target_value)}


def tools_needed(c: Campaign) -> list[dict]:
    """The tools a goal's plan uses, with the steps that use each and whether those steps
    change anything outside Oton (then the tool is needed, not just useful)."""
    found: dict[str, dict] = {}
    steps = (c.playbook or {}).get("steps") or []
    for i, st in enumerate(steps):
        tool = TOOLS.get(st.get("tool") or "")
        if not tool:
            continue
        entry = found.setdefault(tool.key, {**tool.as_dict(), "steps": [], "required": False})
        entry["steps"].append(i + 1)
        if st.get("action_type") not in READ_ONLY:
            entry["required"] = True
    for ch in c.channels or []:
        key = CHANNEL_TOOLS.get(ch.strip().lower())
        tool = TOOLS.get(key or ch.strip().lower())
        if tool and tool.key not in found:
            found[tool.key] = {**tool.as_dict(), "steps": [], "required": False}
    return list(found.values())
