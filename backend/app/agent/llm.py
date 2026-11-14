"""Metered Claude client.

Every model call goes through `MeteredClaude.create()`, which:
  1. reserves the call's worst-case cost from the campaign budget (refusing if it won't fit),
  2. makes the call (Claude Opus 5.5, adaptive thinking, server-side refusal fallback),
  3. settles the reservation at the real cost computed from `usage`.

The reserve and settle steps each run in their own short transaction so no database lock is
held while the model is thinking.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import anthropic

from app.config import get_settings
from app.db import session_scope
from app.models import LedgerEntry, LedgerKind
from app.services import ledger

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
CONTEXT_MGMT_BETA = "context-management-2025-06-27"
THINKING_BINDING_BETA = "thinking-binding-controls-2026-08-01"


@dataclass
class CallResult:
    response: Any
    content: list[dict]  # assistant content, serialized and safe to append to history
    cost: Decimal
    stop_reason: str | None


def serialize_content(blocks) -> list[dict]:
    """Assistant content as plain dicts, exactly as returned (append-only history).

    After a server-side fallback that happened mid-output, model-internal blocks that came
    before the final `fallback` block must not be echoed back (thinking, tool_use, unpaired
    server_tool_use). Everything else is kept verbatim and in place.
    """
    items = [b.model_dump(mode="json", exclude_none=True) if hasattr(b, "model_dump") else dict(b) for b in blocks]
    last_fallback = max((i for i, b in enumerate(items) if b.get("type") == "fallback"), default=None)
    if last_fallback is None:
        return items
    result_ids = {b.get("tool_use_id") for b in items if str(b.get("type", "")).endswith("_tool_result")}
    out = []
    for i, b in enumerate(items):
        t = b.get("type")
        if i < last_fallback:
            if t in ("thinking", "redacted_thinking", "tool_use"):
                continue
            if t == "server_tool_use" and b.get("id") not in result_ids:
                continue
        out.append(b)
    return out


def estimate_input_tokens(*parts: Any) -> int:
    # ~3 characters per token is deliberately pessimistic, so reservations over-estimate.
    return sum(len(json.dumps(p, default=str)) for p in parts if p is not None) // 3 + 500


class MeteredClaude:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None):
        settings = get_settings()
        self.settings = settings
        self.client = client or anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.agent_model

    async def create(
        self,
        *,
        campaign_id: str,
        run_id: str | None,
        purpose: str,
        messages: list[dict],
        system: str | list[dict] | None = None,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        effort: str | None = None,
        output_format: dict | None = None,
        max_web_searches: int = 0,
        agent_loop: bool = False,
    ) -> CallResult:
        max_tokens = max_tokens or self.settings.agent_max_tokens
        est_in = estimate_input_tokens(system, tools, messages)
        worst = ledger.worst_case_cost(self.model, est_in, max_tokens, max_web_searches)

        async with session_scope() as s:
            entry = await ledger.reserve(
                s, campaign_id, LedgerKind.ai_usage, worst, f"AI: {purpose}", run_id=run_id,
                meta={"model": self.model, "purpose": purpose},
            )
            entry_id = entry.id

        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort or self.settings.agent_effort},
            "cache_control": {"type": "ephemeral"},
        }
        if system is not None:
            params["system"] = system
        if tools:
            params["tools"] = tools
        if output_format:
            params["output_config"]["format"] = output_format

        optional = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        if agent_loop:
            optional["betas"] += [CONTEXT_MGMT_BETA, THINKING_BINDING_BETA]
            optional["context_management"] = {"edits": [{"type": "clear_tool_uses_20250919"}]}
            params["thinking"] = {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}

        try:
            try:
                response = await self.client.beta.messages.create(**params, **optional)
            except anthropic.BadRequestError as e:
                # The optional betas are conveniences (refusal fallback, context clearing,
                # lenient thinking replay). If the API rejects one of them, retry once
                # without them rather than failing the whole cycle.
                log.warning("Claude rejected optional features (%s); retrying without them", e.message)
                params["thinking"] = {"type": "adaptive"}
                response = await self.client.beta.messages.create(**params)
        except Exception:
            async with session_scope() as s:
                await ledger.release(s, await s.get(LedgerEntry, entry_id))
            raise

        served_by = getattr(response, "model", None) or self.model
        cost = ledger.cost_from_usage(served_by, response.usage)
        async with session_scope() as s:
            await ledger.settle(
                s, await s.get(LedgerEntry, entry_id), cost,
                meta={"served_by": served_by, "usage": _usage_dict(response.usage)},
            )
        return CallResult(
            response=response,
            content=serialize_content(response.content),
            cost=cost,
            stop_reason=response.stop_reason,
        )


def _usage_dict(usage) -> dict:
    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="json", exclude_none=True)
    return dict(usage or {})
