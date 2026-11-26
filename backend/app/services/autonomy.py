"""How much an AI employee does on its own: recommended settings, heads-ups, earned trust.

Waiting for a yes on everything slows goals down; letting everything go out risks money and
reputation. Each kind of action is judged on four things:

  1. can it be undone, and how much harm is done before it is,
  2. whose name is on it and who sees it (a founder's personal profile vs a company blog),
  3. whether it spends money,
  4. whether the content is sensitive (pricing, legal claims, competitors, complaints, news).

The baseline is a fixed table (PRESETS), so it is predictable and the same for everyone. It is
tailored to the company and goal only in ways that make it *stricter* (a regulated industry, a
client's accounts, personal profiles). At run time the AI reviewer (services/rule_check) can also
only make things stricter: sensitive content asks instead of going out on its own.

Three ways to let work go out without slowing it down, all enforced by services/policy:
  * heads_up - it goes out after HEADS_UP_MINUTES unless someone stops it, so people keep a veto
    without being a bottleneck. App, MCP and merge actions don't hold up the AI employee
    while they wait; browser actions do (they need the live page).
  * daily caps - past the cap, it asks instead.
  * earned trust - after STREAK approvals in a row with little or no editing, the goal suggests
    a heads-up; after HEADS_UP_STREAK heads-ups that went out unstopped, it suggests on its own.
    It never changes a setting by itself in the looser direction.
And one that tightens on its own: when people stop heads-ups (STOPS_TO_DOWNGRADE within a week)
or flag something that went out on its own, that kind of action asks first again on that goal.
"""

from __future__ import annotations

import difflib
import logging
import os
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import TOOLS
from app.models import (
    AgentRun,
    AutonomousAction,
    Campaign,
    CampaignStatus,
    ExclusionRule,
    Organization,
    PermissionGrant,
    RequestKind,
    RequestStatus,
    RunStatus,
    UserRequest,
    utcnow,
)
from app.services import activity
from app.services.events import notify
from app.services.policy import ACTION_TYPES, domain_of

log = logging.getLogger(__name__)

HEADS_UP_MINUTES = int(os.environ.get("AUTOPILOT_HEADS_UP_MINUTES", "30"))
STREAK = 5  # approvals in a row, unedited or lightly edited, before suggesting a heads-up
HEADS_UP_STREAK = 10  # heads-ups that went out unstopped before suggesting "on its own"
LIGHT_EDIT = 0.9  # an approval counts as unedited when the text is at least this similar
STOPS_TO_DOWNGRADE = 2  # heads-ups stopped within a week before it asks first again
NEVER_EARNED = {"spend_money", "merge_code", "delete_content", "modify_account", "other_write"}

# Kinds of action that make public content in someone's name: a personal profile always asks.
PERSONAL_TYPES = ("publish_post", "publish_article", "reply", "send_message")
SOCIAL_TOOLS = ("linkedin", "twitter", "instagram", "facebook", "reddit", "youtube")

CONFIGURABLE = [k for k, t in ACTION_TYPES.items() if t.default == "ask"]


@dataclass(frozen=True)
class Row:
    mode: str  # auto | heads_up | ask | never
    cap: int | None = None  # per 24 hours, for auto and heads_up
    why: str = ""


_ASK_WHY = {
    "send_message": "An email or DM can't be unsent. After you approve a few unchanged, it will suggest a heads-up instead.",
    "modify_account": "Profile and settings changes affect everything else, so it asks.",
    "delete_content": "Deleting can't be undone.",
    "spend_money": "Spending always asks, unless you set a per-action limit.",
    "merge_code": "Code and feature changes need an engineer's review.",
    "other_write": "Anything that doesn't fit a known kind asks, to be safe.",
}

PRESETS: dict[str, dict] = {
    "cautious": {
        "label": "Cautious",
        "summary": "Asks before anything goes out. Slowest, but you see everything first.",
        "rows": {k: Row("ask", why="Asks before anything goes out.") for k in CONFIGURABLE},
    },
    "balanced": {
        "label": "Balanced",
        "summary": "Low-risk, easy-to-undo work goes out on its own or after a heads-up. Money, messages, account "
                   "changes and code always ask.",
        "rows": {
            "engage": Row("auto", 50, "Low risk and easy to undo. A daily limit keeps it natural and within platform limits."),
            "reply": Row("heads_up", 20, "Replies are public and go to real people, so you get a heads-up to stop any of them."),
            "publish_post": Row("heads_up", 5, "Posting often is what grows an audience. You get a heads-up, and a post can be taken down."),
            "publish_article": Row("heads_up", 3, "Articles can be edited or unpublished later. You get a heads-up first."),
            "send_message": Row("ask", why=_ASK_WHY["send_message"]),
            "modify_account": Row("ask", why=_ASK_WHY["modify_account"]),
            "delete_content": Row("ask", why=_ASK_WHY["delete_content"]),
            "spend_money": Row("ask", why=_ASK_WHY["spend_money"]),
            "merge_content": Row("auto", 5, "Small copy, article and image changes that pass their checks are easy to roll back."),
            "merge_code": Row("ask", why=_ASK_WHY["merge_code"]),
            "other_write": Row("ask", why=_ASK_WHY["other_write"]),
        },
    },
    "fast": {
        "label": "Fast",
        "summary": "Most volume. Posts and replies go out on its own; messages get a heads-up. Money, account "
                   "changes and code still ask.",
        "rows": {
            "engage": Row("auto", 100, "Low risk and easy to undo, within platform limits."),
            "reply": Row("auto", 40, "Replies go out on their own, up to a daily limit."),
            "publish_post": Row("auto", 10, "Posts go out on their own, up to a daily limit."),
            "publish_article": Row("auto", 5, "Articles go out on their own, up to a daily limit."),
            "send_message": Row("heads_up", 40, "Messages go out after a heads-up, up to a daily limit."),
            "modify_account": Row("ask", why=_ASK_WHY["modify_account"]),
            "delete_content": Row("ask", why=_ASK_WHY["delete_content"]),
            "spend_money": Row("ask", why=_ASK_WHY["spend_money"]),
            "merge_content": Row("auto", 10, "Small copy, article and image changes that pass their checks are easy to roll back."),
            "merge_code": Row("ask", why=_ASK_WHY["merge_code"]),
            "other_write": Row("ask", why=_ASK_WHY["other_write"]),
        },
    },
}
STRICTNESS = {"auto": 0, "heads_up": 1, "ask": 2, "never": 3}

# Industries where public claims are regulated: posting and replying ask first.
_REGULATED = {
    "healthcare": ("health", "medical", "clinic", "patient", "pharma", "hospital", "therapy", "dental", "telehealth"),
    "financial services": ("bank", "lending", "loan", "insurance", "invest", "wealth", "brokerage", "crypto", "fintech",
                           "credit card", "mortgage"),
    "legal": ("law firm", "legal services", "attorney", "solicitor"),
    "children's": ("children", "kids", "toddler", "baby"),
}
_PUBLIC = ("publish_post", "publish_article", "reply", "send_message")


def regulated_industry(org: Organization | None) -> str | None:
    if not org:
        return None
    p = org.profile or {}
    text = " ".join(str(x) for x in [org.description, p.get("summary"), p.get("offering"), p.get("customers")] if x).lower()
    for name, words in _REGULATED.items():
        if any(w in text for w in words):
            return name
    return None


def _tighten(row: Row, mode: str, why: str) -> Row:
    return row if STRICTNESS[row.mode] >= STRICTNESS[mode] else Row(mode, None, why)


def _gain(key: str, row: Row) -> str:
    label = ACTION_TYPES[key].label.lower()
    if row.mode == "auto":
        return f"Up to {row.cap} a day without waiting for anyone" if row.cap else "Never waits for anyone"
    if row.mode == "heads_up":
        return (f"Up to {row.cap} a day, each going out {HEADS_UP_MINUTES} minutes after a heads-up" if row.cap
                else f"Goes out {HEADS_UP_MINUTES} minutes after a heads-up")
    if row.mode == "never":
        return "Never happens"
    return f"Each \"{label}\" waits for a yes"


async def recommend(s: AsyncSession, c: Campaign) -> dict:
    """The three presets, tailored to this goal (only ever stricter), and which one to pick."""
    org = await s.get(Organization, c.org_id) if c.org_id else None
    industry = regulated_industry(org)
    reasons: list[str] = []
    recommended = "balanced"
    if c.client_name:
        recommended = "cautious"
        reasons.append(f"This goal is for a client ({c.client_name}): their accounts and reputation, so everything asks first.")
    if industry:
        reasons.append(f"Public posts, replies and messages ask first, because {industry} companies face rules on public claims.")
    if not reasons:
        reasons.append("Balanced gets the most done while anything that costs money, can't be undone or touches code waits for a yes.")
    in_plan = {st.get("action_type") for st in (c.playbook or {}).get("steps") or []}
    presets = {}
    for key, p in PRESETS.items():
        rows = []
        for k in CONFIGURABLE:
            row = p["rows"].get(k, Row("ask"))
            if industry and k in _PUBLIC:
                row = _tighten(row, "ask", f"{industry[0].upper() + industry[1:]} companies face rules on public claims, so this asks first.")
            t = ACTION_TYPES[k]
            rows.append({"key": k, "label": t.label, "description": t.description, "mode": row.mode, "daily_cap": row.cap,
                         "why": row.why, "gain": _gain(k, row), "in_plan": k in in_plan})
        rows.sort(key=lambda r: not r["in_plan"])
        presets[key] = {"key": key, "label": p["label"], "summary": p["summary"], "rows": rows}
    tools = {st.get("tool") for st in (c.playbook or {}).get("steps") or []} | {ch.strip().lower() for ch in c.channels or []}
    personal = [{"key": t, "label": TOOLS[t].label} for t in SOCIAL_TOOLS if t in tools and t in TOOLS]
    return {
        "recommended": recommended, "reasons": reasons, "presets": presets, "current": c.autonomy_preset,
        "heads_up_minutes": HEADS_UP_MINUTES, "personal_candidates": personal, "regulated": industry,
    }


def _scopes_for_tool(key: str) -> list[str]:
    t = TOOLS.get(key)
    if not t:
        return [key]
    return [x for x in {t.app, domain_of(t.site) if t.site else None} if x]


async def clear_goal_setting(s: AsyncSession, campaign_id: str, action_type: str) -> None:
    """Remove this goal's own setting for a kind of action (department and org settings stay)."""
    await s.execute(delete(ExclusionRule).where(ExclusionRule.campaign_id == campaign_id,
                                                ExclusionRule.kind == "action_type", ExclusionRule.value == action_type))
    await s.execute(update(PermissionGrant).where(
        PermissionGrant.campaign_id == campaign_id, PermissionGrant.action_type == action_type,
        PermissionGrant.scope.is_(None), PermissionGrant.revoked_at.is_(None)).values(revoked_at=utcnow()))


async def set_goal_mode(s: AsyncSession, c: Campaign, action_type: str, mode: str, *, daily_cap: int | None = None,
                        spend_limit_usd=None, granted_by: str | None = None, source: str = "user") -> None:
    await clear_goal_setting(s, c.id, action_type)
    if mode == "never":
        s.add(ExclusionRule(campaign_id=c.id, org_id=c.org_id, kind="action_type", value=action_type))
    elif mode in ("auto", "heads_up"):
        s.add(PermissionGrant(campaign_id=c.id, org_id=c.org_id, action_type=action_type, mode=mode,
                              daily_cap=daily_cap, spend_limit_usd=spend_limit_usd, granted_by=granted_by, source=source))
    elif mode == "ask" and await _looser_elsewhere(s, c.id, action_type):
        # A department or organization permission would let it go ahead: this goal asks anyway.
        s.add(PermissionGrant(campaign_id=c.id, org_id=c.org_id, action_type=action_type, mode="ask",
                              granted_by=granted_by, source=source))
    await s.flush()


async def _looser_elsewhere(s: AsyncSession, campaign_id: str, action_type: str) -> bool:
    from app.services.policy import applies_to

    return (await s.execute(select(func.count()).select_from(PermissionGrant).where(
        PermissionGrant.action_type == action_type, PermissionGrant.revoked_at.is_(None),
        PermissionGrant.scope.is_(None), PermissionGrant.mode != "ask",
        applies_to(PermissionGrant, campaign_id)))).scalar_one() > 0


async def apply(s: AsyncSession, c: Campaign, preset: str, *, overrides: dict | None = None,
                personal: list[str] | None = None, by: str | None = None) -> list[dict]:
    """Set this goal's permissions from a preset, with the person's changes on top."""
    rec = await recommend(s, c)
    if preset not in rec["presets"]:
        raise ValueError("Unknown preset")
    rows = {r["key"]: r for r in rec["presets"][preset]["rows"]}
    for k, o in (overrides or {}).items():
        if k not in rows:
            raise ValueError(f"Unknown kind of action: {k}")
        mode = o.get("mode", rows[k]["mode"])
        if mode not in STRICTNESS:
            raise ValueError(f"Unknown mode: {mode}")
        if k == "spend_money" and mode in ("auto", "heads_up"):
            raise ValueError("Spending without asking needs a per-action limit: set it on the goal's permissions.")
        cap = o.get("daily_cap", rows[k]["daily_cap"])
        if cap is not None and (not isinstance(cap, int) or cap < 1 or cap > 1000):
            raise ValueError("A daily limit is a whole number from 1 to 1000.")
        rows[k] = {**rows[k], "mode": mode, "daily_cap": cap}
    for k, r in rows.items():
        await set_goal_mode(s, c, k, r["mode"], daily_cap=r["daily_cap"] if r["mode"] in ("auto", "heads_up") else None,
                            granted_by=by, source="preset")
    # Personal profiles: posting, replying and messaging there always ask, whatever the preset.
    await s.execute(update(PermissionGrant).where(PermissionGrant.campaign_id == c.id, PermissionGrant.source == "personal",
                                                  PermissionGrant.revoked_at.is_(None)).values(revoked_at=utcnow()))
    allowed = {p["key"] for p in rec["personal_candidates"]} | set(SOCIAL_TOOLS)
    for tool in personal or []:
        if tool not in allowed:
            raise ValueError(f"Unknown account: {tool}")
        for scope in _scopes_for_tool(tool):
            for k in PERSONAL_TYPES:
                s.add(PermissionGrant(campaign_id=c.id, org_id=c.org_id, action_type=k, scope=scope, mode="ask",
                                      granted_by=by, source="personal"))
    c.autonomy_preset = preset
    c.guardrail_version += 1
    await activity.log(s, c.id, "system", f"Autonomy set to {PRESETS[preset]['label']}"
                       + (f" (changed: {', '.join(ACTION_TYPES[k].label.lower() for k in overrides)})" if overrides else "")
                       + (f"; always asks on personal accounts: {', '.join(personal)}" if personal else ""), status="info")
    await notify(s, c.id, "guardrails")
    await s.flush()
    return list(rows.values())


# --- run time -------------------------------------------------------------------------------------

async def record(s: AsyncSession, campaign_id: str, action_type: str) -> None:
    s.add(AutonomousAction(campaign_id=campaign_id, action_type=action_type))


def heads_up_at():
    return utcnow() + timedelta(minutes=HEADS_UP_MINUTES)


async def release_due(s: AsyncSession) -> int:
    """Heads-ups whose time is up go ahead: approved by nobody, and the run (if it waited) wakes."""
    due = (await s.execute(select(UserRequest).join(Campaign, Campaign.id == UserRequest.campaign_id).where(
        UserRequest.status == RequestStatus.pending.value, UserRequest.auto_approve_at.is_not(None),
        UserRequest.auto_approve_at <= utcnow(), Campaign.status == CampaignStatus.active.value,
    ).with_for_update(skip_locked=True))).scalars().all()
    for req in due:
        req.status = RequestStatus.approved.value
        req.decided_at = utcnow()
        await activity.log(s, req.campaign_id, "decision", f"Went ahead after the heads-up: {req.title}",
                           run_id=req.run_id, status="approved", action_type=req.action_type, channel=req.scope,
                           details={"request_id": req.id, "heads_up": True})
        if req.run_id and not req.queued_call:
            run = await s.get(AgentRun, req.run_id)
            if run and run.status == RunStatus.waiting.value:
                run.status = RunStatus.queued.value
        await notify(s, req.campaign_id, "request", id=req.id)
    return len(due)


async def claim_queued(s: AsyncSession) -> list[str]:
    """Approved heads-ups that didn't hold up the AI employee and haven't run yet."""
    ids = (await s.execute(select(UserRequest.id).where(
        UserRequest.status == RequestStatus.approved.value, UserRequest.queued_call.is_not(None),
        UserRequest.ran_at.is_(None)).limit(20))).scalars().all()
    claimed = []
    for rid in ids:
        r = await s.execute(update(UserRequest).where(UserRequest.id == rid, UserRequest.ran_at.is_(None))
                            .values(ran_at=utcnow()))
        if r.rowcount == 1:
            claimed.append(rid)
    return claimed


async def run_queued(request_id: str) -> None:
    """Make the call a heads-up was holding (with any edits people made in the meantime)."""
    from app.agent.executor import ToolExecutor
    from app.agent.llm import MeteredClaude
    from app.db import session_scope

    async with session_scope() as s:
        req = await s.get(UserRequest, request_id)
        c = await s.get(Campaign, req.campaign_id) if req else None
        if not req or not c:
            return
        call = dict(req.queued_call or {})
        run_id = call.pop("run_id", None) or req.run_id
    ex = ToolExecutor(MeteredClaude(), c.id, run_id or "", c.org_id)
    try:
        outcome = await ex.resume(call, req)
        if outcome.is_error:
            await ex._log("action", f"Couldn't do it after the heads-up: {req.title}", status="failed",
                          action_type=req.action_type, channel=req.scope, details={"error": str(outcome.content)[:1000]})
    except Exception as e:  # noqa: BLE001 - one bad call must not stop the worker
        log.exception("queued call %s failed", request_id)
        async with session_scope() as s:
            await activity.log(s, req.campaign_id, "action", f"Couldn't do it after the heads-up: {req.title}",
                               status="failed", action_type=req.action_type, channel=req.scope,
                               details={"error": f"{type(e).__name__}: {e}"[:1000]})


# --- earned trust, and tightening when things go wrong ----------------------------------------------

def _lightly_edited(req: UserRequest) -> bool:
    if not req.edited_fields:
        return True
    before = (req.preview or {}).get("fields") or {}
    for k, v in req.edited_fields.items():
        old = before.get(k)
        if not isinstance(v, str) or not isinstance(old, str):
            return False
        if difflib.SequenceMatcher(None, old, v).ratio() < LIGHT_EDIT:
            return False
    return True


async def suggestions(s: AsyncSession, campaign_id: str, modes: dict[str, str]) -> dict[str, dict]:
    """Per kind of action, a looser setting this goal has earned (never applied by itself)."""
    rows = (await s.execute(select(UserRequest).where(
        UserRequest.campaign_id == campaign_id, UserRequest.kind == RequestKind.action.value,
        UserRequest.status.in_([RequestStatus.approved.value, RequestStatus.rejected.value]),
    ).order_by(UserRequest.decided_at.desc()).limit(200))).scalars().all()
    # Trust is earned again after something was stopped or flagged: count only what came after.
    since = dict((await s.execute(select(PermissionGrant.action_type, func.max(PermissionGrant.created_at)).where(
        PermissionGrant.campaign_id == campaign_id, PermissionGrant.source == "downgrade",
        PermissionGrant.revoked_at.is_(None)).group_by(PermissionGrant.action_type))).all())
    by_type: dict[str, list[UserRequest]] = {}
    for r in rows:
        if r.action_type in since and r.decided_at and r.decided_at <= since[r.action_type]:
            continue
        by_type.setdefault(r.action_type or "", []).append(r)
    out = {}
    for k, reqs in by_type.items():
        mode = modes.get(k)
        if k in NEVER_EARNED or k not in ACTION_TYPES or mode not in ("ask", "heads_up"):
            continue
        if mode == "ask":
            asked = [r for r in reqs if r.auto_approve_at is None]
            streak = 0
            for r in asked:
                if r.status != RequestStatus.approved.value or not _lightly_edited(r):
                    break
                streak += 1
            if streak >= STREAK:
                out[k] = {"mode": "heads_up", "streak": streak,
                          "reason": f"You approved the last {streak} without changing them (or only slightly). "
                                    f"Let them go out after a {HEADS_UP_MINUTES}-minute heads-up instead?"}
        else:
            ups = [r for r in reqs if r.auto_approve_at is not None]
            streak = 0
            for r in ups:
                if r.status != RequestStatus.approved.value or r.edited_fields:
                    break
                streak += 1
            if streak >= HEADS_UP_STREAK:
                out[k] = {"mode": "auto", "streak": streak,
                          "reason": f"The last {streak} heads-ups went out without anyone stopping or changing them. "
                                    "Skip the heads-up?"}
    return out


async def downgrade(s: AsyncSession, c: Campaign, action_type: str, why: str) -> None:
    """This kind of action asks first again on this goal (overrides department and org permissions)."""
    await s.execute(update(PermissionGrant).where(
        PermissionGrant.campaign_id == c.id, PermissionGrant.action_type == action_type,
        PermissionGrant.revoked_at.is_(None), PermissionGrant.mode != "ask").values(revoked_at=utcnow()))
    s.add(PermissionGrant(campaign_id=c.id, org_id=c.org_id, action_type=action_type, mode="ask", source="downgrade"))
    c.guardrail_version += 1
    label = ACTION_TYPES[action_type].label if action_type in ACTION_TYPES else action_type
    await activity.log(s, c.id, "system", f'"{label}" asks first again: {why}', status="info", action_type=action_type)
    await notify(s, c.id, "guardrails")


async def after_stop(s: AsyncSession, req: UserRequest, c: Campaign) -> str:
    """Someone stopped a heads-up. Stopped twice within a week: that kind of action asks first."""
    if not req.action_type:
        return ""
    stops = (await s.execute(select(func.count()).select_from(UserRequest).where(
        UserRequest.campaign_id == c.id, UserRequest.action_type == req.action_type,
        UserRequest.auto_approve_at.is_not(None), UserRequest.status == RequestStatus.rejected.value,
        UserRequest.decided_at > utcnow() - timedelta(days=7)))).scalar_one()
    if stops >= STOPS_TO_DOWNGRADE:
        await downgrade(s, c, req.action_type, f"{stops} heads-ups were stopped this week.")
        return " · asks first from now on"
    return ""
