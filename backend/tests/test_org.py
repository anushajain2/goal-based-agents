"""Organizations: departments, AI employees, people, invitations, and approval routing."""

import httpx
import pytest
from sqlalchemy import select

from app.agent.llm import MeteredClaude
from app.agent.runner import CycleRunner
from app.browser.controller import BrowserController
from app.db import session_scope
from app.main import app
from app.models import Campaign, PermissionGrant, UserRequest
from app.worker import claim_run, schedule_due_cycles
from tests.fakes import FakeAnthropic, tool_use
from tests.helpers import agent_in, org_of, sign_in, sign_in_with_org


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def goal(agent_id: str, name: str = "Grow the newsletter") -> dict:
    return {"name": name, "goal_description": name, "primary_metric": "subscribers", "budget_total": 20,
            "agent_id": agent_id, "launch": True}


def wants_to_post(state: dict):
    """A scripted AI employee: asks to publish a post, then finishes."""

    def script(kw):
        state["step"] = state.get("step", 0) + 1
        if state["step"] == 1:
            return [tool_use("browser_declare_action", action_type="publish_post", title="Post the launch thread",
                             site="x.com", content="We launched! Here's what we learned building it.")]
        return [tool_use("finish_cycle", summary="Posted.", next_check_in_hours=6)]

    return script


async def run_cycle() -> str:
    runner = CycleRunner(MeteredClaude(client=FakeAnthropic(wants_to_post({}))))
    await schedule_due_cycles()
    run_id = await claim_run("t")
    assert run_id
    await runner.run(run_id)
    return run_id


@pytest.fixture(autouse=True)
def _no_real_browser(monkeypatch):
    async def no_shot(self, run_id):
        raise RuntimeError("no browser in tests")

    monkeypatch.setattr(BrowserController, "screenshot", no_shot)


async def test_first_sign_in_sets_up_an_organization():
    async with client() as c:
        await sign_in(c, "founder@acme.com")
        assert (await c.get("/api/org")).status_code == 409  # not set up yet
        assert (await c.post("/api/org", json={"name": "Acme", "departments": []})).status_code == 400
        r = await c.post("/api/org", json={"name": "Acme", "departments": ["sales", "marketing", "Legal ops"]})
        assert r.status_code == 200
        org = await org_of(c)
        assert org["org"]["name"] == "Acme" and org["me"]["role"] == "owner"
        names = [d["name"] for d in org["departments"]]
        assert names == ["Sales", "Marketing", "Legal ops"]
        # Each department gets an AI employee, and the founder is in every department.
        assert all(len(d["agents"]) == 1 for d in org["departments"])
        assert [d["agents"][0]["name"] for d in org["departments"]][:2] == ["Sales Agent", "Marketing Agent"]
        assert set(org["me"]["department_ids"]) == {d["id"] for d in org["departments"]}
        assert (await c.post("/api/org", json={"name": "Again", "departments": ["sales"]})).status_code == 409


async def test_invited_people_join_on_sign_in_with_their_departments():
    async with client() as owner, client() as maya:
        await sign_in_with_org(owner, "owner@acme.com")
        org = await org_of(owner)
        marketing = next(d["id"] for d in org["departments"] if d["name"] == "Marketing")
        r = await owner.post("/api/invitations", json={"email": "Maya@Acme.com", "department_ids": [marketing]})
        assert r.status_code == 200
        assert [i["email"] for i in (await org_of(owner))["invitations"]] == ["maya@acme.com"]

        await sign_in(maya, "maya@acme.com")
        mine = await org_of(maya)
        assert mine["org"]["id"] == org["org"]["id"]
        assert mine["me"]["role"] == "member" and mine["me"]["department_ids"] == [marketing]
        assert (await org_of(owner))["invitations"] == []
        # Members can't run the organization.
        assert (await maya.post("/api/departments", json={"name": "Finance"})).status_code == 403
        assert (await maya.post("/api/invitations", json={"email": "x@acme.com"})).status_code == 403
        # Someone already in an organization can't be invited to another.
        async with client() as other:
            await sign_in_with_org(other, "boss@other.com", org="Other")
            assert (await other.post("/api/invitations", json={"email": "maya@acme.com"})).status_code == 409


async def test_approvals_follow_the_org_chart():
    async with client() as owner, client() as maya, client() as sam:
        await sign_in_with_org(owner, "owner@acme.com")
        org = await org_of(owner)
        depts = {d["name"]: d["id"] for d in org["departments"]}
        # Maya leads Marketing; Sam is in Sales.
        await owner.post("/api/invitations", json={"email": "maya@acme.com", "head_of": [depts["Marketing"]]})
        await owner.post("/api/invitations", json={"email": "sam@acme.com", "department_ids": [depts["Sales"]]})
        await sign_in(maya, "maya@acme.com")
        await sign_in(sam, "sam@acme.com")
        assert (await maya.get("/api/org")).status_code == 200 and (await sam.get("/api/org")).status_code == 200

        # Maya gives the Marketing Agent a goal; Sam (Sales) can't.
        assert (await sam.post("/api/campaigns", json=goal(agent_in(org, "Marketing")))).status_code == 403
        r = await maya.post("/api/campaigns", json=goal(agent_in(org, "Marketing")))
        assert r.status_code == 200 and r.json()["department"]["name"] == "Marketing"
        goal_id = r.json()["id"]

        await run_cycle()  # the Marketing Agent asks to post -> to its head, Maya, not the owner

        req = (await maya.get("/api/requests")).json()
        assert len(req) == 1
        req = req[0]
        assert req["agent_name"] == "Marketing Agent" and req["approvers"] == ["maya@acme.com"]
        assert req["routed_to_me"] is True and req["can_decide"] is True
        assert (await owner.get("/api/requests")).json() == []  # not in the owner's inbox...
        everything = (await owner.get("/api/requests?scope=all")).json()
        assert everything[0]["can_decide"] is True  # ...though owners and admins can still step in
        assert (await sam.get("/api/requests")).json() == []
        assert (await sam.get("/api/requests?scope=all")).json()[0]["can_decide"] is False
        assert (await sam.post(f"/api/requests/{req['id']}/decide", json={"decision": "approve"})).status_code == 403
        # Everyone can see the goal; only Marketing (or admins) can change it.
        assert (await sam.get(f"/api/campaigns/{goal_id}")).status_code == 200
        assert (await sam.post(f"/api/campaigns/{goal_id}/pause")).status_code == 403

        r = await maya.post(f"/api/requests/{req['id']}/decide", json={"decision": "approve", "note": "Add a link to the demo"})
        assert r.status_code == 200 and r.json()["decided_by_name"] == "maya@acme.com"
        log = (await owner.get(f"/api/campaigns/{goal_id}/activity")).json()
        assert any(a["title"].startswith("Asked maya@acme.com") for a in log)
        assert any("Approved by maya@acme.com" in a["title"] for a in log)


async def test_reporting_lines_can_be_changed():
    async with client() as owner, client() as maya, client() as sam:
        await sign_in_with_org(owner, "owner@acme.com")
        org = await org_of(owner)
        depts = {d["name"]: d["id"] for d in org["departments"]}
        await owner.post("/api/invitations", json={"email": "maya@acme.com", "head_of": [depts["Marketing"]]})
        await owner.post("/api/invitations", json={"email": "sam@acme.com", "department_ids": [depts["Marketing"]]})
        await sign_in(maya, "maya@acme.com")
        await sign_in(sam, "sam@acme.com")
        await org_of(sam)  # joins on first load
        org = await org_of(maya)
        sam_id = next(m["id"] for m in org["members"] if m["email"] == "sam@acme.com")

        # Maya (in Marketing) hires her own AI employee that reports to Sam.
        r = await maya.post("/api/agents", json={"department_id": depts["Marketing"], "name": "Content Agent",
                                                 "objective": "Make Acme the go-to voice on routing", "reports_to_user_id": sam_id})
        assert r.status_code == 200
        content = r.json()["id"]
        info = (await maya.get(f"/api/agents/{content}")).json()
        assert info["objective"] == "Make Acme the go-to voice on routing"
        assert [p["email"] for p in info["approvers"]] == ["sam@acme.com"]
        assert (await maya.post("/api/agents", json={"department_id": depts["Sales"], "name": "x"})).status_code == 403
        assert (await maya.post("/api/agents", json={"department_id": depts["Marketing"], "reports_to_user_id": "nobody"})).status_code == 400

        await maya.post("/api/campaigns", json=goal(content, "Grow blog traffic"))
        await run_cycle()
        assert len((await sam.get("/api/requests")).json()) == 1
        assert (await maya.get("/api/requests")).json() == []

        # Back to the department's head; with no head, to the owner.
        await maya.patch(f"/api/agents/{content}", json={"reports_to_user_id": None})
        assert len((await maya.get("/api/requests")).json()) == 1
        await owner.patch(f"/api/departments/{depts['Marketing']}", json={"head_user_id": None})
        assert len((await owner.get("/api/requests")).json()) == 1
        listed = next(d for d in (await org_of(owner))["departments"] if d["name"] == "Marketing")
        assert listed["agents"][-1]["objective"] == "Make Acme the go-to voice on routing"


async def test_department_without_people_routes_to_admins():
    async with client() as owner, client() as maya:
        await sign_in_with_org(owner, "owner@acme.com", departments=("sales", "marketing", "finance"))
        org = await org_of(owner)
        finance = next(d["id"] for d in org["departments"] if d["name"] == "Finance")
        # Nobody left in Finance.
        await owner.put(f"/api/departments/{finance}/people", json={"user_ids": []})
        await owner.post("/api/invitations", json={"email": "maya@acme.com",
                                                   "department_ids": [d["id"] for d in org["departments"] if d["name"] == "Marketing"]})
        await sign_in(maya, "maya@acme.com")
        await owner.post("/api/campaigns", json=goal(agent_in(org, "Finance"), "Collect overdue invoices"))
        await run_cycle()
        owner_inbox = (await owner.get("/api/requests")).json()
        assert len(owner_inbox) == 1 and owner_inbox[0]["approvers"] == ["owner@acme.com"]
        assert (await maya.get("/api/requests")).json() == []


async def test_dont_ask_again_for_the_whole_department():
    async with client() as owner, client() as maya:
        await sign_in_with_org(owner, "owner@acme.com")
        org = await org_of(owner)
        marketing = next(d["id"] for d in org["departments"] if d["name"] == "Marketing")
        await owner.post("/api/invitations", json={"email": "maya@acme.com", "head_of": [marketing]})
        await sign_in(maya, "maya@acme.com")
        # A second Marketing AI employee.
        r = await owner.post("/api/agents", json={"department_id": marketing, "name": "Content Agent"})
        content_agent = r.json()["id"]

        await maya.post("/api/campaigns", json=goal(agent_in(org, "Marketing")))
        await run_cycle()
        req = (await maya.get("/api/requests")).json()[0]
        # Only admins may allow something org-wide.
        assert (await maya.post(f"/api/requests/{req['id']}/decide",
                                json={"decision": "approve", "remember": True, "remember_scope": "org"})).status_code == 403
        r = await maya.post(f"/api/requests/{req['id']}/decide",
                            json={"decision": "approve", "remember": True, "remember_scope": "department"})
        assert r.status_code == 200
        async with session_scope() as s:
            g = (await s.execute(select(PermissionGrant))).scalar_one()
            assert g.department_id == marketing and g.campaign_id is None

        # The other Marketing AI employee now posts on x.com without asking.
        await maya.post("/api/campaigns", json=goal(content_agent, "Grow blog traffic"))
        await run_cycle()
        assert (await maya.get("/api/requests")).json() == []
        async with session_scope() as s:
            assert len((await s.execute(select(UserRequest))).scalars().all()) == 1


async def test_department_rules_need_department_or_admin():
    async with client() as owner, client() as sam:
        await sign_in_with_org(owner, "owner@acme.com")
        org = await org_of(owner)
        depts = {d["name"]: d["id"] for d in org["departments"]}
        await owner.post("/api/invitations", json={"email": "sam@acme.com", "department_ids": [depts["Sales"]]})
        await sign_in(sam, "sam@acme.com")
        rule = {"kind": "text", "value": "Never mention pricing"}
        assert (await sam.post("/api/exclusions", json={**rule, "department_id": depts["Marketing"]})).status_code == 403
        assert (await sam.post("/api/exclusions", json={**rule, "department_id": depts["Sales"]})).status_code == 200
        assert (await sam.post("/api/exclusions", json=rule)).status_code == 403  # org-wide: admins only
        assert (await owner.post("/api/exclusions", json=rule)).status_code == 200
        levels = sorted(e["level"] for e in (await sam.get(f"/api/exclusions?department_id={depts['Sales']}")).json())
        assert levels == ["department", "org"]


async def test_existing_single_user_data_moves_into_an_organization():
    async with client() as c:
        me = await sign_in(c, "solo@example.com")
        async with session_scope() as s:
            s.add(Campaign(owner_id=me["id"], name="Book meetings", goal_type="sales", goal_description="Book 20 meetings",
                           primary_metric="meetings", budget_total=10, category="Sales"))
        org = await org_of(c)
        assert org["org"]["name"] == "solo's team"
        assert [d["name"] for d in org["departments"]] == ["Sales"]
        goals = (await c.get("/api/campaigns")).json()
        assert goals[0]["agent"]["name"] == "Sales Agent" and goals[0]["department"]["name"] == "Sales"


async def test_roles_and_last_owner():
    async with client() as owner, client() as ann:
        me = await sign_in_with_org(owner, "owner@acme.com")
        await owner.post("/api/invitations", json={"email": "ann@acme.com", "role": "admin"})
        ann_user = await sign_in(ann, "ann@acme.com")
        assert (await org_of(ann))["me"]["is_admin"] is True
        # An admin can't touch owners; the last owner can't be demoted.
        assert (await ann.patch(f"/api/members/{me['id']}", json={"role": "member"})).status_code == 403
        assert (await owner.patch(f"/api/members/{me['id']}", json={"role": "member"})).status_code == 400
        assert (await owner.patch(f"/api/members/{ann_user['id']}", json={"role": "member"})).status_code == 200
        assert (await org_of(ann))["me"]["is_admin"] is False


async def test_department_heads():
    async with client() as owner, client() as member:
        await sign_in_with_org(owner, "boss@acme.test")
        org = await org_of(owner)
        sales = next(d for d in org["departments"] if d["name"] == "Sales")
        assert sales["head"] is None
        # Invite someone to lead Sales: they join it, and lead it, when they sign in.
        r = await owner.post("/api/invitations", json={"email": "lead@acme.test", "head_of": [sales["id"]]})
        assert r.status_code == 200
        pending = (await org_of(owner))["invitations"][0]
        assert pending["head_department_ids"] == [sales["id"]] and pending["department_ids"] == [sales["id"]]
        await sign_in(member, "lead@acme.test")
        org = await org_of(member)
        sales = next(d for d in org["departments"] if d["name"] == "Sales")
        assert sales["head"]["email"] == "lead@acme.test"
        assert "lead@acme.test" in [p["email"] for p in sales["people"]]  # so they approve its work

        # Owners can change or clear the head; heads must be in the organization.
        boss = next(m for m in org["members"] if m["email"] == "boss@acme.test")
        assert (await owner.patch(f"/api/departments/{sales['id']}", json={"head_user_id": "nobody"})).status_code == 400
        assert (await member.patch(f"/api/departments/{sales['id']}", json={"head_user_id": boss["id"]})).status_code == 403
        await owner.patch(f"/api/departments/{sales['id']}", json={"head_user_id": boss["id"]})
        assert next(d for d in (await org_of(owner))["departments"] if d["id"] == sales["id"])["head"]["id"] == boss["id"]
        await owner.patch(f"/api/departments/{sales['id']}", json={"head_user_id": None})
        assert next(d for d in (await org_of(owner))["departments"] if d["id"] == sales["id"])["head"] is None
        await owner.patch(f"/api/departments/{sales['id']}", json={"name": "Revenue"})
        assert any(d["name"] == "Revenue" for d in (await org_of(owner))["departments"])
