"""`python -m app.cli delete-user`: remove an account so the email can go through onboarding again."""

import httpx
from sqlalchemy import func, select

from app.cli import delete_user, plan_delete
from app.db import session_scope
from app.main import app
from app.models import Campaign, Organization, User
from tests.helpers import agent_in, org_of, sign_in, sign_in_with_org


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def count(model) -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def test_sole_member_takes_their_organization_with_them():
    async with client() as c:
        await sign_in_with_org(c, "solo@acme.test")
        org = await org_of(c)
        await c.post("/api/campaigns", json={"name": "g", "goal_description": "g", "primary_metric": "m",
                                             "budget_total": 10, "agent_id": agent_in(org, "Sales")})
    info = await plan_delete("SOLO@acme.test")
    assert info["org"]["others"] == 0 and info["org"]["goals"] == 1
    await delete_user("solo@acme.test")
    assert await count(User) == 0 and await count(Organization) == 0 and await count(Campaign) == 0

    async with client() as c:  # signing up again starts onboarding
        await sign_in(c, "solo@acme.test")
        assert (await c.get("/api/org")).status_code == 409


async def test_team_keeps_goals_and_gets_a_new_owner():
    async with client() as owner, client() as member:
        await sign_in_with_org(owner, "boss@acme.test")
        org = await org_of(owner)
        await owner.post("/api/campaigns", json={"name": "g", "goal_description": "g", "primary_metric": "m",
                                                 "budget_total": 10, "agent_id": agent_in(org, "Sales")})
        await owner.post("/api/invitations", json={"email": "m@acme.test", "role": "admin"})
        await sign_in(member, "m@acme.test")
        assert (await member.get("/api/org")).status_code == 200  # joins on first load
        await owner.post("/api/invitations", json={"email": "later@acme.test"})
        lines = await delete_user("boss@acme.test")
        assert any("m@acme.test an owner" in line for line in lines)
        assert await count(Organization) == 1 and await count(Campaign) == 1
        me = (await member.get("/api/org")).json()["me"]
        assert me["role"] == "owner"


async def test_pending_invitations_are_removed_so_signup_shows_onboarding():
    async with client() as owner, client() as c:
        await sign_in_with_org(owner, "boss@acme.test")
        await owner.post("/api/invitations", json={"email": "new@acme.test"})
        assert (await plan_delete("new@acme.test")) == {"user": None, "invites": 1}
        await delete_user("new@acme.test")
        await sign_in(c, "new@acme.test")
        assert (await c.get("/api/org")).status_code == 409
