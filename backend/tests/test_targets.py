"""Ongoing goals with time-boxed targets, and changes the AI employee proposes."""

from datetime import timedelta

import httpx

from app.agent.executor import ToolExecutor
from app.agent.llm import MeteredClaude
from app.db import session_scope
from app.main import app
from app.models import AgentRun, Campaign, MetricSnapshot, utcnow
from app.services import targets
from app.worker import roll_over_targets
from tests.fakes import FakeAnthropic
from tests.helpers import agent_in, org_of, sign_in_with_org


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def new_goal(c, agent_id: str, launch: bool = True) -> dict:
    r = await c.post("/api/campaigns", json={
        "name": "Get newsletter signups from dispatchers", "goal_description": "Grow the newsletter",
        "primary_metric": "signups", "target_value": 15, "target_period": "week", "budget_total": 10,
        "agent_id": agent_id, "launch": launch})
    assert r.status_code == 200, r.text
    return r.json()


async def record(goal_id: str, value: float, when=None):
    async with session_scope() as s:
        s.add(MetricSnapshot(campaign_id=goal_id, metric="signups", value=value, recorded_at=when or utcnow()))


async def executor_for(goal_id: str, org_id: str) -> ToolExecutor:
    async with session_scope() as s:
        run = AgentRun(campaign_id=goal_id, cycle_number=1, status="running")
        s.add(run)
        await s.flush()
        run_id = run.id
    return ToolExecutor(MeteredClaude(client=FakeAnthropic(lambda kw: [])), goal_id, run_id, org_id)


async def test_a_weekly_target_rolls_over_and_keeps_history():
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test", departments=("marketing",))
        org = await org_of(c)
        draft = await new_goal(c, agent_in(org, "Marketing"), launch=False)
        assert draft["target"]["status"] == "planned" and draft["target"]["progress"] is None
        await record(draft["id"], 4)  # before it starts: not counted
        g = (await c.post(f"/api/campaigns/{draft['id']}/launch")).json()
        g = (await c.get(f"/api/campaigns/{g['id']}")).json()
        t = g["target"]
        assert (t["period"], t["target"], t["status"], t["progress"]) == ("week", 15, "active", 0)
        assert 6.9 < t["days_left"] <= 7

        await record(g["id"], 21)  # running total: 17 this week
        g = (await c.get(f"/api/campaigns/{g['id']}")).json()
        assert g["target"]["progress"] == 17

        # The week ends: hit, and the same target carries on into next week.
        async with session_scope() as s:
            goal = await s.get(Campaign, g["id"])
            closed = await targets.roll_over(s, goal, now=utcnow() + timedelta(days=7, minutes=1))
            assert closed["status"] == "hit" and closed["result"] == 17
        g = (await c.get(f"/api/campaigns/{g['id']}")).json()
        assert g["target"]["history"][-1]["status"] == "hit"
        assert g["target"]["target"] == 15 and g["target"]["status"] == "active"
        log = (await c.get(f"/api/campaigns/{g['id']}/activity")).json()
        assert any("Week ended: 17 of 15 signups: target hit" in a["title"] for a in log)
        assert await roll_over_targets() == 0  # nothing else has ended


async def test_agent_proposes_a_bigger_target_and_a_person_approves():
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test", departments=("marketing",))
        org = await org_of(c)
        g = await new_goal(c, agent_in(org, "Marketing"))
        await record(g["id"], 16)
        ex = await executor_for(g["id"], org["org"]["id"])
        out = await ex.t_propose_change({"change": "target", "target": 30, "period": "week",
                                         "reasoning": "Hit 16 of 15 in four days from two LinkedIn posts."}, "tu_1")
        assert not out.is_error
        again = await ex.t_propose_change({"change": "pause", "reasoning": "x"}, "tu_2")
        assert again.is_error and "already waiting" in again.content  # one at a time

        reqs = (await c.get("/api/requests")).json()
        p = next(r for r in reqs if r["kind"] == "proposal")
        assert p["title"] == "Raise the target to 30 signups a week"
        assert p["preview"]["current"]["progress"] == 16
        r = await c.post(f"/api/requests/{p['id']}/decide",
                         json={"decision": "approve", "edited_fields": {"target": "25"}})
        assert r.status_code == 200, r.text
        g = (await c.get(f"/api/campaigns/{g['id']}")).json()
        t = g["target"]
        assert (t["target"], t["period"], t["progress"], t["set_by"]) == (25, "week", 0, "agent")
        assert t["why"].startswith("Hit 16 of 15")
        assert t["history"][-1]["status"] == "replaced" and t["history"][-1]["result"] == 16
        assert g["target_value"] == 25

        # A declined proposal changes nothing.
        await ex.t_propose_change({"change": "pause", "reasoning": "Signups are flat."}, "tu_3")
        p = next(r for r in (await c.get("/api/requests")).json() if r["kind"] == "proposal")
        await c.post(f"/api/requests/{p['id']}/decide", json={"decision": "reject", "note": "Keep going"})
        assert (await c.get(f"/api/campaigns/{g['id']}")).json()["status"] == "active"


async def test_people_can_set_the_target_themselves():
    async with client() as c:
        await sign_in_with_org(c, "founder@acme.test", departments=("marketing",))
        org = await org_of(c)
        g = await new_goal(c, agent_in(org, "Marketing"))
        g = (await c.patch(f"/api/campaigns/{g['id']}", json={"target_value": 100, "target_period": "month"})).json()
        assert (g["target"]["target"], g["target"]["period"], g["target"]["set_by"]) == (100, "month", "person")
