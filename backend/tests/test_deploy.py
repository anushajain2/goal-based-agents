"""Hosted (Render) behaviour: database URLs from the host, production start-up checks, no Agent
Chrome in the cloud, and a worker that hands its work back when a deploy stops it."""

import pytest
from sqlalchemy import select

from app.agent.tools import all_tools
from app.config import Settings, get_settings, normalize_database_url
from app.db import session_scope
from app.models import AgentRun, RunStatus
from app.worker import release_claims
from tests.test_agent_flow import api, make_campaign  # noqa: F401


def test_host_database_urls_become_asyncpg_urls():
    assert normalize_database_url("postgres://u:p@db:5432/app") == "postgresql+asyncpg://u:p@db:5432/app"
    assert normalize_database_url("postgresql://u:p@db/app?sslmode=require") == "postgresql+asyncpg://u:p@db/app"
    assert (normalize_database_url("postgres://u:p@db/app?sslmode=require&application_name=x")
            == "postgresql+asyncpg://u:p@db/app?application_name=x")
    assert normalize_database_url("sqlite+aiosqlite:///x.db") == "sqlite+aiosqlite:///x.db"
    assert Settings(database_url="postgres://u:p@h/d").database_url == "postgresql+asyncpg://u:p@h/d"


def test_production_refuses_to_start_without_its_essentials():
    bad = Settings(environment="production", secret_key=None, database_url="sqlite+aiosqlite:///x.db",
                   frontend_origin="http://localhost:3000")
    problems = " ".join(bad.check_production())
    assert "SECRET_KEY" in problems and "Postgres" in problems and "https://" in problems
    good = Settings(environment="production", secret_key="k" * 40, database_url="postgres://u:p@h/d",
                    frontend_origin="https://app.example.com", allow_private_mcp=False)
    assert good.check_production() == []
    assert Settings(environment="development").check_production() == []


def test_agent_chrome_is_off_in_production_unless_turned_on():
    assert Settings(environment="development").agent_chrome_enabled
    assert not Settings(environment="production").agent_chrome_enabled
    assert Settings(environment="production", agent_chrome=True).agent_chrome_enabled
    names = lambda tools: {t["name"] for t in tools}  # noqa: E731
    assert any(n.startswith("browser_") for n in names(all_tools(True)))
    assert not any(n.startswith("browser_") for n in names(all_tools(True, browser=False)))
    assert "finish_cycle" in names(all_tools(True, browser=False))


@pytest.fixture
def no_chrome(monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_chrome", False)
    yield


async def test_hosted_copy_says_websites_need_the_desktop_helper(api, no_chrome):  # noqa: F811
    status = (await api.get("/api/status")).json()
    assert status["agent_chrome"] is False and status["chrome_path"] is None
    r = await api.post("/api/browser/open", json={"url": "x.com/login"})
    assert r.status_code == 409 and "desktop helper" in r.json()["detail"]


async def test_a_stopping_worker_hands_its_runs_back(api):  # noqa: F811
    gid = await make_campaign(api)
    async with session_scope() as s:
        run = AgentRun(campaign_id=gid, cycle_number=1, status=RunStatus.running.value, locked_by="w1")
        other = AgentRun(campaign_id=gid, cycle_number=2, status=RunStatus.running.value, locked_by="w2")
        s.add_all([run, other])
    await release_claims("w1")
    async with session_scope() as s:
        rows = {r.locked_by or "released": r.status for r in (await s.execute(
            select(AgentRun).where(AgentRun.campaign_id == gid, AgentRun.cycle_number > 0))).scalars()}
    assert rows == {"released": "queued", "w2": "running"}
