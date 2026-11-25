"""Ask other AI assistants (ChatGPT, Perplexity, Gemini) what they'd recommend for a customer's
questions, the same way the Claude check does. Each runs only when the platform has its key."""

from __future__ import annotations

import json
import re

from app.config import get_settings

from .http import post_json

PROMPT = """A person asks you each question below. Answer as you would for anyone: recommend the \
companies or products you'd actually suggest, best first, up to 5 each, with their website domain when \
you know it. Reply with JSON only, no other text, in this shape:
{"answers": [{"query": "...", "recommendations": [{"name": "...", "domain": "..."}]}]}

Questions:
"""


def configured() -> list[str]:
    s = get_settings()
    return [n for n, k in (("ChatGPT", s.openai_api_key), ("Perplexity", s.perplexity_api_key), ("Gemini", s.gemini_api_key)) if k]


def _parse(text: str) -> list[dict]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return []
    try:
        return list(json.loads(m.group(0)).get("answers") or [])
    except (json.JSONDecodeError, AttributeError):
        return []


async def ask(assistant: str, queries: list[str]) -> list[dict]:
    s = get_settings()
    prompt = PROMPT + "\n".join(f"- {q}" for q in queries)
    if assistant == "ChatGPT" and s.openai_api_key:
        data = await post_json("https://api.openai.com/v1/responses",
                               {"model": s.openai_model, "input": prompt, "tools": [{"type": "web_search"}]},
                               headers={"Authorization": f"Bearer {s.openai_api_key}"})
        text = (data or {}).get("output_text") or " ".join(
            c.get("text", "") for o in (data or {}).get("output") or [] for c in o.get("content") or []
            if c.get("type") == "output_text")
        return _parse(text)
    if assistant == "Perplexity" and s.perplexity_api_key:
        data = await post_json("https://api.perplexity.ai/chat/completions",
                               {"model": s.perplexity_model, "messages": [{"role": "user", "content": prompt}]},
                               headers={"Authorization": f"Bearer {s.perplexity_api_key}"})
        choices = (data or {}).get("choices") or [{}]
        return _parse(((choices[0] or {}).get("message") or {}).get("content", ""))
    if assistant == "Gemini" and s.gemini_api_key:
        data = await post_json(f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}:generateContent",
                               {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]},
                               params={"key": s.gemini_api_key})
        parts = (((data or {}).get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return _parse(" ".join(p.get("text", "") for p in parts))
    return []
