"""Desktop helper: pairing a computer, its connection and the relay, and website steps that wait
for the computer and carry on when it's back."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.agent.llm import MeteredClaude
from app.agent.runner import CycleRunner
from app.api import helper as helper_api
from app.browser import controller as controller_mod
from app.config import get_settings
from app.db import session_scope
from app.main import app
from app.models import Activity, AgentRun, HelperDevice, RunStatus, utcnow
from app.services import helpers
from app.worker import claim_run, wake_helper_runs
from tests.fakes import FakeAnthropic, tool_use
from tests.test_agent_flow import _no_real_browser, api, make_campaign, run_next_cycle  # noqa: F401


@pytest.fixture
def hosted(monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_chrome", False)
    yield


async def pair(api, name="Anusha's MacBook"):  # noqa: F811
    made = (await api.post("/api/helper/pairings")).json()
    assert made["key"].endswith("/api/helper/pair/" + made["code"]) and made["link"].startswith("autopilot://pair?key=")
    r = await api.post("/api/helper/pair", json={"code": made["code"].lower().replace("-", " "), "name": name,
                                                 "platform": "darwin", "version": "0.1.0"})
    assert r.status_code == 200, r.text
    return made, r.json()


async def set_seen(device_id: str, seen_ago_s: float | None, paused: bool = False) -> None:
    async with session_scope() as s:
        d = await s.get(HelperDevice, device_id)
        d.last_seen_at = None if seen_ago_s is None else utcnow() - timedelta(seconds=seen_ago_s)
        d.paused = paused


async def test_pairing_a_computer_once_and_removing_it(api):  # noqa: F811
    made, paired = await pair(api)
    assert paired["token"].startswith("aph_") and paired["org_name"] == "Acme"
    again = await api.post("/api/helper/pair", json={"code": made["code"], "name": "Other"})
    assert again.status_code == 400  # codes work once
    async with session_scope() as s:
        device = await helpers.device_for_token(s, paired["token"])
        assert device and device.name == "Anusha's MacBook" and device.token_hash != paired["token"]
        assert await helpers.device_for_token(s, "aph_wrong") is None
    listed = (await api.get("/api/helper/devices")).json()
    assert [d["name"] for d in listed] == ["Anusha's MacBook"] and listed[0]["online"] is False

    await set_seen(paired["device_id"], 10)
    assert (await api.get("/api/helper/devices")).json()[0]["online"] is True
    await set_seen(paired["device_id"], 10, paused=True)
    assert (await api.get("/api/helper/devices")).json()[0]["online"] is False  # paused counts as offline
    await set_seen(paired["device_id"], 500)
    assert (await api.get("/api/helper/devices")).json()[0]["online"] is False

    assert (await api.delete(f"/api/helper/devices/{paired['device_id']}")).status_code == 200
    assert (await api.get("/api/helper/devices")).json() == []
    async with session_scope() as s:
        assert await helpers.device_for_token(s, paired["token"]) is None  # its token stops working at once


async def test_expired_codes_dont_work(api):  # noqa: F811
    made = (await api.post("/api/helper/pairings")).json()
    async with session_scope() as s:
        from app.models import HelperPairing

        for p in (await s.execute(select(HelperPairing))).scalars():
            p.expires_at = utcnow() - timedelta(seconds=1)
    assert (await api.post("/api/helper/pair", json={"code": made["code"]})).status_code == 400


@pytest.fixture
async def live_server():
    """The real app on a local port, in this event loop (WebSockets need a real server)."""
    import asyncio
    import socket

    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    yield f"ws://127.0.0.1:{port}"
    server.should_exit = True
    await task


async def test_the_relay_carries_devtools_messages_between_worker_and_helper(api, live_server):  # noqa: F811
    import json

    import websockets

    _, paired = await pair(api)
    connect, relay = f"{live_server}/api/helper/connect", f"{live_server}/api/helper/relay/{paired['device_id']}"
    with pytest.raises(websockets.exceptions.WebSocketException):
        async with websockets.connect(connect, additional_headers={"authorization": "Bearer aph_nope"}) as ws:
            await ws.recv()
    async with websockets.connect(connect, additional_headers={"authorization": f"Bearer {paired['token']}"}) as hws:
        hello = json.loads(await hws.recv())
        assert hello["t"] == "hello" and hello["device"]["name"] == "Anusha's MacBook"
        await hws.send(json.dumps({"t": "ping", "paused": False}))
        assert json.loads(await hws.recv()) == {"t": "pong"}

        with pytest.raises(websockets.exceptions.WebSocketException):  # the relay is only for the worker (keyed)
            async with websockets.connect(relay, additional_headers={"x-relay-key": "x"}) as w:
                await w.recv()
        async with websockets.connect(relay, additional_headers={"x-relay-key": helpers.relay_key()}) as wws:
            opened = json.loads(await hws.recv())
            assert opened["t"] == "open"
            ch = opened["c"]
            await wws.send('{"id":1,"method":"Browser.getVersion"}')
            assert json.loads(await hws.recv()) == {"t": "d", "c": ch, "d": '{"id":1,"method":"Browser.getVersion"}'}
            await hws.send(json.dumps({"t": "d", "c": ch, "d": '{"id":1,"result":{"product":"Chrome/140"}}'}))
            assert await wws.recv() == '{"id":1,"result":{"product":"Chrome/140"}}'
        assert json.loads(await hws.recv()) == {"t": "close", "c": ch}  # the worker hung up
        async with session_scope() as s:
            assert helpers.is_online(await s.get(HelperDevice, paired["device_id"]))
    import asyncio

    for _ in range(50):  # the helper went away: offline straight away
        async with session_scope() as s:
            if not helpers.is_online(await s.get(HelperDevice, paired["device_id"])):
                break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("still online after disconnecting")


class FakeController:
    def __init__(self):
        self.opened = []

    async def open(self, run_id, url):
        self.opened.append(url)
        return url

    async def close_run(self, run_id):
        return None


async def test_website_steps_wait_for_the_computer_then_carry_on(api, hosted, monkeypatch):  # noqa: F811
    _, paired = await pair(api)
    gid = await make_campaign(api)
    fake_chrome = FakeController()
    monkeypatch.setattr(controller_mod, "helper_controller", lambda device_id: fake_chrome)
    seen = []

    def worker(kw):
        seen.append(kw)
        tools = {t["name"] for t in kw.get("tools") or []}
        assert "browser_open" in tools  # a paired computer means website tools are on offer
        if len(seen) == 1:
            return [tool_use("browser_open", url="https://x.com/demo")]
        return [tool_use("finish_cycle", summary="Checked the profile.", next_check_in_hours=6)]

    claude = MeteredClaude(client=FakeAnthropic(worker))
    run_id = await run_next_cycle(CycleRunner(claude))  # the computer is offline (never seen)
    async with session_scope() as s:
        run = await s.get(AgentRun, run_id)
        assert run.status == RunStatus.waiting.value
        waiting = list(run.pending["waiting"].values())
        assert waiting[0]["stored"] == {"kind": "helper", "tool": "browser_open", "input": {"url": "https://x.com/demo"}}
        kinds = (await s.execute(select(Activity.kind).where(Activity.run_id == run_id))).scalars().all()
    assert "computer" in kinds and fake_chrome.opened == []
    goal = (await api.get(f"/api/campaigns/{gid}")).json()
    assert goal["current_run"]["waiting_for"] == "computer"

    assert await wake_helper_runs() == 0  # still offline: stays parked
    await set_seen(paired["device_id"], 5)  # the laptop opens
    assert await wake_helper_runs() == 1
    rid = await claim_run("test")
    assert rid == run_id
    await CycleRunner(claude).run(rid)
    assert fake_chrome.opened == ["https://x.com/demo"]
    async with session_scope() as s:
        assert (await s.get(AgentRun, run_id)).status == RunStatus.completed.value


async def test_without_any_computer_website_tools_are_not_offered(api, hosted):  # noqa: F811
    await make_campaign(api)
    offered = []

    def worker(kw):
        offered.append({t["name"] for t in kw.get("tools") or []})
        return [tool_use("finish_cycle", summary="Researched.", next_check_in_hours=6)]

    await run_next_cycle(CycleRunner(MeteredClaude(client=FakeAnthropic(worker))))
    assert not any(n.startswith("browser_") for n in offered[0])
    status = (await api.get("/api/status")).json()
    assert status["helper"]["paired"] == 0 and status["helper"]["online"] is False


async def test_sign_in_buttons_go_to_the_computer(api, hosted, monkeypatch):  # noqa: F811
    r = await api.post("/api/browser/open", json={"url": "x.com/login"})
    assert r.status_code == 409 and "desktop helper" in r.json()["detail"]
    _, paired = await pair(api)
    await set_seen(paired["device_id"], 5)
    sent = []

    class Conn:
        async def send(self, msg):
            sent.append(msg)

    monkeypatch.setitem(helper_api.hub.conns, paired["device_id"], Conn())
    r = await api.post("/api/browser/open", json={"url": "x.com/login"})
    assert r.status_code == 200 and r.json()["where"] == "Anusha's MacBook"
    assert sent == [{"t": "open_url", "url": "https://x.com/login"}]
