"""Passwordless sign-in (Google + emailed codes), sessions, and keeping each user's data private."""

import asyncio
import base64
import hashlib
import json
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import update

from app import auth
from app.config import get_settings
from app.db import session_scope
from app.main import app
from app.models import Campaign, LoginCode, utcnow
from app.services import activity
from tests.helpers import SENT_CODES, sign_in


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


GOAL = {"name": "Mine", "goal_description": "Book 5 calls", "primary_metric": "calls", "budget_total": 5}


# --- email codes -------------------------------------------------------------------------

async def test_email_code_sign_in_creates_account_then_signs_back_in():
    async with client() as c:
        assert (await c.get("/api/auth/me")).status_code == 401
        r = await c.post("/api/auth/email/start", json={"email": "Asha@Example.com"})
        assert r.json() == {"sent": True, "delivery": "email"}
        code = SENT_CODES["asha@example.com"]
        assert len(code) == 6 and code.isdigit()
        r = await c.post("/api/auth/email/verify", json={"email": "asha@example.com", "code": code})
        assert r.status_code == 200 and r.json()["new"] is True
        assert "httponly" in r.headers["set-cookie"].lower()
        assert (await c.patch("/api/auth/me", json={"name": "Asha"})).json()["name"] == "Asha"
        # A code works only once.
        assert (await c.post("/api/auth/email/verify", json={"email": "asha@example.com", "code": code})).status_code == 400
        await c.post("/api/auth/logout")
        assert (await c.get("/api/auth/me")).status_code == 401
        again = await sign_in(c, "asha@example.com")
        assert again["new"] is False and again["name"] == "Asha"


async def test_codes_are_stored_hashed_and_only_the_newest_works():
    async with client() as c:
        await c.post("/api/auth/email/start", json={"email": "x@example.com"})
        first = SENT_CODES["x@example.com"]
        await c.post("/api/auth/email/start", json={"email": "x@example.com"})
        second = SENT_CODES["x@example.com"]
        async with session_scope() as s:
            from sqlalchemy import select

            stored = (await s.execute(select(LoginCode.code_hash))).scalars().all()
        # Codes are never stored in plain text.
        assert all(first not in h and second not in h for h in stored)
        if first != second:
            assert (await c.post("/api/auth/email/verify", json={"email": "x@example.com", "code": first})).status_code == 400
        assert (await c.post("/api/auth/email/verify", json={"email": "x@example.com", "code": second})).status_code == 200


async def test_wrong_codes_are_limited():
    async with client() as c:
        await c.post("/api/auth/email/start", json={"email": "y@example.com"})
        good = SENT_CODES["y@example.com"]
        wrong = "000000" if good != "000000" else "111111"
        for i in range(auth.CODE_MAX_ATTEMPTS):
            r = await c.post("/api/auth/email/verify", json={"email": "y@example.com", "code": wrong})
            assert r.status_code == 400
        # Even the right code is refused after too many wrong tries.
        r = await c.post("/api/auth/email/verify", json={"email": "y@example.com", "code": good})
        assert r.status_code == 400 and "Too many" in r.json()["detail"]


async def test_expired_codes_are_refused():
    async with client() as c:
        await c.post("/api/auth/email/start", json={"email": "z@example.com"})
        async with session_scope() as s:
            await s.execute(update(LoginCode).values(expires_at=utcnow() - timedelta(minutes=1)))
        r = await c.post("/api/auth/email/verify", json={"email": "z@example.com", "code": SENT_CODES["z@example.com"]})
        assert r.status_code == 400 and "expired" in r.json()["detail"]


async def test_codes_per_address_are_rate_limited():
    async with client() as c:
        for _ in range(auth.CODES_PER_HOUR):
            assert (await c.post("/api/auth/email/start", json={"email": "r@example.com"})).status_code == 200
        assert (await c.post("/api/auth/email/start", json={"email": "r@example.com"})).status_code == 429


async def test_bad_input_rejected():
    async with client() as c:
        assert (await c.post("/api/auth/email/start", json={"email": "not-an-email"})).status_code == 422
        assert (await c.post("/api/auth/email/verify", json={"email": "a@b.co", "code": "12ab56"})).status_code == 422


# --- Google ----------------------------------------------------------------------------------

def _id_token(claims: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'RS256'})}.{enc(claims)}.sig"


@pytest.fixture
def google(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", "client-123")
    monkeypatch.setattr(settings, "google_client_secret", "secret-xyz")
    seen: dict = {}

    def run(claims_for):
        async def fake_exchange(code, verifier):
            seen["verifier"] = verifier
            return {"id_token": _id_token(claims_for(seen))}

        monkeypatch.setattr(auth, "exchange_google_code", fake_exchange)

    return seen, run


async def _start_google(c, next_path="/goals"):
    r = await c.get("/api/auth/google/start", params={"next": next_path})
    assert r.status_code == 302
    url = urlparse(r.headers["location"])
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.netloc == "accounts.google.com" and q["client_id"] == "client-123"
    assert q["code_challenge_method"] == "S256" and q["redirect_uri"].endswith("/api/auth/google/callback")
    return q


def _good_claims(q, **over):
    return {"iss": "https://accounts.google.com", "aud": "client-123", "exp": time.time() + 600, "sub": "g-1",
            "email": "Gina@Example.com", "email_verified": True, "name": "Gina", "nonce": q["nonce"], **over}


async def test_google_sign_in_happy_path_and_pkce(google):
    seen, run = google
    async with client() as c:
        assert (await c.get("/api/auth/options")).json()["google"] is True
        q = await _start_google(c)
        run(lambda _: _good_claims(q))
        r = await c.get("/api/auth/google/callback", params={"code": "abc", "state": q["state"]})
        assert r.status_code == 302 and r.headers["location"] == "/goals"
        # The verifier we sent Google matches the challenge in the sign-in link (PKCE).
        challenge = base64.urlsafe_b64encode(hashlib.sha256(seen["verifier"].encode()).digest()).rstrip(b"=").decode()
        assert challenge == q["code_challenge"]
        me = (await c.get("/api/auth/me")).json()
        assert me["email"] == "gina@example.com" and me["name"] == "Gina"


@pytest.mark.parametrize("bad", [
    {"aud": "someone-else"}, {"iss": "https://evil.example"}, {"exp": 1}, {"nonce": "replayed"},
    {"email_verified": False},
])
async def test_google_rejects_bad_tokens(google, bad):
    _, run = google
    async with client() as c:
        q = await _start_google(c)
        run(lambda _: _good_claims(q, **bad))
        r = await c.get("/api/auth/google/callback", params={"code": "abc", "state": q["state"]})
        assert r.status_code == 302 and r.headers["location"].startswith("/login?error=")
        assert (await c.get("/api/auth/me")).status_code == 401


async def test_google_rejects_forged_state_and_missing_cookie(google):
    _, run = google
    async with client() as c:
        q = await _start_google(c)
        run(lambda _: _good_claims(q))
        r = await c.get("/api/auth/google/callback", params={"code": "abc", "state": "forged"})
        assert r.headers["location"].startswith("/login?error=")
    async with client() as fresh:  # no sign-in cookie at all (link opened elsewhere)
        r = await fresh.get("/api/auth/google/callback", params={"code": "abc", "state": q["state"]})
        assert r.headers["location"].startswith("/login?error=")


async def test_google_links_to_existing_email_account(google):
    _, run = google
    async with client() as c:
        first = await sign_in(c, "gina@example.com")
        await c.post("/api/auth/logout")
        q = await _start_google(c)
        run(lambda _: _good_claims(q))
        await c.get("/api/auth/google/callback", params={"code": "abc", "state": q["state"]})
        assert (await c.get("/api/auth/me")).json()["id"] == first["id"]


async def test_google_hidden_when_not_configured():
    async with client() as c:
        assert (await c.get("/api/auth/options")).json()["google"] is False
        assert (await c.get("/api/auth/google/start")).status_code == 404


async def test_open_redirects_are_blocked():
    assert auth.safe_next("//evil.example") == "/home"
    assert auth.safe_next("https://evil.example") == "/home"
    assert auth.safe_next("/goals/1") == "/goals/1"


# --- sessions and privacy ---------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/campaigns", "/api/overview", "/api/activity", "/api/requests", "/api/grants",
                                  "/api/exclusions", "/api/connections", "/api/status"])
async def test_app_endpoints_need_sign_in(path):
    async with client() as c:
        assert (await c.get(path)).status_code == 401


async def test_users_only_see_their_own_goals():
    async with client() as a, client() as b:
        await sign_in(a, "a@example.com")
        await sign_in(b, "b@example.com")
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
        await sign_in(first, "first@example.com")
        await sign_in(second, "second@example.com")
        assert [g["name"] for g in (await first.get("/api/campaigns")).json()] == ["Old"]
        assert (await second.get("/api/campaigns")).json() == []


async def test_live_updates_need_sign_in_and_do_not_hold_the_database():
    """The event stream must not keep a transaction open (on SQLite that would lock every request)."""
    async with client() as c:
        assert (await c.get("/api/events")).status_code == 401
        await sign_in(c, "live@example.com")

        async def open_stream():
            async with c.stream("GET", "/api/events") as r:
                assert r.status_code == 200
                await asyncio.sleep(2)

        stream = asyncio.create_task(open_stream())
        await asyncio.sleep(0.3)
        r = await asyncio.wait_for(c.post("/api/campaigns", json=GOAL), timeout=5)
        assert r.status_code == 200
        stream.cancel()
