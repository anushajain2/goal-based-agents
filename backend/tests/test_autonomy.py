"""Autonomy: recommended presets, heads-ups, daily caps, earned trust and tightening when things go wrong."""

from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.agent.executor import Pending, ToolExecutor
from app.agent.llm import MeteredClaude
from app.connectors import github as github_mod
from app.connectors.github import content_only
from app.db import session_scope
from app.main import app
from app.models import AgentRun, Campaign, Organization, PermissionGrant, UserRequest, utcnow
from app.services import autonomy, policy
from tests.fakes import FakeAnthropic
from tests.helpers import agent_in, org_of, sign_in_with_org


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def goal_for(c, agent_id: str, name: str = "Grow the audience", **extra) -> str:
    r = await c.post("/api/campaigns", json={"name": name, "goal_description": name, "primary_metric": "followers",
                                             "budget_total": 10, "agent_id": agent_id, "launch": True, **extra})
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def executor_for(goal_id: str, org_id: str, reviewer=None, quality_score: int = 5) -> ToolExecutor:
    async with session_scope() as s:
        run = AgentRun(campaign_id=goal_id, cycle_number=1, status="running")
        s.add(run)
        await s.flush()
        run_id = run.id
    fake = FakeAnthropic(lambda kw: [], reviewer=reviewer,
                         routes={"score": lambda kw: {"score": quality_score, "fixes": ["Be more specific"]}})
    return ToolExecutor(MeteredClaude(client=fake), goal_id, run_id, org_id)


def perms_by_key(perms: list[dict]) -> dict[str, dict]:
    return {p["key"]: p for p in perms}


# --- the policy engine ------------------------------------------------------------------------------

@pytest.mark.parametrize("slug,expected", [
    ("TWITTER_FOLLOW_USER", "engage"),
    ("TWITTER_LIKE_A_POST", "engage"),
    ("LINKEDIN_CREATE_COMMENT_ON_POST", "reply"),
    ("REDDIT_POST_REDDIT_COMMENT", "reply"),
    ("GMAIL_REPLY_TO_EMAIL", "send_message"),
])
def test_replies_are_their_own_kind(slug, expected):
    assert policy.classify_app_action(slug) == expected


async def _campaign() -> str:
    async with session_scope() as s:
        c = Campaign(name="t", goal_type="followers", goal_description="g", primary_metric="followers",
                     budget_total=Decimal(10))
        s.add(c)
        await s.flush()
        return c.id


async def test_strictest_grant_wins_and_daily_caps_ask():
    cid = await _campaign()
    async with session_scope() as s:
        s.add(PermissionGrant(campaign_id=None, action_type="publish_post", mode="auto"))  # org-wide: on its own
        s.add(PermissionGrant(campaign_id=cid, action_type="publish_post", mode="heads_up", daily_cap=2))
        s.add(PermissionGrant(campaign_id=cid, action_type="publish_post", scope="linkedin", mode="ask", source="personal"))
        s.add(PermissionGrant(campaign_id=cid, action_type="engage", mode="auto", daily_cap=1))
    async with session_scope() as s:
        assert (await policy.decide(s, cid, action_type="publish_post", app="twitter")).outcome == "heads_up"
        d = await policy.decide(s, cid, action_type="publish_post", app="linkedin")
        assert d.outcome == "ask" and "personal account" in d.reason
        d = await policy.decide(s, cid, action_type="engage")
        assert d.outcome == "allow" and d.autonomous
        await autonomy.record(s, cid, "engage")
    async with session_scope() as s:
        d = await policy.decide(s, cid, action_type="engage")
        assert d.outcome == "ask" and "daily limit" in d.reason
        # Older than a day doesn't count.
        from app.models import AutonomousAction
        for a in (await s.execute(select(AutonomousAction))).scalars():
            a.created_at = utcnow() - timedelta(hours=25)
    async with session_scope() as s:
        assert (await policy.decide(s, cid, action_type="engage")).outcome == "allow"


def test_content_only_merges():
    md = [{"path": "content/blog/launch.md", "status": "added", "additions": 80, "deletions": 0},
          {"path": "public/images/launch.png", "status": "added", "additions": 0, "deletions": 0}]
    assert content_only(md, "success")[0]
    assert content_only(md, "none") == (False, "no checks ran on it")
    assert content_only(md, "failure") == (False, "its checks failed")
    assert not content_only(md + [{"path": "src/app.ts", "additions": 1, "deletions": 0}], "success")[0]
    assert not content_only([{"path": "content/pricing.md", "additions": 3, "deletions": 1}], "success")[0]
    assert not content_only([{"path": "blog/huge.md", "additions": 400, "deletions": 0}], "success")[0]
    assert not content_only([{"path": "blog/old.md", "status": "removed", "additions": 0, "deletions": 9}], "success")[0]
    assert content_only([{"path": "content/authors/jane.md", "additions": 3, "deletions": 1}], "success")[0]


# --- recommending and applying presets ---------------------------------------------------------------

async def test_recommended_presets_are_tailored_and_applied():
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test")
        org = await org_of(c)
        goal = await goal_for(c, agent_in(org, "Marketing"))
        async with session_scope() as s:
            (await s.get(Campaign, goal)).playbook = {"steps": [
                {"text": "Write posts", "action_type": "create_draft", "tool": "none"},
                {"text": "Post them", "action_type": "publish_post", "tool": "linkedin"},
                {"text": "Reply to comments", "action_type": "reply", "tool": "twitter"}]}

        rec = (await c.get(f"/api/campaigns/{goal}/autonomy")).json()
        assert rec["recommended"] == "balanced" and rec["regulated"] is None
        rows = {r["key"]: r for r in rec["presets"]["balanced"]["rows"]}
        assert rows["publish_post"]["mode"] == "heads_up" and rows["publish_post"]["daily_cap"] == 5
        assert rows["spend_money"]["mode"] == "ask" and rows["merge_code"]["mode"] == "ask"
        assert [r["key"] for r in rec["presets"]["balanced"]["rows"]][:2] == ["reply", "publish_post"]  # in the plan first
        assert {p["key"] for p in rec["personal_candidates"]} == {"linkedin", "twitter"}
        assert all(r["mode"] == "ask" for r in rec["presets"]["cautious"]["rows"])
        assert "autonomy" in (await c.get(f"/api/campaigns/{goal}/readiness")).json()

        r = await c.post(f"/api/campaigns/{goal}/autonomy", json={
            "preset": "balanced", "overrides": {"reply": {"mode": "auto", "daily_cap": 7}}, "personal": ["linkedin"]})
        assert r.status_code == 200, r.text
        p = perms_by_key(r.json()["permissions"])
        assert p["publish_post"]["mode"] == "heads_up" and p["publish_post"]["daily_cap"] == 5
        assert p["reply"]["mode"] == "auto" and p["reply"]["daily_cap"] == 7
        assert p["engage"]["mode"] == "auto" and p["send_message"]["mode"] == "ask"
        assert set(p["publish_post"]["asks_on"]) == {"linkedin", "linkedin.com"}
        assert (await c.get(f"/api/campaigns/{goal}")).json()  # still readable
        async with session_scope() as s:
            assert (await s.get(Campaign, goal)).autonomy_preset == "balanced"
            d = await policy.decide(s, goal, action_type="publish_post", site="https://www.linkedin.com/feed")
            assert d.outcome == "ask"
            assert (await policy.decide(s, goal, action_type="publish_post", app="twitter")).outcome == "heads_up"

        # Applying again replaces the goal's settings rather than piling them up.
        await c.post(f"/api/campaigns/{goal}/autonomy", json={"preset": "cautious"})
        p = perms_by_key((await c.get(f"/api/campaigns/{goal}/permissions")).json()["action_types"])
        assert p["publish_post"]["mode"] == "ask" and p["reply"]["mode"] == "ask" and p["publish_post"]["asks_on"] == []

        bad = await c.post(f"/api/campaigns/{goal}/autonomy", json={"preset": "fast", "overrides": {"spend_money": {"mode": "auto"}}})
        assert bad.status_code == 400
        # A single kind can be set to a heads-up with a daily limit too.
        r = await c.put(f"/api/campaigns/{goal}/permissions/send_message", json={"mode": "heads_up", "daily_cap": 12})
        assert r.status_code == 200 and r.json()["permission"]["mode"] == "heads_up" and r.json()["permission"]["daily_cap"] == 12
        assert (await c.put(f"/api/campaigns/{goal}/permissions/spend_money", json={"mode": "heads_up"})).status_code == 400


async def test_clients_and_regulated_industries_get_stricter_recommendations():
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test")
        org = await org_of(c)
        async with session_scope() as s:
            o = await s.get(Organization, org["org"]["id"])
            o.profile = {**(o.profile or {}), "summary": "A telehealth clinic for busy parents"}
        goal = await goal_for(c, agent_in(org, "Marketing"))
        rec = (await c.get(f"/api/campaigns/{goal}/autonomy")).json()
        assert rec["regulated"] == "healthcare"
        rows = {r["key"]: r for r in rec["presets"]["fast"]["rows"]}
        assert rows["publish_post"]["mode"] == "ask" and "public claims" in rows["publish_post"]["why"]
        assert rows["engage"]["mode"] == "auto"  # likes aren't claims

        client_goal = await goal_for(c, agent_in(org, "Marketing"), "Grow Bistro's audience", client_name="Bistro Co")
        rec = (await c.get(f"/api/campaigns/{client_goal}/autonomy")).json()
        assert rec["recommended"] == "cautious" and "Bistro Co" in rec["reasons"][0]


# --- heads-ups --------------------------------------------------------------------------------------

def fake_github(calls: list, files: list[dict], checks: str = "success") -> FastAPI:
    gh = FastAPI()
    state = {"merged": False}

    @gh.api_route("/{path:path}", methods=["GET", "POST", "PUT"])
    async def any_route(path: str, request: Request):
        calls.append((request.method, "/" + path))
        if path == "repos/acme/site":
            return {"full_name": "acme/site", "default_branch": "main", "private": True, "permissions": {"push": True}}
        if path == "repos/acme/site/pulls/9":
            return {"number": 9, "title": "Launch post", "html_url": "https://github.com/acme/site/pull/9", "state": "open",
                    "merged": state["merged"], "additions": 80, "deletions": 0, "changed_files": len(files),
                    "head": {"ref": "autopilot/launch", "sha": "abc123"}}
        if path == "repos/acme/site/pulls/9/files":
            return [{"filename": f["path"], "status": "added", "additions": f.get("additions", 10), "deletions": 0} for f in files]
        if path == "repos/acme/site/commits/abc123/check-runs":
            return {"check_runs": [{"status": "completed", "conclusion": checks}]}
        if path == "repos/acme/site/commits/abc123/status":
            return {"statuses": []}
        if path == "repos/acme/site/pulls/9/merge":
            state["merged"] = True
            return {"merged": True, "sha": "m1", "message": "merged"}
        return JSONResponse({"message": "Not Found"}, status_code=404)

    return gh


async def _connect_github(c, monkeypatch, calls, files, checks="success"):
    monkeypatch.setattr(github_mod, "TRANSPORT", httpx.ASGITransport(app=fake_github(calls, files, checks)))
    r = await c.post("/api/integrations/github", json={"repo": "acme/site", "token": "ghp_good_token"})
    assert r.status_code == 200, r.text


async def test_content_merges_follow_the_preset_and_heads_ups_dont_hold_up_work(monkeypatch):
    calls: list = []
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test", departments=("engineering", "marketing"))
        org = await org_of(c)
        await _connect_github(c, monkeypatch, calls, [{"path": "content/blog/launch.md"}])
        goal = await goal_for(c, agent_in(org, "Engineering"), "Publish the launch post")
        await c.post(f"/api/campaigns/{goal}/autonomy", json={"preset": "balanced"})
        ex = await executor_for(goal, org["org"]["id"])

        out = await ex.call("github_merge_pull_request", {"number": 9}, "t1")
        assert not isinstance(out, Pending) and '"merged": true' in out.content, "small content merges go on their own"

        # As a heads-up: queued, the AI employee carries on, and it merges once the time is up.
        await c.put(f"/api/campaigns/{goal}/permissions/merge_content", json={"mode": "heads_up"})
        calls.clear()
        out = await ex.call("github_merge_pull_request", {"number": 9}, "t2")
        assert not isinstance(out, Pending) and "Scheduled with a heads-up" in out.content
        assert not any(p.endswith("/merge") for _, p in calls)
        req = (await c.get("/api/requests")).json()[0]
        assert req["auto_approve_at"] and req["preview"]["heads_up"] and req["action_type"] == "merge_content"
        async with session_scope() as s:
            assert await autonomy.release_due(s) == 0  # not yet
            (await s.get(UserRequest, req["id"])).auto_approve_at = utcnow() - timedelta(seconds=1)
        async with session_scope() as s:
            assert await autonomy.release_due(s) == 1
        async with session_scope() as s:
            claimed = await autonomy.claim_queued(s)
        assert claimed == [req["id"]]
        async with session_scope() as s:
            assert await autonomy.claim_queued(s) == []  # only once
        await autonomy.run_queued(req["id"])
        assert any(p.endswith("/pulls/9/merge") for _, p in calls)
        log = (await c.get(f"/api/campaigns/{goal}/activity")).json()
        assert any(a["title"].startswith("Went ahead after the heads-up") for a in log)


async def test_code_merges_always_ask(monkeypatch):
    calls: list = []
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test", departments=("engineering",))
        org = await org_of(c)
        await _connect_github(c, monkeypatch, calls, [{"path": "src/app.ts"}])
        goal = await goal_for(c, agent_in(org, "Engineering"), "Ship it")
        await c.post(f"/api/campaigns/{goal}/autonomy", json={"preset": "fast"})
        ex = await executor_for(goal, org["org"]["id"])
        out = await ex.call("github_merge_pull_request", {"number": 9}, "t1")
        assert isinstance(out, Pending)
        async with session_scope() as s:
            req = await s.get(UserRequest, out.request_id)
            assert req.action_type == "merge_code" and "isn't content" in req.preview["details"]


async def test_browser_heads_up_waits_and_stops_tighten(monkeypatch):
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test")
        org = await org_of(c)
        goal = await goal_for(c, agent_in(org, "Marketing"))
        await c.post(f"/api/campaigns/{goal}/autonomy", json={"preset": "balanced"})
        ex = await executor_for(goal, org["org"]["id"])

        async def declare(n):
            return await ex.call("browser_declare_action", {
                "action_type": "publish_post", "title": f"Post tip #{n}", "site": "x.com",
                "content": f"Tip #{n}: route planning saves dispatchers an hour a day. Here's how we measure it."}, f"t{n}")

        out = await declare(1)
        assert isinstance(out, Pending), "the click needs the live page, so a browser heads-up waits"
        async with session_scope() as s:
            req = await s.get(UserRequest, out.request_id)
            assert req.auto_approve_at is not None and req.queued_call is None
        # Stop it, then stop another: after two stops in a week, posting asks first on this goal.
        r = await c.post(f"/api/requests/{out.request_id}/decide", json={"decision": "reject"})
        assert r.status_code == 200
        out = await declare(2)
        r = await c.post(f"/api/requests/{out.request_id}/decide", json={"decision": "reject"})
        p = perms_by_key((await c.get(f"/api/campaigns/{goal}/permissions")).json()["action_types"])
        assert p["publish_post"]["mode"] == "ask" and p["publish_post"]["source"] == "downgrade"
        log = (await c.get(f"/api/campaigns/{goal}/activity")).json()
        assert any(a["title"].startswith("Stopped by") for a in log)
        assert any("asks first again" in a["title"] for a in log)
        out = await declare(3)
        async with session_scope() as s:
            assert (await s.get(UserRequest, out.request_id)).auto_approve_at is None


async def test_sensitive_content_and_weak_drafts_ask_instead_of_going_out():
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test")
        org = await org_of(c)
        goal = await goal_for(c, agent_in(org, "Marketing"))
        await c.post(f"/api/campaigns/{goal}/autonomy", json={"preset": "fast"})
        post = {"action_type": "publish_post", "title": "Post", "site": "x.com",
                "content": "We just cut our prices by 40% for every plan this week only, here's why we did it."}

        sensitive = await executor_for(goal, org["org"]["id"], reviewer=lambda kw: {
            "violates": False, "rule": "", "explanation": "", "sensitive": True, "sensitive_reason": "It mentions pricing"})
        out = await sensitive.call("browser_declare_action", post, "t1")
        assert isinstance(out, Pending)
        async with session_scope() as s:
            req = await s.get(UserRequest, out.request_id)
            assert req.auto_approve_at is None and req.rationale.startswith("It mentions pricing")

        weak = await executor_for(goal, org["org"]["id"], quality_score=3)
        out = await weak.call("browser_declare_action", post, "t2")
        assert "Quality check: 3/5" in out.content  # first it's sent back for a rewrite
        await weak.call("browser_declare_action", post, "t3")
        out = await weak.call("browser_declare_action", post, "t4")
        assert isinstance(out, Pending)
        async with session_scope() as s:
            assert "quality check scored it 3/5" in (await s.get(UserRequest, out.request_id)).rationale

        fine = await executor_for(goal, org["org"]["id"])
        out = await fine.call("browser_declare_action", post, "t5")
        assert not isinstance(out, Pending) and "authorization_id" in out.content


# --- earned trust and flags ---------------------------------------------------------------------------

async def test_approving_unchanged_suggests_a_heads_up_and_flags_tighten():
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test")
        org = await org_of(c)
        goal = await goal_for(c, agent_in(org, "Marketing"))
        ex = await executor_for(goal, org["org"]["id"])
        text = "Dispatchers lose an hour a day to manual routing. Here's the checklist we use to get it back."
        for n in range(autonomy.STREAK):
            out = await ex.call("browser_declare_action", {"action_type": "reply", "title": f"Reply {n}", "site": "x.com",
                                                            "content": text + f" ({n})"}, f"t{n}")
            assert isinstance(out, Pending)
            edit = {"content": text + f" ({n})!"} if n == 2 else None  # a tiny edit still counts
            r = await c.post(f"/api/requests/{out.request_id}/decide", json={"decision": "approve", "edited_fields": edit})
            assert r.status_code == 200, r.text
            p = perms_by_key((await c.get(f"/api/campaigns/{goal}/permissions")).json()["action_types"])
            assert (p["reply"]["suggestion"] is None) == (n < autonomy.STREAK - 1)
        assert p["reply"]["suggestion"]["mode"] == "heads_up"
        # Spending, deleting and code never get suggested.
        assert all(p[k]["suggestion"] is None for k in autonomy.NEVER_EARNED)

        r = await c.put(f"/api/campaigns/{goal}/permissions/reply", json={"mode": "auto", "daily_cap": 10})
        assert r.json()["permission"]["mode"] == "auto"
        r = await c.post(f"/api/campaigns/{goal}/autonomy/flag", json={"action_type": "reply", "note": "Too salesy"})
        assert r.status_code == 200
        p = perms_by_key(r.json()["permissions"])
        assert p["reply"]["mode"] == "ask" and p["reply"]["suggestion"] is None
        assert (await c.post(f"/api/campaigns/{goal}/autonomy/flag", json={"action_type": "research"})).status_code == 400


async def test_dont_ask_again_replaces_a_heads_up():
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test")
        org = await org_of(c)
        goal = await goal_for(c, agent_in(org, "Marketing"))
        await c.post(f"/api/campaigns/{goal}/autonomy", json={"preset": "balanced"})
        ex = await executor_for(goal, org["org"]["id"])
        out = await ex.call("browser_declare_action", {
            "action_type": "publish_article", "title": "Publish the guide", "site": "acme.test",
            "content": "The complete guide to routing for small fleets: what to measure and what to change first."}, "t1")
        assert isinstance(out, Pending)
        r = await c.post(f"/api/requests/{out.request_id}/decide", json={"decision": "approve", "remember": True,
                                                                         "remember_any_channel": True})
        assert r.status_code == 200 and r.json()["title"]
        p = perms_by_key((await c.get(f"/api/campaigns/{goal}/permissions")).json()["action_types"])
        assert p["publish_article"]["mode"] == "auto"
        async with session_scope() as s:
            live = (await s.execute(select(PermissionGrant).where(
                PermissionGrant.campaign_id == goal, PermissionGrant.action_type == "publish_article",
                PermissionGrant.revoked_at.is_(None)))).scalars().all()
            assert [g.mode for g in live] == ["auto"]
