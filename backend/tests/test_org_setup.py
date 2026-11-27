"""Setup: onboarding researches the company and finds what it's missing out on (goals come from the
findings); "Suggest more goals" plans goals per function from that research; functions can be added."""

import httpx
import pytest
from sqlalchemy import func, select

from app.agent import org_setup
from app.agent.llm import MeteredClaude
from app.agent.org_setup import run_org_setup, tidy_plan
from app.config import get_settings
from app.db import session_scope
from app.main import app
from app.models import LedgerEntry, OrgSetup
from app.services import website
from app.services.website import Page, SiteReading
from app.worker import claim_setup
from tests.fakes import FakeAnthropic, text
from tests.helpers import org_of, sign_in


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def goal(name: str, category: str = "Sales", **kw) -> dict:
    return {"name": name, "goal_description": f"{name}: details", "done_when": "Meeting held", "primary_metric": "meetings",
            "target_value": 10, "category": category, "use_case": "Cold outbound", "cycle_hours": 5,
            "duration_days": 30, "paid_spend_usd": 0, "channels": ["Email", "LinkedIn"],
            "steps": [{"text": "Find ops leaders", "action_type": "research", "tool": "web"},
                      {"text": "Write a first email to each", "action_type": "create_draft", "tool": "gmail"},
                      {"text": "Send each email", "action_type": "send_message", "tool": "gmail"}],
            "why": "You just raised a seed round.", "first_week": "40 leads with a drafted email each",
            "start_here": False, "key_results": ["15 demos held", "300 accounts in the CRM", "Reply rate above 8%",
                                                 "a fourth that gets cut"], **kw}


PLAN = {
    "profile": {"summary": "Acme makes routing software for mid-size logistics companies.",
                "offering": "Route planning SaaS", "customers": "Logistics companies, 50-500 people",
                "business_model": "Subscription", "stage": "Seed", "funding": "$3M seed (2026)", "team": "8 people",
                "traction": "12 paying customers", "current_focus": ["Pipeline for new AEs", "Design partners in the EU"],
                "challenges": ["Long sales cycles"]},
    "departments": [
        {"kind": "sales", "name": "Sales", "agent_title": "Outbound pipeline", "why": "Hiring AEs.",
         "objective": "Fill the pipeline for the new AEs",
         "goals": [goal("Book 15 demos with Heads of Ops"), goal("Build a list of 300 logistics companies"),
                   goal("Re-engage 40 stalled deals"), goal("A fourth goal that should be cut"),
                   goal("A fifth goal that should be cut")]},
        {"kind": "marketing", "name": "Marketing", "agent_title": "Content and community", "why": "No content yet.",
         "goals": [goal("Get 200 newsletter signups", "Marketing & demand gen", target_value=None)]},
        {"kind": "custom", "name": "Sales", "agent_title": "duplicate name", "why": "", "goals": [goal("Dup dept goal")]},
        {"kind": "finance", "name": "Finance", "agent_title": "", "why": "", "goals": []},  # no goals: skipped
    ],
}


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")


@pytest.fixture
def fake_site(monkeypatch):
    async def read(url):
        return SiteReading(url="https://acme.test/", pages=[
            Page(url="https://acme.test/", title="Acme", description="Routing for logistics", text="Plan routes in minutes."),
            Page(url="https://acme.test/careers", title="Careers", description="", text="We're hiring two AEs."),
        ])
    monkeypatch.setattr(org_setup, "read_site", read)


def research_script(kw):
    return [text("Identity: Acme (acme.test).\nStage and funding: $3M seed.\nSources: https://news.test/acme"),
            {"type": "web_search_tool_result", "tool_use_id": "srv_1",
             "content": [{"type": "web_search_result", "url": "https://news.test/acme", "title": "Acme raises seed"}]}]


async def suggest_goals(c, fake) -> dict:
    """The Team page's "Suggest more goals": plans goals per function from what setup learned."""
    r = await c.post("/api/org/setup", json={"mode": "goals"})
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "goals"
    await run_org_setup(r.json()["id"], MeteredClaude(client=fake))
    return (await c.get("/api/org/setup")).json()


async def onboard(c, fake=None, **body) -> str:
    setup_id = await start_setup(c, **body)
    await run_org_setup(setup_id, MeteredClaude(client=fake or FakeAnthropic(research_script, org_planner=lambda kw: PLAN)))
    return setup_id


async def start_setup(c, **body) -> str:
    await sign_in(c, "founder@acme.test")
    r = await c.post("/api/org", json={"name": "Acme", "website": "acme.test",
                                       "description": "Routing software for logistics teams", **body})
    assert r.status_code == 200, r.text
    return r.json()["setup_id"]


async def test_onboarding_researches_then_finds_gaps_without_planning_functions(with_key, fake_site):
    async with client() as c:
        setup_id = await start_setup(c)
        assert setup_id
        org = await org_of(c)
        assert org["departments"] == []
        assert org["org"]["website"] == "https://acme.test"

        fake = FakeAnthropic(research_script, org_planner=lambda kw: PLAN, searches=4)
        await run_org_setup(setup_id, MeteredClaude(client=fake))

        st = (await c.get("/api/org/setup")).json()
        assert st["setup"]["status"] == "done", st["setup"]["error"]
        assert st["setup"]["mode"] == "start" and st["task"] is None
        assert [x["key"] for x in st["setup"]["steps"]] == ["website", "research", "profile", "scan"]
        assert [x["status"] for x in st["setup"]["steps"]] == ["done"] * 4
        assert "2 pages" in st["setup"]["steps"][0]["detail"]
        assert "4 web searches" in st["setup"]["steps"][1]["detail"]
        assert st["setup"]["cost_usd"] > 0
        profile = st["org"]["profile"]
        assert profile["stage"] == "Seed" and profile["summary"].startswith("Acme makes routing software")
        assert profile["sources"] == [{"url": "https://news.test/acme", "title": "Acme raises seed"}]
        assert "opportunities" in profile
        # No functions or goals planned up front: goals come from what the check finds.
        assert (await org_of(c))["departments"] == []
        assert (await c.get("/api/campaigns")).json() == []
        assert not any("departments" in (k.get("output_config") or {}).get("format", {}).get("schema", {}).get("properties", {})
                       for k in fake.calls)

    # The research was paid by the organization, not charged to any goal budget.
    async with session_scope() as s:
        assert (await s.execute(select(func.count()).select_from(LedgerEntry))).scalar_one() == 0
    # The research used the web search tool.
    research_call = fake.calls[0]
    assert research_call["tools"][0]["type"] == "web_search_20260209"
    assert "acme.test" in research_call["messages"][0]["content"]
    # Then the scan starts by picking which checks to run for this company.
    pick_call = next(c for c in fake.calls if "checks" in (c.get("output_config") or {}).get("format", {}).get("schema", {}).get("properties", {}))
    assert "Identity: Acme" in pick_call["messages"][0]["content"]


async def test_suggest_more_goals_plans_goals_per_function_from_the_research(with_key, fake_site):
    async with client() as c:
        await onboard(c)
        fake = FakeAnthropic(research_script, org_planner=lambda kw: PLAN, searches=3)
        st = await suggest_goals(c, fake)
        assert st["task"]["status"] == "done", st["task"]["error"]
        assert st["setup"]["mode"] == "start"  # the onboarding research is still "the setup"
        assert [x["key"] for x in st["task"]["steps"]] == ["plan", "create"]
        assert st["task"]["steps"][0]["detail"] == "2 functions, 4 goals"
        assert fake.agent_calls() == []  # no new web research
        plan_call = next(k for k in fake.calls if "departments" in (k.get("output_config") or {}).get("format", {}).get("schema", {}).get("properties", {}))
        msg = plan_call["messages"][0]["content"]
        assert "Stage and funding: $3M seed" in msg  # the onboarding research, reused
        assert "Suggest the goals worth setting up now" in msg
        picks = [g["name"] for d in st["task"]["plan"]["departments"] for g in d["goals"] if g["start_here"]]
        assert picks == ["Book 15 demos with Heads of Ops", "Get 200 newsletter signups"]  # top goal of top functions
        assert st["org"]["profile"]["stage"] == "Seed"  # the profile stays

        org = await org_of(c)
        names = [d["name"] for d in org["departments"]]
        assert names == ["Sales", "Marketing"]  # duplicate and empty functions dropped
        sales = org["departments"][0]
        assert sales["agents"][0]["title"] == "Outbound pipeline"
        assert [p["email"] for p in sales["people"]] == ["founder@acme.test"]

        goals = (await c.get("/api/campaigns")).json()
        assert len(goals) == 4  # at most three per function
        assert {g["status"] for g in goals} == {"draft"}  # nothing runs until someone starts it
        assert {g["origin"] for g in goals} == {"setup"}
        first = next(g for g in goals if g["name"] == "Book 15 demos with Heads of Ops")
        assert first["suggested_reason"] == "You just raised a seed round."
        assert first["cycle_hours"] == 6  # snapped to a schedule people can pick
        assert first["agent"]["id"] == sales["agents"][0]["id"]
        full = (await c.get(f"/api/campaigns/{first['id']}")).json()
        # Suggested goals start with a one-week budget: every 6h for 7 days = 28 sessions x $0.30 = $8.40 (no rounding),
        # and keep the estimate for the whole goal (120 sessions = $36) for when people continue.
        assert first["budget"]["total"] == 8.4
        basis = full["budget_basis"]
        assert (basis["sessions"], basis["starter"], basis["full_usd"], basis["basis"]) == (28, True, 36.0, "typical")
        assert first["first_deliverable"] == "40 leads with a drafted email each"
        assert first["key_results"] == ["15 demos held", "300 accounts in the CRM", "Reply rate above 8%"]
        basis = (await c.patch(f"/api/campaigns/{first['id']}", json={"cycle_hours": 12})).json()["budget_basis"]
        assert (basis["sessions"], basis["suggested_usd"], basis["full_usd"]) == (14, 4.2, 18.0)
        assert [st["action_type"] for st in full["playbook"]["steps"]] == ["research", "create_draft", "send_message"]
        assert "Routing software for logistics teams" in full["context"]
        assert "Seed" in full["context"]

        # Asking again suggests only what's missing: the plan is told what exists, and names don't repeat.
        fake2 = FakeAnthropic(research_script, org_planner=lambda kw: PLAN)
        await suggest_goals(c, fake2)
        msg2 = next(k for k in fake2.calls if "departments" in (k.get("output_config") or {}).get("format", {}).get("schema", {}).get("properties", {}))["messages"][0]["content"]
        assert "Book 15 demos with Heads of Ops" in msg2 and "Sales, Marketing" in msg2
        assert len((await org_of(c))["departments"]) == 2
        assert len((await c.get("/api/campaigns")).json()) == 4


async def test_research_pauses_are_resumed(with_key, fake_site):
    calls = {"n": 0}

    def paused_once(kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return [text("Searching..."), {"type": "server_tool_use", "id": "srv_9", "name": "web_search", "input": {"query": "acme"}}]
        return research_script(kw)

    async with client() as c:
        setup_id = await start_setup(c)
        fake = FakeAnthropic(paused_once, org_planner=lambda kw: PLAN)
        await run_org_setup(setup_id, MeteredClaude(client=fake))
        assert (await c.get("/api/org/setup")).json()["setup"]["status"] == "done"
    second = fake.calls[1]["messages"]
    assert second[-1]["role"] == "assistant"  # the paused turn is sent back as-is, no extra prompt
    assert second[-1]["content"][-1]["type"] == "server_tool_use"


async def test_failed_research_still_profiles_from_site_and_description(with_key, fake_site):
    def broken(kw):
        raise RuntimeError("search is down")

    async with client() as c:
        setup_id = await start_setup(c)
        await run_org_setup(setup_id, MeteredClaude(client=FakeAnthropic(broken, org_planner=lambda kw: PLAN)))
        st = (await c.get("/api/org/setup")).json()["setup"]
        assert st["status"] == "done"
        assert [x["status"] for x in st["steps"]] == ["done", "failed", "done", "done"]


async def test_failed_setup_offers_retry_and_basic_team(with_key, fake_site):
    def bad_profile(kw):
        raise RuntimeError("model unavailable")

    async with client() as c:
        setup_id = await start_setup(c)
        await run_org_setup(setup_id, MeteredClaude(client=FakeAnthropic(research_script, profile=bad_profile)))
        st = (await c.get("/api/org/setup")).json()
        assert st["setup"]["status"] == "failed"
        assert "model unavailable" in st["setup"]["error"]
        assert st["setup"]["steps"][2]["status"] == "failed"
        assert st["has_team"] is False

        # Try again (with a better description)...
        r = await c.post("/api/org/setup", json={"description": "Route planning SaaS for EU logistics companies"})
        assert r.status_code == 200
        assert (await c.post("/api/org/setup", json={})).status_code == 409  # one at a time
        assert (await org_of(c))["org"]["description"].startswith("Route planning")
        # ...or start with a basic set of goals instead.
        assert (await c.post("/api/org/setup/basic")).status_code == 200
        names = [d["name"] for d in (await org_of(c))["departments"]]
        assert names == ["Sales", "Marketing", "Customer Research", "Customer Support"]


async def test_failed_goal_suggestions_say_why(with_key, fake_site):
    def bad_plan(kw):
        raise RuntimeError("model unavailable")

    async with client() as c:
        await onboard(c)
        st = await suggest_goals(c, FakeAnthropic(research_script, org_planner=bad_plan))
        assert st["task"]["status"] == "failed" and "model unavailable" in st["task"]["error"]
        assert st["setup"]["status"] == "done"  # the onboarding results are untouched


async def test_without_a_claude_key_starts_with_a_basic_team(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    async with client() as c:
        await sign_in(c, "solo@acme.test")
        r = (await c.post("/api/org", json={"name": "Acme", "description": "B2B SaaS platform for logistics teams. Book a demo."})).json()
        # Without Claude nothing decides the type of company: the general starter team, until it's researched.
        assert r["setup_id"] is None and r["setup_skipped"] == "no_api_key" and r["company_type"] == "general"
        org = await org_of(c)
        assert [d["name"] for d in org["departments"]] == ["Sales", "Marketing", "Customer Research", "Customer Support"]
        assert org["departments"][0]["agents"][0]["name"] == "Outbound Agent"
        assert org["org"]["profile"]["pack_label"] == "Business"
        goals = (await c.get("/api/campaigns")).json()
        assert len(goals) == 4 and {g["status"] for g in goals} == {"draft"}
        book = next(g for g in goals if g["name"] == "Book meetings with ideal customers")
        assert book["target"]["target"] == 4 and book["target"]["period"] == "week" and book["budget"]["total"] > 0
        assert (await c.post("/api/org/setup", json={})).status_code == 400


async def test_needs_a_website_or_description(with_key):
    async with client() as c:
        await sign_in(c, "a@acme.test")
        assert (await c.post("/api/org", json={"name": "Acme"})).status_code == 400
        assert (await c.post("/api/org", json={"name": "Acme", "website": "not a website"})).status_code == 400


async def test_worker_claims_each_setup_once(with_key):
    async with client() as c:
        setup_id = await start_setup(c)
    assert await claim_setup("w1") == setup_id
    assert await claim_setup("w2") is None
    async with session_scope() as s:
        setup = await s.get(OrgSetup, setup_id)
        assert setup.status == "running" and setup.attempts == 1


async def test_website_reader_refuses_private_addresses():
    for url in ["http://127.0.0.1:8000/admin", "http://localhost/", "http://169.254.169.254/latest/meta-data",
                "http://10.0.0.5/", "http://printer.local/", "ftp://example.com"]:
        reading = await website.read_site(url)
        assert reading.pages == [] and reading.error, url


def test_website_text_extraction_and_page_picking():
    html = """<html><head><title>Acme | Routing</title><meta name="description" content="Routes fast">
    <style>.x{}</style><script>track()</script></head><body><nav><a href="/about">About us</a>
    <a href="/pricing">Pricing</a><a href="https://other.test/about">Elsewhere</a><a href="/careers">Jobs</a>
    <a href="/logo.png">Logo</a></nav><h1>Plan routes in minutes</h1><p>Used by 40 fleets.</p></body></html>"""
    page, links = website._parse("https://acme.test/", html)
    assert page.title == "Acme | Routing" and page.description == "Routes fast"
    assert "Plan routes in minutes" in page.text and "track()" not in page.text
    picked = website._pick_pages("https://acme.test/", links)
    assert picked == ["https://acme.test/about", "https://acme.test/pricing", "https://acme.test/careers"]


def test_tidy_plan_limits():
    many = {"profile": {}, "departments": [
        {"kind": "sales", "name": f"Team {i}", "agent_title": "", "why": "",
         "goals": [goal(f"G{i}-{j}", duration_days=900, paid_spend_usd=-5, cycle_hours=0.1, target_value=-3)
                   for j in range(3)]}
        for i in range(9)]}
    out = tidy_plan(many)
    assert len(out["departments"]) == 4  # 12 goals in total, three per function
    g = out["departments"][0]["goals"][0]
    assert g["duration_days"] == 90 and g["paid_spend_usd"] == 0
    assert g["cycle_hours"] == 1 and g["target_value"] is None


def test_planner_picks_at_most_three_goals_to_start_with():
    plan = {"profile": {}, "departments": [
        {"kind": "sales", "name": f"Team {i}", "agent_title": "", "why": "",
         "goals": [goal(f"G{i}-{j}", start_here=True) for j in range(2)]} for i in range(3)]}
    picks = [g["name"] for d in tidy_plan(plan)["departments"] for g in d["goals"] if g["start_here"]]
    assert picks == ["G0-0", "G0-1", "G1-0"]


async def test_switching_older_suggestions_to_starter_budgets(with_key, fake_site):
    async with client() as c:
        await onboard(c)
        await suggest_goals(c, FakeAnthropic(research_script, org_planner=lambda kw: PLAN))
        from app.models import Campaign
        async with session_scope() as s:  # make them look like suggestions from before starter budgets
            for g in (await s.execute(select(Campaign))).scalars():
                g.budget_total = 40
                g.budget_basis = {"days": 30, "sessions": 120}
        r = (await c.post("/api/org/setup/starter-budgets")).json()
        assert r["changed"] == 4 and r["before_usd"] == 160 and r["after_usd"] == 33.6
        assert {g["budget"]["total"] for g in (await c.get("/api/campaigns")).json()} == {8.4}
        assert (await c.post("/api/org/setup/starter-budgets")).json()["changed"] == 0


def test_team_size_follows_the_company():
    def plan(size):
        return {"profile": {"size": size}, "later": [], "departments": [
            {"kind": "custom", "name": f"Team {i}", "agent_title": "", "why": "", "goals": [goal(f"G{i}")]}
            for i in range(12)]}
    assert len(tidy_plan(plan("tiny"))["departments"]) == 4
    assert len(tidy_plan(plan("mid"))["departments"]) == 8
    assert len(tidy_plan(plan("large"))["departments"]) == 10
    assert tidy_plan(plan("enormous"))["profile"]["size"] == "small"  # unknown sizes fall back


def test_later_functions_are_tidied():
    plan = {"profile": {"size": "tiny"}, "departments": PLAN["departments"][:1], "later": [
        {"kind": "sales", "name": "Sales", "when": "already in the team"},
        {"kind": "finance", "name": "Finance", "when": "once you have recurring revenue"},
        {"kind": "finance", "name": "Finance", "when": "duplicate"},
        {"kind": "legal", "name": "", "when": "when enterprise deals start"},
        {"kind": "it", "name": "IT & Security", "when": "x"}, {"kind": "hiring", "name": "People", "when": "y"},
        {"kind": "custom", "name": "Facilities", "when": "z"}]}
    later = tidy_plan(plan)["later"]
    assert [x["name"] for x in later] == ["Finance", "Legal & Compliance", "IT & Security", "People"]


async def test_adding_a_function_later_reuses_research(with_key, fake_site):
    first = {**PLAN, "profile": {**PLAN["profile"], "size": "tiny", "size_reason": "8 people, $3M seed"},
             "later": [{"kind": "finance", "name": "Finance", "when": "once you have recurring revenue"},
                       {"kind": "legal", "name": "Legal & Compliance", "when": "when enterprise deals start"}]}
    finance_plan = {"profile": {"size": "tiny"}, "later": [], "departments": [
        PLAN["departments"][0],  # not asked for: dropped
        {"kind": "finance", "name": "Finance", "agent_title": "Cash and invoices", "why": "12 paying customers.",
         "objective": "Keep cash collected and burn visible",
         "goals": [goal("Chase overdue invoices", "Finance"), goal("Monthly burn and runway report", "Finance")]}]}
    async with client() as c:
        await onboard(c, FakeAnthropic(research_script, org_planner=lambda kw: first))
        await suggest_goals(c, FakeAnthropic(research_script, org_planner=lambda kw: first))
        st = (await c.get("/api/org/setup")).json()
        assert st["org"]["profile"]["size_reason"] == "8 people, $3M seed"
        assert [x["name"] for x in st["org"]["profile"]["later"]] == ["Finance", "Legal & Compliance"]

        assert (await c.post("/api/org/setup", json={"add_functions": []})).status_code == 400
        again = (await c.post("/api/org/setup", json={"add_functions": ["finance"]})).json()["id"]
        fake = FakeAnthropic(research_script, org_planner=lambda kw: finance_plan, searches=3)
        await run_org_setup(again, MeteredClaude(client=fake))
        assert fake.agent_calls() == []  # no new web research
        planner_msg = fake.calls[0]["messages"][0]["content"]
        assert "add these functions now: Finance" in planner_msg and "Sales, Marketing" in planner_msg
        assert "Stage and funding: $3M seed" in planner_msg  # earlier research reused

        st = (await c.get("/api/org/setup")).json()
        assert st["task"]["status"] == "done", st["task"]["error"]
        assert st["task"]["mode"] == "include" and [x["status"] for x in st["task"]["steps"]] == ["done", "done"]
        assert [x["name"] for x in st["org"]["profile"]["later"]] == ["Legal & Compliance"]
        assert st["org"]["profile"]["size_reason"] == "8 people, $3M seed"  # profile kept
        org = await org_of(c)
        assert [d["name"] for d in org["departments"]] == ["Sales", "Marketing", "Finance"]
        assert org["departments"][2]["agents"][0]["objective"] == "Keep cash collected and burn visible"
        goals = (await c.get("/api/campaigns")).json()
        assert len(goals) == 6 and sum(g["name"].startswith("Chase") for g in goals) == 1


async def test_planner_starts_from_the_pack_and_staffs_several_ai_employees(with_key, fake_site):
    plan = {"profile": {**PLAN["profile"], "size": "small", "company_type": "startup"}, "later": [], "departments": [
        {"kind": "marketing", "name": "Marketing", "why": "No pipeline from content yet.", "agents": [
            {"role": "seo", "name": "SEO Agent", "title": "Search for logistics buyers", "objective": "Own 'route planning' searches",
             "goals": [goal("Grow organic search traffic", "Marketing & demand gen")]},
            {"role": "content", "name": "Content Agent", "title": "LinkedIn for dispatchers", "objective": "Be the voice of dispatchers",
             "goals": [goal("Grow LinkedIn following among dispatchers", "Marketing & demand gen")]}]},
        {"kind": "product", "name": "Product", "why": "", "agents": [
            {"role": "pm", "name": "Product Agent", "title": "Metrics and PRDs", "objective": "Know what to build", "goals": [goal("PRDs")]}]},
        {"kind": "engineering", "name": "Engineering", "why": "", "agents": [
            {"role": "engineer", "name": "Engineering Agent", "title": "Fixes", "objective": "Ship", "goals": [goal("Ship fixes")]}]},
    ]}
    async with client() as c:
        await onboard(c, FakeAnthropic(research_script, org_planner=lambda kw: plan),
                      description="Route planning SaaS for logistics teams. Book a demo.")
        fake = FakeAnthropic(research_script, org_planner=lambda kw: plan)
        await suggest_goals(c, fake)
        planner = next(k for k in fake.calls if "departments" in (k.get("output_config") or {}).get("format", {}).get("schema", {}).get("properties", {}))
        msg = planner["messages"][0]["content"]
        assert "Likely type: B2B startup" in msg and "Likely size: small" in msg  # from the onboarding profile
        assert "sdr (Sales)" in planner["messages"][0]["content"]  # the pack's roles by size
        assert "seo: SEO" in planner["system"]  # the role catalog

        org = await org_of(c)
        marketing = next(d for d in org["departments"] if d["name"] == "Marketing")
        assert [(a["name"], a["title"], a["role"]) for a in marketing["agents"]] == [
            ("SEO Agent", "Search for logistics buyers", "seo"), ("Content Agent", "LinkedIn for dispatchers", "content")]
        product = next(d for d in org["departments"] if d["name"] == "Product")["agents"][0]
        engineering = next(d for d in org["departments"] if d["name"] == "Engineering")["agents"][0]
        assert product["handoff_to_agent_id"] == engineering["id"]
        goals = {g["name"]: g for g in (await c.get("/api/campaigns")).json()}
        assert goals["Grow organic search traffic"]["agent"]["name"] == "SEO Agent"
        assert goals["Grow LinkedIn following among dispatchers"]["agent"]["name"] == "Content Agent"
        st = (await c.get("/api/org/setup")).json()
        assert st["org"]["profile"]["company_type"] == "startup" and st["org"]["profile"]["pack_label"] == "B2B startup"
