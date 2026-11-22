"""A goal's plan, in plain steps people can read before they start it.

Each step names the riskiest kind of action it involves (see services/policy.ACTION_TYPES)
and the main tool it uses. The kind of action is what decides, live, whether that step
happens on its own or waits for someone's approval, so the plan people see always matches
what the policy engine will actually enforce.
"""

from __future__ import annotations

import json
import logging

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


STEP_GUIDANCE = """Steps: 3 to 6 plain-English steps, in order, saying how the AI employee will \
pursue the goal. Keep preparing and doing apart, so approval points are obvious: "Write a \
personalised first email to each person" (create_draft) comes before "Send each email" \
(send_message). action_type is the riskiest kind of action in the step: research, read_data \
and create_draft happen on their own; engage, publish_post, publish_article, send_message, \
modify_account, delete_content, spend_money and other_write wait for a person's approval. \
tool is the main tool the step uses: a listed tool, "web" for web research and browsing, or \
"none"."""


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
    outreach = main in ("gmail", "outlook", "linkedin", "twitter")
    steps = [
        {"text": f"Research who and what matters for: {c.goal_description[:120]}", "action_type": "research", "tool": "web"},
        {"text": "Build a list of the best people, companies or places to focus on", "action_type": "research", "tool": "web"},
        {"text": "Write the messages or posts, tailored to each one", "action_type": "create_draft", "tool": main},
        {"text": "Send or publish them, one by one", "action_type": "send_message" if outreach else "publish_post", "tool": main},
        {"text": f"Follow up and count {c.primary_metric}", "action_type": "send_message" if outreach else "read_data", "tool": main},
    ]
    return {"steps": steps, "source": "default"}


async def generate_playbook(claude: MeteredClaude, c: Campaign) -> dict:
    """Ask Claude for the plan of one goal (charged to that goal's budget; a few cents)."""
    tools_list = ", ".join(f"{k} ({t.label})" for k, t in TOOLS.items())
    prompt = (
        f"Goal: {c.goal_description}\n"
        f"Counts as done when: {c.done_when or '(not given)'}\n"
        f"Progress measured as: {c.primary_metric}" + (f" (target {c.target_value:g})" if c.target_value else "") + "\n"
        f"Preferred channels: {', '.join(c.channels) if c.channels else 'any'}\n"
        f"Context:\n{(c.context or '(none)')[:3000]}\n\n"
        f"Tools available: {tools_list}.\n\n{STEP_GUIDANCE}"
    )
    result = await claude.create(
        campaign_id=c.id, run_id=None, purpose="plan of action", role="worker",
        system="You plan how an AI employee will achieve a business goal. It researches, builds lists, "
               "writes, sends, posts and uses the company's apps, and asks a person before anything public, "
               "outgoing or paid. Be concrete and brief.",
        messages=[{"role": "user", "content": prompt}], max_tokens=4000,
        output_format={"type": "json_schema", "schema": {
            "type": "object", "properties": {"steps": {"type": "array", "items": step_schema()}},
            "required": ["steps"], "additionalProperties": False}},
    )
    text = "\n".join(b.get("text", "") for b in result.content if b.get("type") == "text")
    try:
        steps = tidy_steps(json.loads(text).get("steps"))
    except (json.JSONDecodeError, AttributeError):
        steps = []
    return {"steps": steps, "source": "generated"} if steps else default_playbook(c)


def tools_needed(c: Campaign) -> list[dict]:
    """The tools a goal's plan uses, with the steps that use each and whether those steps
    change anything outside Autopilot (then the tool is needed, not just useful)."""
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
