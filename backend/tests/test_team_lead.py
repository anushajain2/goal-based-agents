"""Teams and their AI team leads: one person gets a team's requests, and the lead proposes changes."""

from datetime import timedelta
from decimal import Decimal

import httpx

from app.agent.llm import MeteredClaude
from app.agent.team_lead import run_review, schedule_due_reviews
from app.config import get_settings
from app.db import session_scope
from app.main import app
from app.models import Campaign, Department, LeadReview, utcnow
from tests.fakes import FakeAnthropic
from tests.helpers import agent_in, org_of, sign_in, sign_in_with_org


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def dept_of(org: dict, name: str) -> dict:
    return next(d for d in org["departments"] if d["name"] == name)


async def goal(c, agent_id: str, name: str, launch: bool = True) -> str:
    r = await c.post("/api/campaigns", json={"name": name, "goal_description": name, "primary_metric": "signups",
                                             "target_value": 15, "target_period": "week", "budget_total": 10,
                                             "agent_id": agent_id, "launch": launch})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def lead_answer(proposals):
    def answer(kw):
        props = kw["output_config"]["format"]["schema"]["properties"]
        if "proposals" not in props:
            return {"violates": False, "rule": "", "explanation": ""}
        return {"health": "mixed", "summary": "Signups beat the target; the webinar goal is stuck.", "proposals": proposals}
    return answer


async def test_the_first_person_on_a_team_gets_its_requests():
    async with client() as owner, client() as maya:
        await sign_in_with_org(owner, "founder@acme.test", departments=("marketing", "sales"))
        org = await org_of(owner)
        marketing = dept_of(org, "Marketing")
        assert marketing["head"] is None  # nobody yet: requests go to the owner
        await owner.post("/api/invitations", json={"email": "maya@acme.test", "department_ids": [marketing["id"]]})
        await sign_in(maya, "maya@acme.test")
        await org_of(maya)  # joins
        org = await org_of(owner)
        assert dept_of(org, "Marketing")["head"]["email"] == "maya@acme.test"
        assert dept_of(org, "Sales")["head"] is None
        # Moving her off the team sends its requests back to the owner.
        maya_id = next(m["id"] for m in org["members"] if m["email"] == "maya@acme.test")
        await owner.patch(f"/api/members/{maya_id}", json={"department_ids": [dept_of(org, "Sales")["id"]]})
        org = await org_of(owner)
        assert dept_of(org, "Marketing")["head"] is None
        assert dept_of(org, "Sales")["head"]["email"] == "maya@acme.test"


async def test_lead_reviews_the_team_and_proposes_changes(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test", departments=("marketing",))
        org = await org_of(c)
        agent = agent_in(org, "Marketing")
        team = dept_of(org, "Marketing")
        assert team["lead"]["name"] == "Marketing Lead" and team["lead"]["enabled"] and team["lead"]["last"] is None
        signups = await goal(c, agent, "Get newsletter signups")
        webinars = await goal(c, agent, "Fill webinars")
        r = await c.post(f"/api/departments/{team['id']}/lead/review")
        assert r.status_code == 200, r.text
        assert (await c.post(f"/api/departments/{team['id']}/lead/review")).status_code == 409  # one at a time

        proposals = [
            {"type": "target", "goal_id": signups, "reasoning": "17 of 15 in week one.", "target": 30, "period": "week", "new_goal": None},
            {"type": "pause", "goal_id": "not-a-goal", "reasoning": "x", "target": None, "period": None, "new_goal": None},
            {"type": "pause", "goal_id": webinars, "reasoning": "0 registrations after 2 weeks.", "target": None, "period": None, "new_goal": None},
            {"type": "new_goal", "goal_id": "", "reasoning": "Churned customers are a cheap win.", "target": None, "period": None,
             "new_goal": {"name": "Win back churned customers", "goal_description": "Re-engage customers who cancelled",
                          "primary_metric": "customers won back", "done_when": "Customer re-subscribes",
                          "target_value": 3, "target_period": "month", "first_week": "A list of 40 churned customers",
                          "key_results": ["3 won back"], "agent_id": "unknown"}},
            {"type": "resume", "goal_id": signups, "reasoning": "already running: dropped", "target": None, "period": None, "new_goal": None},
        ]
        fake = FakeAnthropic(lambda kw: [], reviewer=lead_answer(proposals))
        await run_review(r.json()["id"], MeteredClaude(client=fake))

        team = dept_of(await org_of(c), "Marketing")
        last = team["lead"]["last"]
        assert last["status"] == "done" and last["health"] == "mixed" and last["cost_usd"] > 0
        assert [p["type"] for p in last["proposals"]] == ["target", "pause", "new_goal"]  # bad ones dropped, at most 3
        assert team["lead"]["spent_this_month_usd"] > 0
        assert "Signups beat the target" in last["summary"]
        assert "Marketing Lead" in fake.calls[0]["system"] or "Marketing team" in fake.calls[0]["system"]
        assert "Get newsletter signups" in fake.calls[0]["messages"][0]["content"]

        reqs = {r["title"]: r for r in (await c.get("/api/requests")).json() if r["kind"] == "proposal"}
        assert set(reqs) == {"Raise the target to 30 signups a week", 'Pause "Fill webinars"',
                             "Start a new goal: Win back churned customers"}
        new = reqs["Start a new goal: Win back churned customers"]
        assert new["preview"]["source"] == "lead" and new["preview"]["lead"] == "Marketing Lead"
        draft = (await c.get(f"/api/campaigns/{new['campaign_id']}")).json()
        assert draft["status"] == "draft" and draft["origin"] == "lead" and draft["agent"]["id"] == agent
        assert draft["target"]["target"] == 3 and draft["target"]["period"] == "month"

        for title in reqs:
            r = await c.post(f"/api/requests/{reqs[title]['id']}/decide", json={"decision": "approve"})
            assert r.status_code == 200, r.text
        goals = {g["name"]: g for g in (await c.get("/api/campaigns")).json()}
        assert goals["Get newsletter signups"]["target"]["target"] == 30
        assert goals["Fill webinars"]["status"] == "paused"
        started = goals["Win back churned customers"]
        assert started["status"] == "active" and started["target"]["status"] == "active"


async def test_reviews_run_on_schedule_within_a_monthly_limit(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test", departments=("marketing", "sales"))
        org = await org_of(c)
        await goal(c, agent_in(org, "Marketing"), "Get newsletter signups")
        await goal(c, agent_in(org, "Sales"), "Book demos", launch=False)  # no live goals: no reviews
        assert await schedule_due_reviews() == 0  # starts the clock
        async with session_scope() as s:
            for d in (await s.execute(Department.__table__.select())).all():
                dept = await s.get(Department, d.id)
                if dept.lead_last_review_at:
                    dept.lead_last_review_at = utcnow() - timedelta(days=8)
        assert await schedule_due_reviews() == 1
        assert await schedule_due_reviews() == 0  # already queued

        team = dept_of(org, "Marketing")
        r = await c.patch(f"/api/departments/{team['id']}/lead", json={"monthly_cap_usd": 0, "review_days": 3})
        assert r.status_code == 200
        async with session_scope() as s:
            for rv in (await s.execute(LeadReview.__table__.select())).all():
                (await s.get(LeadReview, rv.id)).status = "done"
            (await s.get(LeadReview, rv.id)).cost_usd = Decimal("0.01")
        r = await c.post(f"/api/departments/{team['id']}/lead/review")
        assert r.status_code == 400 and "limit" in r.json()["detail"]
        await c.patch(f"/api/departments/{team['id']}/lead", json={"enabled": False})
        assert dept_of(await org_of(c), "Marketing")["lead"]["enabled"] is False
