"""WhatsApp: connecting a number, cards inside the 24-hour window, templates outside it, and
deciding from a phone (approve, edit, decline with a reason, stop, answer, earned trust)."""

import hashlib
import hmac
import itertools
import json
import uuid
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI, Request

from app.config import get_settings
from app.db import session_scope
from app.main import app
from app.models import Campaign, User, UserRequest, WhatsAppMessage, utcnow
from app.org import goal_department
from app.services import autonomy, whatsapp
from tests.helpers import agent_in, org_of, sign_in_with_org

NUMBER = "447700900123"
SECRET = "test-app-secret"


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


@pytest.fixture
def sent(monkeypatch) -> list[dict]:
    """WhatsApp turned on, with a fake Graph API that records what we send."""
    st = get_settings()
    for k, v in {"whatsapp_access_token": "tok", "whatsapp_phone_number_id": "PNID", "whatsapp_business_number": "+1 415 555 0100",
                 "whatsapp_app_secret": SECRET, "whatsapp_verify_token": "verify-me"}.items():
        monkeypatch.setattr(st, k, v)
    out: list[dict] = []
    graph = FastAPI()
    ids = itertools.count(1)

    @graph.post("/{version}/{phone}/messages")
    async def messages(version: str, phone: str, request: Request):
        body = await request.json()
        body["_id"] = f"wamid.out{next(ids)}"
        out.append(body)
        return {"messages": [{"id": body["_id"]}]}

    monkeypatch.setattr(whatsapp, "TRANSPORT", httpx.ASGITransport(app=graph))
    return out


def signed(data: dict) -> tuple[bytes, dict]:
    raw = json.dumps(data).encode()
    sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"x-hub-signature-256": f"sha256={sig}", "content-type": "application/json"}


async def inbound(c, *, text: str | None = None, tap: str | None = None, template_tap: str | None = None,
                  context: str | None = None, frm: str = NUMBER) -> None:
    msg: dict = {"from": frm, "id": f"wamid.in{uuid.uuid4().hex[:8]}", "timestamp": "1"}
    if text is not None:
        msg |= {"type": "text", "text": {"body": text}}
    if tap is not None:
        msg |= {"type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": tap, "title": "x"}}}
    if template_tap is not None:
        msg |= {"type": "button", "button": {"payload": template_tap, "text": "x"}}
    if context:
        msg["context"] = {"from": "14155550100", "id": context}
    raw, headers = signed({"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [msg]}}]}]})
    r = await c.post("/api/whatsapp/webhook", content=raw, headers=headers)
    assert r.status_code == 200, r.text


def texts(sent: list[dict]) -> list[str]:
    """Everything a person would read in the messages we sent."""
    out = []
    for m in sent:
        if m["type"] == "text":
            out.append(m["text"]["body"])
        elif m["type"] == "interactive":
            out.append(m["interactive"]["body"]["text"])
        elif m["type"] == "template":
            out.append(m["template"]["name"] + ": " + " | ".join(p["text"] for p in m["template"]["components"][0]["parameters"]))
    return out


def buttons(m: dict) -> dict[str, str]:
    """title -> payload of an interactive buttons message."""
    return {b["reply"]["title"]: b["reply"]["id"] for b in m["interactive"]["action"]["buttons"]}


def last_card(sent: list[dict]) -> dict:
    return next(m for m in reversed(sent) if m["type"] == "interactive" and m["interactive"]["type"] == "button")


async def connect(c, sent) -> dict:
    """Sign in, set up an organization and a goal, and connect WhatsApp the way a person would."""
    await sign_in_with_org(c, "founder@acme.test")
    org = await org_of(c)
    r = await c.post("/api/campaigns", json={"name": "Grow our audience", "goal_description": "Posts for dispatchers",
                                             "primary_metric": "followers", "budget_total": 10,
                                             "agent_id": agent_in(org, "Marketing"), "launch": True})
    goal = r.json()["id"]
    link = (await c.post("/api/whatsapp/link")).json()
    assert link["url"].startswith("https://wa.me/14155550100?text=Connect%20my%20Oton%20account")
    await inbound(c, text=link["text"])
    me = (await c.get("/api/whatsapp/me")).json()
    assert me["connected"] and me["number"].endswith("0123") and "•" in me["number"]
    sent.clear()
    return {"org": org, "goal": goal}


async def make_request(goal: str, **kw) -> str:
    async with session_scope() as s:
        c = await s.get(Campaign, goal)
        r = UserRequest(campaign_id=goal, department_id=await goal_department(s, c), kind=kw.pop("kind", "action"), **kw)
        s.add(r)
        await s.flush()
        return r.id


POST = "Dispatchers who batch stops by zone before 9am save about 40 minutes a day. Here's the 3-step checklist we use."


async def deliver() -> int:
    async with session_scope() as s:
        return await whatsapp.deliver(s)


async def status_of(rid: str) -> UserRequest:
    async with session_scope() as s:
        return await s.get(UserRequest, rid)


# --- connecting ------------------------------------------------------------------------------------

async def test_connecting_a_number_and_the_webhook_checks(sent):
    async with client() as c:
        assert (await c.get("/api/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                                             "hub.challenge": "42"})).text == "42"
        assert (await c.get("/api/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope"})).status_code == 403
        raw, headers = signed({"entry": []})
        assert (await c.post("/api/whatsapp/webhook", content=raw, headers={**headers, "x-hub-signature-256": "sha256=bad"})).status_code == 403

        await sign_in_with_org(c, "founder@acme.test")
        assert (await c.get("/api/whatsapp/me")).json() == {**(await c.get("/api/whatsapp/me")).json(), "available": True,
                                                            "connected": False}
        # A wrong code from a stranger links nothing.
        await inbound(c, text="Connect my Oton account: ABCDEF")
        assert "isn't connected to Oton" in texts(sent)[-1]

        link = (await c.post("/api/whatsapp/link")).json()
        await inbound(c, text=link["text"])
        assert "You're connected" in texts(sent)[-2] and "Nothing is waiting" in texts(sent)[-1]
        async with session_scope() as s:
            u = (await s.execute(__import__("sqlalchemy").select(User))).scalar_one()
            assert u.whatsapp_number == "+" + NUMBER and u.whatsapp_link_code_hash is None
        # The same code can't be used twice, and "stop" disconnects.
        await inbound(c, text="stop")
        assert "Disconnected" in texts(sent)[-1]
        assert (await c.get("/api/whatsapp/me")).json()["connected"] is False
        r = await c.put("/api/whatsapp/me", json={"heads_ups": False})
        assert r.json()["prefs"] == {"approvals": True, "heads_ups": False, "questions": True}


# --- deciding from WhatsApp -------------------------------------------------------------------------

async def test_full_card_then_approve_and_the_next_one_follows(sent):
    async with client() as c:
        ctx = await connect(c, sent)
        first = await make_request(ctx["goal"], action_type="publish_post", scope="x.com", title="Post a routing tip on X",
                                   rationale="Needs your approval.",
                                   preview={"site": "x.com", "fields": {"content": POST}, "editable": ["content"],
                                            "quality": {"score": 5, "fixes": []}})
        second = await make_request(ctx["goal"], action_type="send_message", scope="gmail", title="Email Dana at Fleetco",
                                    preview={"fields": {"to": "dana@fleetco.test", "subject": "Routing", "body": "Hi Dana"},
                                             "editable": ["body"]})
        assert await deliver() == 2
        assert await deliver() == 0, "each request goes out once"
        card = sent[0]["interactive"]
        assert POST in card["body"]["text"] and "Quality check 5/5" in card["body"]["text"]
        assert set(buttons(sent[0])) == {"Approve", "Edit", "Decline"}
        assert "Grow our audience" in card["body"]["text"] and card["header"]["text"] == "Publish posts on x.com"

        sent.clear()
        await inbound(c, tap=buttons({"interactive": card})["Approve"])
        r = await status_of(first)
        assert r.status == "approved" and r.decided_by
        assert texts(sent)[0].startswith("Approved.")
        assert "email Dana at Fleetco" in " ".join(texts(sent)) and "To:* dana@fleetco.test" in " ".join(texts(sent))
        log = (await c.get(f"/api/campaigns/{ctx['goal']}/activity")).json()
        assert any(a["kind"] == "decision" and a["details"].get("via") == "whatsapp" for a in log)

        # A stale tap on the first one says it's done, and moves on.
        sent.clear()
        await inbound(c, tap=buttons({"interactive": card})["Approve"])
        assert "was already approved by" in texts(sent)[0]


async def test_edit_then_approve_and_decline_with_a_reason(sent):
    async with client() as c:
        ctx = await connect(c, sent)
        rid = await make_request(ctx["goal"], action_type="publish_post", scope="x.com", title="Post a tip",
                                 preview={"fields": {"content": POST}, "editable": ["content"]})
        await deliver()
        await inbound(c, tap=buttons(last_card(sent))["Edit"])
        assert texts(sent)[-1] == POST, "the current text comes on its own, easy to copy"
        await inbound(c, text=POST.replace("40 minutes", "45 minutes"))
        confirm = last_card(sent)
        assert "45 minutes" in confirm["interactive"]["body"]["text"]
        await inbound(c, tap=buttons(confirm)["Approve edited"])
        r = await status_of(rid)
        assert r.status == "approved" and "45 minutes" in r.edited_fields["content"]

        rid = await make_request(ctx["goal"], action_type="publish_post", title="Post another tip",
                                 preview={"fields": {"content": POST}, "editable": ["content"]})
        await deliver()
        await inbound(c, tap=buttons(last_card(sent))["Decline"])
        assert "Why not?" in texts(sent)[-1]
        assert (await status_of(rid)).status == "pending", "it waits for the reason"
        await inbound(c, text="Too similar to yesterday's post")
        r = await status_of(rid)
        assert r.status == "rejected" and r.decision_note == "Too similar to yesterday's post"


async def test_reply_to_a_card_is_a_comment_or_new_text(sent):
    async with client() as c:
        ctx = await connect(c, sent)
        rid = await make_request(ctx["goal"], action_type="publish_post", title="Post a tip",
                                 preview={"fields": {"content": POST}, "editable": ["content"]})
        await deliver()
        await inbound(c, text="Go ahead, and tag @fleetco", context=last_card(sent)["_id"])
        choice = last_card(sent)
        assert set(buttons(choice)) == {"Approve + comment", "Use as new text", "Cancel"}
        await inbound(c, tap=buttons(choice)["Approve + comment"])
        r = await status_of(rid)
        assert r.status == "approved" and r.decision_note == "Go ahead, and tag @fleetco" and not r.edited_fields


async def test_outside_the_window_a_template_then_cards(sent):
    async with client() as c:
        ctx = await connect(c, sent)
        async with session_scope() as s:
            u = (await s.execute(__import__("sqlalchemy").select(User))).scalar_one()
            u.whatsapp_last_inbound_at = utcnow() - timedelta(hours=30)
        first = await make_request(ctx["goal"], action_type="publish_post", title="Post a tip",
                                   preview={"fields": {"content": POST}, "editable": ["content"]})
        second = await make_request(ctx["goal"], action_type="publish_post", title="Post another",
                                    preview={"fields": {"content": "Short one"}, "editable": ["content"]})
        assert await deliver() == 1
        assert len(sent) == 1 and sent[0]["type"] == "template"
        t = sent[0]["template"]
        assert t["name"] == "autopilot_approval"
        params = [p["text"] for p in t["components"][0]["parameters"]]
        assert "\n" not in "".join(params) and "Also waiting: 1 more." in params[3]
        # One unanswered nudge is enough.
        await make_request(ctx["goal"], action_type="publish_post", title="Third", preview={"fields": {"content": "x"}})
        assert await deliver() == 0

        # "Approve" on the template works when it showed everything; then the window is open.
        approve = t["components"][1]["parameters"][0]["payload"]
        sent.clear()
        await inbound(c, template_tap=approve)
        assert (await status_of(first)).status == "approved"
        assert sent[-1]["type"] == "interactive" and "Short one" in texts(sent)[-1]
        assert (await status_of(second)).status == "pending"


async def test_heads_ups_stop_and_send_now(sent):
    async with client() as c:
        ctx = await connect(c, sent)
        rid = await make_request(ctx["goal"], action_type="publish_post", title="Post a tip", auto_approve_at=autonomy.heads_up_at(),
                                 preview={"fields": {"content": POST}, "editable": ["content"], "heads_up": True})
        await deliver()
        card = last_card(sent)
        assert set(buttons(card)) == {"Send now", "Edit", "Stop it"}
        assert "*Heads-up:*" in card["interactive"]["body"]["text"] and "unless you stop it" in card["interactive"]["body"]["text"]
        await inbound(c, tap=buttons(card)["Stop it"])
        assert (await status_of(rid)).status == "rejected", "stopping is immediate: it's on a clock"
        assert "Stopped. It won't go out." in texts(sent)[-1] or "Stopped. It won't go out." in " ".join(texts(sent))
        await inbound(c, text="Wrong tone")
        r = await status_of(rid)
        assert r.decision_note == "Wrong tone"
        log = (await c.get(f"/api/campaigns/{ctx['goal']}/activity")).json()
        assert any("Wrong tone" in a["title"] for a in log)


async def test_questions_by_button_list_or_reply(sent):
    async with client() as c:
        ctx = await connect(c, sent)
        q1 = await make_request(ctx["goal"], kind="question", title="Which region first?",
                                preview={"question": "Which region first?", "options": ["UK", "Germany"]})
        await deliver()
        card = last_card(sent)
        assert set(buttons(card)) == {"UK", "Germany", "Skip"}
        await inbound(c, tap=buttons(card)["Germany"])
        r = await status_of(q1)
        assert r.status == "approved" and r.decision_note == "Germany"

        long_options = ["Fleet managers at mid-size logistics companies", "Owner-operators", "Dispatch software resellers", "Ports"]
        q2 = await make_request(ctx["goal"], kind="question", title="Who should I target?",
                                preview={"question": "Who should I target?", "options": long_options})
        await deliver()
        lst = next(m for m in reversed(sent) if m["type"] == "interactive" and m["interactive"]["type"] == "list")
        rows = lst["interactive"]["action"]["sections"][0]["rows"]
        assert rows[0]["title"] == "Option 1" and rows[0]["description"] == long_options[0] and rows[-1]["title"] == "Skip"
        await inbound(c, text="Owner-operators in Texas", context=lst["_id"])
        r = await status_of(q2)
        assert r.status == "approved" and r.decision_note == "Owner-operators in Texas"


async def test_money_and_code_stay_in_the_app_and_buttons_cant_be_forged(sent):
    async with client() as c:
        ctx = await connect(c, sent)
        rid = await make_request(ctx["goal"], action_type="spend_money", title="Boost the launch post", est_spend_usd=Decimal("40"),
                                 preview={"fields": {"budget": "40"}})
        await deliver()
        m = sent[-1]["interactive"]
        assert m["type"] == "cta_url" and m["action"]["parameters"]["url"].endswith(f"/approvals?id={rid}")
        assert "It spends money" in m["body"]["text"]
        # Even a correctly signed "approve" for it only shows the card again.
        async with session_scope() as s:
            uid = (await s.execute(__import__("sqlalchemy").select(User))).scalar_one().id
        await inbound(c, tap=whatsapp.payload("ok", rid, uid))
        assert (await status_of(rid)).status == "pending"
        # A token signed for someone else is refused.
        other = await make_request(ctx["goal"], action_type="publish_post", title="Post", preview={"fields": {"content": "x"}})
        await inbound(c, tap=whatsapp.payload("ok", other, "someone-else"))
        assert (await status_of(other)).status == "pending" and "isn't valid" in " ".join(texts(sent))
        # Free text that isn't about a request gets a product-only answer, not a chat.
        sent.clear()
        await inbound(c, text="What's the weather like?")
        assert "I can only take answers, edits and comments" in texts(sent)[0]


async def test_approving_unchanged_offers_to_ask_less(sent):
    async with client() as c:
        ctx = await connect(c, sent)
        for n in range(autonomy.STREAK):
            await make_request(ctx["goal"], action_type="reply", scope="x.com", title=f"Reply {n}",
                               preview={"fields": {"content": f"{POST} ({n})"}, "editable": ["content"]})
        await deliver()
        for n in range(autonomy.STREAK):
            await inbound(c, tap=buttons(last_card(sent))["Approve"])
        offer = last_card(sent)
        assert offer["interactive"]["header"]["text"] == "Ask less often?"
        await inbound(c, tap=buttons(offer)["Use a heads-up"])
        p = {x["key"]: x for x in (await c.get(f"/api/campaigns/{ctx['goal']}/permissions")).json()["action_types"]}
        assert p["reply"]["mode"] == "heads_up" and p["reply"]["source"] == "earned" and p["reply"]["daily_cap"] == 20
        assert "now goes ahead after a heads-up" in texts(sent)[-1]


async def test_a_closed_window_falls_back_to_a_template(sent):
    async with client() as c:
        ctx = await connect(c, sent)
        await make_request(ctx["goal"], action_type="publish_post", title="Post", preview={"fields": {"content": "x"}})
        await deliver()
        wamid = sent[-1]["_id"]
        raw, headers = signed({"entry": [{"changes": [{"value": {"statuses": [
            {"id": wamid, "status": "failed", "errors": [{"code": 131047, "title": "Re-engagement message"}]}]}}]}]})
        await c.post("/api/whatsapp/webhook", content=raw, headers=headers)
        async with session_scope() as s:
            u = (await s.execute(__import__("sqlalchemy").select(User))).scalar_one()
            assert u.whatsapp_last_inbound_at is None
            assert not (await s.execute(__import__("sqlalchemy").select(WhatsAppMessage).where(
                WhatsAppMessage.wa_message_id == wamid))).first()
        sent.clear()
        assert await deliver() == 1 and sent[0]["type"] == "template"


async def test_reviews_suggestions_and_a_burst_arrive_one_at_a_time(sent):
    async with client() as c:
        ctx = await connect(c, sent)
        prd = "# CSV export\n\n" + ("Dispatchers copy routes by hand every morning. " * 60)
        await make_request(ctx["goal"], kind="review", title="CSV export for routes",
                           preview={"kind": "prd", "summary": "Dispatchers ask for it weekly.", "fields": {"content": prd},
                                    "editable": ["content"], "handoff_to": "Engineering Agent"})
        sug = await make_request(ctx["goal"], kind="proposal", title="Raise the weekly target to 60",
                                 rationale="46 of 40 last week.",
                                 preview={"change": {"type": "target", "target": 60, "period": "week"},
                                          "current": {"target": 40, "period": "week", "progress": 46},
                                          "fields": {"target": "60"}, "editable": ["target"]})
        await make_request(ctx["goal"], kind="connect", title="Connect hubspot", scope="hubspot",
                           preview={"app": "hubspot", "url": "https://connect.example/hubspot"})
        assert await deliver() == 3
        assert texts(sent)[0] == "3 new things need you. First, 2 more after this:"
        # The long PRD came first as plain text, then its card.
        assert sent[1]["type"] == "text" and sent[1]["text"]["body"].startswith("# CSV export")
        card = last_card(sent)
        assert "The full text is in the message above" in card["interactive"]["body"]["text"]
        assert set(buttons(card)) == {"Approve", "Edit", "Ask for changes"}
        await inbound(c, tap=buttons(card)["Ask for changes"])
        await inbound(c, text="Add Excel export too")
        # Next: the team lead's suggestion, with a number you can change.
        card = last_card(sent)
        assert "Now: 40 per week (46 so far)" in card["interactive"]["body"]["text"]
        await inbound(c, tap=buttons(card)["Change number"])
        await inbound(c, text="eighty")
        assert "needs to be a number" in texts(sent)[-1]
        await inbound(c, text="80")
        r = await status_of(sug)
        assert r.status == "approved" and r.edited_fields == {"target": "80"}
        card = last_card(sent)
        assert "https://connect.example/hubspot" in card["interactive"]["body"]["text"]
        assert set(buttons(card)) == {"I've connected it", "Not now"}


async def test_templates_are_consistent_and_submitted(sent, monkeypatch):
    import re

    from app import cli

    for name, t in whatsapp.TEMPLATES.items():
        n = len(set(re.findall(r"\{\{(\d+)\}\}", t["body"])))
        assert n == len(t["example"]), name
        assert len(t["buttons"]) <= 3 and all(len(b) <= 20 for b in t["buttons"])
    monkeypatch.setattr(get_settings(), "whatsapp_waba_id", "WABA1")
    submitted: list[dict] = []
    graph = FastAPI()

    @graph.post("/{version}/{waba}/message_templates")
    async def create(version: str, waba: str, request: Request):
        submitted.append(await request.json())
        return {"id": "t1", "status": "PENDING"}

    messages_api = whatsapp.TRANSPORT
    monkeypatch.setattr(whatsapp, "TRANSPORT", httpx.ASGITransport(app=graph))
    lines = await cli.create_whatsapp_templates()
    monkeypatch.setattr(whatsapp, "TRANSPORT", messages_api)
    assert lines == [f"{n}: submitted (PENDING)" for n in whatsapp.TEMPLATES]
    assert {t["category"] for t in submitted} == {"UTILITY"}

    # And what's sent matches each template's placeholders.
    async with client() as c:
        ctx = await connect(c, sent)
        async with session_scope() as s:
            u = (await s.execute(__import__("sqlalchemy").select(User))).scalar_one()
            u.whatsapp_last_inbound_at = None
        monkeypatch.setattr(whatsapp, "TEMPLATE_GAP", timedelta(0))
        kinds = [dict(action_type="publish_post", title="Post", preview={"fields": {"content": "x"}}),
                 dict(action_type="publish_post", title="Post", auto_approve_at=autonomy.heads_up_at(),
                      preview={"fields": {"content": "x"}}),
                 dict(kind="question", title="Q?", preview={"question": "Q?"}),
                 dict(action_type="spend_money", title="Buy ads", preview={"fields": {"budget": "5"}})]
        for kw in kinds:
            rid = await make_request(ctx["goal"], **kw)
            sent.clear()
            await deliver()
            t = sent[0]["template"]
            spec = whatsapp.TEMPLATES[t["name"]]
            assert len(t["components"][0]["parameters"]) == len(spec["example"]), t["name"]
            assert len(t["components"]) - 1 == len(spec["buttons"]), t["name"]
            async with session_scope() as s:
                (await s.get(UserRequest, rid)).status = "cancelled"
