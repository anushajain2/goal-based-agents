"""AI review of outgoing actions against free-text rules and the built-in rules.

This is the "soft" layer of guardrails. Hard blocks (action types, apps, sites) are
enforced in code by services/policy.py; free-text rules like "never mention competitors"
can only be judged by reading the content, so a separate Claude call reviews every
non-read action before it runs. It is a strong check, not a guarantee.

The same call says whether the content is sensitive (pricing, legal or health claims,
competitors, complaints, news). That never blocks anything; it only means an action that would
have gone out on its own asks a person first. The reviewer can only make things stricter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.agent.llm import MeteredClaude

BUILT_IN_RULES = [
    "No buying, trading or faking followers, likes, reviews, views or any other engagement.",
    "No fake accounts, sockpuppets, bots posing as people, or impersonating anyone.",
    "No spam: no unsolicited bulk messages, no repetitive or deceptive posting, no mass follow/unfollow.",
    "No false or misleading claims about the product, prices, results or endorsements.",
    "Follow each platform's rules and terms of service.",
    "Never enter, request or reveal passwords, payment card numbers or other credentials.",
]

_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "violates": {"type": "boolean"},
            "rule": {"type": "string"},
            "explanation": {"type": "string"},
            "sensitive": {"type": "boolean"},
            "sensitive_reason": {"type": "string"},
        },
        "required": ["violates", "rule", "explanation", "sensitive", "sensitive_reason"],
        "additionalProperties": False,
    },
}

_SYSTEM = (
    "You review a single action an autonomous marketing agent is about to take on a user's "
    "behalf. Decide whether the action clearly breaks any of the rules listed. Judge only "
    "against the rules; do not judge strategy or quality. If no rule is broken, set "
    'violates=false and rule="". If one is, set violates=true, quote that rule in `rule`, '
    "and explain in one short sentence.\n\n"
    "Separately, set sensitive=true if the content touches any of: prices, discounts or refunds; legal, medical, "
    "financial or safety claims; a competitor by name; a customer complaint or an angry person; news, politics, "
    "tragedies or other charged topics; or personal data about someone. Then give sensitive_reason in a few words "
    '(e.g. "It mentions pricing"). Otherwise sensitive=false and sensitive_reason="".'
)


@dataclass
class RuleVerdict:
    violates: bool
    rule: str
    explanation: str
    uncertain: bool = False  # reviewer could not decide -> ask the user instead of blocking
    sensitive: bool = False  # touches a sensitive topic -> ask instead of going ahead on its own
    sensitive_reason: str = ""


async def check_action(
    claude: MeteredClaude,
    *,
    campaign_id: str,
    run_id: str | None,
    user_rules: list[str],
    action_summary: str,
    action_payload: dict,
) -> RuleVerdict:
    rules = BUILT_IN_RULES + user_rules
    numbered = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(rules))
    prompt = (
        f"Rules:\n{numbered}\n\nAction the agent wants to take:\n{action_summary}\n\n"
        f"Exact payload:\n{json.dumps(action_payload, ensure_ascii=False, default=str)[:12000]}"
    )
    result = await claude.create(
        campaign_id=campaign_id,
        run_id=run_id,
        purpose="guardrail check",
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        task="rule_check",
        max_tokens=4000,
        output_format=_SCHEMA,
    )
    if result.stop_reason == "refusal":
        return RuleVerdict(True, "Safety review", "The automated reviewer declined to assess this action.", True)
    text = next((b.get("text", "") for b in result.content if b.get("type") == "text"), "")
    try:
        data = json.loads(text)
        return RuleVerdict(bool(data["violates"]), str(data.get("rule", "")), str(data.get("explanation", "")),
                           sensitive=bool(data.get("sensitive", False)),
                           sensitive_reason=str(data.get("sensitive_reason") or ""))
    except (ValueError, KeyError):
        # Fail closed: an unreadable verdict never lets the action through silently; the
        # pipeline turns `uncertain` into a request for the user's approval.
        return RuleVerdict(True, "Review failed", "The guardrail reviewer returned an unreadable answer.", True)
