"""The quality bar: outgoing work is scored before a person sees it (or before it goes out on
its own), so people only get drafts worth approving.

Each kind of work has a short checklist. Below the bar, the draft goes back to the AI employee
with the specific fixes; after two tries it goes to the person anyway, with the reviewer's notes
attached, so nothing is silently held back. A fast model does the scoring (a fraction of a cent).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.agent.llm import MeteredClaude

PASS = 4  # out of 5
MAX_TRIES = 2  # rewrites asked for before a draft goes to the person anyway
MIN_CHARS = 40  # shorter than this isn't really "content"

CHECKLISTS: dict[str, list[str]] = {
    "send_message": [
        "Personal: mentions something specific and true about this recipient or their company",
        "One clear, easy next step (a question or a small ask), not several",
        "Short: readable in 20 seconds; no filler, no buzzwords",
        "Sounds like a person from the company, in its voice; no hype or pressure",
        "Correct names, facts and links; nothing made up",
    ],
    "publish_post": [
        "The first line makes the right reader stop scrolling",
        "One idea, with something specific: a number, an example, a story or a how-to",
        "Useful or interesting to the audience even if they never buy",
        "In the company's voice; no hype, clickbait or empty claims",
        "Fits the platform (length, format, hashtags) and ends with a natural next step",
    ],
    "publish_article": [
        "Answers the reader's question fully and early",
        "Specific and expert: examples, numbers, steps; better than what already ranks",
        "Clear structure: headings, short paragraphs, scannable",
        "Accurate; claims are true and sourced where it matters",
        "A clear next step for the reader",
    ],
    "engage": [
        "Adds something: an insight, an answer or a genuine question; not 'Great post!'",
        "Relevant to what was said; reads naturally",
        "Not salesy; no links or pitches unless asked",
    ],
}
GENERIC = [
    "Clear and correct for its purpose",
    "In the company's voice; no hype or made-up facts",
    "Good enough that a busy manager would approve it without edits",
]

_SYSTEM = """You are the toughest, fairest reviewer at the company. Score one piece of work an AI \
employee wrote, before a manager sees it, against the checklist: 5 = a great professional would be \
proud of it; 4 = good, approve as is; 3 = needs edits; 2 = weak; 1 = shouldn't go out. List the \
specific fixes that would get it to 5 (empty when it's already there). Judge the writing itself; \
ignore whether it's allowed (that's checked elsewhere)."""

_SCHEMA = {"type": "json_schema", "schema": {"type": "object", "properties": {
    "score": {"type": "integer"}, "fixes": {"type": "array", "items": {"type": "string"}}},
    "required": ["score", "fixes"], "additionalProperties": False}}


@dataclass
class Review:
    score: int
    fixes: list[str] = field(default_factory=list)

    @property
    def passes(self) -> bool:
        return self.score >= PASS

    def as_dict(self) -> dict:
        return {"score": self.score, "fixes": self.fixes}


def content_of(fields: dict | None) -> str:
    """The written parts of an action: long text fields (body, message, post...)."""
    parts = [f"{k}: {v}" for k, v in (fields or {}).items() if isinstance(v, str) and len(v) >= 20]
    return "\n\n".join(parts)


async def review(claude: MeteredClaude, *, campaign_id: str, run_id: str | None, action_type: str, title: str,
                 content: str, goal: str, voice: str) -> Review | None:
    """None when there's nothing to review or the reviewer couldn't decide (never blocks work)."""
    if len(content) < MIN_CHARS:
        return None
    checklist = CHECKLISTS.get(action_type, GENERIC)
    prompt = (f"Goal it serves: {goal}\nCompany and voice:\n{voice[:1500] or '(not given)'}\n\n"
              f"Checklist:\n" + "\n".join(f"- {c}" for c in checklist)
              + f"\n\nThe work ({title}):\n{content[:6000]}")
    result = await claude.create(campaign_id=campaign_id, run_id=run_id, purpose="quality check", role="checker",
                                 system=_SYSTEM, messages=[{"role": "user", "content": prompt}], max_tokens=1500,
                                 output_format=_SCHEMA)
    text = next((b.get("text", "") for b in result.content if b.get("type") == "text"), "")
    try:
        data = json.loads(text)
        score = int(data["score"])
    except (ValueError, KeyError, TypeError):
        return None
    return Review(max(1, min(score, 5)), [str(f)[:200] for f in data.get("fixes") or []][:5])
