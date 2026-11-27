"""Outreach goals carry what a good founder or SDR knows: a specific opener, warm-up, the right
channel, one follow-up, a protected sender, and results kept by channel and opener."""

from app.agent import approach as goal_approach
from app.agent.executor import ToolExecutor
from app.agent.llm import MeteredClaude
from app.agent.playbook import OUTREACH_KNOWHOW, default_playbook, is_outreach
from app.api import plan as plan_api
from app.db import session_scope
from app.models import AgentRun, Campaign
from tests.fakes import FakeAnthropic, text
from tests.test_agent_flow import _no_real_browser, api, make_campaign  # noqa: F401
from tests.test_goal_engine import approach


def test_outreach_goals_are_recognised_and_posting_goals_are_not():
    assert is_outreach(Campaign(name="Book meetings with ideal customers", primary_metric="meetings booked"))
    assert is_outreach(Campaign(name="Win new clients", use_case="Client acquisition", primary_metric="discovery calls booked"))
    assert is_outreach(Campaign(name="Anything", primary_metric="x",
                                playbook={"steps": [{"text": "Send", "action_type": "send_message", "tool": "gmail"}]}))
    assert not is_outreach(Campaign(name="Post on LinkedIn and X 3x a week", primary_metric="posts published"))


def test_default_outreach_plan_starts_with_the_basics_and_stops_after_one_follow_up():
    steps = default_playbook(Campaign(name="Book meetings", goal_description="Book meetings with fleet managers",
                                      primary_metric="meetings booked", channels=["Email"]))["steps"]
    texts = [s["text"] for s in steps]
    assert "separate outreach domain" in texts[0] and steps[0]["action_type"] == "modify_account"
    assert any("something specific about them" in t for t in texts)
    assert any("Warm up" in t for t in texts)
    assert any("one follow-up on another channel, then stop" in t for t in texts)
    assert "by channel and opener" in texts[-1]
    # A posting goal on LinkedIn isn't turned into messaging.
    post = default_playbook(Campaign(name="Post on LinkedIn 3x a week", goal_description="Post",
                                     primary_metric="posts published", channels=["LinkedIn"]))["steps"]
    assert not any(s["action_type"] == "send_message" for s in post)


async def test_the_plan_and_every_session_get_the_outreach_know_how(api, monkeypatch):
    fake = FakeAnthropic(lambda kw: [text("ok")], routes={"approaches": approach})
    monkeypatch.setattr(plan_api, "MeteredClaude", lambda: MeteredClaude(client=fake))
    meetings = await make_campaign(api, launch=False, name="Book meetings with fleet managers", primary_metric="meetings booked")
    posts = await make_campaign(api, launch=False, name="Post on LinkedIn 3x a week", primary_metric="posts published")
    await api.post(f"/api/campaigns/{meetings}/approach")
    await api.post(f"/api/campaigns/{posts}/approach")
    prompts = [k["messages"][0]["content"] for k in fake.calls if "approaches" in k["output_config"].get("format", {}).get("schema", {}).get("properties", {})]
    assert "How good outreach works" in prompts[0] and "How good outreach works" not in prompts[1]
    assert "Warm up where they're active" in OUTREACH_KNOWHOW and "separate domain" in OUTREACH_KNOWHOW


async def test_results_are_kept_by_channel_and_opener_and_shown_to_the_next_session(api):
    gid = await make_campaign(api, launch=False, name="Book meetings with fleet managers", primary_metric="meetings booked")
    async with session_scope() as s:
        run = AgentRun(campaign_id=gid, cycle_number=1, status="running")
        s.add(run)
        await s.flush()
        run_id = run.id
        org_id = (await s.get(Campaign, gid)).org_id
    ex = ToolExecutor(MeteredClaude(client=FakeAnthropic(lambda kw: [])), gid, run_id, org_id)
    rows = [{"channel": "LinkedIn", "opener": "their funding round", "sent": 40, "replies": 6, "meetings": 2},
            {"channel": "Email", "opener": "generic intro", "sent": 60, "replies": 1, "meetings": 0}]
    out = await ex.call("record_channel_results", {"rows": rows}, "t1")
    assert not out.is_error
    # Totals so far: a later report replaces the same channel and opener.
    await ex.call("record_channel_results", {"rows": [{**rows[0], "sent": 50, "replies": 8, "meetings": 3}]}, "t2")
    async with session_scope() as s:
        a = (await s.get(Campaign, gid)).approach
    assert len(a["outreach"]) == 2
    brief = goal_approach.brief_text(a)
    assert "## Outreach so far, by channel and opener" in brief
    first = brief.split("by channel and opener (do more of what books calls)\n")[1].splitlines()[0]
    assert first == '- LinkedIn / "their funding round": 50 sent, 8 replies (16% reply), 3 meetings'
    log = (await api.get(f"/api/campaigns/{gid}/activity")).json()
    assert any("best so far LinkedIn" in x["title"] for x in log)
