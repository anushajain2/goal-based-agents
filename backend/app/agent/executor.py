"""Executes the agent's tool calls, through the guardrail pipeline.

For every outward action:

    classify -> hard blocks -> AI rule check -> grant / approval -> budget reserve -> execute -> log

A call that needs the user returns `Pending`; the runner parks the run until the user
decides, then calls `resume()` with the stored call to finish it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.agent.llm import MeteredClaude
from app.browser import chrome
from app.browser.controller import BrowserError, get_controller, is_commit
from app.connectors.composio_hub import get_hub
from app.db import session_scope
from app.models import (
    BrowserAuthorization,
    Campaign,
    LedgerKind,
    MetricSnapshot,
    RequestKind,
    RequestStatus,
    UserRequest,
    utcnow,
)
from app.services import activity, ledger, policy
from app.services.events import notify
from app.services.rule_check import check_action

log = logging.getLogger(__name__)

AUTH_TTL = timedelta(minutes=20)
AUTH_USES = 3


@dataclass
class Outcome:
    content: Any  # str or list of content blocks
    is_error: bool = False
    finished: dict | None = None  # set by finish_cycle


@dataclass
class Pending:
    request_id: str
    stored: dict = field(default_factory=dict)  # what to do once the user decides


def _json(data: Any, limit: int = 12000) -> str:
    text = json.dumps(data, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "... [truncated]"


class ToolExecutor:
    def __init__(self, claude: MeteredClaude, campaign_id: str, run_id: str):
        self.claude = claude
        self.campaign_id = campaign_id
        self.run_id = run_id
        self.browser = get_controller()
        self.hub = get_hub()

    # ------------------------------------------------------------------ dispatch

    async def call(self, name: str, tool_input: dict, tool_use_id: str) -> Outcome | Pending:
        handler = getattr(self, f"t_{name}", None)
        if handler is None:
            return Outcome(f"Unknown tool {name}.", is_error=True)
        try:
            return await handler(tool_input or {}, tool_use_id)
        except BrowserError as e:
            await self._step(f"Browser step didn't work: {e}"[:300], channel="browser", status="failed")
            return Outcome(str(e), is_error=True)
        except chrome.ChromeUnavailable as e:
            await self._log("error", f"Agent Chrome unavailable: {e}", status="failed", channel="browser")
            return Outcome(f"Agent Chrome is unavailable: {e}", is_error=True)
        except ledger.BudgetExceeded as e:
            await self._log("budget", f"Blocked by budget: {e}", status="blocked")
            return Outcome(f"Not enough budget for this: {e}", is_error=True)
        except Exception as e:
            log.exception("tool %s failed", name)
            await self._step(f"{name.replace('_', ' ')} failed: {type(e).__name__}"[:300], status="failed")
            return Outcome(f"{name} failed: {type(e).__name__}: {e}", is_error=True)

    async def resume(self, stored: dict, request: UserRequest) -> Outcome:
        """Finish a call that was waiting on the user."""
        kind = stored["kind"]
        if request.status == RequestStatus.cancelled.value:
            return Outcome("The request was cancelled. Continue without it.", is_error=True)
        if kind == "login":
            if request.status == RequestStatus.approved.value:
                return Outcome(
                    f"The user says they have signed in to {stored['site']}. Take a snapshot to confirm."
                )
            return Outcome(f"The user declined to sign in to {stored['site']}. Use another approach.", is_error=True)
        if kind == "connect":
            if request.status != RequestStatus.approved.value:
                return Outcome(f"The user declined to connect {stored['app']}.", is_error=True)
            connected = await self.hub.is_connected(stored["app"])
            return Outcome(
                f"{stored['app']} is now connected." if connected
                else f"{stored['app']} is still not connected (the sign-in may not have finished).",
                is_error=not connected,
            )

        # action approvals
        if request.status == RequestStatus.rejected.value:
            note = f" Their note: {request.decision_note}" if request.decision_note else ""
            return Outcome(
                f"The user declined this action.{note} Do not retry the same action; adjust your plan.",
                is_error=True,
            )
        edited = request.edited_fields or {}
        if kind == "app_action":
            args = {**stored["arguments"], **edited}
            return await self._execute_app_action(stored, args, approved=True, edited=bool(edited))
        if kind == "browser_action":
            content = edited.get("content", stored.get("content"))
            return await self._issue_authorization(stored, request.id, content=content, edited="content" in edited)
        return Outcome("Unknown pending action.", is_error=True)

    # ------------------------------------------------------------------ helpers

    async def _campaign(self, s) -> Campaign:
        return await s.get(Campaign, self.campaign_id)

    async def _step(self, title: str, *, channel: str | None = None, status: str = "info",
                    details: dict | None = None) -> None:
        """A small step for the work log (shown under "all steps")."""
        await self._log("step", title, channel=channel, status=status, details=details)

    async def _log(self, kind: str, title: str, **kw) -> None:
        async with session_scope() as s:
            await activity.log(s, self.campaign_id, kind, title, run_id=self.run_id, **kw)

    async def _gate(
        self,
        *,
        action_type: str,
        title: str,
        payload: dict,
        app: str | None = None,
        site: str | None = None,
        spend_usd: Decimal | None = None,
    ) -> tuple[str, str]:
        """Run hard blocks + AI rule check + grants. Returns (outcome, reason)."""
        async with session_scope() as s:
            rules = await policy.exclusions_for(s, self.campaign_id)
            decision = await policy.decide(
                s, self.campaign_id, action_type=action_type, app=app, site=site,
                est_spend_usd=spend_usd, rules=rules,
            )
        if decision.outcome == "block":
            return "block", decision.reason
        if action_type in policy.READ_ONLY:
            return "allow", decision.reason
        verdict = await check_action(
            self.claude, campaign_id=self.campaign_id, run_id=self.run_id,
            user_rules=policy.text_rules(rules), action_summary=title, action_payload=payload,
        )
        if verdict.violates and not verdict.uncertain:
            return "block", f'Breaks the rule "{verdict.rule}": {verdict.explanation}'
        if verdict.uncertain:
            return "ask", f"{verdict.explanation} Asking you instead."
        return decision.outcome, decision.reason

    async def _create_request(
        self, *, kind: RequestKind, tool_use_id: str, title: str, rationale: str = "",
        action_type: str | None = None, scope: str | None = None, preview: dict | None = None,
        spend_usd: Decimal | None = None,
    ) -> str:
        async with session_scope() as s:
            req = UserRequest(
                campaign_id=self.campaign_id, run_id=self.run_id, tool_use_id=tool_use_id, kind=kind.value,
                action_type=action_type, scope=scope, title=title[:300], rationale=rationale,
                preview=preview or {}, est_spend_usd=spend_usd,
            )
            s.add(req)
            await s.flush()
            await activity.log(
                s, self.campaign_id, "request", f"Waiting for you: {title}", run_id=self.run_id,
                status="waiting", action_type=action_type, channel=scope, details={"request_id": req.id},
            )
            await notify(s, self.campaign_id, "request", id=req.id)
            return req.id

    # ------------------------------------------------------------------ app connectors

    async def t_app_find_actions(self, inp: dict, _id: str) -> Outcome:
        if not self.hub.enabled:
            return Outcome("App connectors are not configured. Use the browser instead.", is_error=True)
        actions = await self.hub.search_actions(inp["query"], inp.get("app"))
        await self._step(f'Looked up how to "{inp["query"]}" in {inp.get("app") or "connected apps"}',
                         channel=inp.get("app") or "apps")
        if not actions:
            return Outcome("No matching app actions. Try other words, or use the browser.")
        return Outcome(_json([a.for_agent() for a in actions], 20000))

    async def t_app_list_connections(self, inp: dict, _id: str) -> Outcome:
        if not self.hub.enabled:
            return Outcome("App connectors are not configured. Use the browser instead.")
        return Outcome(_json(await self.hub.connected_apps()))

    async def t_app_request_connection(self, inp: dict, tool_use_id: str) -> Outcome | Pending:
        if not self.hub.enabled:
            return Outcome("App connectors are not configured. Use the browser instead.", is_error=True)
        app = inp["app"].lower()
        if await self.hub.is_connected(app):
            return Outcome(f"{app} is already connected.")
        async with session_scope() as s:
            rules = await policy.exclusions_for(s, self.campaign_id)
        block = policy.check_hard_blocks(rules, action_type="read_data", app=app)
        if block:
            await self._log("blocked", f"Blocked: connect {app}", status="blocked", channel=app,
                            details={"reason": block.reason})
            return Outcome(f"Blocked by the user's guardrails: {block.reason}", is_error=True)
        link = await self.hub.connect_link(app)
        request_id = await self._create_request(
            kind=RequestKind.connect, tool_use_id=tool_use_id, title=f"Connect {app}",
            rationale=inp.get("reason", ""), scope=app, preview={"url": link["redirect_url"], "app": app},
        )
        return Pending(request_id, {"kind": "connect", "app": app})

    async def t_app_run_action(self, inp: dict, tool_use_id: str) -> Outcome | Pending:
        if not self.hub.enabled:
            return Outcome("App connectors are not configured. Use the browser instead.", is_error=True)
        action = await self.hub.get_action(inp["slug"])
        args = inp.get("arguments") or {}
        summary = inp.get("summary") or action.name
        action_type = action.action_type
        spend = Decimal(str(inp["spend_usd"])) if inp.get("spend_usd") is not None else None
        if action_type == "spend_money" and spend is None:
            return Outcome("This action spends money: call again with spend_usd (the maximum cost).", is_error=True)

        stored = {
            "kind": "app_action", "slug": action.slug, "app": action.toolkit, "arguments": args,
            "summary": summary, "action_type": action_type,
            "spend_usd": str(spend) if spend is not None else None,
        }
        outcome, reason = await self._gate(
            action_type=action_type, title=summary, app=action.toolkit, spend_usd=spend,
            payload={"app": action.toolkit, "action": action.slug, "arguments": args},
        )
        if outcome == "block":
            await self._log("blocked", f"Blocked: {summary}", status="blocked", action_type=action_type,
                            channel=action.toolkit, details={"reason": reason, "arguments": args})
            return Outcome(f"Blocked by the user's guardrails: {reason} Do not try to do this another way.",
                           is_error=True)
        if outcome == "ask":
            editable = [k for k, v in args.items() if isinstance(v, str) and len(v) >= 20]
            request_id = await self._create_request(
                kind=RequestKind.action, tool_use_id=tool_use_id, title=summary, rationale=reason,
                action_type=action_type, scope=action.toolkit, spend_usd=spend,
                preview={
                    "app": action.toolkit, "action": action.slug, "action_name": action.name,
                    "fields": args, "editable": editable,
                },
            )
            return Pending(request_id, stored)
        return await self._execute_app_action(stored, args, approved=False, edited=False)

    async def _execute_app_action(self, stored: dict, args: dict, *, approved: bool, edited: bool) -> Outcome:
        spend = Decimal(stored["spend_usd"]) if stored.get("spend_usd") else None
        entry_id = None
        if spend:
            async with session_scope() as s:
                entry = await ledger.reserve(
                    s, self.campaign_id, LedgerKind.spend, spend, stored["summary"], run_id=self.run_id,
                    meta={"app": stored["app"], "action": stored["slug"]},
                )
                entry_id = entry.id
        result = await self.hub.execute(stored["slug"], args)
        async with session_scope() as s:
            if entry_id:
                from app.models import LedgerEntry

                entry = await s.get(LedgerEntry, entry_id)
                if result["successful"]:
                    await ledger.settle(s, entry, spend)
                else:
                    await ledger.release(s, entry)
            await activity.log(
                s, self.campaign_id, "step" if stored["action_type"] in policy.READ_ONLY else "action",
                stored["summary"], run_id=self.run_id,
                status="done" if result["successful"] else "failed", action_type=stored["action_type"],
                channel=stored["app"], cost_usd=spend if result["successful"] else None,
                details={"action": stored["slug"], "arguments": args, "approved_by_user": approved,
                         "edited_by_user": edited, "error": result.get("error"),
                         "result": _json(result.get("data"), 3000)},
            )
        prefix = "The user edited the content before approving; this is what was sent. " if edited else ""
        if not result["successful"]:
            return Outcome(f"The action failed: {result.get('error')}", is_error=True)
        return Outcome(prefix + _json({"arguments_used": args, "result": result.get("data")}))

    # ------------------------------------------------------------------ browser

    async def _snapshot_outcome(self, prefix: str = "") -> Outcome:
        snap = await self.browser.snapshot(self.run_id)
        return Outcome(prefix + snap)

    async def _site_block(self, url: str) -> policy.Block | None:
        async with session_scope() as s:
            rules = await policy.exclusions_for(s, self.campaign_id)
        return policy.check_hard_blocks(rules, action_type="research", site=url)

    async def t_browser_open(self, inp: dict, _id: str) -> Outcome:
        url = inp["url"]
        block = await self._site_block(url)
        if block:
            await self._log("blocked", f"Blocked: open {policy.domain_of(url)}", status="blocked",
                            channel=policy.domain_of(url), details={"reason": block.reason})
            return Outcome(f"Blocked by the user's guardrails: {block.reason}", is_error=True)
        final = await self.browser.open(self.run_id, url)
        await self._step(f"Opened {final[:150]}", channel=policy.domain_of(final), details={"url": final})
        if policy.domain_of(final) != policy.domain_of(url):
            block = await self._site_block(final)
            if block:
                await self.browser.open(self.run_id, "about:blank")
                return Outcome(f"The page redirected to a blocked site: {block.reason}", is_error=True)
        return await self._snapshot_outcome()

    async def t_browser_snapshot(self, inp: dict, _id: str) -> Outcome:
        return await self._snapshot_outcome()

    async def t_browser_screenshot(self, inp: dict, _id: str) -> Outcome:
        name, b64 = await self.browser.screenshot(self.run_id)
        url = await self.browser.current_url(self.run_id)
        await self._step(f"Took a screenshot of {policy.domain_of(url)}", channel=policy.domain_of(url),
                         details={"screenshot": name, "url": url})
        return Outcome([
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
            {"type": "text", "text": f"Screenshot of {await self.browser.current_url(self.run_id)}"},
        ])

    async def t_browser_scroll(self, inp: dict, _id: str) -> Outcome:
        await self.browser.scroll(self.run_id, inp.get("direction", "down"))
        return await self._snapshot_outcome()

    async def t_browser_back(self, inp: dict, _id: str) -> Outcome:
        await self.browser.back(self.run_id)
        return await self._snapshot_outcome()

    async def _use_authorization(self, authorization_id: str | None, what: str) -> tuple[bool, str]:
        if not authorization_id:
            return False, (
                f"Blocked: {what} is a final commit step. Declare it first with browser_declare_action and "
                "pass the authorization_id you get back."
            )
        async with session_scope() as s:
            auth = (
                await s.execute(
                    select(BrowserAuthorization)
                    .where(BrowserAuthorization.id == authorization_id, BrowserAuthorization.run_id == self.run_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if not auth or auth.uses_remaining <= 0 or auth.expires_at < utcnow():
                return False, "That authorization_id is invalid, used up or expired. Declare the action again."
            auth.uses_remaining -= 1
            return True, auth.title

    async def _commit_log(self, title: str, what: str, url: str) -> None:
        await self._log("action", f"{title} ({what})", channel=policy.domain_of(url), details={"url": url})

    async def t_browser_click(self, inp: dict, _id: str) -> Outcome:
        ref = int(inp["ref"])
        info = await self.browser.element_info(self.run_id, ref)
        url = await self.browser.current_url(self.run_id)
        commit_title = None
        if is_commit(info):
            ok, msg = await self._use_authorization(inp.get("authorization_id"), f'clicking "{info["name"]}"')
            if not ok:
                return Outcome(msg, is_error=True)
            commit_title = msg
        await self.browser.click(self.run_id, ref)
        new_url = await self.browser.current_url(self.run_id)
        block = await self._site_block(new_url)
        if block:
            await self.browser.back(self.run_id)
            return Outcome(f"That link leads to a blocked site: {block.reason}", is_error=True)
        if commit_title:
            await self._commit_log(commit_title, f'clicked "{info["name"]}"', url)
        else:
            await self._step(f'Clicked "{info["name"] or "a link"}"', channel=policy.domain_of(url))
        return await self._snapshot_outcome(f'Clicked [{ref}] "{info["name"]}".\n\n')

    async def t_browser_type(self, inp: dict, _id: str) -> Outcome:
        ref = int(inp["ref"])
        info = await self.browser.element_info(self.run_id, ref)
        if info.get("type") == "password" or "password" in info.get("autocomplete", "") or "cc-" in info.get(
            "autocomplete", ""
        ):
            await self._log("blocked", "Refused to type into a password or card field", status="blocked")
            return Outcome(
                "Blocked: you never type passwords or card details. Use browser_request_login so the user "
                "signs in themselves.", is_error=True,
            )
        commit_title = None
        if inp.get("submit") and not info.get("search"):
            ok, msg = await self._use_authorization(inp.get("authorization_id"), "submitting this form")
            if not ok:
                return Outcome(msg, is_error=True)
            commit_title = msg
        await self.browser.type(self.run_id, ref, inp["text"])
        url = await self.browser.current_url(self.run_id)
        field = info.get("name") or "a text box"
        await self._step(f'Typed into "{field[:60]}"', channel=policy.domain_of(url),
                         details={"content": inp["text"][:2000]})
        if inp.get("submit"):
            await self.browser.press(self.run_id, "Enter")
            if commit_title:
                await self._commit_log(commit_title, "submitted", url)
        return await self._snapshot_outcome(f"Typed into [{ref}].\n\n")

    async def t_browser_press(self, inp: dict, _id: str) -> Outcome:
        key = inp["key"]
        focused = await self.browser.focused_info(self.run_id) or {}
        submits = "enter" in key.lower() and focused.get("editable") and not focused.get("search")
        # Plain Enter in a multi-line field just adds a line break; anything else submits.
        if submits and key.lower() == "enter" and focused.get("tag") != "input":
            submits = False
        commit_title = None
        if submits:
            ok, msg = await self._use_authorization(inp.get("authorization_id"), f"pressing {key}")
            if not ok:
                return Outcome(msg, is_error=True)
            commit_title = msg
        url = await self.browser.current_url(self.run_id)
        await self.browser.press(self.run_id, key)
        if commit_title:
            await self._commit_log(commit_title, f"pressed {key}", url)
        return await self._snapshot_outcome(f"Pressed {key}.\n\n")

    async def t_browser_declare_action(self, inp: dict, tool_use_id: str) -> Outcome | Pending:
        action_type = inp.get("action_type", "other_write")
        if action_type in policy.READ_ONLY:
            return Outcome("Reading and research do not need declaring. Go ahead.")
        site = policy.domain_of(inp["site"])
        spend = Decimal(str(inp["spend_usd"])) if inp.get("spend_usd") is not None else None
        if action_type == "spend_money" and spend is None:
            return Outcome("Spending money: call again with spend_usd (the maximum cost).", is_error=True)
        stored = {
            "kind": "browser_action", "action_type": action_type, "title": inp["title"], "site": site,
            "content": inp.get("content"), "details": inp.get("details"),
            "spend_usd": str(spend) if spend is not None else None,
        }
        outcome, reason = await self._gate(
            action_type=action_type, title=inp["title"], site=site, spend_usd=spend,
            payload={"site": site, "content": inp.get("content"), "details": inp.get("details")},
        )
        if outcome == "block":
            await self._log("blocked", f"Blocked: {inp['title']}", status="blocked", action_type=action_type,
                            channel=site, details={"reason": reason, "content": inp.get("content")})
            return Outcome(f"Blocked by the user's guardrails: {reason} Do not try to do this another way.",
                           is_error=True)
        if outcome == "ask":
            shot = None
            try:
                shot, _ = await self.browser.screenshot(self.run_id)
            except Exception:  # noqa: BLE001 - a preview screenshot is nice-to-have
                pass
            fields = {"content": inp["content"]} if inp.get("content") else {}
            request_id = await self._create_request(
                kind=RequestKind.action, tool_use_id=tool_use_id, title=inp["title"], rationale=reason,
                action_type=action_type, scope=site, spend_usd=spend,
                preview={"site": site, "fields": fields, "editable": list(fields), "details": inp.get("details"),
                         "screenshot": shot},
            )
            return Pending(request_id, stored)
        return await self._issue_authorization(stored, None, content=inp.get("content"), edited=False)

    async def _issue_authorization(self, stored: dict, request_id: str | None, *, content: str | None,
                                   edited: bool) -> Outcome:
        spend = Decimal(stored["spend_usd"]) if stored.get("spend_usd") else None
        async with session_scope() as s:
            if spend:
                # Browser purchases can't be measured precisely; the declared maximum is charged.
                entry = await ledger.reserve(s, self.campaign_id, LedgerKind.spend, spend, stored["title"],
                                             run_id=self.run_id, meta={"site": stored["site"]})
                await ledger.settle(s, entry, spend)
            auth = BrowserAuthorization(
                run_id=self.run_id, request_id=request_id, action_type=stored["action_type"],
                title=stored["title"][:300], uses_remaining=AUTH_USES, expires_at=utcnow() + AUTH_TTL,
            )
            s.add(auth)
            await s.flush()
            auth_id = auth.id
        msg = f"Allowed. authorization_id={auth_id} (valid for {AUTH_USES} commit steps, 20 minutes)."
        if edited:
            msg += f"\nThe user edited the content. Use exactly this text:\n{content}"
        return Outcome(msg)

    async def t_browser_request_login(self, inp: dict, tool_use_id: str) -> Outcome | Pending:
        site = policy.domain_of(inp["site"])
        block = await self._site_block(site)
        if block:
            return Outcome(f"Blocked by the user's guardrails: {block.reason}", is_error=True)
        try:
            await self.browser.open(self.run_id, inp["login_url"])
        except Exception:  # noqa: BLE001
            pass
        request_id = await self._create_request(
            kind=RequestKind.login, tool_use_id=tool_use_id, title=f"Sign in to {site} in Agent Chrome",
            rationale=inp.get("reason", ""), scope=site, preview={"url": inp["login_url"], "site": site},
        )
        return Pending(request_id, {"kind": "login", "site": site, "url": inp["login_url"]})

    # ------------------------------------------------------------------ campaign

    async def t_record_metric(self, inp: dict, _id: str) -> Outcome:
        async with session_scope() as s:
            s.add(MetricSnapshot(campaign_id=self.campaign_id, metric=inp["metric"][:120],
                                 value=float(inp["value"]), source=inp.get("source", "")[:200],
                                 note=inp.get("note", "") or ""))
            await activity.log(s, self.campaign_id, "metric", f"{inp['metric']}: {inp['value']:g}",
                               run_id=self.run_id, status="info", channel=inp.get("source"))
            await notify(s, self.campaign_id, "metric")
        return Outcome("Recorded.")

    async def t_update_strategy(self, inp: dict, _id: str) -> Outcome:
        async with session_scope() as s:
            campaign = await self._campaign(s)
            campaign.strategy = inp["strategy"][:5000]
            await activity.log(s, self.campaign_id, "strategy", "Updated the strategy", run_id=self.run_id,
                               status="info", details={"strategy": campaign.strategy})
            await notify(s, self.campaign_id, "campaign")
        return Outcome("Strategy updated.")

    async def t_notify_user(self, inp: dict, _id: str) -> Outcome:
        await self._log("note", inp["message"], status="info")
        return Outcome("Noted in the user's activity log.")

    async def t_finish_cycle(self, inp: dict, _id: str) -> Outcome:
        hours = min(72.0, max(0.5, float(inp.get("next_check_in_hours") or 6)))
        return Outcome("Cycle finished.", finished={"summary": inp.get("summary", ""), "hours": hours})
