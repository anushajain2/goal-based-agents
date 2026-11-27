"""What a goal will do (its plan), who decides what (permissions), what it needs before it starts
(readiness), how its budget was worked out, and custom MCP tools behind the same approval gate."""

import json

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from app.agent.executor import Pending, ToolExecutor
from app.agent.llm import MeteredClaude
from app.agent.playbook import tools_needed
from app.connectors import mcp_client
from app.db import session_scope
from app.main import app
from app.models import AgentRun, Campaign, McpServer, RequestStatus, UserRequest
from app.services import estimate, policy
from tests.fakes import FakeAnthropic
from tests.helpers import agent_in, org_of, sign_in, sign_in_with_org


async def with_org(c, email: str) -> dict:
    await sign_in_with_org(c, email)
    return await org_of(c)


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


STEPS = [
    {"text": "Find 200 ops leaders at logistics companies", "action_type": "research", "tool": "web"},
    {"text": "Write a personal first email to each", "action_type": "create_draft", "tool": "gmail"},
    {"text": "Send each email", "action_type": "send_message", "tool": "gmail"},
    {"text": "Book demos on the calendar", "action_type": "other_write", "tool": "googlecalendar"},
]


async def new_goal(c, org, dept="Sales", **kw) -> dict:
    body = {"name": "Book 15 demos", "goal_description": "Book 15 demos with ops leaders", "primary_metric": "demos",
            "budget_total": 40, "cycle_hours": 6, "agent_id": agent_in(org, dept), "channels": ["Email"], **kw}
    r = await c.post("/api/campaigns", json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def set_playbook(goal_id: str, steps=STEPS) -> None:
    async with session_scope() as s:
        (await s.get(Campaign, goal_id)).playbook = {"steps": steps, "source": "setup"}


# --- budget -------------------------------------------------------------------------------------

def test_budget_formula():
    b = estimate.compute(0.30, cycle_hours=6, days=30)
    assert (b["sessions"], b["ai_usd"], b["suggested_usd"]) == (120, 36.0, 36.0)
    b = estimate.compute(0.30, cycle_hours=24, days=14, paid_spend=50)
    assert (b["sessions"], b["suggested_usd"]) == (14, 54.2)  # 14 x 0.30 + 50, to the cent
    # One-off work (DNS records, a page) is priced by the sessions it needs, not a session every cycle for weeks.
    b = estimate.compute(0.30, cycle_hours=6, days=42, max_sessions=3)
    assert (b["sessions"], b["suggested_usd"]) == (3, 0.9)  # 3 x 0.30: the exact cost, no rounding up
    assert estimate.compute(0.30, cycle_hours=24, days=7, max_sessions=50)["sessions"] == 7  # never more than the cycles


async def test_budget_basis_on_goals_and_from_history():
    async with client() as c:
        org = await with_org(c, "a@acme.test")
        g = await new_goal(c, org)
        assert g["budget_basis"]["sessions"] == 120 and g["budget_basis"]["chosen_usd"] == 40
        g = (await c.patch(f"/api/campaigns/{g['id']}", json={"cycle_hours": 12})).json()
        assert g["budget_basis"]["sessions"] == 60
        est = (await c.get("/api/estimate?cycle_hours=3&days=7")).json()
        assert est["sessions"] == 56 and est["basis"] == "typical"

        # Once there are real sessions, estimates use their average cost.
        from app.models import LedgerEntry
        async with session_scope() as s:
            for i, cost in enumerate([0.10, 0.20, 0.30]):
                run = AgentRun(campaign_id=g["id"], cycle_number=i + 1, status="completed")
                s.add(run)
                await s.flush()
                s.add(LedgerEntry(campaign_id=g["id"], run_id=run.id, kind="ai_usage", status="settled",
                                  amount_usd=cost, description="AI"))
        est = (await c.get("/api/estimate?cycle_hours=6&days=30")).json()
        assert est["basis"] == "history" and est["per_session_usd"] == 0.2 and est["history_sessions"] == 3
        full = (await c.get(f"/api/campaigns/{g['id']}")).json()
        assert full["pace"]["per_session_usd"] == 0.2 and full["pace"]["sessions_left"] == 197  # $39.40 left


# --- permissions --------------------------------------------------------------------------------

async def test_permissions_match_what_the_policy_engine_enforces():
    async with client() as c:
        org = await with_org(c, "a@acme.test")
        g = await new_goal(c, org)
        perms = (await c.get(f"/api/campaigns/{g['id']}/permissions")).json()
        modes = {p["key"]: p["mode"] for p in perms["action_types"]}
        assert modes["research"] == "auto" and modes["send_message"] == "ask" and modes["spend_money"] == "ask"
        assert perms["approvers"] == ["a@acme.test"] or perms["approvers"] == [perms["approvers"][0]]
        assert perms["can_edit"] is True

        async def decided(action_type):
            async with session_scope() as s:
                return (await policy.decide(s, g["id"], action_type=action_type)).outcome

        assert await decided("send_message") == "ask"
        r = (await c.put(f"/api/campaigns/{g['id']}/permissions/send_message", json={"mode": "auto"})).json()
        assert r["permission"]["mode"] == "auto" and r["permission"]["set_at"] == "goal" and r["note"] is None
        assert await decided("send_message") == "allow"
        await c.put(f"/api/campaigns/{g['id']}/permissions/send_message", json={"mode": "never"})
        assert await decided("send_message") == "block"
        await c.put(f"/api/campaigns/{g['id']}/permissions/send_message", json={"mode": "ask"})
        assert await decided("send_message") == "ask"

        # Things that change nothing outside Oton can't be made to "ask first"; spending needs a limit.
        assert (await c.put(f"/api/campaigns/{g['id']}/permissions/research", json={"mode": "ask"})).status_code == 400
        assert (await c.put(f"/api/campaigns/{g['id']}/permissions/spend_money", json={"mode": "auto"})).status_code == 400
        r = await c.put(f"/api/campaigns/{g['id']}/permissions/spend_money", json={"mode": "auto", "spend_limit_usd": 20})
        assert r.json()["permission"]["spend_limit_usd"] == 20

        # An organization-wide "never" wins, and the goal page says where it was set.
        await c.post("/api/exclusions", json={"kind": "action_type", "value": "publish_post"})
        r = (await c.put(f"/api/campaigns/{g['id']}/permissions/publish_post", json={"mode": "auto"})).json()
        assert r["permission"]["mode"] == "never" and r["permission"]["set_at"] == "org"
        assert "whole organization" in r["note"]


async def test_other_departments_cannot_change_a_goals_permissions():
    async with client() as owner, client() as member:
        org = await with_org(owner, "boss@acme.test")
        g = await new_goal(owner, org, dept="Sales")
        mkt = next(d["id"] for d in org["departments"] if d["name"] == "Marketing")
        await owner.post("/api/invitations", json={"email": "m@acme.test", "department_ids": [mkt]})
        await sign_in(member, "m@acme.test")
        assert (await member.get(f"/api/campaigns/{g['id']}/permissions")).json()["can_edit"] is False
        r = await member.put(f"/api/campaigns/{g['id']}/permissions/send_message", json={"mode": "auto"})
        assert r.status_code == 403


# --- plan and readiness -------------------------------------------------------------------------

async def test_plan_without_a_key_is_an_outline_from_the_channels(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    async with client() as c:
        org = await with_org(c, "a@acme.test")
        g = await new_goal(c, org, channels=["LinkedIn"])
        book = (await c.post(f"/api/campaigns/{g['id']}/playbook")).json()
        assert book["source"] == "default"
        assert {st["tool"] for st in book["steps"]} >= {"web", "linkedin"}
        assert any(st["action_type"] == "send_message" for st in book["steps"])


async def test_plan_is_generated_once_and_charged_to_the_goal(monkeypatch):
    from app.api import plan as plan_api
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    fake = FakeAnthropic(lambda kw: [], reviewer=lambda kw: {"steps": STEPS})
    monkeypatch.setattr(plan_api, "MeteredClaude", lambda: MeteredClaude(client=fake))
    async with client() as c:
        org = await with_org(c, "a@acme.test")
        g = await new_goal(c, org)
        book = (await c.post(f"/api/campaigns/{g['id']}/playbook")).json()
        assert book["source"] == "generated" and len(book["steps"]) == 4
        await c.post(f"/api/campaigns/{g['id']}/playbook")
        assert len(fake.calls) == 1  # kept, not remade on every view
        full = (await c.get(f"/api/campaigns/{g['id']}")).json()
        assert full["budget"]["ai_usage"] > 0


async def test_readiness_lists_tools_and_who_approves():
    async with client() as c:
        org = await with_org(c, "a@acme.test")
        g = await new_goal(c, org)
        await set_playbook(g["id"])
        r = (await c.get(f"/api/campaigns/{g['id']}/readiness")).json()
        tools = {t["key"]: t for t in r["tools"]}
        assert set(tools) == {"gmail", "googlecalendar"}
        assert tools["gmail"]["required"] is True and tools["gmail"]["steps"] == [2, 3]
        assert tools["gmail"]["status"] == "missing" and tools["gmail"]["can_connect_app"] is False  # no Composio key
        assert r["department"] == "Sales" and r["approvers"]
        assert {p["key"]: p["mode"] for p in r["permissions"]}["send_message"] == "ask"

        assert (await c.post("/api/sites/signed-in", json={"site": "https://mail.google.com/mail/u/0"})).status_code == 200
        r = (await c.get(f"/api/campaigns/{g['id']}/readiness")).json()
        assert {t["key"]: t["status"] for t in r["tools"]}["gmail"] == "signed_in"
        sites = (await c.get("/api/connections")).json()["sites"]
        assert any(x["site"] == "mail.google.com" for x in sites)


def test_tools_needed_only_requires_tools_used_to_change_things():
    c = Campaign(channels=["Reddit"], playbook={"steps": [
        {"text": "Read the CRM", "action_type": "read_data", "tool": "hubspot"},
        {"text": "Email people", "action_type": "send_message", "tool": "gmail"}]})
    needed = {t["key"]: t["required"] for t in tools_needed(c)}
    assert needed == {"hubspot": False, "gmail": True, "reddit": False}


# --- MCP ----------------------------------------------------------------------------------------

def fake_mcp_server(calls: list) -> FastAPI:
    server = FastAPI()
    tools = [
        {"name": "lookup_contact", "description": "Find a contact", "annotations": {"readOnlyHint": True},
         "inputSchema": {"type": "object", "properties": {"email": {"type": "string"}}}},
        {"name": "create_invoice", "description": "Bill a customer",
         "inputSchema": {"type": "object", "properties": {"customer": {"type": "string"}}}},
        {"name": "remove_contact", "description": "Delete a contact", "annotations": {"destructiveHint": True},
         "inputSchema": {"type": "object"}},
        {"name": "get_stats", "description": "Sounds read-only, isn't marked", "inputSchema": {"type": "object"}},
    ]

    @server.post("/mcp")
    async def rpc(request: Request):
        if request.headers.get("authorization") != "Bearer sekrit":
            return Response(status_code=401)
        msg = await request.json()
        if "id" not in msg:
            return Response(status_code=202)
        method = msg["method"]
        if method == "initialize":
            body = {"jsonrpc": "2.0", "id": msg["id"],
                    "result": {"protocolVersion": "2025-06-18", "serverInfo": {"name": "crm"}, "capabilities": {}}}
            return JSONResponse(body, headers={"mcp-session-id": "sess-1"})
        assert request.headers.get("mcp-session-id") == "sess-1"
        if method == "tools/list":
            return JSONResponse({"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": tools}})
        if method == "tools/call":
            calls.append(msg["params"])
            result = {"content": [{"type": "text", "text": f"ran {msg['params']['name']}"}]}
            # answer as a server-sent event, like streaming servers do
            sse = f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': result})}\n\n"
            return Response(sse, media_type="text/event-stream")
        return JSONResponse({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "nope"}})

    return server


@pytest.fixture
def mcp_calls(monkeypatch):
    calls: list = []
    monkeypatch.setattr(mcp_client, "TRANSPORT", httpx.ASGITransport(app=fake_mcp_server(calls)))
    return calls


async def test_mcp_tools_run_behind_the_approval_gate(mcp_calls):
    async with client() as c:
        org = await with_org(c, "a@acme.test")
        r = await c.post("/api/mcp-servers", json={"name": "Our CRM", "url": "http://crm.test/mcp", "auth_header": "sekrit"})
        server = r.json()
        assert server["name"] == "our-crm" and server["error"] is None and server["has_key"]
        kinds = {t["name"]: (t["kind"], t["asks_first"]) for t in server["tools"]}
        assert kinds == {"lookup_contact": ("read_data", False), "create_invoice": ("spend_money", True),
                         "remove_contact": ("delete_content", True), "get_stats": ("other_write", True)}
        async with session_scope() as s:  # the key is stored encrypted
            stored = (await s.execute(select(McpServer))).scalar_one()
            assert "sekrit" not in (stored.auth_encrypted or "")

        g = await new_goal(c, org)
        async with session_scope() as s:
            run = AgentRun(campaign_id=g["id"], cycle_number=1, status="running")
            s.add(run)
            await s.flush()
            run_id = run.id
        ex = ToolExecutor(MeteredClaude(client=FakeAnthropic(lambda kw: [])), g["id"], run_id, org["org"]["id"])

        listed = json.loads((await ex.call("mcp_list_tools", {}, "t0")).content)
        assert listed[0]["server"] == "our-crm"

        # Reading runs straight away.
        out = await ex.call("mcp_call_tool", {"server": "our-crm", "tool": "lookup_contact",
                                              "arguments": {"email": "x@y.test"}, "summary": "Look up X"}, "t1")
        assert not isinstance(out, Pending) and "ran lookup_contact" in out.content
        assert len(mcp_calls) == 1

        # Anything else waits for a person, and nothing reaches the server until they approve.
        out = await ex.call("mcp_call_tool", {"server": "our-crm", "tool": "get_stats", "arguments": {},
                                              "summary": "Get stats"}, "t2")
        assert isinstance(out, Pending) and len(mcp_calls) == 1
        async with session_scope() as s:
            req = await s.get(UserRequest, out.request_id)
            assert req.scope == "our-crm" and req.action_type == "other_write"
            req.status = RequestStatus.approved.value
            stored_call = out.stored
        result = await ex.resume(stored_call, req)
        assert "ran get_stats" in result.content and len(mcp_calls) == 2

        # A "never" for the kind of action blocks it outright.
        await c.put(f"/api/campaigns/{g['id']}/permissions/delete_content", json={"mode": "never"})
        out = await ex.call("mcp_call_tool", {"server": "our-crm", "tool": "remove_contact", "arguments": {},
                                              "summary": "Remove a contact"}, "t3")
        assert out.is_error and "Blocked" in out.content and len(mcp_calls) == 2


async def test_mcp_server_errors_are_shown_not_raised(mcp_calls):
    async with client() as c:
        await sign_in_with_org(c, "a@acme.test")
        server = (await c.post("/api/mcp-servers", json={"name": "crm", "url": "http://crm.test/mcp"})).json()
        assert "refused" in server["error"] and server["tools"] == []
        assert (await c.post("/api/mcp-servers", json={"name": "crm", "url": "http://crm.test/mcp"})).status_code == 409


async def test_agents_get_mcp_tools_only_when_the_org_has_servers(mcp_calls, monkeypatch):
    from app.agent.runner import CycleRunner
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    from tests.fakes import tool_use

    async with client() as c:
        org = await with_org(c, "a@acme.test")
        g = await new_goal(c, org, launch=True)
        await set_playbook(g["id"])
        await c.post("/api/mcp-servers", json={"name": "crm", "url": "http://crm.test/mcp", "auth_header": "sekrit"})
        async with session_scope() as s:
            run = AgentRun(campaign_id=g["id"], cycle_number=1, status="running")
            s.add(run)
            await s.flush()
            run_id = run.id
        fake = FakeAnthropic(lambda kw: [tool_use("finish_cycle", summary="Done.", next_check_in_hours=6)])
        await CycleRunner(MeteredClaude(client=fake)).run(run_id)
        first = fake.agent_calls()[0]
        names = [t.get("name") for t in first["tools"]]
        assert "mcp_call_tool" in names
        brief = first["messages"][0]["content"]
        assert "The plan the team agreed to" in brief and "Send each email" in brief
        assert "crm: lookup_contact" in brief
