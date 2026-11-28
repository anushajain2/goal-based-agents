"""Quick fixes and long-term goals: a long-term goal never spends more than its weekly limit, and
pauses until Monday when the week's limit is used up (it stays on)."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.agent.llm import MeteredClaude
from app.agent.opportunities import weekly_limit
from app.agent.runner import CycleRunner
from app.db import session_scope
from app.models import AgentRun, Campaign, LedgerEntry, LedgerKind, utcnow
from app.services import ledger
from tests.fakes import FakeAnthropic
from tests.test_agent_flow import _no_real_browser, api, make_campaign  # noqa: F401
from tests.test_org_setup import client, fake_site, goal, onboard, research_script, with_key  # noqa: F401


def test_the_weekly_limit_is_a_plain_number_from_the_work_it_does():
    cap, basis = weekly_limit(0.30, 24, 0, "typical", 0)  # daily work at $0.30 a session: $2.10 -> $3
    assert cap == 3 and basis["sessions_per_week"] == 7
    assert weekly_limit(0.30, 6, 20, "typical", 0)[0] == 30  # 28 sessions ($8.40) + $20 of ads -> $30
    assert ledger.week_start().weekday() == 0 and ledger.week_start().hour == 0


async def test_a_long_term_goal_spends_up_to_its_weekly_limit_then_waits_for_monday(api):
    gid = await make_campaign(api, budget_total=100)
    r = await api.patch(f"/api/campaigns/{gid}", json={"weekly_cap": 3})
    assert r.status_code == 200 and r.json()["weekly_cap"] == 3
    async with session_scope() as s:
        # Last week's spending doesn't count; this week's does.
        s.add(LedgerEntry(campaign_id=gid, kind=LedgerKind.ai_usage.value, status="settled", amount_usd=Decimal("5"),
                          description="last week", created_at=ledger.week_start() - timedelta(hours=2)))
        s.add(LedgerEntry(campaign_id=gid, kind=LedgerKind.ai_usage.value, status="settled", amount_usd=Decimal("2.9"),
                          description="this week", created_at=utcnow()))
    async with session_scope() as s:
        state = await ledger.budget_state(s, await s.get(Campaign, gid))
        assert state.week == Decimal("2.9") and state.remaining_this_week == Decimal("0.1")
        assert state.as_dict()["weekly_cap"] == 3 and state.as_dict()["week"] == 2.9
        with pytest.raises(ledger.BudgetExceeded) as e:
            await ledger.reserve(s, gid, LedgerKind.ai_usage, Decimal("0.2"), "a session")
        assert e.value.which == "weekly limit"
        run = AgentRun(campaign_id=gid, cycle_number=1, status="running")
        s.add(run)
        await s.flush()
        run_id = run.id
    await CycleRunner(MeteredClaude(client=FakeAnthropic(lambda kw: [])))._out_of_budget(run_id, gid, "weekly limit")
    async with session_scope() as s:
        c = await s.get(Campaign, gid)
        assert c.status == "active"  # still on: back on Monday
        assert c.next_cycle_at.replace(tzinfo=None) >= (ledger.week_start() + timedelta(days=7)).replace(tzinfo=None)
    log = (await api.get(f"/api/campaigns/{gid}/activity")).json()
    assert any("This week's limit ($3.00) is used up" in a["title"] for a in log)
    full = (await api.get(f"/api/campaigns/{gid}")).json()
    assert full["budget"]["weekly_cap"] == 3 and full["budget"]["week"] == 2.9


async def test_findings_come_as_quick_fixes_or_long_term_goals(with_key, fake_site):
    from tests.test_opportunities import script

    def f(title, horizon, **kw):
        g = goal(f"Goal: {title}", "Marketing & demand gen", cycle_hours=24)
        return {"check": "", "team_kind": "marketing", "title": title, "evidence": "Seen.", "points": ["A fact"],
                "impact": "x", "estimate": "", "assumption": "", "confidence": "high", "pull": 4, "metric_name": "",
                "metric_now": "", "metric_goal": "", "source_urls": [], "goal_id": "", "new_goal": g,
                "horizon": horizon, "sessions": kw.get("sessions", 0), "objective": kw.get("objective", ""),
                "keeps_doing": kw.get("keeps_doing", []), "weekly_paid_usd": kw.get("paid", 0)}

    out = {"findings": [
        f("No analytics on the site", "quick", sessions=2, objective="ignored", keeps_doing=["ignored"]),
        f("Competitors get 25x your LinkedIn engagement", "ongoing", objective="10K+ followers across LinkedIn and X",
          keeps_doing=["3 useful posts a week", "Reply to every comment", "Weekly take on industry news"]),
    ]}
    async with client() as c:
        await onboard(c, FakeAnthropic(script, scanner=lambda kw: out))
        opp = (await c.get("/api/org/setup")).json()["org"]["profile"]["opportunities"]
        quick, ongoing = opp["findings"]
        assert quick["horizon"] == "quick" and quick["total_usd"] and quick["weekly_usd"] is None
        assert quick["objective"] == "" and quick["keeps_doing"] == []
        assert ongoing["horizon"] == "ongoing" and ongoing["objective"] == "10K+ followers across LinkedIn and X"
        assert ongoing["keeps_doing"][0] == "3 useful posts a week"
        assert ongoing["weekly_usd"] == 3  # daily work at the typical $0.30 a session
        goals = {g["id"]: g for g in (await c.get("/api/campaigns")).json()}
        assert goals[ongoing["goal_id"]]["weekly_cap"] == 3 and goals[ongoing["goal_id"]]["budget_total"] == 3 * 52
        assert goals[quick["goal_id"]]["weekly_cap"] is None
