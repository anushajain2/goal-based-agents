"""How a goal gets hit (funnel and bottleneck), pace, the quality bar, measured progress, and the
experiments, learnings and updates the strategist keeps."""

from datetime import timedelta

from sqlalchemy import select

from app.agent.llm import MeteredClaude
from app.agent.runner import CycleRunner
from app.api import plan as plan_api
from app.db import session_scope
from app.models import Activity, Campaign, MetricSnapshot, UserRequest, utcnow
from app.services import targets
from tests.fakes import FakeAnthropic, text, tool_use
from tests.test_agent_flow import _no_real_browser, api, make_campaign, run_next_cycle  # noqa: F401


def approach(kw):
    return {"stages": [{"name": "Prospects contacted", "benchmark": "40 a week", "unit": "a week"},
                       {"name": "Replies", "benchmark": "5-10% reply", "unit": "a week"},
                       {"name": "Meetings booked", "benchmark": "30% of replies", "unit": "a week"}],
            "bottleneck": "Replies", "bottleneck_why": "Cold lists reply rarely at first.",
            "approaches": [{"name": "Personal cold email", "what": "Short, researched emails", "why": "Proven",
                            "creative": False, "tool": "gmail", "milestone": 1},
                           {"name": "Founder X thread series", "what": "Weekly thread on routing costs", "why": "Ops leads read X",
                            "example": "We cut a 40-van fleet's miles by rerouting 3 depots. Here's how:",
                            "creative": True, "tool": "twitter", "milestone": 1},
                           {"name": "Free route-cost calculator", "what": "A calculator page that captures leads",
                            "why": "Useful before talking to sales", "creative": True, "tool": "none", "milestone": 2}],
            "experiment": {"hypothesis": "Naming their depot raises replies", "change": "Mention the depot city in line 1",
                           "judge_after": "40 emails"}}


async def test_how_a_goal_gets_hit_is_made_once_before_it_starts(api, monkeypatch):
    fake = FakeAnthropic(lambda kw: [text("ok")], routes={"approaches": approach})
    monkeypatch.setattr(plan_api, "MeteredClaude", lambda: MeteredClaude(client=fake))
    gid = await make_campaign(api, launch=False, primary_metric="meetings")
    made = (await api.post(f"/api/campaigns/{gid}/approach")).json()
    assert [s["name"] for s in made["model"]["stages"]] == ["Prospects contacted", "Replies", "Meetings booked"]
    assert made["model"]["bottleneck"] == "Replies"
    assert [a["creative"] for a in made["approaches"]] == [False, True, True]
    assert made["approaches"][2]["milestone"] == 2
    assert made["experiments"][0]["status"] == "planned"
    n = len(fake.calls)
    assert (await api.post(f"/api/campaigns/{gid}/approach")).json() == made  # made once
    assert len(fake.calls) == n
    full = (await api.get(f"/api/campaigns/{gid}")).json()
    assert full["approach"]["model"]["bottleneck"] == "Replies" and full["has_approach"]
    assert made["approaches"][1]["example"].startswith("We cut a 40-van fleet's miles") and made["v"] == 2
    # The strategies are for this goal's own number: not process, not other goals' work.
    system = next(k for k in fake.calls if "approaches" in k["output_config"].get("format", {}).get("schema", {}).get("properties", {}))["system"]
    assert "NOT approaches: anything about the process (approvals" in system
    assert "work that belongs to a different goal" in system
    assert "never internal steps such as drafting, approving or scheduling" in system


async def test_an_older_plan_is_remade_before_the_goal_starts(api, monkeypatch):
    fake = FakeAnthropic(lambda kw: [text("ok")], routes={"approaches": approach})
    monkeypatch.setattr(plan_api, "MeteredClaude", lambda: MeteredClaude(client=fake))
    gid = await make_campaign(api, launch=False, primary_metric="posts")
    async with session_scope() as s:  # a plan from before strategies had examples
        (await s.get(Campaign, gid)).approach = {"model": {"stages": [{"name": "Posts approved"}], "bottleneck": "Posts approved"},
                                                 "approaches": [{"name": "Weekly batch approval in Slack", "what": "x"}]}
    made = (await api.post(f"/api/campaigns/{gid}/approach")).json()
    assert made["v"] == 2 and "Weekly batch approval in Slack" not in [a["name"] for a in made["approaches"]]


def test_pace_says_how_far_behind_and_what_it_needs():
    c = Campaign(primary_metric="meetings", targets=[])
    now = utcnow()
    c.targets = [{"id": "t", "period": "week", "target": 10.0, "status": "active", "baseline": 0.0,
                  "start": (now - timedelta(days=3.5)).isoformat(), "end": (now + timedelta(days=3.5)).isoformat()}]
    p = targets.pace(c, 2.0, now)
    assert p["status"] == "behind" and p["expected_by_now"] == 5.0 and p["needed"] == 8.0
    assert p["per_day_needed"] == round(8 / 3.5, 2) and p["per_day_so_far"] == round(2 / 3.5, 2)
    text_ = targets.pace_text(c, p, waiting=2, oldest_hours=30)
    assert "BEHIND" in text_ and "2 approvals waiting on people, the oldest for 30 hours" in text_
    assert targets.pace(c, 6.0, now)["status"] == "ahead"
    assert targets.pace(c, 10.0, now)["status"] == "hit"


def session_with_plan(extra: dict, worker):
    def planner(kw):
        return {"assessment": "Replies are the bottleneck.", "plan": ["Rewrite opener", "Send 20"], "strategy": "", **extra}

    return FakeAnthropic(worker, planner=planner, routes={"approaches": approach})


async def test_the_strategist_keeps_the_funnel_experiments_learnings_and_posts_an_update(api):
    gid = await make_campaign(api, primary_metric="meetings")
    extra = {"stages": [{"name": "Prospects contacted", "now": 40}, {"name": "Replies", "now": 1},
                        {"name": "Meetings booked", "now": 0}],
             "bottleneck": "Replies", "bottleneck_why": "1 reply from 40 emails (2.5%), benchmark 5-10%.",
             "focus": ["Personal cold email", "Founder X thread series"],
             "approach_status": [{"name": "Free route-cost calculator", "status": "planned"}],
             "new_approach": {"name": "Depot-opening alerts", "what": "Email fleets the week they open a depot",
                              "why": "Timing beats copy", "creative": True, "tool": "web"},
             "experiment": {"action": "start", "hypothesis": "", "change": "", "judge_after": "", "result": ""},
             "learnings": [{"text": "Generic openers get no replies", "evidence": "1 of 40 replied"}],
             "update": {"measured": "40 emails sent, 1 reply (2.5%).", "learned": "Generic openers don't work here.",
                        "changing": "Opening with the prospect's depot city from today."}}
    briefs = []

    def worker(kw):
        briefs.append(kw["messages"][0]["content"])
        return [tool_use("finish_cycle", summary="Rewrote the opener.", next_check_in_hours=6)]

    await run_next_cycle(CycleRunner(MeteredClaude(client=session_with_plan(extra, worker))))
    async with session_scope() as s:
        c = await s.get(Campaign, gid)
        a = c.approach
        reports = (await s.execute(select(Activity).where(Activity.campaign_id == gid, Activity.kind == "report"))).scalars().all()
    assert {s_["name"]: s_["now"] for s_ in a["model"]["stages"]} == {"Prospects contacted": 40, "Replies": 1, "Meetings booked": 0}
    assert a["model"]["why"].startswith("1 reply from 40")
    statuses = {x["name"]: x["status"] for x in a["approaches"]}
    assert statuses["Personal cold email"] == "testing" and statuses["Depot-opening alerts"] == "testing"
    assert a["experiments"][0]["status"] == "running"  # the planned first experiment started
    assert a["learnings"][0]["text"] == "Generic openers get no replies"
    assert len(reports) == 1 and reports[0].details["changing"].startswith("Opening with")
    # The worker's brief carries the funnel, the bottleneck, the approaches and the learnings.
    assert "## How this goal gets hit" in briefs[0] and "Replies: not measured yet" in briefs[0]
    assert "<- bottleneck" in briefs[0] and "Founder X thread series [planned, creative]" in briefs[0]
    assert "E.g. We cut a 40-van fleet's miles" in briefs[0]  # each strategy reaches the work with its example

    # Next session: the experiment is judged and dropped, with its result; no news, no update.
    extra2 = {**extra, "new_approach": None, "learnings": [],
              "experiment": {"action": "drop", "hypothesis": "", "change": "", "judge_after": "",
                             "result": "2 of 40 replied (5%), within noise"},
              "update": {"measured": "", "learned": "", "changing": ""}}
    async with session_scope() as s:
        c = await s.get(Campaign, gid)
        c.next_cycle_at = c.created_at  # due now
    await run_next_cycle(CycleRunner(MeteredClaude(client=session_with_plan(extra2, worker))))
    async with session_scope() as s:
        a = (await s.get(Campaign, gid)).approach
        n = len((await s.execute(select(Activity).where(Activity.campaign_id == gid, Activity.kind == "report"))).all())
    assert a["experiments"][0]["status"] == "dropped" and "5%" in a["experiments"][0]["result"]
    assert n == 1
    assert "[running] Naming their depot raises replies" in briefs[-1]  # dropped by this session's plan


async def test_weak_drafts_go_back_for_a_rewrite_before_anyone_sees_them(api):
    gid = await make_campaign(api)
    seen = []

    def worker(kw):
        step = len(seen)
        seen.append(kw["messages"][-1])
        if step == 0:
            return [tool_use("browser_declare_action", action_type="publish_post", title="Launch post", site="x.com",
                             content="We launched something great today, check it out!!!")]
        if step == 1:
            return [tool_use("browser_declare_action", action_type="publish_post", title="Launch post", site="x.com",
                             content="Dispatchers lose 41 minutes a day re-planning routes. v2 cuts that to 5. Here's how.")]
        return [tool_use("finish_cycle", summary="Posted.", next_check_in_hours=6)]

    scores = iter([2, 5])

    def reviewer(kw):
        return {"score": next(scores), "fixes": ["Lead with a specific number", "Say who it's for"]}

    fake = FakeAnthropic(worker, routes={"fixes": reviewer, "approaches": approach})
    await run_next_cycle(CycleRunner(MeteredClaude(client=fake)))
    bounced = seen[1]["content"][0]
    assert bounced["is_error"] and "Quality check: 2/5" in bounced["content"] and "Lead with a specific number" in bounced["content"]
    async with session_scope() as s:
        reqs = (await s.execute(select(UserRequest).where(UserRequest.campaign_id == gid))).scalars().all()
    # Only the rewritten post reached a person, with the reviewer's score attached.
    assert len(reqs) == 1 and "41 minutes" in reqs[0].preview["fields"]["content"]
    assert reqs[0].preview["quality"]["score"] == 5


async def test_metrics_count_as_measured_only_when_read_from_a_tool_used_that_session(api):
    gid = await make_campaign(api)

    def worker(kw):
        if len(kw["messages"]) == 1:
            return [tool_use("record_metric", metric="followers", value=120, how="read_from_tool", tool="hubspot",
                             source="HubSpot"),
                    tool_use("record_metric", metric="followers", value=121, how="counted", source="my own count")]
        return [tool_use("finish_cycle", summary="Recorded.", next_check_in_hours=6)]

    await run_next_cycle(CycleRunner(MeteredClaude(client=FakeAnthropic(worker, routes={"approaches": approach}))))
    async with session_scope() as s:
        snaps = (await s.execute(select(MetricSnapshot).where(MetricSnapshot.campaign_id == gid)
                                 .order_by(MetricSnapshot.id))).scalars().all()
    assert [(m.value, m.verified) for m in snaps] == [(120, False), (121, False)]  # HubSpot wasn't read this session
    full = (await api.get(f"/api/campaigns/{gid}")).json()
    assert [m["verified"] for m in full["metrics"]] == [False, False]

    from app.agent.executor import ToolExecutor

    ex = ToolExecutor(MeteredClaude(client=FakeAnthropic(lambda kw: [])), gid, "run-x")
    ex.sources_read.add("hubspot")
    out = await ex.t_record_metric({"metric": "followers", "value": 130, "how": "read_from_tool", "tool": "HubSpot",
                                    "source": "HubSpot contacts"}, "t1")
    assert out.content == "Recorded as measured."
    async with session_scope() as s:
        last = (await s.execute(select(MetricSnapshot).where(MetricSnapshot.campaign_id == gid)
                                .order_by(MetricSnapshot.id.desc()))).scalars().first()
    assert last.verified


async def test_approve_as_written_rate_per_ai_employee(api):
    from tests.test_agent_flow import scripted_cycle

    gid = await make_campaign(api)
    state: dict = {}
    await run_next_cycle(CycleRunner(MeteredClaude(client=FakeAnthropic(scripted_cycle(state), routes={"approaches": approach}))))
    req = (await api.get("/api/requests?status=pending")).json()[0]
    r = await api.post(f"/api/requests/{req['id']}/decide", json={"decision": "approve"})
    assert r.status_code == 200, r.text
    full = (await api.get(f"/api/campaigns/{gid}")).json()
    assert full["approvals"] == {"decided": 1, "as_is": 1, "edited": 0, "declined": 0, "rate": 1.0}
    org = (await api.get("/api/org")).json()
    agent = next(a for d in org["departments"] for a in d["agents"] if a["approved_as_is"])
    assert agent["approved_as_is"] == {"decided": 1, "as_is": 1, "rate": 1.0}
