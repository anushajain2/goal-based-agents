"""Shared test helpers."""

# Sign-in codes "sent" during tests, by email address (filled in by a conftest fixture).
SENT_CODES: dict[str, str] = {}


async def sign_in(client, email: str) -> dict:
    """Sign in with an emailed code, as a user would."""
    r = await client.post("/api/auth/email/start", json={"email": email})
    assert r.status_code == 200, r.text
    r = await client.post("/api/auth/email/verify", json={"email": email, "code": SENT_CODES[email.lower()]})
    assert r.status_code == 200, r.text
    return r.json()


async def sign_in_with_org(client, email: str, org: str = "Acme", departments=("sales", "marketing")) -> dict:
    """Sign in and set up an organization (the first-run flow)."""
    user = await sign_in(client, email)
    r = await client.post("/api/org", json={"name": org, "departments": list(departments)})
    assert r.status_code == 200, r.text
    return user


async def org_of(client) -> dict:
    r = await client.get("/api/org")
    assert r.status_code == 200, r.text
    return r.json()


def agent_in(org: dict, department_name: str) -> str:
    dept = next(d for d in org["departments"] if d["name"] == department_name)
    return dept["agents"][0]["id"]
