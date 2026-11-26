"""Approvals, heads-ups and questions on WhatsApp, so people can decide from their phone.

One WhatsApp Business number (Meta's Cloud API, the platform's own, like the Composio key)
serves every organization. What people can do from WhatsApp is what they can do in Needs you:
approve (as is or edited), decline with a reason, stop or send a heads-up early, answer a
question, approve a hand-in or a Reviewer's suggestion. Decisions go through
services/decisions, so the same rules apply wherever someone decides.

Meta's rules, and how this keeps the experience good within them:
  * Opt-in: people connect by sending our number a one-time code from their own phone
    (a wa.me link prefills it). That proves the number is theirs and is their opt-in.
    "stop" disconnects at any time.
  * 24-hour window: after someone writes or taps, we may send anything for 24 hours. Inside it
    every request arrives as a full card: the exact content, why, the quality score, and buttons.
    Outside it, the first message must be a pre-approved utility template (TEMPLATES); one tap
    on it reopens the window, and the rest of the queue follows one card at a time. At most one
    template goes out per TEMPLATE_GAP while someone hasn't answered, so it never nags.
  * Business use only: this is a workflow for our product, not a general chatbot (Meta bars
    those). Free text is only ever an answer, an edit, a reason or a comment on a request.

What still needs the app, and why: spending money, merging code and deleting things (a
thumb-tap shouldn't do those), and signing in to a website (that happens in Oton Chrome).
Those arrive with the details and a link straight to the request.

Every button carries a signed token bound to the request and the person, and replies are only
accepted from the connected number of someone allowed to decide.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import quote

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    Campaign,
    RequestKind,
    RequestStatus,
    User,
    UserRequest,
    WhatsAppMessage,
    utcnow,
)
from app.org import Member, approvers, can_decide, load_member
from app.services import activity, autonomy, decisions, permissions
from app.services.events import notify
from app.services.policy import ACTION_TYPES

log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com"
TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests point this at a fake Graph API

WINDOW = timedelta(hours=23, minutes=50)  # WhatsApp's 24 hours, with a margin
TEMPLATE_GAP = timedelta(hours=4)  # at most one template per this, while unanswered
LINK_CODE_TTL = timedelta(minutes=15)
RECENT = timedelta(days=3)  # requests older than this aren't pushed to WhatsApp
APP_ONLY_TYPES = {"spend_money": "It spends money", "merge_code": "It merges code",
                  "delete_content": "It deletes something"}
DEFAULT_PREFS = {"approvals": True, "heads_ups": True, "questions": True}
TRUST_ASK_EVERY = timedelta(days=7)
BODY_MAX = 1024  # interactive message body
TEXT_MAX = 4096  # plain text message
MAX_CHUNKS = 3

# Utility templates (created with `python -m app.cli whatsapp-templates`, approved by Meta).
# Quick-reply buttons carry a signed payload set per message.
TEMPLATES: dict[str, dict] = {
    "autopilot_approval": {
        "body": "{{1}} is waiting for your OK on the goal \"{{2}}\".\n\nWhat it wants to do: {{3}}\n\n{{4}}\n\n"
                "Tap a button to decide here, or open Oton.",
        "example": ["Oton", "Grow our audience", "Post a routing tip on X",
                    "Tip: batch stops by zone before 9am. Also waiting: 2 more."],
        "buttons": ["Approve", "Show details", "Decline"],
    },
    "autopilot_heads_up": {
        "body": "Heads-up from {{1}} on the goal \"{{2}}\": it will {{3}} in about {{4}} minutes unless you stop it.\n\n"
                "{{5}}\n\nTap Stop it to cancel, or Show details to see or change it first.",
        "example": ["Oton", "Grow our audience", "post a routing tip on X", "30",
                    "Tip: batch stops by zone before 9am."],
        "buttons": ["Stop it", "Show details", "Send now"],
    },
    "autopilot_question": {
        "body": "{{1}} has a question about the goal \"{{2}}\":\n\n{{3}}\n\nTap Answer to reply here, or Skip to let it decide.",
        "example": ["Oton", "Book 20 meetings", "Which three customers should I ask for a case study?"],
        "buttons": ["Answer", "Skip"],
    },
    "autopilot_waiting": {
        "body": "{{1}} needs you on the goal \"{{2}}\": {{3}}\n\n{{4}}",
        "example": ["Oton", "Ship the export", "Merge pull request #9", "Tap Show me for the details."],
        "buttons": ["Show me"],
    },
}


class WhatsAppError(Exception):
    pass


def enabled() -> bool:
    return get_settings().whatsapp_enabled


# --- sending ---------------------------------------------------------------------------------------

def _digits(number: str) -> str:
    return re.sub(r"\D", "", number or "")


def _cut(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _flat(text: str, n: int) -> str:
    """Template parameters: no new lines, tabs or runs of spaces, and not empty."""
    text = re.sub(r"\s+", " ", text or "").strip()
    return _cut(text, n) or "-"


async def _post(payload: dict) -> str:
    st = get_settings()
    url = f"{GRAPH}/{st.whatsapp_graph_version}/{st.whatsapp_phone_number_id}/messages"
    async with httpx.AsyncClient(timeout=20, transport=TRANSPORT) as c:
        try:
            r = await c.post(url, json={"messaging_product": "whatsapp", "recipient_type": "individual", **payload},
                             headers={"Authorization": f"Bearer {st.whatsapp_access_token}"})
        except httpx.HTTPError as e:
            raise WhatsAppError(f"Couldn't reach WhatsApp ({type(e).__name__})") from e
    if r.status_code >= 400:
        try:
            err = r.json().get("error", {})
            msg = f"{err.get('code')}: {err.get('message')}"
        except ValueError:
            msg = r.text[:200]
        raise WhatsAppError(f"WhatsApp refused the message ({msg})")
    return (r.json().get("messages") or [{}])[0].get("id") or f"unknown-{secrets.token_hex(6)}"


class Out:
    """Messages to one person, recorded so replies to them find their request."""

    def __init__(self, s: AsyncSession, user: User):
        self.s, self.user, self.to = s, user, _digits(user.whatsapp_number or "")

    async def _send(self, payload: dict, kind: str, request_id: str | None) -> str:
        wa_id = await _post({"to": self.to, **payload})
        self.s.add(WhatsAppMessage(user_id=self.user.id, request_id=request_id, wa_message_id=wa_id,
                                   direction="out", kind=kind))
        return wa_id

    async def text(self, body: str, request_id: str | None = None) -> str:
        return await self._send({"type": "text", "text": {"body": _cut(body, TEXT_MAX), "preview_url": True}},
                                "text", request_id)

    async def buttons(self, body: str, buttons: list[tuple[str, str]], *, request_id: str | None = None,
                      header: str | None = None, footer: str | None = None) -> str:
        inter = {"type": "button", "body": {"text": _cut(body, BODY_MAX)},
                 "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": _cut(t, 20)}} for i, t in buttons[:3]]}}
        if header:
            inter["header"] = {"type": "text", "text": _cut(header, 60)}
        if footer:
            inter["footer"] = {"text": _cut(footer, 60)}
        return await self._send({"type": "interactive", "interactive": inter}, "card", request_id)

    async def choices(self, body: str, label: str, rows: list[tuple[str, str, str]], *, request_id: str | None = None,
                      header: str | None = None, footer: str | None = None) -> str:
        inter = {"type": "list", "body": {"text": _cut(body, BODY_MAX)},
                 "action": {"button": _cut(label, 20), "sections": [{"title": _cut(label, 24), "rows": [
                     {"id": i, "title": _cut(t, 24), **({"description": _cut(d, 72)} if d else {})} for i, t, d in rows[:10]]}]}}
        if header:
            inter["header"] = {"type": "text", "text": _cut(header, 60)}
        if footer:
            inter["footer"] = {"text": _cut(footer, 60)}
        return await self._send({"type": "interactive", "interactive": inter}, "list", request_id)

    async def link(self, body: str, label: str, url: str, *, request_id: str | None = None,
                   header: str | None = None) -> str:
        inter = {"type": "cta_url", "body": {"text": _cut(body, BODY_MAX)},
                 "action": {"name": "cta_url", "parameters": {"display_text": _cut(label, 20), "url": url}}}
        if header:
            inter["header"] = {"type": "text", "text": _cut(header, 60)}
        return await self._send({"type": "interactive", "interactive": inter}, "card", request_id)

    async def template(self, name: str, params: list[str], payloads: list[str], request_id: str | None) -> str:
        components = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
        components += [{"type": "button", "sub_type": "quick_reply", "index": str(i),
                        "parameters": [{"type": "payload", "payload": p}]} for i, p in enumerate(payloads)]
        return await self._send({"type": "template", "template": {
            "name": name, "language": {"code": get_settings().whatsapp_template_lang}, "components": components}},
            "template", request_id)


# --- signed button payloads ----------------------------------------------------------------------

def _sig(action: str, rid: str, uid: str) -> str:
    return hmac.new(get_settings().secret(), f"wa|{action}|{rid}|{uid}".encode(), hashlib.sha256).hexdigest()[:20]


def payload(action: str, rid: str, uid: str) -> str:
    return f"{action}.{rid}.{_sig(action, rid, uid)}"


def parse_payload(p: str, uid: str) -> tuple[str, str] | None:
    parts = (p or "").split(".")
    if len(parts) != 3 or not hmac.compare_digest(parts[2], _sig(parts[0], parts[1], uid)):
        return None
    return parts[0], parts[1]


# --- linking a number -----------------------------------------------------------------------------

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I


def _code_hash(code: str) -> str:
    return hmac.new(get_settings().secret(), f"wa-link|{code.upper()}".encode(), hashlib.sha256).hexdigest()


def start_link(user: User) -> dict:
    """A one-time code the person sends from their own phone (a wa.me link prefills it)."""
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
    user.whatsapp_link_code_hash = _code_hash(code)
    user.whatsapp_link_code_expires_at = utcnow() + LINK_CODE_TTL
    text = f"Connect my Oton account: {code}"
    number = _digits(get_settings().whatsapp_business_number or "")
    return {"code": code, "url": f"https://wa.me/{number}?text={quote(text)}", "text": text,
            "expires_at": user.whatsapp_link_code_expires_at.isoformat()}


def prefs_of(user: User) -> dict:
    return {**DEFAULT_PREFS, **(user.whatsapp_prefs or {})}


def unlink(user: User) -> None:
    user.whatsapp_number = None
    user.whatsapp_linked_at = None
    user.whatsapp_last_inbound_at = None
    user.whatsapp_state = None


def masked(number: str | None) -> str | None:
    d = _digits(number or "")
    return f"+{'•' * max(0, len(d) - 4)}{d[-4:]}" if d else None


# --- what a request looks like ----------------------------------------------------------------------

def in_window(user: User) -> bool:
    at = user.whatsapp_last_inbound_at
    return bool(at and utcnow() - at < WINDOW)


def app_link(req: UserRequest) -> str:
    return get_settings().frontend_origin.rstrip("/") + f"/approvals?id={req.id}"


def app_only(req: UserRequest) -> str | None:
    """Why this one needs the app, or None when it can be decided on WhatsApp."""
    if req.kind == RequestKind.action.value:
        if req.action_type in APP_ONLY_TYPES:
            return APP_ONLY_TYPES[req.action_type]
        if req.est_spend_usd:
            return "It spends money"
    return None


def pref_key(req: UserRequest) -> str:
    if req.kind == RequestKind.question.value:
        return "questions"
    if req.auto_approve_at:
        return "heads_ups"
    return "approvals"


_FIELD_ORDER = ["to", "recipient", "recipients", "email", "channel", "subreddit", "subject", "title", "content",
                "body", "text", "message", "comment", "description"]
_GENERIC_REASONS = {"Needs your approval.", "Goes ahead after a heads-up unless someone stops it.", ""}


def _fields(req: UserRequest) -> list[tuple[str, str]]:
    f = (req.preview or {}).get("fields") or {}
    keys = sorted(f, key=lambda k: (_FIELD_ORDER.index(k) if k in _FIELD_ORDER else 99, k))
    out = []
    for k in keys:
        v = f[k]
        if v in (None, "", [], {}):
            continue
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        elif not isinstance(v, str):
            v = str(v)
        out.append((k, v))
    return out


def _quote(text: str) -> str:
    return "\n".join("> " + line if line.strip() else ">" for line in text.strip().splitlines())


def _fields_text(req: UserRequest) -> str:
    parts = []
    for k, v in _fields(req):
        label = k.replace("_", " ").capitalize()
        if len(v) > 80 or "\n" in v:
            parts.append(f"*{label}:*\n{_quote(v)}")
        else:
            parts.append(f"*{label}:* {v}")
    return "\n".join(parts)


def _minutes_left(req: UserRequest) -> int:
    if not req.auto_approve_at:
        return 0
    return max(1, round((req.auto_approve_at - utcnow()).total_seconds() / 60))


def editable(req: UserRequest) -> list[str]:
    return list((req.preview or {}).get("editable") or [])


async def _who(s: AsyncSession, req: UserRequest) -> tuple[str, Campaign]:
    """Who's asking, as people see it: Oton (the goal is named alongside), or the team's Reviewer."""
    c = await s.get(Campaign, req.campaign_id)
    lead = (req.preview or {}).get("lead")
    return (f"the {lead}" if lead else "Oton"), c


def _upper_first(text: str) -> str:
    return text[:1].upper() + text[1:]


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text and not text[:2].isupper() else text


async def card(s: AsyncSession, out: Out, req: UserRequest, *, note: str = "") -> None:
    """The full request: everything needed to decide, with buttons. Long content goes first as
    plain text (WhatsApp cards hold 1024 characters)."""
    agent, c = await _who(s, req)
    uid = out.user.id
    goal = (c.name + (f" (for {c.client_name})" if c.client_name else "")) if c else ""
    why = req.rationale if req.rationale not in _GENERIC_REASONS else ""
    p = req.preview or {}
    quality = p.get("quality")
    qline = (f"Quality check {quality['score']}/5" + (f" · notes: {'; '.join(quality['fixes'][:2])}" if quality.get("fixes") and quality["score"] < 4 else "")) if quality else ""

    async def with_long(intro: str, content: str, tail: str) -> str:
        """The card body; content that doesn't fit goes before it as plain text."""
        body = "\n\n".join(x for x in [intro, content, tail] if x)
        if len(body) <= BODY_MAX - 20:
            return body
        chunks = [content[i:i + TEXT_MAX - 100] for i in range(0, len(content), TEXT_MAX - 100)]
        for i, chunk in enumerate(chunks[:MAX_CHUNKS]):
            more = f"\n\n… the rest is in Oton: {app_link(req)}" if i == MAX_CHUNKS - 1 and len(chunks) > MAX_CHUNKS else ""
            await out.text(chunk + more, req.id)
        return "\n\n".join(x for x in [intro, "_The full text is in the message above._", tail] if x)

    if note:
        await out.text(note)

    if req.kind == RequestKind.action.value:
        label = ACTION_TYPES.get(req.action_type or "", ACTION_TYPES["other_write"]).label
        where = f" on {req.scope}" if req.scope else ""
        if req.auto_approve_at:
            intro = (f"*Heads-up:* {agent} will *{_lower_first(req.title)}*{where} in about {_minutes_left(req)} min "
                     f"unless you stop it.\n_{goal}_")
        else:
            intro = f"{agent} wants to *{_lower_first(req.title)}*{where}.\n_{goal}_"
        if why:
            intro += f"\n\n_Why it's asking:_ {why}"
        details = p.get("details") if isinstance(p.get("details"), str) else ""
        content = "\n".join(x for x in [_fields_text(req), _cut(details, 600)] if x)
        reason = app_only(req)
        if reason:
            body = "\n\n".join(x for x in [intro, _cut(content, 600), qline,
                                            f"*{reason}, so it's decided in Oton.*"] if x)
            await out.link(body, "Open in Oton", app_link(req), request_id=req.id, header=f"{label}")
            return
        body = await with_long(intro, content, qline)
        if req.auto_approve_at:
            btns = [(payload("ok", req.id, uid), "Send now")]
        else:
            btns = [(payload("ok", req.id, uid), "Approve")]
        if editable(req):
            btns.append((payload("ed", req.id, uid), "Edit"))
        btns.append((payload("no", req.id, uid), "Stop it" if req.auto_approve_at else "Decline"))
        await out.buttons(body, btns, request_id=req.id, header=_cut(f"{label}{where}", 60),
                          footer="Reply to this message to add a comment")
        return

    if req.kind == RequestKind.question.value:
        q = p.get("question") or req.title
        intro = f"{agent} has a question:\n*{q}*\n_{goal}_" + (f"\n\n{why}" if why else "")
        options = [o for o in p.get("options") or [] if isinstance(o, str) and o.strip()]
        if options and len(options) <= 3 and all(len(o) <= 20 for o in options):
            btns = [(payload(f"o{i}", req.id, uid), o) for i, o in enumerate(options)]
            if len(btns) < 3:
                btns.append((payload("skip", req.id, uid), "Skip"))
            await out.buttons(intro, btns, request_id=req.id, header="Question",
                              footer="Or reply to this message with your answer")
        elif options:
            rows = [(payload(f"o{i}", req.id, uid), o if len(o) <= 24 else f"Option {i + 1}", "" if len(o) <= 24 else o)
                    for i, o in enumerate(options[:9])]
            rows.append((payload("skip", req.id, uid), "Skip", "Let it decide"))
            await out.choices(intro, "Pick an answer", rows, request_id=req.id, header="Question",
                              footer="Or reply to this message with your answer")
        else:
            await out.buttons(intro + "\n\nReply to this message with your answer.",
                              [(payload("ans", req.id, uid), "Answer"), (payload("skip", req.id, uid), "Skip: you decide")],
                              request_id=req.id, header="Question")
        return

    if req.kind == RequestKind.review.value:
        kind = {"prd": "a PRD", "analysis": "an analysis", "report": "a report"}.get(p.get("kind", ""), "some work")
        intro = f"{agent} handed in {kind}: *{req.title}*\n_{goal}_"
        if p.get("summary"):
            intro += f"\n\n{p['summary']}"
        content = ((p.get("fields") or {}).get("content") or "").strip()
        tail = "Approving hands it on as a new goal to build it." if p.get("handoff_to") else ""
        body = await with_long(intro, content, tail)
        btns = [(payload("ok", req.id, uid), "Approve")]
        if editable(req):
            btns.append((payload("ed", req.id, uid), "Edit"))
        btns.append((payload("no", req.id, uid), "Ask for changes"))
        await out.buttons(body, btns, request_id=req.id, header="Review")
        return

    if req.kind == RequestKind.proposal.value:
        ch = p.get("change") or {}
        yes = {"target": "Approve new target", "pause": "Pause it", "resume": "Restart it", "new_goal": "Start this goal",
               "new_agent": "Start this goal"}.get(ch.get("type", ""), "Approve")
        lines = [f"{_upper_first(agent)} suggests: *{req.title}*", f"_{goal}_"]
        cur = p.get("current") or {}
        if ch.get("type") == "target" and cur.get("target") is not None:
            lines.append(f"Now: {cur['target']:g} per {cur.get('period', 'period')}"
                         + (f" ({cur['progress']:g} so far)" if cur.get("progress") is not None else ""))
            lines.append(f"New: {(p.get('fields') or {}).get('target', ch.get('target'))} per {ch.get('period', 'period')}")
        if p.get("budget_usd"):
            lines.append(f"Budget: ${p['budget_usd']:.2f}")
        body = "\n".join(lines) + (f"\n\n_Why:_ {req.rationale}" if req.rationale else "")
        btns = [(payload("ok", req.id, uid), yes)]
        if ch.get("type") == "target":
            btns.append((payload("ed", req.id, uid), "Change number"))
        btns.append((payload("no", req.id, uid), "Keep as is"))
        await out.buttons(body, btns, request_id=req.id, header="Suggestion")
        return

    if req.kind == RequestKind.connect.value:
        body = (f"{agent} needs *{p.get('app') or req.scope}* connected to carry on with \"{goal}\".\n\n"
                f"Connect it here (it opens the app's own sign-in): {p.get('url')}" + (f"\n\n{why}" if why else ""))
        await out.buttons(body, [(payload("ok", req.id, uid), "I've connected it"), (payload("no", req.id, uid), "Not now")],
                          request_id=req.id, header="Connect an app")
        return

    if req.kind == RequestKind.login.value:
        body = (f"{agent} needs you to sign in to *{p.get('site') or req.scope}* in Oton Chrome, the AI's own Chrome window "
                f"on your computer, for \"{goal}\". Sign in there, then tap below." + (f"\n\n{why}" if why else ""))
        await out.buttons(body, [(payload("ok", req.id, uid), "I've signed in"), (payload("no", req.id, uid), "Not now")],
                          request_id=req.id, header="Sign in")
        return

    await out.link(f"{agent} needs you: *{req.title}*\n_{goal}_", "Open in Oton", app_link(req), request_id=req.id)


def _template_preview(req: UserRequest) -> tuple[str, bool]:
    """A one-paragraph preview for a template, and whether it shows everything."""
    text = " · ".join(f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in _fields(req))
    flat = re.sub(r"\s+", " ", text).strip()
    return _flat(flat, 600), len(flat) <= 600


async def template_for(s: AsyncSession, out: Out, req: UserRequest, more: int) -> None:
    """Outside the 24-hour window: a pre-approved template. One tap reopens the window."""
    agent, c = await _who(s, req)
    agent = _upper_first(agent)
    uid = out.user.id
    goal = _flat(c.name if c else "", 120)
    also = f" Also waiting: {more} more." if more else ""
    if req.kind == RequestKind.action.value and not app_only(req):
        preview, _ = _template_preview(req)
        if req.auto_approve_at:
            await out.template("autopilot_heads_up",
                               [_flat(agent, 60), goal, _flat(_lower_first(req.title), 200), str(_minutes_left(req)),
                                _flat(preview + also, 700)],
                               [payload("no", req.id, uid), payload("sh", req.id, uid), payload("tok", req.id, uid)], req.id)
        else:
            await out.template("autopilot_approval",
                               [_flat(agent, 60), goal, _flat(req.title, 200), _flat(preview + also, 700)],
                               [payload("tok", req.id, uid), payload("sh", req.id, uid), payload("no", req.id, uid)], req.id)
        return
    if req.kind == RequestKind.question.value:
        await out.template("autopilot_question", [_flat(agent, 60), goal, _flat((req.preview or {}).get("question") or req.title, 700)],
                           [payload("sh", req.id, uid), payload("skip", req.id, uid)], req.id)
        return
    extra = (app_only(req) + ", so it's decided in Oton.") if app_only(req) else "Tap Show me for the details."
    await out.template("autopilot_waiting", [_flat(agent, 60), goal, _flat(req.title, 200), _flat(extra + also, 300)],
                       [payload("sh", req.id, uid)], req.id)


# --- whose turn it is --------------------------------------------------------------------------------

async def pending_for(s: AsyncSession, user: User, *, exclude: set[str] | None = None) -> list[UserRequest]:
    """What's waiting on this person, heads-ups first (they're on a clock), then oldest first."""
    member = await load_member(s, user)
    if not member:
        return []
    rows = (await s.execute(select(UserRequest).join(Campaign, Campaign.id == UserRequest.campaign_id).where(
        Campaign.org_id == member.org_id, UserRequest.status == RequestStatus.pending.value,
    ).order_by(UserRequest.created_at))).scalars().all()
    out = []
    for r in rows:
        if exclude and r.id in exclude:
            continue
        c = await s.get(Campaign, r.campaign_id)
        if user.id in {u.id for u in await approvers(s, c.org_id, r.department_id, c.agent_id)}:
            out.append(r)
    return sorted(out, key=lambda r: (r.auto_approve_at is None, r.auto_approve_at or r.created_at))


async def send_next(s: AsyncSession, out: Out, *, exclude: set[str] | None = None, lead: str = "") -> None:
    queue = await pending_for(s, out.user, exclude=exclude)
    if not queue:
        await out.text((lead + "\n\n" if lead else "") + "That's everything. Nothing else is waiting on you.")
        return
    more = len(queue) - 1
    note = (lead + " " if lead else "") + (f"Next ({more} more after this):" if more else "Next, the last one:")
    await card(s, out, queue[0], note=note.strip())


async def show_queue(s: AsyncSession, out: Out) -> None:
    queue = await pending_for(s, out.user)
    if not queue:
        await out.text("Nothing is waiting on you right now. New requests from Oton will show up here.")
        return
    if len(queue) == 1:
        await card(s, out, queue[0])
        return
    rows = []
    for r in queue[:10]:
        _, c = await _who(s, r)
        tag = "Heads-up" if r.auto_approve_at else {"question": "Question", "review": "Review", "proposal": "Suggestion"}.get(r.kind, "Approval")
        rows.append((payload("sh", r.id, out.user.id), _cut(r.title, 24), _cut(f"{tag} · {c.name}" if c else tag, 72)))
    await out.choices(f"{len(queue)} things are waiting on you." + (" Showing the first 10." if len(queue) > 10 else ""),
                      "See them", rows)


# --- delivering new requests ----------------------------------------------------------------------------

async def deliver(s: AsyncSession, limit: int = 40) -> int:
    """Push new requests to the people they're routed to (run by the worker every few seconds)."""
    if not enabled():
        return 0
    users = (await s.execute(select(User).where(User.whatsapp_number.is_not(None)))).scalars().all()
    if not users:
        return 0
    by_id = {u.id: u for u in users}
    reqs = (await s.execute(select(UserRequest).where(
        UserRequest.status == RequestStatus.pending.value, UserRequest.created_at > utcnow() - RECENT,
    ).order_by(UserRequest.created_at))).scalars().all()
    if not reqs:
        return 0
    sent_pairs = set((await s.execute(select(WhatsAppMessage.request_id, WhatsAppMessage.user_id).where(
        WhatsAppMessage.direction == "out", WhatsAppMessage.request_id.in_([r.id for r in reqs])))).all())
    new: dict[str, list[UserRequest]] = {}
    for r in reqs:
        c = await s.get(Campaign, r.campaign_id)
        if not c:
            continue
        for u in await approvers(s, c.org_id, r.department_id, c.agent_id):
            if u.id in by_id and (r.id, u.id) not in sent_pairs and prefs_of(by_id[u.id]).get(pref_key(r), True):
                new.setdefault(u.id, []).append(r)
    sent = 0
    for uid, items in new.items():
        if sent >= limit:
            break
        user = by_id[uid]
        out = Out(s, user)
        items.sort(key=lambda r: (r.auto_approve_at is None, r.auto_approve_at or r.created_at))
        try:
            if in_window(user):
                if len(items) >= 3:
                    for r in items:  # recorded as told, so they aren't pushed again; "next" shows each
                        s.add(WhatsAppMessage(user_id=uid, request_id=r.id, wa_message_id="queued", direction="out", kind="queued"))
                    await card(s, out, items[0], note=f"{len(items)} new things need you. First, {len(items) - 1} more after this:")
                else:
                    for r in items:
                        await card(s, out, r)
                sent += len(items)
            else:
                if await _template_recently(s, user):
                    continue  # one unanswered nudge is enough; the rest follow when they reply
                await template_for(s, out, items[0], len(items) - 1)
                for r in items[1:]:
                    s.add(WhatsAppMessage(user_id=uid, request_id=r.id, wa_message_id="queued", direction="out", kind="queued"))
                sent += 1
        except WhatsAppError as e:
            log.warning("WhatsApp delivery to %s failed: %s", uid, e)
    return sent


async def _template_recently(s: AsyncSession, user: User) -> bool:
    last = (await s.execute(select(func.max(WhatsAppMessage.created_at)).where(
        WhatsAppMessage.user_id == user.id, WhatsAppMessage.kind == "template"))).scalar_one()
    if not last:
        return False
    answered = user.whatsapp_last_inbound_at and user.whatsapp_last_inbound_at > last
    return not answered and utcnow() - last < TEMPLATE_GAP


# --- incoming messages ------------------------------------------------------------------------------------

def check_signature(raw: bytes, header: str | None) -> bool:
    secret = get_settings().whatsapp_app_secret or ""
    if not secret or not header or not header.startswith("sha256="):
        return False
    good = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, header.split("=", 1)[1])


async def handle_webhook(s: AsyncSession, data: dict) -> None:
    for entry in data.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for status in value.get("statuses") or []:
                await _status(s, status)
            for msg in value.get("messages") or []:
                try:
                    await _inbound(s, msg)
                except WhatsAppError as e:
                    log.warning("WhatsApp reply failed: %s", e)


async def _status(s: AsyncSession, status: dict) -> None:
    """A message we sent couldn't be delivered because the 24-hour window had closed (131047):
    forget the window, so the next one goes as a template."""
    if status.get("status") != "failed":
        return
    if not any(str(e.get("code")) == "131047" for e in status.get("errors") or []):
        return
    msg = (await s.execute(select(WhatsAppMessage).where(WhatsAppMessage.wa_message_id == status.get("id")))).scalars().first()
    if msg and msg.user_id:
        user = await s.get(User, msg.user_id)
        if user:
            user.whatsapp_last_inbound_at = None
        if msg.request_id:
            await s.delete(msg)  # so it's delivered again


LINK_RE = re.compile(r"\b([A-HJ-NP-Z2-9]{6})\b")
STOP_WORDS = {"stop", "unsubscribe", "disconnect"}
LIST_WORDS = {"list", "pending", "next", "menu", "waiting", "show", "inbox"}


async def _inbound(s: AsyncSession, msg: dict) -> None:
    wa_id = msg.get("id") or ""
    seen = (await s.execute(select(WhatsAppMessage.id).where(WhatsAppMessage.wa_message_id == wa_id,
                                                              WhatsAppMessage.direction == "in"))).first()
    if seen:
        return  # Meta retries webhooks
    number = "+" + _digits(msg.get("from") or "")
    user = (await s.execute(select(User).where(User.whatsapp_number == number))).scalar_one_or_none()
    s.add(WhatsAppMessage(user_id=user.id if user else None, wa_message_id=wa_id, direction="in", kind="inbound"))
    text = ((msg.get("text") or {}).get("body") or "").strip()
    tapped = ((msg.get("button") or {}).get("payload")
              or ((msg.get("interactive") or {}).get("button_reply") or {}).get("id")
              or ((msg.get("interactive") or {}).get("list_reply") or {}).get("id"))

    if text and (not user or LINK_RE.search(text)) and await _maybe_link(s, number, text):
        return
    if not user:
        await _post({"to": _digits(number), "type": "text", "text": {"body": (
            "This number isn't connected to Oton yet. In Oton, open Settings → WhatsApp and tap "
            "Connect WhatsApp to get your code.")}})
        return
    user.whatsapp_last_inbound_at = utcnow()
    out = Out(s, user)
    member = await load_member(s, user)
    if not member:
        await out.text("You're not part of an organization in Oton any more, so there's nothing to show here.")
        return
    if tapped:
        parsed = parse_payload(tapped, user.id)
        if not parsed:
            await out.text("That button isn't valid any more. Here's what's waiting:")
            await show_queue(s, out)
            return
        await _tap(s, out, member, *parsed)
        return
    if text:
        await _text(s, out, member, text, (msg.get("context") or {}).get("id"))
        return
    await out.text("I can only read text and button taps here.")


async def _maybe_link(s: AsyncSession, number: str, text: str) -> bool:
    for code in LINK_RE.findall(text):
        user = (await s.execute(select(User).where(User.whatsapp_link_code_hash == _code_hash(code)))).scalar_one_or_none()
        if not user or not user.whatsapp_link_code_expires_at or user.whatsapp_link_code_expires_at < utcnow():
            continue
        other = (await s.execute(select(User).where(User.whatsapp_number == number, User.id != user.id))).scalar_one_or_none()
        if other:
            unlink(other)
            await s.flush()
        user.whatsapp_number = number
        user.whatsapp_linked_at = utcnow()
        user.whatsapp_last_inbound_at = utcnow()
        user.whatsapp_link_code_hash = None
        user.whatsapp_link_code_expires_at = None
        user.whatsapp_state = None
        out = Out(s, user)
        await out.text(
            f"You're connected{', ' + user.name.split()[0] if user.name else ''}. Approvals, heads-ups and questions from "
            "Oton will come here, with everything you need to decide. Tap the buttons, or reply to a message to "
            "answer or comment. Send \"list\" to see what's waiting, or \"stop\" to disconnect.")
        await show_queue(s, out)
        return True
    return False


async def _request(s: AsyncSession, member: Member, rid: str) -> UserRequest | None:
    req = await s.get(UserRequest, rid)
    c = await s.get(Campaign, req.campaign_id) if req else None
    return req if req and c and c.org_id == member.org_id else None


def _state(user: User) -> dict:
    return dict(user.whatsapp_state or {})


def _set_state(user: User, **kw) -> None:
    user.whatsapp_state = {**{k: v for k, v in _state(user).items() if k == "asked"}, **kw}


async def _decide(s: AsyncSession, out: Out, member: Member, req: UserRequest, decision: str, *,
                  note: str | None = None, edited: dict | None = None, ask_why: bool = False) -> bool:
    agent, c = await _who(s, req)
    try:
        async with s.begin_nested():  # a refused decision leaves nothing half-done
            await decisions.decide(s, member, req.id, decisions.DecisionIn(
                decision=decision, note=note, edited_fields=edited, via="whatsapp"))
    except decisions.DecisionError as e:
        if e.status == 409:
            await s.refresh(req)
            who = await s.get(User, req.decided_by) if req.decided_by else None
            done = {"approved": "approved", "rejected": "declined", "cancelled": "cancelled"}.get(req.status, req.status)
            await send_next(s, out, exclude={req.id}, lead=(
                f"\"{_cut(req.title, 60)}\" was already {done}" + (f" by {who.name or who.email}" if who else "") + "."))
        else:
            await out.text(e.message)
        return False
    _set_state(out.user)
    ok = decision == "approve"
    heads = req.auto_approve_at is not None
    lead = {
        "action": ("Sending it now." if heads else f"Approved. {agent} will go ahead" + (" with your edit." if edited else "."))
        if ok else ("Stopped. It won't go out." if heads else f"Declined. {agent} won't do this."),
        "question": f"Thanks, {agent} has your answer." if ok else f"Skipped. {agent} will use its judgment.",
        "review": "Approved." if ok else f"Sent back to {agent}.",
        "proposal": "Done." if ok else "Kept as it is.",
        "connect": f"Thanks. {agent} will check the connection.", "login": f"Thanks. {agent} will carry on.",
    }.get(req.kind, "Done.")
    if ask_why:
        _set_state(out.user, wait="why", request_id=req.id)
        lead += f" Want to tell {agent} why? Reply with a reason and it will adjust, or just carry on."
    if ok and req.kind == "action" and c and await _offer_trust(s, out, member, req, c, lead):
        return True
    await send_next(s, out, exclude={req.id}, lead=lead)
    return True


async def _offer_trust(s: AsyncSession, out: Out, member: Member, req: UserRequest, c: Campaign, lead: str) -> bool:
    """After an approval: offer the looser setting this goal has earned (never applied by itself)."""
    from app.org import goal_department

    if not req.action_type or not member.in_department(await goal_department(s, c)):
        return False
    key = f"{c.id}:{req.action_type}"
    asked = (_state(out.user).get("asked") or {}).get(key)
    if asked and utcnow() - datetime.fromisoformat(asked) < TRUST_ASK_EVERY:
        return False
    modes = {p["key"]: p["mode"] for p in await permissions.effective(s, c.id, with_suggestions=False)}
    sug = (await autonomy.suggestions(s, c.id, modes)).get(req.action_type)
    if not sug:
        return False
    state = _state(out.user)
    state["asked"] = {**(state.get("asked") or {}), key: utcnow().isoformat()}
    out.user.whatsapp_state = state
    words = {"heads_up": "Use a heads-up", "auto": "Let it go ahead"}[sug["mode"]]
    await out.buttons(f"{lead}\n\n{sug['reason']}", [(payload("tr", req.id, out.user.id), words),
                                                     (payload("tk", req.id, out.user.id), "Keep asking")],
                      header="Ask less often?")
    return True


async def _tap(s: AsyncSession, out: Out, member: Member, action: str, rid: str) -> None:
    if action == "ls":
        await show_queue(s, out)
        return
    if action == "cx":
        _set_state(out.user)
        await send_next(s, out, lead="OK, left it as it was.")
        return
    if action not in ("oke", "okc"):
        _set_state(out.user)  # a tap moves on from whatever was half-done
    req = await _request(s, member, rid)
    if not req:
        await out.text("I can't find that request any more.")
        return
    if action in ("tr", "tk"):
        await _trust_answer(s, out, member, req, action == "tr")
        return
    if req.status != RequestStatus.pending.value:
        await _decide(s, out, member, req, "approve")  # explains who decided, then shows the next
        return
    if not await can_decide(s, member, req.campaign_id, req.department_id):
        await out.text("This one goes to someone else on your team, so you can't decide it here.")
        return
    if action == "sh":
        await card(s, out, req)
        return
    if app_only(req) and action in ("ok", "tok", "oke"):
        await card(s, out, req)
        return
    if action == "tok":  # "Approve" on a template: only when the template showed everything
        if req.kind != RequestKind.action.value or not _template_preview(req)[1]:
            await card(s, out, req, note="Here's all of it first:")
            return
        await _decide(s, out, member, req, "approve")
        return
    if action == "ok":
        await _decide(s, out, member, req, "approve")
        return
    if action == "no":
        if req.kind == RequestKind.action.value and not req.auto_approve_at:
            agent, _ = await _who(s, req)
            _set_state(out.user, wait="reason", request_id=req.id)
            await out.buttons(f"Why not? {agent} reads your reason and adjusts. Reply with it, or decline without one.",
                              [(payload("nr", req.id, out.user.id), "Just decline"), (payload("cx", "-", out.user.id), "Cancel")],
                              request_id=req.id)
            return
        if req.kind in (RequestKind.review.value,):
            _set_state(out.user, wait="changes", request_id=req.id)
            await out.buttons("What should change? Reply with your notes and it goes back with them.",
                              [(payload("nr", req.id, out.user.id), "Send back, no notes"), (payload("cx", "-", out.user.id), "Cancel")],
                              request_id=req.id)
            return
        await _decide(s, out, member, req, "reject", ask_why=bool(req.auto_approve_at))
        return
    if action == "nr":
        await _decide(s, out, member, req, "reject", note=None)
        return
    if action == "skip":
        await _decide(s, out, member, req, "reject")
        return
    if action == "ans":
        _set_state(out.user, wait="answer", request_id=req.id)
        await out.text("Go ahead: send your answer as your next message.", req.id)
        return
    if action.startswith("o") and action[1:].isdigit() and req.kind == RequestKind.question.value:
        options = (req.preview or {}).get("options") or []
        i = int(action[1:])
        if i < len(options):
            await _decide(s, out, member, req, "approve", note=options[i])
        return
    if action == "ed" or (action.startswith("e") and action[1:].isdigit()):
        await _start_edit(s, out, req, None if action == "ed" else int(action[1:]))
        return
    if action in ("oke", "okc"):
        st = _state(out.user)
        if st.get("request_id") != req.id or "draft" not in st:
            await card(s, out, req, note="That edit expired. Here it is again:")
            return
        if action == "oke":
            await _decide(s, out, member, req, "approve", edited={st["field"]: st["draft"]})
        else:
            await _decide(s, out, member, req, "approve", note=st["draft"])
        return
    await out.text("I didn't understand that button.")


async def _start_edit(s: AsyncSession, out: Out, req: UserRequest, index: int | None) -> None:
    fields = editable(req)
    if not fields:
        await out.text("There's nothing to edit on this one.")
        return
    if index is None and len(fields) > 1:
        rows = [(payload(f"e{i}", req.id, out.user.id), f.replace("_", " ").capitalize(), "") for i, f in enumerate(fields)]
        await out.choices("Which part do you want to change?", "Choose", rows, request_id=req.id)
        return
    field = fields[index or 0] if (index or 0) < len(fields) else fields[0]
    current = str(((req.preview or {}).get("fields") or {}).get(field, ""))
    _set_state(out.user, wait="edit", request_id=req.id, field=field)
    if req.kind == RequestKind.proposal.value:
        await out.text(f"Send the new number (now {current}).", req.id)
        return
    await out.text(f"Here's the current {field.replace('_', ' ')}. Copy it, change it, and send your version as your next message:", req.id)
    await out.text(current or "(empty)", req.id)


async def _trust_answer(s: AsyncSession, out: Out, member: Member, req: UserRequest, yes: bool) -> None:
    from app.org import goal_department

    c = await s.get(Campaign, req.campaign_id)
    if not yes:
        await send_next(s, out, exclude={req.id}, lead="OK, it will keep asking.")
        return
    if not c or not member.in_department(await goal_department(s, c)):
        await out.text("Only people on this team (or admins) can change that.")
        return
    modes = {p["key"]: p["mode"] for p in await permissions.effective(s, c.id, with_suggestions=False)}
    sug = (await autonomy.suggestions(s, c.id, modes)).get(req.action_type or "")
    if not sug:
        await send_next(s, out, exclude={req.id}, lead="That setting has already changed.")
        return
    row = autonomy.PRESETS["balanced"]["rows"].get(req.action_type)
    await autonomy.set_goal_mode(s, c, req.action_type, sug["mode"], daily_cap=row.cap if row else None,
                                 granted_by=member.user.id, source="earned")
    c.guardrail_version += 1
    label = ACTION_TYPES[req.action_type].label
    words = {"heads_up": "goes ahead after a heads-up", "auto": "does this on its own"}[sug["mode"]]
    who = member.user.name or member.user.email
    await activity.log(s, c.id, "system", f'"{label}": {words} (earned; set by {who} on WhatsApp)', status="info")
    await notify(s, c.id, "guardrails")
    tail = " You'll still get a heads-up you can stop." if sug["mode"] == "heads_up" else ""
    await send_next(s, out, exclude={req.id}, lead=f"Done: on \"{c.name}\", \"{label.lower()}\" now {words}.{tail} "
                                                   "Change it any time on the goal page.")


async def _text(s: AsyncSession, out: Out, member: Member, text: str, context_id: str | None) -> None:
    low = text.strip().lower().strip(".!")
    if low in STOP_WORDS:
        unlink(out.user)
        await out.text("Disconnected. You won't get anything from Oton here. Reconnect any time in Settings → WhatsApp.")
        return
    if low in ("help", "?"):
        await out.text("Here you can approve, decline, edit and answer what Oton sends you. Tap the buttons, "
                       "or reply to a message to answer it or add a comment. Send \"list\" to see what's waiting, or "
                       "\"stop\" to disconnect.")
        return
    if low in LIST_WORDS:
        _set_state(out.user)
        await show_queue(s, out)
        return

    st = _state(out.user)
    req = await _request(s, member, st["request_id"]) if st.get("request_id") else None
    # A reply to one of our messages is about that request, whatever was going on before.
    if context_id:
        m = (await s.execute(select(WhatsAppMessage).where(WhatsAppMessage.wa_message_id == context_id,
                                                           WhatsAppMessage.user_id == out.user.id))).scalars().first()
        if m and m.request_id:
            quoted = await _request(s, member, m.request_id)
            if quoted and quoted is not req:
                req, st = quoted, {}
    if not req:
        await out.buttons("I can only take answers, edits and comments on what Oton sent you. "
                          "Reply to one of its messages, or see what's waiting.",
                          [(payload("ls", "-", out.user.id), "What's waiting")])
        return
    if req.status != RequestStatus.pending.value:
        if st.get("wait") == "why" and req.kind == "action":
            await _late_reason(s, out, req, text)
            return
        await _decide(s, out, member, req, "approve")  # says who decided it, and shows the next
        return
    if not await can_decide(s, member, req.campaign_id, req.department_id):
        await out.text("This one goes to someone else on your team, so you can't decide it here.")
        return

    wait = st.get("wait")
    if req.kind == RequestKind.question.value:
        await _decide(s, out, member, req, "approve", note=text)
        return
    if wait in ("reason", "changes"):
        await _decide(s, out, member, req, "reject", note=text)
        return
    if wait == "edit":
        field = st.get("field") or (editable(req) or ["content"])[0]
        if req.kind == RequestKind.proposal.value:
            number = text.replace(",", "").strip()
            try:
                float(number)
            except ValueError:
                await out.text("That needs to be a number. Send just the number, e.g. 60.")
                return
            await _decide(s, out, member, req, "approve", edited={field: number})
            return
        _set_state(out.user, wait="confirm", request_id=req.id, field=field, draft=text)
        verb = "Send edited" if req.auto_approve_at else "Approve edited"
        await out.buttons(f"Your version:\n\n{_quote(_cut(text, 900))}",
                          [(payload("oke", req.id, out.user.id), verb), (payload("ed", req.id, out.user.id), "Edit again"),
                           (payload("cx", "-", out.user.id), "Cancel")], request_id=req.id)
        return
    if app_only(req):
        await out.link("This one is decided in Oton. Your comment wasn't sent; add it there.", "Open in Oton",
                       app_link(req), request_id=req.id)
        return
    # A reply to a request card: a comment, or new text for it.
    _set_state(out.user, wait="confirm", request_id=req.id, field=(editable(req) or [None])[0], draft=text)
    btns = [(payload("okc", req.id, out.user.id), "Approve + comment")]
    if editable(req) and req.kind == RequestKind.action.value:
        btns.append((payload("oke", req.id, out.user.id), "Use as new text"))
    btns.append((payload("cx", "-", out.user.id), "Cancel"))
    await out.buttons(f"What should I do with this?\n\n{_quote(_cut(text, 600))}", btns, request_id=req.id)


async def _late_reason(s: AsyncSession, out: Out, req: UserRequest, text: str) -> None:
    """A reason sent after declining or stopping: kept on the request and in the work log."""
    agent, _ = await _who(s, req)
    req.decision_note = ((req.decision_note + "\n") if req.decision_note else "") + text
    who = out.user.name or out.user.email
    await activity.log(s, req.campaign_id, "note", f"Why {who} said no to \"{_cut(req.title, 80)}\": {_cut(text, 300)}",
                       action_type=req.action_type, details={"request_id": req.id, "via": "whatsapp"})
    _set_state(out.user)
    await send_next(s, out, exclude={req.id}, lead=f"Thanks, {agent} will take that into account.")
