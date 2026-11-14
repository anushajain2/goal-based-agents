"""The agent loop for one optimization cycle.

The conversation is persisted after every step and only ever appended to (never edited),
which keeps the prompt cache warm and Claude's earlier thinking valid. When a tool call
needs the user, the run is parked with its state in `AgentRun.pending`; it may wait hours
or days and survives restarts. When the user decides, the API re-queues the run and a
worker picks it up here, finishes the parked calls, and carries on.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

import anthropic
from sqlalchemy import func, or_, select
from sqlalchemy.orm.attributes import flag_modified

from app.agent import prompts
from app.agent.executor import Outcome, Pending, ToolExecutor
from app.agent.llm import MeteredClaude
from app.agent.tools import MAX_WEB_SEARCHES_PER_CALL, all_tools
from app.config import get_settings
from app.connectors.composio_hub import get_hub
from app.db import session_scope
from app.models import (
    Activity,
    AgentRun,
    Campaign,
    CampaignStatus,
    LedgerEntry,
    LedgerKind,
    LedgerStatus,
    MetricSnapshot,
    PermissionGrant,
    RunStatus,
    UserRequest,
    utcnow,
)
from app.services import activity, ledger, policy
from app.services.events import notify

log = logging.getLogger(__name__)

NUDGE = "Continue with this cycle. When you have done what you planned, call finish_cycle."
MAX_NUDGES = 2


def _tool_result(tool_use_id: str, outcome: dict) -> dict:
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": outcome["content"]}
    if outcome.get("is_error"):
        block["is_error"] = True
    return block


def _outcome_dict(o: Outcome) -> dict:
    return {"content": o.content, "is_error": o.is_error}


async def _active_grants(s, campaign_id: str) -> list[PermissionGrant]:
    return list(
        (
            await s.execute(
                select(PermissionGrant).where(
                    PermissionGrant.revoked_at.is_(None),
                    or_(PermissionGrant.campaign_id == campaign_id, PermissionGrant.campaign_id.is_(None)),
                )
            )
        ).scalars()
    )


class CycleRunner:
    def __init__(self, claude: MeteredClaude | None = None):
        self.claude = claude or MeteredClaude()
        self.settings = get_settings()
        self.hub = get_hub()

    # ------------------------------------------------------------------ persistence

    async def _save(self, run_id: str, **fields) -> None:
        async with session_scope() as s:
            run = await s.get(AgentRun, run_id)
            for k, v in fields.items():
                setattr(run, k, v)
                if k in ("messages", "pending"):
                    flag_modified(run, k)
            await notify(s, run.campaign_id, "run", id=run_id, status=run.status)

    async def _log(self, campaign_id: str, run_id: str, kind: str, title: str, **kw) -> None:
        async with session_scope() as s:
            await activity.log(s, campaign_id, kind, title, run_id=run_id, **kw)

    # ------------------------------------------------------------------ entry point

    async def run(self, run_id: str) -> None:
        async with session_scope() as s:
            run = await s.get(AgentRun, run_id)
            campaign = await s.get(Campaign, run.campaign_id)
            campaign_id = campaign.id
            if campaign.status != CampaignStatus.active.value:
                run.status = RunStatus.stopped.value
                return
            messages: list = list(run.messages or [])
            pending = run.pending
            uses_apps = run.uses_apps
            model_calls = run.model_calls
            nudges = run.nudges
            seen_version = run.guardrail_version_seen

        executor = ToolExecutor(self.claude, campaign_id, run_id)

        if pending:
            done = await self._resolve_pending(run_id, executor, pending)
            if not done:
                await self._save(run_id, status=RunStatus.waiting.value, pending=pending)
                return
            messages.append({"role": "user", "content": [_tool_result(i, pending["results"][i])
                                                         for i in pending["order"]]})
            seen_version = await self._maybe_guardrail_update(campaign_id, messages, seen_version)
            await self._save(run_id, messages=messages, pending=None, guardrail_version_seen=seen_version,
                             status=RunStatus.running.value)
            if pending.get("finished"):
                await self._complete(run_id, campaign_id, pending["finished"])
                return

        if not messages:
            uses_apps = self.hub.enabled
            brief, seen_version = await self._brief(campaign_id, run_id, uses_apps)
            messages = [{"role": "user", "content": brief}]
            await self._save(run_id, messages=messages, uses_apps=uses_apps, guardrail_version_seen=seen_version)
            await self._log(campaign_id, run_id, "cycle", "Started a new optimization cycle", status="info")

        tools = all_tools(uses_apps)

        while True:
            async with session_scope() as s:
                status = (await s.get(Campaign, campaign_id)).status
            if status != CampaignStatus.active.value:
                await self._save(run_id, status=RunStatus.stopped.value)
                return
            if model_calls >= self.settings.max_model_calls_per_cycle:
                await self._complete(run_id, campaign_id, {
                    "summary": f"Stopped this cycle after {model_calls} steps (the per-cycle limit).",
                    "hours": 1.0})
                return

            try:
                result = await self.claude.create(
                    campaign_id=campaign_id, run_id=run_id, purpose="agent step",
                    system=prompts.SYSTEM_PROMPT, tools=tools, messages=messages,
                    max_web_searches=MAX_WEB_SEARCHES_PER_CALL, agent_loop=True,
                )
            except ledger.BudgetExceeded as e:
                await self._out_of_budget(run_id, campaign_id, str(e))
                return
            except anthropic.APIError as e:
                await self._fail(run_id, campaign_id, f"Claude API error: {getattr(e, 'message', e)}")
                return

            model_calls += 1
            messages.append({"role": "assistant", "content": result.content})
            await self._save(run_id, messages=messages, model_calls=model_calls)

            tool_uses = [b for b in result.content if b.get("type") == "tool_use"]

            if result.stop_reason == "refusal":
                await self._log(campaign_id, run_id, "error", "Claude declined to continue this cycle",
                                status="failed")
                await self._complete(run_id, campaign_id, {"summary": "Cycle ended early (model declined).",
                                                           "hours": 6.0})
                return
            if result.stop_reason == "pause_turn":
                continue
            if not tool_uses:
                if nudges >= MAX_NUDGES:
                    text = " ".join(b.get("text", "") for b in result.content if b.get("type") == "text")
                    await self._complete(run_id, campaign_id, {"summary": text[:500] or "Cycle ended.",
                                                               "hours": 6.0})
                    return
                nudges += 1
                messages.append({"role": "user", "content": NUDGE})
                await self._save(run_id, messages=messages, nudges=nudges)
                continue

            results: dict[str, dict] = {}
            waiting: dict[str, dict] = {}
            finished = None
            for block in tool_uses:
                outcome = await executor.call(block["name"], block.get("input") or {}, block["id"])
                if isinstance(outcome, Pending):
                    waiting[block["id"]] = {"request_id": outcome.request_id, "stored": outcome.stored}
                else:
                    results[block["id"]] = _outcome_dict(outcome)
                    if outcome.finished:
                        finished = outcome.finished

            order = [b["id"] for b in tool_uses]
            if waiting:
                pending = {"order": order, "results": results, "waiting": waiting, "finished": finished}
                await self._save(run_id, pending=pending, status=RunStatus.waiting.value)
                return

            messages.append({"role": "user", "content": [_tool_result(i, results[i]) for i in order]})
            seen_version = await self._maybe_guardrail_update(campaign_id, messages, seen_version)
            await self._save(run_id, messages=messages, guardrail_version_seen=seen_version)
            if finished:
                await self._complete(run_id, campaign_id, finished)
                return

    # ------------------------------------------------------------------ pieces

    async def _resolve_pending(self, run_id: str, executor: ToolExecutor, pending: dict) -> bool:
        """Finish parked calls the user has decided on. True when nothing is left waiting."""
        for tool_use_id, item in list(pending["waiting"].items()):
            async with session_scope() as s:
                request = await s.get(UserRequest, item["request_id"])
            if request is None:
                outcome = Outcome("The request no longer exists.", is_error=True)
            elif request.status == "pending":
                continue
            else:
                outcome = await executor.resume(item["stored"], request)
            pending["results"][tool_use_id] = _outcome_dict(outcome)
            del pending["waiting"][tool_use_id]
            await self._save(run_id, pending=pending)
        return not pending["waiting"]

    async def _maybe_guardrail_update(self, campaign_id: str, messages: list, seen: int) -> int:
        """If guardrails changed mid-cycle, tell the agent right away (appended, never edited)."""
        async with session_scope() as s:
            campaign = await s.get(Campaign, campaign_id)
            if campaign.guardrail_version == seen:
                return seen
            rules = await policy.exclusions_for(s, campaign_id)
            grants = await _active_grants(s, campaign_id)
            messages.append({"role": "system", "content": prompts.guardrail_update_message(rules, grants)})
            return campaign.guardrail_version

    async def _brief(self, campaign_id: str, run_id: str, uses_apps: bool) -> tuple[str, int]:
        connections = None
        if uses_apps:
            try:
                connections = await self.hub.connected_apps()
            except Exception:  # noqa: BLE001
                log.warning("could not list Composio connections", exc_info=True)
        async with session_scope() as s:
            campaign = await s.get(Campaign, campaign_id)
            run = await s.get(AgentRun, run_id)
            budget = (await ledger.budget_state(s, campaign)).as_dict()
            rules = await policy.exclusions_for(s, campaign_id)
            grants = await _active_grants(s, campaign_id)
            cycles = (
                await s.execute(
                    select(AgentRun.cycle_number, AgentRun.summary)
                    .where(AgentRun.campaign_id == campaign_id, AgentRun.summary.is_not(None))
                    .order_by(AgentRun.cycle_number.desc()).limit(5)
                )
            ).all()
            metrics = list(
                (
                    await s.execute(
                        select(MetricSnapshot).where(MetricSnapshot.campaign_id == campaign_id)
                        .order_by(MetricSnapshot.recorded_at.desc()).limit(10)
                    )
                ).scalars()
            )
            acts = list(
                (
                    await s.execute(
                        select(Activity).where(Activity.campaign_id == campaign_id,
                                               Activity.kind.in_(["action", "blocked", "decision"]))
                        .order_by(Activity.id.desc()).limit(25)
                    )
                ).scalars()
            )
            brief = prompts.campaign_brief(
                campaign=campaign, budget=budget, cycle_number=run.cycle_number, rules=rules, grants=grants,
                recent_cycles=[f"Cycle {n}: {summary}" for n, summary in reversed(cycles)],
                metrics=list(reversed(metrics)),
                recent_activity=[f"{a.created_at:%m-%d %H:%M} [{a.status}] {a.title}" for a in reversed(acts)],
                connections=connections, apps_enabled=uses_apps,
            )
            return brief, campaign.guardrail_version

    async def _cycle_ai_cost(self, s, run_id: str) -> Decimal:
        return Decimal(
            (
                await s.execute(
                    select(func.coalesce(func.sum(LedgerEntry.amount_usd), 0)).where(
                        LedgerEntry.run_id == run_id, LedgerEntry.kind == LedgerKind.ai_usage.value,
                        LedgerEntry.status == LedgerStatus.settled.value,
                    )
                )
            ).scalar_one()
        )

    async def _complete(self, run_id: str, campaign_id: str, finished: dict) -> None:
        async with session_scope() as s:
            run = await s.get(AgentRun, run_id)
            campaign = await s.get(Campaign, campaign_id)
            run.status = RunStatus.completed.value
            run.summary = finished.get("summary") or "Cycle complete."
            run.pending = None
            campaign.cycles_completed = max(campaign.cycles_completed, run.cycle_number)
            now = utcnow()
            campaign.next_cycle_at = now + timedelta(hours=float(finished.get("hours") or campaign.cycle_hours))
            if campaign.end_date and campaign.end_date <= now:
                campaign.status = CampaignStatus.completed.value
            cost = await self._cycle_ai_cost(s, run_id)
            await activity.log(
                s, campaign_id, "cycle", f"Cycle {run.cycle_number} complete: {run.summary}", run_id=run_id,
                status="info", cost_usd=cost,
                details={"next_check_in": campaign.next_cycle_at.isoformat(), "model_calls": run.model_calls},
            )
            await notify(s, campaign_id, "campaign")
        await executor_cleanup(run_id)

    async def _out_of_budget(self, run_id: str, campaign_id: str, message: str) -> None:
        async with session_scope() as s:
            campaign = await s.get(Campaign, campaign_id)
            run = await s.get(AgentRun, run_id)
            budget = await ledger.budget_state(s, campaign)
            daily = budget.remaining_today is not None and budget.remaining_today < budget.remaining
            run.status = RunStatus.stopped.value
            if daily:
                # Daily cap reached: pick up again tomorrow, campaign stays active.
                tomorrow = (utcnow() + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
                campaign.next_cycle_at = tomorrow
                title = "Paused until tomorrow: daily budget cap reached"
            else:
                campaign.status = CampaignStatus.out_of_budget.value
                title = "Campaign paused: budget used up"
            run.summary = title  # marks the run as finished, so resuming the campaign starts fresh
            await activity.log(s, campaign_id, "budget", title, run_id=run_id, status="blocked",
                               details={"message": message})
            await notify(s, campaign_id, "campaign")
        await executor_cleanup(run_id)

    async def _fail(self, run_id: str, campaign_id: str, error: str) -> None:
        async with session_scope() as s:
            run = await s.get(AgentRun, run_id)
            campaign = await s.get(Campaign, campaign_id)
            run.status = RunStatus.failed.value
            run.error = error[:2000]
            campaign.next_cycle_at = utcnow() + timedelta(hours=1)
            await activity.log(s, campaign_id, "error", f"Cycle stopped: {error[:300]}", run_id=run_id,
                               status="failed")
            await notify(s, campaign_id, "campaign")
        await executor_cleanup(run_id)


async def executor_cleanup(run_id: str) -> None:
    from app.browser.controller import get_controller

    try:
        await get_controller().close_run(run_id)
    except Exception:  # noqa: BLE001
        pass
