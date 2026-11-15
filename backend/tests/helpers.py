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
