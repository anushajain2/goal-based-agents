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
from sqlalchemy import func, select
from sqlalchemy.orm.attributes import flag_modified

from app.agent import approach as goal_approach
from app.agent import prompts
from app.agent.executor import Outcome, Pending, ToolExecutor
from app.agent.llm import MeteredClaude
from app.agent.planner import make_plan
from app.agent.tools import MAX_WEB_SEARCHES_PER_CALL, all_tools
from app.config import get_settings
from app.connectors.composio_hub import hub_for_org
from app.db import session_scope
from app.models import (
    Activity,
    Agent,
    AgentRun,
    Campaign,
    Integration,
    McpServer,
    CampaignStatus,
    Department,
    LedgerEntry,
    LedgerKind,
    LedgerStatus,
    MetricSnapshot,
    Organization,
    PermissionGrant,
    RunStatus,
    UserRequest,
    utcnow,
)
from app.org import approvers
from app.services import activity, ledger, policy, targets
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
                    PermissionGrant.revoked_at.is_(None), policy.applies_to(PermissionGrant, campaign_id)
                )
            )
        ).scalars()
    )


class CycleRunner:
    def __init__(self, claude: MeteredClaude | None = None):
        self.claude = claude or MeteredClaude()
        self.settings = get_settings()

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
            owner_id = campaign.org_id  # app connections belong to the organization
            if campaign.status != CampaignStatus.active.value:
                run.status = RunStatus.stopped.value
                return
            messages: list = list(run.messages or [])
            pending = run.pending
            uses_apps = run.uses_apps
            uses_mcp = run.uses_mcp
            tool_sets = list(run.tool_sets or [])
            model_calls = run.model_calls
            nudges = run.nudges
            seen_version = run.guardrail_version_seen

        executor = ToolExecutor(self.claude, campaign_id, run_id, owner_id)

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

        if not self.claude.configured:
            await self._fail(run_id, campaign_id,
                             "No Claude API key. Add ANTHROPIC_API_KEY to the .env file and restart the app.")
            return

        if not messages:
            hub = await hub_for_org(owner_id)
            uses_apps = hub.enabled
            async with session_scope() as s:
                uses_mcp = bool((await s.execute(select(McpServer.id).where(McpServer.org_id == owner_id).limit(1))).first())
                kinds = {k for (k,) in (await s.execute(select(Integration.kind).where(Integration.org_id == owner_id))).all()}
                tool_sets = sorted({"github": "github", "postgres": "database"}[k] for k in kinds if k in ("github", "postgres"))
            await self._log(campaign_id, run_id, "cycle", "Started a work session", status="info")
            try:
                model = await self._ensure_approach(campaign_id)
            except ledger.BudgetExceeded as e:
                await self._out_of_budget(run_id, campaign_id, str(e))
                return
            brief, seen_version = await self._brief(campaign_id, run_id, uses_apps, owner_id)
            try:
                plan = await make_plan(self.claude, campaign_id=campaign_id, run_id=run_id, brief=brief, approach=model)
            except ledger.BudgetExceeded as e:
                await self._out_of_budget(run_id, campaign_id, str(e))
                return
            except anthropic.APIError as e:
                await self._fail(run_id, campaign_id, f"Claude API error: {getattr(e, 'message', e)}")
                return
            if plan:
                brief += "\n\n## The strategist's plan for this session\n" + plan.as_text()
                await self._record_plan(campaign_id, run_id, plan)
            messages = [{"role": "user", "content": brief}]
            await self._save(run_id, messages=messages, uses_apps=uses_apps, uses_mcp=uses_mcp, tool_sets=tool_sets,
                             guardrail_version_seen=seen_version)

        browser = self.settings.agent_chrome_enabled
        tools = all_tools(uses_apps, uses_mcp, tool_sets, browser=browser)
        system = prompts.SYSTEM_PROMPT if browser else prompts.SYSTEM_PROMPT + prompts.NO_BROWSER

        while True:
            async with session_scope() as s:
                status = (await s.get(Campaign, campaign_id)).status
            if status != CampaignStatus.active.value:
                await self._save(run_id, status=RunStatus.stopped.value)
                return
            if model_calls >= self.settings.max_model_calls_per_cycle:
                await self._complete(run_id, campaign_id, {
                    "summary": f"Paused this session after {model_calls} steps (the per-session limit).",
                    "hours": 1.0})
                return

            try:
                result = await self.claude.create(
                    campaign_id=campaign_id, run_id=run_id, purpose="agent step", role="worker",
                    system=system, tools=tools, messages=messages,
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
            await self._log_narration(campaign_id, run_id, result.content, result.cost)

            tool_uses = [b for b in result.content if b.get("type") == "tool_use"]

            if result.stop_reason == "refusal":
                await self._log(campaign_id, run_id, "error", "The AI declined to continue this session",
                                status="failed")
                await self._complete(run_id, campaign_id, {"summary": "Session ended early (the AI declined to continue).",
                                                           "hours": 6.0})
                return
            if result.stop_reason == "pause_turn":
                continue
            if not tool_uses:
                if nudges >= MAX_NUDGES:
                    text = " ".join(b.get("text", "") for b in result.content if b.get("type") == "text")
                    await self._complete(run_id, campaign_id, {"summary": text[:500] or "Session ended.",
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

    async def _ensure_approach(self, campaign_id: str) -> dict | None:
        """How the goal gets hit, made once (usually already made when people started the goal)."""
        async with session_scope() as s:
            campaign = await s.get(Campaign, campaign_id)
            if campaign.approach:
                return campaign.approach
        try:
            made = await goal_approach.generate(self.claude, campaign)
        except ledger.BudgetExceeded:
            raise
        except Exception:  # noqa: BLE001 - the session can still run on the plain plan
            log.warning("could not work out how goal %s gets hit", campaign_id, exc_info=True)
            made = goal_approach.default(campaign)
        async with session_scope() as s:
            campaign = await s.get(Campaign, campaign_id)
            campaign.approach = campaign.approach or made
            return campaign.approach

    async def _record_plan(self, campaign_id: str, run_id: str, plan) -> None:
        async with session_scope() as s:
            await activity.log(
                s, campaign_id, "plan", plan.assessment or "Planned this session", run_id=run_id, status="info",
                details={"plan": plan.steps, "assessment": plan.assessment},
            )
            if plan.extra:
                campaign = await s.get(Campaign, campaign_id)
                posted = goal_approach.apply(campaign, plan.extra)
                flag_modified(campaign, "approach")
                if posted:
                    await activity.log(s, campaign_id, "report", posted["changing"] or posted["learned"] or posted["measured"],
                                       run_id=run_id, status="info", details=posted)
            if plan.strategy:
                campaign = await s.get(Campaign, campaign_id)
                campaign.strategy = plan.strategy[:5000]
                await activity.log(s, campaign_id, "strategy", "Updated the strategy", run_id=run_id,
                                   status="info", details={"strategy": campaign.strategy})
            await notify(s, campaign_id, "campaign")

    async def _log_narration(self, campaign_id: str, run_id: str, content: list[dict], cost) -> None:
        """Log what the agent says it is doing, and its web searches, as work-log steps."""
        entries: list[tuple[str, str, str | None, dict]] = []
        for b in content:
            t = b.get("type")
            if t in ("text", "thinking"):
                note = (b.get("text") if t == "text" else b.get("thinking")) or ""
                note = " ".join(note.split())
                if note and "interrupted before it finished" not in note:
                    entries.append(("update", note[:400], None, {}))
            elif t == "server_tool_use":
                inp = b.get("input") or {}
                if b.get("name") == "web_search":
                    entries.append(("step", f'Searched the web for "{inp.get("query", "")}"', "web", {}))
                elif b.get("name") == "web_fetch":
                    url = inp.get("url", "")
                    entries.append(("step", f"Read {url}", policy.domain_of(url) if url else "web", {"url": url}))
        if not entries:
            return
        async with session_scope() as s:
            for i, (kind, title, channel, details) in enumerate(entries):
                await activity.log(
                    s, campaign_id, kind, title, run_id=run_id, status="info", channel=channel, details=details,
                    # Attribute this AI call's cost to the first note it produced.
                    cost_usd=cost if i == 0 else None,
                )

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

    async def _brief(self, campaign_id: str, run_id: str, uses_apps: bool,
                     owner_id: str | None = None) -> tuple[str, int]:
        connections = None
        if uses_apps:
            try:
                connections = await (await hub_for_org(owner_id)).connected_apps(owner_id)
            except Exception:
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
            agent = await s.get(Agent, campaign.agent_id) if campaign.agent_id else None
            dept = await s.get(Department, agent.department_id) if agent else None
            org = await s.get(Organization, campaign.org_id) if campaign.org_id else None
            people = await approvers(s, campaign.org_id, dept.id if dept else None, campaign.agent_id) if campaign.org_id else []
            identity = prompts.identity_line(
                agent.name if agent else None, dept.name if dept else None, org.name if org else None,
                [p.name or p.email for p in people],
            )
            await targets.roll_over(s, campaign)
            value = await targets.value_now(s, campaign)
            target_text = targets.describe(campaign, value) if targets.active(campaign) else ""
            waiting = (await s.execute(select(func.count(), func.min(UserRequest.created_at)).where(
                UserRequest.campaign_id == campaign_id, UserRequest.status == "pending"))).one()
            oldest = (utcnow() - waiting[1]).total_seconds() / 3600 if waiting[1] else None
            pace_text = targets.pace_text(campaign, targets.pace(campaign, value), waiting[0], oldest)
            brief = identity + "\n\n" + prompts.campaign_brief(
                campaign=campaign, budget=budget, cycle_number=run.cycle_number, rules=rules, grants=grants,
                recent_cycles=[f"Cycle {n}: {summary}" for n, summary in reversed(cycles)],
                metrics=list(reversed(metrics)),
                recent_activity=[f"{a.created_at:%m-%d %H:%M} [{a.status}] {a.title}" for a in reversed(acts)],
                connections=connections, apps_enabled=uses_apps, target_text=target_text,
            )
            servers = (await s.execute(select(McpServer).where(McpServer.org_id == campaign.org_id)
                                       .order_by(McpServer.created_at))).scalars().all() if campaign.org_id else []
            brief += prompts.plan_and_tools(campaign.playbook, servers)
            brief += goal_approach.brief_text(campaign.approach, pace_text)
            integrations = (await s.execute(select(Integration).where(Integration.org_id == campaign.org_id))).scalars().all() \
                if campaign.org_id else []
            handoff_to = await s.get(Agent, agent.handoff_to_agent_id) if agent and agent.handoff_to_agent_id else None
            brief += prompts.code_data_and_handoffs(integrations, handoff_to.name if handoff_to else None,
                                                    agent.handoff_review if agent else True)
            return brief, campaign.guardrail_version

    async def _cycle_ai_cost(self, s, run_id: str) -> Decimal:
        total = (
            await s.execute(
                select(func.coalesce(func.sum(LedgerEntry.amount_usd), 0)).where(
                    LedgerEntry.run_id == run_id, LedgerEntry.kind == LedgerKind.ai_usage.value,
                    LedgerEntry.status == LedgerStatus.settled.value,
                )
            )
        ).scalar_one()
        return Decimal(str(total)).quantize(Decimal("0.000001"))

    async def _complete(self, run_id: str, campaign_id: str, finished: dict) -> None:
        async with session_scope() as s:
            run = await s.get(AgentRun, run_id)
            campaign = await s.get(Campaign, campaign_id)
            run.status = RunStatus.completed.value
            run.summary = finished.get("summary") or "Cycle complete."
            run.pending = None
            campaign.cycles_completed = max(campaign.cycles_completed, run.cycle_number)
            now = utcnow()
            # The agent picks when to check in next, within 0.5x-2x of the owner's preferred rhythm.
            wanted = float(finished.get("hours") or campaign.cycle_hours)
            hours = min(max(wanted, campaign.cycle_hours / 2, 0.5), campaign.cycle_hours * 2, 72)
            campaign.next_cycle_at = now + timedelta(hours=hours)
            if campaign.end_date and campaign.end_date <= now:
                campaign.status = CampaignStatus.completed.value
            cost = await self._cycle_ai_cost(s, run_id)
            await activity.log(
                s, campaign_id, "cycle", f"Session {run.cycle_number} done: {run.summary}", run_id=run_id,
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
