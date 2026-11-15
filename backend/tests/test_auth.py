"""Accounts, sessions and keeping each user's data private."""

import httpx
import pytest

from app.db import session_scope
from app.main import app
from app.models import Campaign
from app.services import activity


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


GOAL = {"name": "Mine", "goal_description": "Book 5 calls", "primary_metric": "calls", "budget_total": 5}


async def test_signup_login_logout_and_me():
    async with client() as c:
        assert (await c.get("/api/auth/me")).status_code == 401
        r = await c.post("/api/auth/signup", json={"name": "Asha", "email": "Asha@Example.com", "password": "longenough1"})
        assert r.status_code == 200 and r.json()["email"] == "asha@example.com"
        assert "httponly" in r.headers["set-cookie"].lower()
        assert (await c.get("/api/auth/me")).json()["name"] == "Asha"
        assert (await c.post("/api/auth/signup", json={"email": "asha@example.com", "password": "longenough1"})).status_code == 409
        await c.post("/api/auth/logout")
        assert (await c.get("/api/auth/me")).status_code == 401
        assert (await c.post("/api/auth/login", json={"email": "asha@example.com", "password": "wrong-password"})).status_code == 401
        r = await c.post("/api/auth/login", json={"email": "ASHA@example.com", "password": "longenough1"})
        assert r.status_code == 200
        assert (await c.get("/api/auth/me")).status_code == 200


async def test_short_password_and_bad_email_rejected():
    async with client() as c:
        assert (await c.post("/api/auth/signup", json={"email": "a@b.co", "password": "short"})).status_code == 422
        assert (await c.post("/api/auth/signup", json={"email": "not-an-email", "password": "longenough1"})).status_code == 422


@pytest.mark.parametrize("path", ["/api/campaigns", "/api/overview", "/api/activity", "/api/requests", "/api/grants",
                                  "/api/exclusions", "/api/connections", "/api/status"])
async def test_app_endpoints_need_sign_in(path):
    async with client() as c:
        assert (await c.get(path)).status_code == 401


async def test_users_only_see_their_own_goals():
    async with client() as a, client() as b:
        await a.post("/api/auth/signup", json={"email": "a@example.com", "password": "longenough1"})
        await b.post("/api/auth/signup", json={"email": "b@example.com", "password": "longenough1"})
        goal = (await a.post("/api/campaigns", json=GOAL)).json()
        await a.post("/api/exclusions", json={"campaign_id": None, "kind": "text", "value": "A's rule"})
        await a.post("/api/grants", json={"campaign_id": None, "action_type": "engage"})

        assert [g["id"] for g in (await a.get("/api/campaigns")).json()] == [goal["id"]]
        assert (await b.get("/api/campaigns")).json() == []
        for path in [f"/api/campaigns/{goal['id']}", f"/api/campaigns/{goal['id']}/activity",
                     f"/api/campaigns/{goal['id']}/sessions"]:
            assert (await b.get(path)).status_code == 404
        assert (await b.post(f"/api/campaigns/{goal['id']}/pause")).status_code == 404
        assert (await b.delete(f"/api/campaigns/{goal['id']}")).status_code == 404
        assert (await b.get("/api/activity")).json() == []
        assert (await b.get("/api/exclusions")).json() == [] and (await b.get("/api/grants")).json() == []
        assert (await b.post("/api/exclusions", json={"campaign_id": goal["id"], "kind": "text", "value": "x"})).status_code == 404
        a_rule = (await a.get("/api/exclusions")).json()[0]["id"]
        assert (await b.delete(f"/api/exclusions/{a_rule}")).status_code == 404
        assert (await b.get("/api/overview")).json()["goals"]["total"] == 0


async def test_first_account_claims_goals_made_before_accounts_existed():
    async with session_scope() as s:
        c = Campaign(name="Old", goal_type="custom", goal_description="old goal", primary_metric="m", budget_total=5)
        s.add(c)
        await s.flush()
        await activity.log(s, c.id, "system", "made before accounts")
    async with client() as first, client() as second:
        await first.post("/api/auth/signup", json={"email": "first@example.com", "password": "longenough1"})
        await second.post("/api/auth/signup", json={"email": "second@example.com", "password": "longenough1"})
        assert [g["name"] for g in (await first.get("/api/campaigns")).json()] == ["Old"]
        assert (await second.get("/api/campaigns")).json() == []
