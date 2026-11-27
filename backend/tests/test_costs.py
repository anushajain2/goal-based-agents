"""Per-task models and AI cost by task."""

from decimal import Decimal

from sqlalchemy import select

from app.agent.llm import TASKS, MeteredClaude, task_model, usage_org
from app.agent.opportunities import social_rows
from app.config import get_settings
from app.db import session_scope
from app.models import ModelUsage, Organization
from tests.fakes import FakeAnthropic, text
from tests.test_agent_flow import _no_real_browser, api, make_campaign  # noqa: F401
from tests.helpers import sign_in_with_org


def test_each_task_has_its_model_and_can_be_changed_on_its_own(monkeypatch):
    s = get_settings()
    assert task_model(s, "findings") == (s.planner_model, s.planner_effort)  # the first thing people see
    assert task_model(s, "quality_check") == (s.worker_model, s.worker_effort)  # writing taste
    assert task_model(s, "session_strategist") == (s.planner_model, s.planner_effort)
    assert task_model(s, "rule_check") == (s.checker_model, s.checker_effort)
    monkeypatch.setattr(s, "task_models", {"session_strategist": "worker", "findings": "claude-some-model"})
    monkeypatch.setattr(s, "task_efforts", {"goal_steps": "low", "findings": "high"})
    assert task_model(s, "session_strategist") == (s.worker_model, s.worker_effort)
    assert task_model(s, "findings") == ("claude-some-model", "high")
    assert task_model(s, "goal_steps") == (s.worker_model, "low")
    assert len(TASKS) == 18


async def test_every_call_is_recorded_with_its_task_model_and_organization(api):
    gid = await make_campaign(api, launch=False)
    fake = FakeAnthropic(lambda kw: [text("ok")])
    claude = MeteredClaude(client=fake)
    await claude.create(campaign_id=gid, run_id=None, purpose="quality check", task="quality_check",
                        messages=[{"role": "user", "content": "x"}], max_tokens=100)
    async with session_scope() as s:
        org = (await s.execute(select(Organization))).scalars().first()
    token = usage_org.set(org.id)
    try:  # a call for the organization, not a goal (setup, the company check)
        await claude.create(campaign_id=None, run_id=None, purpose="setup profile", task="company_profile",
                            messages=[{"role": "user", "content": "x"}], max_tokens=100)
    finally:
        usage_org.reset(token)
    assert fake.calls[0]["model"] == get_settings().worker_model
    async with session_scope() as s:
        rows = (await s.execute(select(ModelUsage).order_by(ModelUsage.created_at))).scalars().all()
    assert [(r.task, r.org_id) for r in rows] == [("quality_check", org.id), ("company_profile", org.id)]
    assert rows[0].input_tokens == 2000 and rows[0].output_tokens == 300 and rows[0].cost_usd > Decimal("0")


async def test_only_operators_see_cost_by_task(api, monkeypatch):
    gid = await make_campaign(api, launch=False)
    await MeteredClaude(client=FakeAnthropic(lambda kw: [text("ok")])).create(
        campaign_id=gid, run_id=None, purpose="work step", task="work", messages=[{"role": "user", "content": "x"}])
    assert (await api.get("/api/ops/costs")).status_code == 403
    me = (await api.get("/api/auth/me")).json()["email"]
    monkeypatch.setattr(get_settings(), "operator_emails", f"someone@else.test, {me.upper()}")
    data = (await api.get("/api/ops/costs?days=7")).json()
    assert data["calls"] == 1 and data["total_usd"] > 0
    top = data["tasks"][0]
    assert top["task"] == "work" and top["calls"] == 1 and top["share"] == 1.0 and top["label"] == "Work session steps"
    assert {t["task"] for t in data["tasks"]} == set(TASKS)  # every task listed, with its model now
    assert data["orgs"][0]["calls"] == 1
    assert (await api.get("/api/org")).json()["me"]["is_operator"] is True


def test_social_numbers_say_how_much_could_be_seen():
    acc = lambda company, posts, eng, coverage: {"company": company, "who": "company", "name": company, "platform": "linkedin",  # noqa: E731
                                                 "url": "", "coverage": coverage, "posts_30d": posts, "engagement_30d": eng, "note": ""}
    rows = social_rows({"accounts": [acc("Acme", 3, 20, "partial"), acc("Routeco", 12, 900, "blocked")]}, "Acme",
                       [{"name": "Routeco", "domain": "routeco.test"}])
    li = next(r for r in rows if r["key"] == "social_linkedin")
    assert li["you"]["display"] == "3 posts · 20 likes and comments (at least: only partly visible)"
    assert li["others"][0]["display"] == "Couldn't read"  # blocked: no numbers, whatever came back
