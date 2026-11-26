"""Product and engineering AI employees: hand-ins, reviews and hand-offs, GitHub, and read-only SQL."""

import json
import os

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.agent.executor import Pending, ToolExecutor
from app.agent.llm import MeteredClaude
from app.connectors import github as github_mod
from app.connectors.database import QueryError, check_sql, run_read_only
from app.db import session_scope
from app.main import app
from app.models import AgentRun, Campaign, Deliverable, RequestStatus, UserRequest
from tests.fakes import FakeAnthropic
from tests.helpers import agent_in, org_of, sign_in, sign_in_with_org


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def setup_org(c) -> dict:
    await sign_in_with_org(c, "founder@acme.test", departments=("product", "engineering", "sales"))
    return await org_of(c)


async def goal_for(c, agent_id: str, name: str = "3 prioritised PRDs") -> str:
    r = await c.post("/api/campaigns", json={"name": name, "goal_description": name, "primary_metric": "PRDs",
                                             "budget_total": 10, "agent_id": agent_id, "launch": True})
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def executor_for(goal_id: str, org_id: str) -> ToolExecutor:
    async with session_scope() as s:
        run = AgentRun(campaign_id=goal_id, cycle_number=1, status="running")
        s.add(run)
        await s.flush()
        run_id = run.id
    return ToolExecutor(MeteredClaude(client=FakeAnthropic(lambda kw: [])), goal_id, run_id, org_id)


PRD = {"kind": "prd", "title": "CSV export for routes", "summary": "Dispatchers ask for it weekly.",
       "content": "# CSV export\n\n## Problem\nDispatchers copy routes by hand.\n\n## Solution\nAn Export button."}


# --- hand-ins, reviews and hand-offs --------------------------------------------------------------

async def test_prd_review_then_hand_off_to_engineering():
    async with client() as c:
        org = await setup_org(c)
        product, engineering = agent_in(org, "Product"), agent_in(org, "Engineering")
        assert (await c.patch(f"/api/agents/{product}", json={"handoff_to_agent_id": product})).status_code == 400
        r = await c.patch(f"/api/agents/{product}", json={"handoff_to_agent_id": engineering, "handoff_review": True})
        assert r.status_code == 200
        info = (await c.get(f"/api/agents/{product}")).json()
        assert info["handoff_to_agent_id"] == engineering and info["handoff_review"] is True

        goal = await goal_for(c, product)
        ex = await executor_for(goal, org["org"]["id"])
        out = await ex.call("submit_work", PRD, "t1")
        assert not isinstance(out, Pending) and "once approved it goes to Engineering Agent" in out.content

        req = (await c.get("/api/requests")).json()[0]
        assert req["kind"] == "review" and req["preview"]["handoff_to"] == "Engineering Agent"
        assert req["run_id"] is None  # reviews don't hold up the Product Agent's work
        assert req["preview"]["fields"]["content"].startswith("# CSV export")

        # Approve with an edit: the edited PRD is what Engineering gets, as a started goal.
        edited = PRD["content"] + "\n\n## Out of scope\nExcel."
        r = await c.post(f"/api/requests/{req['id']}/decide",
                         json={"decision": "approve", "edited_fields": {"content": edited}})
        assert r.status_code == 200
        goals = (await c.get("/api/campaigns")).json()
        build = next(g for g in goals if g["name"] == "Build: CSV export for routes")
        assert build["agent"]["id"] == engineering and build["status"] == "active"
        assert build["budget"]["total"] == 10 and build["origin"] == "handoff"
        full = (await c.get(f"/api/campaigns/{build['id']}")).json()
        assert "Out of scope" in full["context"]
        assert [st["action_type"] for st in full["playbook"]["steps"]] == ["read_data", "propose_code", "merge_code"]
        docs = (await c.get(f"/api/deliverables?agent_id={product}")).json()
        assert docs[0]["status"] == "handed_off" and docs[0]["handed_to_campaign_id"] == build["id"]
        log = (await c.get(f"/api/campaigns/{goal}/activity")).json()
        assert any("and handed on as a new goal: Build: CSV export for routes" in a["title"] for a in log)


async def test_direct_hand_off_and_changes_requested():
    async with client() as c:
        org = await setup_org(c)
        product, engineering = agent_in(org, "Product"), agent_in(org, "Engineering")
        await c.patch(f"/api/agents/{product}", json={"handoff_to_agent_id": engineering, "handoff_review": False})
        goal = await goal_for(c, product)
        ex = await executor_for(goal, org["org"]["id"])
        out = await ex.call("submit_work", PRD, "t1")
        assert "Engineering Agent got it" in out.content
        assert (await c.get("/api/requests")).json() == []
        assert any(g["name"].startswith("Build: ") for g in (await c.get("/api/campaigns")).json())

        # Analyses always go to people, never straight to another AI employee.
        await ex.call("submit_work", {**PRD, "kind": "analysis", "title": "Why activation dropped"}, "t2")
        req = (await c.get("/api/requests")).json()[0]
        assert req["preview"]["handoff_to"] is None
        await c.post(f"/api/requests/{req['id']}/decide", json={"decision": "reject", "note": "Split by plan"})
        docs = (await c.get(f"/api/deliverables?campaign_id={goal}")).json()
        assert {d["title"]: d["status"] for d in docs}["Why activation dropped"] == "changes_requested"


# --- GitHub ---------------------------------------------------------------------------------------

def fake_github(calls: list) -> FastAPI:
    gh = FastAPI()
    files = {"README.md": "# Acme", "src/export.py": "def export():\n    pass\n"}
    state = {"merged": False}

    @gh.api_route("/{path:path}", methods=["GET", "POST", "PUT"])
    async def any_route(path: str, request: Request):
        body = await request.body()
        calls.append((request.method, "/" + path, json.loads(body) if body else None))
        if request.headers.get("authorization") != "Bearer ghp_good_token":
            return JSONResponse({"message": "Bad credentials"}, status_code=401)
        if path == "repos/acme/app":
            return {"full_name": "acme/app", "default_branch": "main", "private": True, "permissions": {"push": True}}
        if path.startswith("repos/acme/app/contents/"):
            name = path.split("contents/", 1)[1]
            if request.method == "PUT":
                return {"content": {"path": name}}
            if name in files:
                import base64
                return {"content": base64.b64encode(files[name].encode()).decode(), "sha": "abc"}
            return JSONResponse({"message": "Not Found"}, status_code=404)
        if path == "repos/acme/app/git/ref/heads/main":
            return {"object": {"sha": "base123"}}
        if path == "repos/acme/app/git/refs":
            return {"ref": "refs/heads/x"}
        if path == "repos/acme/app/pulls" and request.method == "POST":
            return {"number": 7, "html_url": "https://github.com/acme/app/pull/7"}
        if path == "repos/acme/app/pulls/7" and request.method == "GET":
            return {"number": 7, "title": "CSV export", "html_url": "https://github.com/acme/app/pull/7", "state": "open",
                    "merged": state["merged"], "additions": 40, "deletions": 2, "changed_files": 2, "head": {"ref": "oton/csv"}}
        if path == "repos/acme/app/pulls/7/merge":
            state["merged"] = True
            return {"merged": True, "sha": "merged1", "message": "Pull Request successfully merged"}
        if path == "repos/acme/app/issues":
            return [{"number": 3, "title": "Export is slow", "labels": [{"name": "bug"}], "body": "..", "html_url": "u"}]
        return JSONResponse({"message": "Not Found"}, status_code=404)

    return gh


@pytest.fixture
def gh_calls(monkeypatch):
    calls: list = []
    monkeypatch.setattr(github_mod, "TRANSPORT", httpx.ASGITransport(app=fake_github(calls)))
    return calls


async def test_engineering_opens_prs_on_its_own_but_merging_waits_for_an_engineer(gh_calls):
    async with client() as c:
        org = await setup_org(c)
        assert (await c.post("/api/integrations/github", json={"repo": "acme/app", "token": "ghp_bad_token_x"})).status_code == 400
        r = await c.post("/api/integrations/github", json={"repo": "acme/app", "token": "ghp_good_token"})
        assert r.status_code == 200 and r.json()["config"] == {"repo": "acme/app", "default_branch": "main"}
        listed = (await c.get("/api/integrations")).json()
        assert listed[0]["name"] == "acme/app" and "token" not in json.dumps(listed)

        goal = await goal_for(c, agent_in(org, "Engineering"), "Ship 3 small fixes")
        ex = await executor_for(goal, org["org"]["id"])
        assert "def export" in (await ex.call("github_read_file", {"path": "src/export.py"}, "t0")).content
        assert "Export is slow" in (await ex.call("github_list_issues", {}, "t1")).content

        out = await ex.call("github_open_pull_request", {
            "title": "CSV export", "body": "Adds CSV export (PRD: CSV export for routes).", "branch": "csv export",
            "files": [{"path": "src/export.py", "content": "def export():\n    return 'csv'\n"},
                      {"path": "src/new.py", "content": "x = 1\n"}]}, "t2")
        assert not isinstance(out, Pending), "proposing code is on its own by default"
        assert '"number": 7' in out.content
        puts = [p for m, p, _ in gh_calls if m == "PUT" and "/contents/" in p]
        assert puts == ["/repos/acme/app/contents/src/export.py", "/repos/acme/app/contents/src/new.py"]
        ref = next(b for m, p, b in gh_calls if p.endswith("/git/refs"))
        assert ref["ref"] == "refs/heads/oton/csv-export"
        assert not any(p.endswith("/merge") for _, p, _ in gh_calls)

        out = await ex.call("github_merge_pull_request", {"number": 7, "summary": "Tested locally"}, "t3")
        assert isinstance(out, Pending), "merging always asks"
        assert not any(p.endswith("/merge") for _, p, _ in gh_calls)
        async with session_scope() as s:
            req = await s.get(UserRequest, out.request_id)
            assert req.action_type == "merge_code" and "github.com/acme/app/pull/7" in req.preview["details"]
            req.status = RequestStatus.approved.value
        result = await ex.resume(out.stored, req)
        assert '"merged": true' in result.content
        assert any(p.endswith("/pulls/7/merge") for _, p, _ in gh_calls)

        # Readiness shows GitHub as connected for a goal whose plan uses it.
        async with session_scope() as s:
            (await s.get(Campaign, goal)).playbook = {"steps": [{"text": "Read code", "action_type": "read_data", "tool": "github"}]}
        tools = (await c.get(f"/api/campaigns/{goal}/readiness")).json()["tools"]
        assert tools == [{**tools[0], "key": "github", "status": "connected", "kind": "github"}]


async def test_sessions_get_code_tools_only_when_github_is_connected(gh_calls, monkeypatch):
    from app.agent.runner import CycleRunner
    from app.config import get_settings
    from tests.fakes import tool_use
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")

    async with client() as c:
        org = await setup_org(c)
        goal = await goal_for(c, agent_in(org, "Engineering"), "Ship fixes")
        async def one_session() -> list[str]:
            async with session_scope() as s:
                run = AgentRun(campaign_id=goal, cycle_number=1, status="running")
                s.add(run)
                await s.flush()
                run_id = run.id
            fake = FakeAnthropic(lambda kw: [tool_use("finish_cycle", summary="Done.", next_check_in_hours=6)])
            await CycleRunner(MeteredClaude(client=fake)).run(run_id)
            return [t.get("name") for t in fake.agent_calls()[0]["tools"]]
        assert "github_open_pull_request" not in await one_session()
        await c.post("/api/integrations/github", json={"repo": "acme/app", "token": "ghp_good_token"})
        names = await one_session()
        assert "github_open_pull_request" in names and "submit_work" in names and "db_query" not in names


# --- read-only SQL --------------------------------------------------------------------------------

def test_only_single_read_statements_are_accepted():
    assert check_sql(" select 1; ") == "select 1"
    assert check_sql("WITH x AS (select 1) select * from x")
    for bad in ["delete from users", "select 1; drop table users", "update t set a=1", "", "insert into t values (1)"]:
        with pytest.raises(QueryError):
            check_sql(bad)


PG = os.environ.get("TEST_DATABASE_URL", "")


@pytest.mark.skipif(not PG.startswith("postgresql"), reason="needs a Postgres database (TEST_DATABASE_URL)")
async def test_read_only_queries_on_postgres():
    url = PG.replace("postgresql+asyncpg://", "postgresql://")
    result = await run_read_only(url, "select 1 as one, now() as at")
    assert result["rows"][0]["one"] == 1 and isinstance(result["rows"][0]["at"], str)
    # Even if a write slipped past the check, the database refuses it in a read-only transaction.
    with pytest.raises(QueryError):
        await run_read_only(url, "with x as (insert into users (id, email) values ('x', 'x@x') returning 1) select * from x")


async def test_database_connection_errors_are_plain():
    async with client() as c:
        await setup_org(c)
        r = await c.post("/api/integrations/postgres", json={"name": "Prod", "url": "postgresql://nobody:x@127.0.0.1:1/nope"})
        assert r.status_code == 400 and "Couldn't connect" in r.json()["detail"]
        assert (await c.post("/api/integrations/postgres", json={"url": "mysql://x"})).status_code == 422


async def test_only_admins_connect_code_and_data(gh_calls):
    async with client() as owner, client() as member:
        await setup_org(owner)
        await owner.post("/api/invitations", json={"email": "m@acme.test"})
        await sign_in(member, "m@acme.test")
        await org_of(member)
        r = await member.post("/api/integrations/github", json={"repo": "acme/app", "token": "ghp_good_token"})
        assert r.status_code == 403
        async with session_scope() as s:
            assert (await s.execute(select(Deliverable))).first() is None
