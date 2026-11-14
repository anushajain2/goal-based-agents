"""End-to-end agent cycles against a scripted Claude: approvals, grants, blocks, budget."""

from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.agent.llm import MeteredClaude
from app.agent.runner import CycleRunner
from app.browser.controller import BrowserController
from app.db import session_scope
from app.main import app
from app.models import Activity, AgentRun, Campaign, LedgerEntry, PermissionGrant, UserRequest
from app.worker import claim_run, schedule_due_cycles
from tests.fakes import FakeAnthropic, text, tool_use


@pytest.fixture(autouse=True)
def _no_real_browser(monkeypatch):
    async def no_shot(self, run_id):
        raise RuntimeError("no browser in this test")

    async def noop(self, run_id):
        return None

    monkeypatch.setattr(BrowserController, "screenshot", no_shot)
    monkeypatch.setattr(BrowserController, "close_run", noop)


@pytest.fixture
async def api():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        yield client


async def make_campaign(api, **overrides) -> str:
    body = {
        "name": "Grow X", "goal_type": "followers", "goal_description": "Grow @demo on X",
        "primary_metric": "followers", "budget_total": 20, "channels": ["x.com"], "launch": True,
        **overrides,
    }
    r = await api.post("/api/campaigns", json=body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def run_next_cycle(runner: CycleRunner) -> str:
    await schedule_due_cycles()
    run_id = await claim_run("test")
    assert run_id
    await runner.run(run_id)
    return run_id


async def resume(runner: CycleRunner) -> str:
    run_id = await claim_run("test")
    assert run_id, "expected the decided run to be queued"
    await runner.run(run_id)
    return run_id


async def run_row(run_id) -> AgentRun:
    async with session_scope() as s:
        return await s.get(AgentRun, run_id)


async def titles(campaign_id) -> list[str]:
    async with session_scope() as s:
        rows = (await s.execute(select(Activity).where(Activity.campaign_id == campaign_id)
                                .order_by(Activity.id))).scalars()
        return [f"{a.kind}:{a.status}:{a.title}" for a in rows]


def last_tool_results(kwargs) -> list[dict]:
    for m in reversed(kwargs["messages"]):
        if m["role"] == "user" and isinstance(m["content"], list):
            return m["content"]
    return []


POST = "Shipping v2 today: 3x faster sync. Try it free."


def scripted_cycle(state: dict):
    """Cycle: set strategy + record metric -> declare a post -> finish."""

    def script(kw):
        step = state.setdefault("step", 0)
        state["step"] += 1
        if step == 0:
            return [text("Planning."),
                    tool_use("update_strategy", strategy="- Post daily product updates"),
                    tool_use("record_metric", metric="followers", value=100, source="X profile")]
        if step == 1:
            return [tool_use("browser_declare_action", action_type="publish_post", title="Post v2 launch tweet",
                             site="x.com", content=POST)]
        state["results_seen"] = last_tool_results(kw)
        return [tool_use("finish_cycle", summary="Posted the launch tweet.", next_check_in_hours=4)]

    return script


async def test_approval_then_dont_ask_again(api):
    cid = await make_campaign(api)
    state: dict = {}
    fake = FakeAnthropic(scripted_cycle(state))
    runner = CycleRunner(MeteredClaude(client=fake))

    run_id = await run_next_cycle(runner)
    run = await run_row(run_id)
    assert run.status == "waiting"

    reqs = (await api.get("/api/requests")).json()
    assert len(reqs) == 1
    req = reqs[0]
    assert req["action_type"] == "publish_post" and req["scope"] == "x.com"
    assert req["preview"]["fields"]["content"] == POST

    edited = POST + " #launch"
    r = await api.post(f"/api/requests/{req['id']}/decide", json={
        "decision": "approve", "remember": True, "edited_fields": {"content": edited}})
    assert r.status_code == 200, r.text

    await resume(runner)
    run = await run_row(run_id)
    assert run.status == "completed" and run.summary == "Posted the launch tweet."
    result_text = state["results_seen"][0]["content"]
    assert "authorization_id=" in result_text and edited in result_text

    # The grant exists and the next cycle's post goes through without asking.
    async with session_scope() as s:
        grants = (await s.execute(select(PermissionGrant))).scalars().all()
        assert [(g.action_type, g.scope) for g in grants] == [("publish_post", "x.com")]
        campaign = await s.get(Campaign, cid)
        campaign.next_cycle_at = campaign.created_at  # due now
    state.clear()
    run2 = await run_next_cycle(runner)
    assert (await run_row(run2)).status == "completed"
    assert len((await api.get("/api/requests")).json()) == 0
    assert "authorization_id=" in state["results_seen"][0]["content"]

    # AI usage is metered into the ledger; the cycle line carries its cost.
    async with session_scope() as s:
        ai = (await s.execute(select(LedgerEntry).where(LedgerEntry.kind == "ai_usage"))).scalars().all()
        assert ai and all(e.status == "settled" for e in ai)
        assert sum(e.amount_usd for e in ai) > 0
    log = await titles(cid)
    assert any(t.startswith("request:waiting:Waiting for you: Post v2 launch tweet") for t in log)
    assert any("Approved (edited): Post v2 launch tweet" in t and "won't ask again" in t for t in log)
    assert any(t.startswith("cycle:info:Cycle 1 complete") for t in log)
    assert any(t.startswith("metric:info:followers: 100") for t in log)

    detail = (await api.get(f"/api/campaigns/{cid}")).json()
    assert detail["strategy"] == "- Post daily product updates"
    assert detail["budget"]["ai_usage"] > 0


async def test_rejection_is_reported_to_agent(api):
    await make_campaign(api)
    state: dict = {}
    runner = CycleRunner(MeteredClaude(client=FakeAnthropic(scripted_cycle(state))))
    await run_next_cycle(runner)
    req = (await api.get("/api/requests")).json()[0]
    await api.post(f"/api/requests/{req['id']}/decide", json={"decision": "reject", "note": "Too salesy"})
    await resume(runner)
    result = state["results_seen"][0]
    assert result.get("is_error") and "declined" in result["content"] and "Too salesy" in result["content"]


async def test_hard_block_and_text_rule(api):
    cid = await make_campaign(api, exclusions=[{"kind": "action_type", "value": "publish_post"}])
    state: dict = {}
    runner = CycleRunner(MeteredClaude(client=FakeAnthropic(scripted_cycle(state))))
    run_id = await run_next_cycle(runner)
    assert (await run_row(run_id)).status == "completed"
    result = state["results_seen"][0]
    assert result["is_error"] and "Blocked by the user's guardrails" in result["content"]
    assert any(t.startswith("blocked:blocked:Blocked: Post v2 launch tweet") for t in await titles(cid))
    assert (await api.get("/api/requests")).json() == []

    # Free-text rule: the AI reviewer flags it -> blocked without asking.
    cid2 = await make_campaign(api, name="Other", exclusions=[{"kind": "text", "value": "Never say 'free'"}])
    state2: dict = {}
    reviewer = lambda kw: {"violates": True, "rule": "Never say 'free'", "explanation": "It says free."}
    runner2 = CycleRunner(MeteredClaude(client=FakeAnthropic(scripted_cycle(state2), reviewer)))
    await schedule_due_cycles()
    async with session_scope() as s:
        run = (await s.execute(select(AgentRun).where(AgentRun.campaign_id == cid2))).scalar_one()
    await claim_run("t")  # claims cid2's run (cid's is completed)
    await runner2.run(run.id)
    assert "Never say 'free'" in state2["results_seen"][0]["content"]


async def test_guardrail_change_reaches_running_agent(api):
    cid = await make_campaign(api)
    seen: dict = {}

    def script(kw):
        step = seen.setdefault("step", 0)
        seen["step"] += 1
        if step == 0:
            return [tool_use("browser_declare_action", action_type="publish_post", title="Post", site="x.com",
                             content="hello world, this is a post")]
        seen["messages"] = kw["messages"]
        return [tool_use("finish_cycle", summary="done", next_check_in_hours=2)]

    runner = CycleRunner(MeteredClaude(client=FakeAnthropic(script)))
    await run_next_cycle(runner)
    # While the run waits for approval, the user adds a guardrail, then approves.
    r = await api.post("/api/exclusions", json={"campaign_id": cid, "kind": "text", "value": "No emojis"})
    assert r.status_code == 200
    req = (await api.get("/api/requests")).json()[0]
    await api.post(f"/api/requests/{req['id']}/decide", json={"decision": "approve"})
    await resume(runner)
    system_msgs = [m for m in seen["messages"] if m["role"] == "system"]
    assert system_msgs and "No emojis" in system_msgs[-1]["content"]
    # Appended after the tool results, never edited into history.
    assert seen["messages"][-1]["role"] == "system" and seen["messages"][-2]["role"] == "user"


async def test_budget_exhaustion_pauses_campaign(api):
    cid = await make_campaign(api, budget_total=0.05)  # less than one worst-case call
    runner = CycleRunner(MeteredClaude(client=FakeAnthropic(lambda kw: [text("hi")])))
    run_id = await run_next_cycle(runner)
    assert (await run_row(run_id)).status == "stopped"
    detail = (await api.get(f"/api/campaigns/{cid}")).json()
    assert detail["status"] == "out_of_budget"
    assert any("budget used up" in t for t in await titles(cid))


async def test_pause_stops_and_resume_continues(api):
    cid = await make_campaign(api)
    state: dict = {}
    runner = CycleRunner(MeteredClaude(client=FakeAnthropic(scripted_cycle(state))))
    run_id = await run_next_cycle(runner)  # parks on approval
    await api.post(f"/api/campaigns/{cid}/pause")
    req = (await api.get("/api/requests")).json()[0]
    await api.post(f"/api/requests/{req['id']}/decide", json={"decision": "approve"})
    await resume(runner)  # campaign paused -> run stops, nothing executed
    assert (await run_row(run_id)).status == "stopped"
    await api.post(f"/api/campaigns/{cid}/resume")
    await resume(runner)
    assert (await run_row(run_id)).status == "completed"


async def test_spend_grant_requires_limit(api):
    cid = await make_campaign(api)
    r = await api.post("/api/grants", json={"campaign_id": cid, "action_type": "spend_money"})
    assert r.status_code == 400
    r = await api.post("/api/grants", json={"campaign_id": cid, "action_type": "spend_money", "spend_limit_usd": 5})
    assert r.status_code == 200
    assert Decimal(str(r.json()["spend_limit_usd"])) == Decimal(5)


async def test_user_request_rows_link_to_run(api):
    await make_campaign(api)
    runner = CycleRunner(MeteredClaude(client=FakeAnthropic(scripted_cycle({}))))
    run_id = await run_next_cycle(runner)
    async with session_scope() as s:
        req = (await s.execute(select(UserRequest))).scalar_one()
        assert req.run_id == run_id and req.tool_use_id
