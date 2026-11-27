"""Metered Claude client.

Every model call goes through `MeteredClaude.create()`, which:
  1. reserves the call's worst-case cost from the campaign budget (refusing if it won't fit),
  2. makes the call with the model for its role (planner / worker / checker),
  3. settles the reservation at the real cost computed from `usage`.

The reserve and settle steps each run in their own short transaction so no database lock is
held while the model is thinking.
"""

from __future__ import annotations

import contextvars
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

# Every kind of model call Oton makes: its name, its default slot and a label for the cost view.
# The slot's model and effort apply unless TASK_MODELS / TASK_EFFORTS override the task.
TASKS: dict[str, tuple[str, str]] = {
    # Strategy and planning
    "session_strategist": ("planner", "Session strategist"),
    "goal_plan": ("planner", "Goal plan (how it will do it)"),
    "suggest_goals": ("planner", "Suggest more goals"),
    "reviewer": ("planner", "Reviewer review"),
    "video_storyboard": ("planner", "Launch video storyboard"),
    # Doing the work
    "work": ("worker", "Work session steps"),
    # Web research
    "company_research": ("worker", "Company research"),
    "check_investigation": ("worker", "Company check investigations"),
    "social_read": ("worker", "Social media read"),
    "search_ranking": ("checker", "Search ranking (no Google data)"),
    "ai_recommend": ("worker", "Does the AI recommend you? (Claude)"),
    # Structuring and judgment
    "pick_checks": ("worker", "Picking the checks"),
    "findings": ("planner", "Writing the findings"),
    "company_profile": ("worker", "Company profile"),
    "company_type": ("checker", "Company type"),
    "goal_steps": ("worker", "A goal's steps"),
    # Guardrails and quality
    "rule_check": ("checker", "Guardrail rule check"),
    "quality_check": ("worker", "Quality check on drafts"),
}
ROLES = ("planner", "worker", "checker")

# The organization a call is for, when it isn't for a goal (setup, the company check, videos):
# set by those jobs so their usage is counted for the right organization.
usage_org: contextvars.ContextVar[str | None] = contextvars.ContextVar("usage_org", default=None)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
CONTEXT_MGMT_BETA = "context-management-2025-06-27"
THINKING_BINDING_BETA = "thinking-binding-controls-2026-08-01"
DISPLAY_UPDATES_BETA = "thinking-display-updates-2026-08-18"


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


ROLES = ("planner", "worker", "checker")


def _supports_server_fallback(model: str) -> bool:
    # Haiku has no server-side refusal fallback; Opus and Sonnet do.
    return model.startswith(("claude-opus", "claude-sonnet", "claude-fable"))


def slot_model(s, role: str) -> tuple[str, str]:
    return {
        "planner": (s.planner_model, s.planner_effort),
        "worker": (s.worker_model, s.worker_effort),
        "checker": (s.checker_model, s.checker_effort),
    }[role]


def task_model(s, task: str) -> tuple[str, str]:
    """The model and effort for a task: its default slot's, unless TASK_MODELS / TASK_EFFORTS say otherwise."""
    model, effort = slot_model(s, TASKS[task][0])
    override = (s.task_models or {}).get(task)
    if override:
        model, effort = slot_model(s, override) if override in ROLES else (override, effort)
    return model, (s.task_efforts or {}).get(task) or effort


class MeteredClaude:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None):
        settings = get_settings()
        self.settings = settings
        # A real client needs a key; an injected client (tests) is assumed ready.
        self.configured = client is not None or bool(settings.anthropic_api_key)
        self.client = client or anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)

    def model_for(self, role: str) -> tuple[str, str]:
        return slot_model(self.settings, role)

    def model_for_task(self, task: str) -> tuple[str, str]:
        return task_model(self.settings, task)

    async def create(
        self,
        *,
        campaign_id: str | None,
        run_id: str | None,
        purpose: str,
        task: str,
        messages: list[dict],
        system: str | list[dict] | None = None,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        output_format: dict | None = None,
        max_web_searches: int = 0,
        agent_loop: bool = False,
    ) -> CallResult:
        model, effort = self.model_for_task(task)
        role = TASKS[task][0]
        # A Gemini model can write a structured answer (no tools); without a Gemini key the task's
        # usual Claude model does it.
        gemini = model.startswith("gemini") and not tools
        if model.startswith("gemini") and (tools or not self.settings.gemini_api_key):
            model, effort = slot_model(self.settings, role)
            gemini = False
        max_tokens = max_tokens or self.settings.agent_max_tokens
        est_in = estimate_input_tokens(system, tools, messages)
        worst = ledger.worst_case_cost(model, est_in, max_tokens, max_web_searches)

        # campaign_id=None: work for the whole organization (e.g. setup research), which is
        # not charged to any goal's budget. The caller records the returned cost itself.
        entry_id = None
        if campaign_id:
            async with session_scope() as s:
                entry = await ledger.reserve(
                    s, campaign_id, LedgerKind.ai_usage, worst, f"AI: {purpose}", run_id=run_id,
                    meta={"model": model, "role": role, "task": task, "purpose": purpose},
                )
                entry_id = entry.id

        try:
            response = None
            if gemini:
                try:
                    response = await _gemini_create(self.settings, model, effort, system, messages, max_tokens, output_format)
                except Exception as e:  # noqa: BLE001 - a plan still gets written, by Claude
                    log.warning("Gemini (%s) failed for %s, using Claude instead: %s", model, task, e)
                    model, effort = slot_model(self.settings, role)
            if response is None:
                response = await self._claude_call(model, effort, max_tokens, messages, system, tools, output_format,
                                                   agent_loop)
        except Exception:
            if entry_id:
                async with session_scope() as s:
                    await ledger.release(s, await s.get(LedgerEntry, entry_id))
            raise

        served_by = getattr(response, "model", None) or model
        cost = ledger.cost_from_usage(served_by, response.usage)
        await _record_usage(task, served_by, response.usage, cost, campaign_id)
        if entry_id:
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


    async def _claude_call(self, model: str, effort: str, max_tokens: int, messages: list[dict], system, tools,
                           output_format, agent_loop: bool):
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
            "cache_control": {"type": "ephemeral"},
        }
        if system is not None:
            params["system"] = system
        if tools:
            params["tools"] = tools
        if output_format:
            params["output_config"]["format"] = output_format

        optional: dict[str, Any] = {"betas": []}
        if _supports_server_fallback(model):
            optional["betas"].append(FALLBACK_BETA)
            optional["fallbacks"] = "default"
        if agent_loop:
            optional["betas"] += [CONTEXT_MGMT_BETA, THINKING_BINDING_BETA, DISPLAY_UPDATES_BETA]
            optional["context_management"] = {"edits": [{"type": "clear_tool_uses_20250919"}]}
            # "updates": short progress notes between tool calls, shown in the work log.
            params["thinking"] = {
                "type": "adaptive",
                "display": "updates",
                "block_binding": {"prefix_mismatch_behavior": "drop_block"},
            }
        if not optional["betas"]:
            optional.pop("betas")

        try:
            return await self.client.beta.messages.create(**params, **optional)
        except anthropic.BadRequestError as e:
            if not optional:
                raise
            # The optional betas are conveniences (refusal fallback, context clearing,
            # progress notes, lenient thinking replay). If the API rejects one of them,
            # retry once without them rather than failing the whole session.
            log.warning("Claude rejected optional features (%s); retrying without them", e.message)
            params["thinking"] = {"type": "adaptive"}
            return await self.client.beta.messages.create(**params)


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    server_tool_use: Any = None

    def model_dump(self, **_) -> dict:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens}


@dataclass
class _Response:
    content: list
    stop_reason: str
    model: str
    usage: _Usage


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_GEMINI_THINKING = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "xhigh"}


def _gemini_parts(content) -> list[dict]:
    if isinstance(content, str):
        return [{"text": content}]
    parts = []
    for b in content or []:
        if b.get("type") == "text" and b.get("text"):
            parts.append({"text": b["text"]})
        elif b.get("type") == "image" and (b.get("source") or {}).get("type") == "base64":
            parts.append({"inlineData": {"mimeType": b["source"]["media_type"], "data": b["source"]["data"]}})
    return parts


async def _gemini_create(settings, model: str, effort: str, system, messages: list[dict], max_tokens: int,
                         output_format: dict | None) -> _Response:
    """One Gemini call that answers like a Messages API response (text content, usage)."""
    import httpx

    sys_text = system if isinstance(system, str) else "\n\n".join(
        b.get("text", "") for b in system or [] if isinstance(b, dict))
    config: dict[str, Any] = {"maxOutputTokens": max_tokens,
                              "thinkingConfig": {"thinkingLevel": _GEMINI_THINKING.get(effort, "medium")}}
    if output_format and output_format.get("schema"):
        config.update(responseMimeType="application/json", responseJsonSchema=output_format["schema"])
    body: dict[str, Any] = {
        "contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": _gemini_parts(m["content"])}
                     for m in messages],
        "generationConfig": config,
    }
    if sys_text:
        body["systemInstruction"] = {"parts": [{"text": sys_text}]}
    async with httpx.AsyncClient(timeout=240) as client:
        r = await client.post(GEMINI_URL.format(model=model), json=body,
                              headers={"x-goog-api-key": settings.gemini_api_key})
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    cand = (data.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts") or [] if not p.get("thought"))
    if not text:
        raise RuntimeError(f"Gemini returned no text ({cand.get('finishReason')})")
    meta = data.get("usageMetadata") or {}
    usage = _Usage(input_tokens=int(meta.get("promptTokenCount") or 0),
                   output_tokens=int(meta.get("candidatesTokenCount") or 0) + int(meta.get("thoughtsTokenCount") or 0))
    return _Response(content=[{"type": "text", "text": text}], stop_reason="end_turn",
                     model=data.get("modelVersion") or model, usage=usage)


async def _record_usage(task: str, model: str, usage, cost: Decimal, campaign_id: str | None) -> None:
    """One row per model call, for the cost view (best effort: never fails the call)."""
    from app.models import Campaign, ModelUsage

    def n(name: str) -> int:
        return int(getattr(usage, name, 0) or 0)

    searches = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0
    try:
        async with session_scope() as s:
            org_id = usage_org.get()
            if campaign_id and not org_id:
                c = await s.get(Campaign, campaign_id)
                org_id = c.org_id if c else None
            s.add(ModelUsage(org_id=org_id, campaign_id=campaign_id, task=task, model=model[:80],
                             input_tokens=n("input_tokens"), output_tokens=n("output_tokens"),
                             cache_read_tokens=n("cache_read_input_tokens"),
                             cache_write_tokens=n("cache_creation_input_tokens"), web_searches=int(searches),
                             cost_usd=cost))
    except Exception:  # noqa: BLE001
        log.warning("couldn't record model usage for %s", task, exc_info=True)


def _usage_dict(usage) -> dict:
    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="json", exclude_none=True)
    return dict(usage or {})
