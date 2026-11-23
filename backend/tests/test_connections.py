"""Connecting tools: an organization's own Composio key, signing in with GitHub, and one overview."""

from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import FastAPI, Request

from app.api import integrations as integrations_api
from app.config import get_settings
from app.connectors import github as github_mod
from app.db import session_scope
from app.main import app
from app.models import Campaign, Integration
from sqlalchemy import select
from tests.helpers import agent_in, org_of, sign_in, sign_in_with_org


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_an_organization_can_use_its_own_composio_key(monkeypatch):
    checked = []

    async def check(key, org_id):
        checked.append(key)
        if key == "bad-key-123456":
            raise RuntimeError("401")
    monkeypatch.setattr(integrations_api, "check_composio_key", check)
    monkeypatch.setattr(get_settings(), "composio_api_key", None)
    async with client() as owner, client() as maya:
        await sign_in_with_org(owner, "founder@acme.test")
        org = await org_of(owner)
        assert (await owner.get("/api/status")).json()["composio_enabled"] is False
        assert (await owner.post("/api/integrations/composio", json={"api_key": "bad-key-123456"})).status_code == 400
        r = await owner.post("/api/integrations/composio", json={"api_key": "comp_live_abcdef9876"})
        assert r.status_code == 200 and r.json()["config"] == {"key_hint": "9876"}
        st = (await owner.get("/api/status")).json()
        assert st["composio_enabled"] is True and st["composio_source"] == "org"
        async with session_scope() as s:
            row = (await s.execute(select(Integration).where(Integration.kind == "composio"))).scalar_one()
            assert "comp_live" not in row.secret_encrypted  # stored encrypted
        # Members can't change it.
        sales = next(d["id"] for d in org["departments"] if d["name"] == "Sales")
        await owner.post("/api/invitations", json={"email": "maya@acme.test", "department_ids": [sales]})
        await sign_in(maya, "maya@acme.test")
        await org_of(maya)
        assert (await maya.post("/api/integrations/composio", json={"api_key": "comp_live_x123456"})).status_code == 403


async def test_the_platform_key_is_shared_by_default(monkeypatch):
    monkeypatch.setattr(get_settings(), "composio_api_key", "platform-key")
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test")
        st = (await c.get("/api/status")).json()
        assert st["composio_enabled"] is True and st["composio_source"] == "platform"


def fake_github(calls: list) -> FastAPI:
    gh = FastAPI()

    @gh.post("/login/oauth/access_token")
    async def token(request: Request):
        form = await request.form()
        calls.append(("token", form["code"], form["client_id"]))
        return {"access_token": "gho_signed_in"} if form["code"] == "good" else {"error": "bad_verification_code"}

    @gh.get("/user/repos")
    async def repos(request: Request):
        assert request.headers["authorization"] == "Bearer gho_signed_in"
        return [{"full_name": "acme/app", "private": True, "pushed_at": "2026-11-20", "permissions": {"push": True}},
                {"full_name": "other/read-only", "permissions": {"push": False}}]

    @gh.get("/repos/{owner}/{name}")
    async def repo(owner: str, name: str):
        return {"full_name": f"{owner}/{name}", "default_branch": "main", "private": True, "permissions": {"push": True}}
    return gh


async def test_sign_in_with_github_then_pick_a_repository(monkeypatch):
    calls: list = []
    monkeypatch.setattr(github_mod, "TRANSPORT", httpx.ASGITransport(app=fake_github(calls)))
    monkeypatch.setattr(get_settings(), "github_client_id", "Iv1.client")
    monkeypatch.setattr(get_settings(), "github_client_secret", "shh")
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test")
        assert (await c.get("/api/status")).json()["github_sign_in"] is True
        url = (await c.get("/api/integrations/github/sign-in")).json()["url"]
        q = parse_qs(urlparse(url).query)
        assert url.startswith("https://github.com/login/oauth/authorize") and q["client_id"] == ["Iv1.client"]
        assert q["scope"] == ["repo"] and q["redirect_uri"][0].endswith("/api/integrations/github/callback")

        r = await c.get("/api/integrations/github/callback", params={"code": "good", "state": "forged"})
        assert r.headers["location"].endswith("/connections?github=expired")
        r = await c.get("/api/integrations/github/callback", params={"code": "bad", "state": q["state"][0]})
        assert r.headers["location"].endswith("/connections?github=failed")
        r = await c.get("/api/integrations/github/callback", params={"code": "good", "state": q["state"][0]})
        assert r.status_code == 307 and r.headers["location"].endswith("/connections?github=choose")

        repos = (await c.get("/api/integrations/github/repos")).json()
        assert [x["full_name"] for x in repos] == ["acme/app"]  # only ones it can push to
        r = await c.post("/api/integrations/github/repo", json={"repo": "acme/app"})
        assert r.status_code == 200, r.text
        kinds = {i["kind"]: i for i in (await c.get("/api/integrations")).json()}
        assert set(kinds) == {"github"} and kinds["github"]["config"]["via"] == "sign_in"


async def test_without_a_github_app_people_use_a_token(monkeypatch):
    monkeypatch.setattr(get_settings(), "github_client_id", None)
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test")
        assert (await c.get("/api/integrations/github/sign-in")).status_code == 400


async def test_one_overview_of_every_tool_the_goals_use(monkeypatch):
    monkeypatch.setattr(get_settings(), "composio_api_key", None)
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test", departments=("sales", "product"))
        org = await org_of(c)
        live = (await c.post("/api/campaigns", json={
            "name": "Book demos", "goal_description": "Book demos", "primary_metric": "demos", "budget_total": 10,
            "agent_id": agent_in(org, "Sales"), "launch": True})).json()
        draft = (await c.post("/api/campaigns", json={
            "name": "Weekly metrics brief", "goal_description": "Brief", "primary_metric": "briefs", "budget_total": 10,
            "agent_id": agent_in(org, "Product")})).json()
        async with session_scope() as s:
            (await s.get(Campaign, live["id"])).playbook = {"steps": [
                {"text": "Find leads", "action_type": "research", "tool": "web"},
                {"text": "Draft emails", "action_type": "create_draft", "tool": "gmail"},
                {"text": "Send emails", "action_type": "send_message", "tool": "gmail"}]}
            (await s.get(Campaign, draft["id"])).playbook = {"steps": [
                {"text": "Query signups", "action_type": "read_data", "tool": "database"},
                {"text": "Write the brief", "action_type": "create_draft", "tool": "none"}]}
        ov = (await c.get("/api/connections/overview")).json()
        tools = {t["key"]: t for t in ov["tools"]}
        assert set(tools) == {"gmail", "database"}
        gmail = tools["gmail"]
        assert gmail["status"] == "missing" and gmail["live_goals"] == 1 and gmail["required"]
        assert gmail["on_its_own"] == ["create drafts"] and gmail["needs_ok"] == ["send messages"]
        assert [g["name"] for g in gmail["goals"]] == ["Book demos"]
        assert tools["database"]["live_goals"] == 0 and not tools["database"]["required"]
        assert ov["tools"][0]["key"] == "gmail"  # what live goals are missing comes first
        assert ov["summary"] == {"needed": 2, "connected": 0, "missing_live": 1}
        assert ov["composio"]["enabled"] is False

        await c.post("/api/sites/signed-in", json={"site": "mail.google.com"})
        tools = {t["key"]: t for t in (await c.get("/api/connections/overview")).json()["tools"]}
        assert tools["gmail"]["status"] == "signed_in"
