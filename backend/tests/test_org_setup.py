"""First-run setup: research the company, then set up departments, AI employees and draft goals."""

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
            "why": "You just raised a seed round.", **kw}


PLAN = {
    "profile": {"summary": "Acme makes routing software for mid-size logistics companies.",
                "offering": "Route planning SaaS", "customers": "Logistics companies, 50-500 people",
                "business_model": "Subscription", "stage": "Seed", "funding": "$3M seed (2026)", "team": "8 people",
                "traction": "12 paying customers", "current_focus": ["Pipeline for new AEs", "Design partners in the EU"],
                "challenges": ["Long sales cycles"]},
    "departments": [
        {"kind": "sales", "name": "Sales", "agent_title": "Outbound pipeline", "why": "Hiring AEs.",
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


async def start_setup(c, **body) -> str:
    await sign_in(c, "founder@acme.test")
    r = await c.post("/api/org", json={"name": "Acme", "website": "acme.test",
                                       "description": "Routing software for logistics teams", **body})
    assert r.status_code == 200, r.text
    return r.json()["setup_id"]


async def test_setup_researches_and_builds_a_focused_team(with_key, fake_site):
    async with client() as c:
        setup_id = await start_setup(c)
        assert setup_id
        org = await org_of(c)
        assert org["departments"] == []  # setup creates them
        assert org["org"]["website"] == "https://acme.test"

        fake = FakeAnthropic(research_script, org_planner=lambda kw: PLAN, searches=4)
        await run_org_setup(setup_id, MeteredClaude(client=fake))

        st = (await c.get("/api/org/setup")).json()
        assert st["setup"]["status"] == "done", st["setup"]["error"]
        assert [x["status"] for x in st["setup"]["steps"]] == ["done"] * 4
        assert "2 pages" in st["setup"]["steps"][0]["detail"]
        assert "4 web searches" in st["setup"]["steps"][1]["detail"]
        assert st["setup"]["cost_usd"] > 0
        profile = st["org"]["profile"]
        assert profile["stage"] == "Seed"
        assert profile["sources"] == [{"url": "https://news.test/acme", "title": "Acme raises seed"}]

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
        # The budget is worked out, not guessed: every 6h for 30 days = 120 sessions x $0.30 = $36 -> $40.
        assert first["budget"]["total"] == 40
        assert full["budget_basis"]["sessions"] == 120 and full["budget_basis"]["basis"] == "typical"
        assert [st["action_type"] for st in full["playbook"]["steps"]] == ["research", "create_draft", "send_message"]
        assert "Routing software for logistics teams" in full["context"]
        assert "Seed" in full["context"]

    # The research was paid by the organization, not charged to any goal budget.
    async with session_scope() as s:
        assert (await s.execute(select(func.count()).select_from(LedgerEntry))).scalar_one() == 0
    # The research used the web search tool, and the plan used structured output.
    research_call = fake.calls[0]
    assert research_call["tools"][0]["type"] == "web_search_20260209"
    assert "acme.test" in research_call["messages"][0]["content"]
    assert "Research brief" in fake.calls[-1]["messages"][0]["content"]


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


async def test_failed_research_still_plans_from_site_and_description(with_key, fake_site):
    def broken(kw):
        raise RuntimeError("search is down")

    async with client() as c:
        setup_id = await start_setup(c)
        await run_org_setup(setup_id, MeteredClaude(client=FakeAnthropic(broken, org_planner=lambda kw: PLAN)))
        st = (await c.get("/api/org/setup")).json()["setup"]
        assert st["status"] == "done"
        assert [x["status"] for x in st["steps"]] == ["done", "failed", "done", "done"]


async def test_failed_plan_offers_retry_and_basic_team(with_key, fake_site):
    def bad_plan(kw):
        raise RuntimeError("model unavailable")

    async with client() as c:
        setup_id = await start_setup(c)
        await run_org_setup(setup_id, MeteredClaude(client=FakeAnthropic(research_script, org_planner=bad_plan)))
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
        # ...or start with a basic team instead.
        assert (await c.post("/api/org/setup/basic")).status_code == 200
        assert [d["name"] for d in (await org_of(c))["departments"]] == ["Sales", "Marketing", "Customer Research"]


async def test_rerun_adds_only_whats_missing(with_key, fake_site):
    async with client() as c:
        setup_id = await start_setup(c)
        await run_org_setup(setup_id, MeteredClaude(client=FakeAnthropic(research_script, org_planner=lambda kw: PLAN)))
        again = (await c.post("/api/org/setup", json={})).json()["id"]
        await run_org_setup(again, MeteredClaude(client=FakeAnthropic(research_script, org_planner=lambda kw: PLAN)))
        assert len((await org_of(c))["departments"]) == 2
        assert len((await c.get("/api/campaigns")).json()) == 4


async def test_without_a_claude_key_starts_with_a_basic_team(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    async with client() as c:
        await sign_in(c, "solo@acme.test")
        r = (await c.post("/api/org", json={"name": "Acme", "description": "We make routing software"})).json()
        assert r["setup_id"] is None and r["setup_skipped"] == "no_api_key"
        assert len((await org_of(c))["departments"]) == 3
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
