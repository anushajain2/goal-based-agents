"""The planner: one call to the most capable model at the start of each work session.

It reads the goal, the numbers so far and recent work, then writes a short plan for this
session (and updates the overall strategy when results call for it). The cheaper worker
model then carries the plan out step by step. Planning is where judgement matters most;
doing the steps is where most of the calls (and cost) are.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.agent.llm import MeteredClaude

_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "assessment": {"type": "string"},
            "plan": {"type": "array", "items": {"type": "string"}},
            "strategy": {"type": "string"},
        },
        "required": ["assessment", "plan", "strategy"],
        "additionalProperties": False,
    },
}

_SYSTEM = """You are the strategist for Autopilot, an AI employee that works toward a business \
goal for an early-stage founder or agency owner, within a budget and the owner's guardrails.

Read the brief and write the plan for the next work session:
- assessment: one or two sentences on where the goal stands and what the latest results say.
- plan: 2 to 6 concrete steps for this session, in order, each one short line. Pick the most \
valuable next actions toward the finish line. Be realistic about the remaining budget: the \
worker's own AI usage is paid from it too, so prefer a few high-quality actions.
- strategy: the updated overall strategy as short markdown bullet points (under 200 words), or \
an empty string if the current strategy still holds.

Respect the guardrails and the rules that always apply. Never plan fake engagement, spam, \
impersonation or misleading claims."""


@dataclass
class Plan:
    assessment: str
    steps: list[str]
    strategy: str

    def as_text(self) -> str:
        lines = [f"Assessment: {self.assessment}", "", "Plan for this session:"]
        lines += [f"{i}. {s}" for i, s in enumerate(self.steps, 1)]
        return "\n".join(lines)


async def make_plan(claude: MeteredClaude, *, campaign_id: str, run_id: str, brief: str) -> Plan | None:
    result = await claude.create(
        campaign_id=campaign_id, run_id=run_id, purpose="plan the session", role="planner",
        system=_SYSTEM, messages=[{"role": "user", "content": brief}],
        max_tokens=8000, output_format=_SCHEMA,
    )
    if result.stop_reason == "refusal":
        return None
    text = next((b.get("text", "") for b in result.content if b.get("type") == "text"), "")
    try:
        data = json.loads(text)
        steps = [str(s) for s in data.get("plan") or []][:8]
        return Plan(str(data.get("assessment", "")), steps, str(data.get("strategy", "")).strip())
    except (ValueError, AttributeError):
        return None
