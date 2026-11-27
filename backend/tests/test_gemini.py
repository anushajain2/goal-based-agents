"""Goal plans can be written by Gemini (Gemini 4 Neon by default); Claude writes them when there's no
Gemini key or Gemini fails."""

import json

import httpx
import pytest
from sqlalchemy import select

from app.agent.llm import MeteredClaude
from app.config import get_settings
from app.db import session_scope
from app.models import ModelUsage
from tests.fakes import FakeAnthropic, text
from tests.test_agent_flow import _no_real_browser, api, make_campaign  # noqa: F401

SCHEMA = {"type": "json_schema", "schema": {"type": "object", "properties": {"approaches": {"type": "array"}},
                                            "required": ["approaches"], "additionalProperties": False}}


@pytest.fixture
def gemini(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["key"], seen["body"] = str(request.url), request.headers.get("x-goog-api-key"), json.loads(request.content)
        if seen.get("fail"):
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True},
                                                  {"text": json.dumps({"approaches": [{"name": "Weekly post"}]})}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 400, "thoughtsTokenCount": 600},
            "modelVersion": "gemini-4-neon-001"})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(get_settings(), "gemini_api_key", "g-key")
    return seen


async def plan_call(claude: MeteredClaude, gid: str):
    return await claude.create(campaign_id=gid, run_id=None, purpose="how this goal gets hit", task="goal_plan",
                               system="Write plainly.", messages=[{"role": "user", "content": "Goal: 3 posts a week"}],
                               max_tokens=6000, output_format=SCHEMA)


async def test_goal_plans_are_written_by_gemini_when_it_is_set_up(api, gemini):
    gid = await make_campaign(api, launch=False)
    fake = FakeAnthropic(lambda kw: [text("unused")])
    result = await plan_call(MeteredClaude(client=fake), gid)
    assert json.loads(result.content[0]["text"]) == {"approaches": [{"name": "Weekly post"}]}  # its thoughts left out
    assert fake.calls == []
    assert gemini["url"].endswith("/models/gemini-4-neon:generateContent") and gemini["key"] == "g-key"
    body = gemini["body"]
    assert body["systemInstruction"]["parts"][0]["text"] == "Write plainly."
    assert body["contents"] == [{"role": "user", "parts": [{"text": "Goal: 3 posts a week"}]}]
    cfg = body["generationConfig"]
    assert cfg["responseMimeType"] == "application/json" and cfg["responseJsonSchema"] == SCHEMA["schema"]
    assert cfg["thinkingConfig"] == {"thinkingLevel": "medium"} and cfg["maxOutputTokens"] == 6000
    # Priced as Gemini 4 Neon (a dated version name too): 1,000 in at $3/M + 1,000 out (answer + thinking) at $15/M.
    assert float(result.cost) == pytest.approx(0.018)
    async with session_scope() as s:
        row = (await s.execute(select(ModelUsage))).scalars().one()
    assert (row.task, row.model, row.input_tokens, row.output_tokens) == ("goal_plan", "gemini-4-neon-001", 1000, 1000)


async def test_claude_writes_the_plan_when_gemini_fails_or_isnt_set_up(api, gemini, monkeypatch):
    gid = await make_campaign(api, launch=False)
    gemini["fail"] = True
    fake = FakeAnthropic(lambda kw: [text("ok")], routes={"approaches": lambda kw: {"approaches": []}})
    await plan_call(MeteredClaude(client=fake), gid)
    assert fake.calls[0]["model"] == get_settings().planner_model
    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    gemini.pop("url")
    await plan_call(MeteredClaude(client=fake), gid)
    assert "url" not in gemini and len(fake.calls) == 2


async def test_x_without_its_own_app_gets_a_clear_message_not_a_crash(api, monkeypatch):
    """Composio has no shared login for X: say what to do instead of a 500."""
    from types import SimpleNamespace

    from app.connectors import composio_hub

    class AuthConfigs:
        def list(self, toolkit_slug):
            return SimpleNamespace(items=[])

        def create(self, slug, body):
            raise RuntimeError('404 Default auth config not found for toolkit "twitter". '
                               "Composio does not have managed credentials for this toolkit.")

    fake_client = SimpleNamespace(auth_configs=AuthConfigs())
    monkeypatch.setattr(composio_hub.ComposioHub, "_client", fake_client)
    monkeypatch.setattr(get_settings(), "composio_api_key", "c-key")
    r = await api.post("/api/connections/twitter/connect")
    assert r.status_code == 400
    msg = r.json()["detail"]
    assert "X can't be connected with a shared login" in msg and "own X developer app" in msg
    assert "desktop helper" in msg
