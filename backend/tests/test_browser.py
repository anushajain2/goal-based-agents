"""Autopilot Chrome against a real Chrome (headless here) and a local test page."""

import http.server
import shutil
import threading
from decimal import Decimal

import pytest

from app.agent.executor import ToolExecutor
from app.agent.llm import MeteredClaude
from app.browser import chrome
from app.browser.controller import get_controller
from app.config import get_settings
from app.db import session_scope
from app.models import AgentRun, Campaign, ExclusionRule, PermissionGrant
from tests.fakes import FakeAnthropic

PAGE = b"""<!doctype html><html><head><title>Fake Social</title></head><body>
<h1>Compose</h1>
<input aria-label="Search" type="search" id="q">
<textarea aria-label="What's happening?" id="box"></textarea>
<input type="password" aria-label="Password">
<button id="post" onclick="document.getElementById('out').innerText='POSTED:'+document.getElementById('box').value">Post</button>
<button onclick="document.getElementById('out').innerText='TAB'">Explore</button>
<a href="/other">Other page</a>
<div id="out"></div>
</body></html>"""

pytestmark = pytest.mark.skipif(not shutil.which("google-chrome") and not chrome.find_chrome(),
                                reason="Chrome not installed")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("content-type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module", autouse=True)
async def headless_chrome(tmp_path_factory):
    settings = get_settings()
    settings.browser_headless = True
    settings.chrome_profile_dir = tmp_path_factory.mktemp("profile") / "agent-chrome-profile"
    settings.chrome_debug_port = 9444
    settings.data_dir = tmp_path_factory.mktemp("data")
    yield
    await chrome.stop_agent_chrome()


async def setup_run(grant: bool = False, block_site: str | None = None) -> tuple[str, str]:
    async with session_scope() as s:
        c = Campaign(name="b", goal_type="followers", goal_description="g", primary_metric="followers",
                     budget_total=Decimal(10), status="active")
        s.add(c)
        await s.flush()
        run = AgentRun(campaign_id=c.id, cycle_number=1, status="running")
        s.add(run)
        if grant:
            s.add(PermissionGrant(campaign_id=c.id, action_type="publish_post", scope="127.0.0.1"))
        if block_site:
            s.add(ExclusionRule(campaign_id=c.id, kind="site", value=block_site))
        await s.flush()
        return c.id, run.id


async def test_snapshot_guard_and_authorized_post(site):
    cid, run_id = await setup_run(grant=True)
    ex = ToolExecutor(MeteredClaude(client=FakeAnthropic(lambda kw: [])), cid, run_id)

    snap = (await ex.call("browser_open", {"url": site}, "t1")).content
    assert "Fake Social" in snap and 'button "Post"' in snap and "[password field]" in snap
    refs = {line.split('"')[1]: int(line.split("]")[0][1:]) for line in snap.splitlines()
            if line.startswith("[")}

    # Passwords are never typed.
    out = await ex.call("browser_type", {"ref": refs["Password"], "text": "hunter2"}, "t2")
    assert out.is_error and "never type passwords" in out.content

    # Typing a draft is fine; clicking Post without authorization is blocked by the guard.
    out = await ex.call("browser_type", {"ref": refs["What's happening?"], "text": "Hello from Autopilot"}, "t3")
    assert not out.is_error
    out = await ex.call("browser_click", {"ref": refs["Post"]}, "t4")
    assert out.is_error and "browser_declare_action" in out.content

    # Non-commit buttons click freely.
    out = await ex.call("browser_click", {"ref": refs["Explore"]}, "t5")
    assert not out.is_error and "TAB" in out.content

    # Declare (auto-allowed by the grant) -> authorization -> the click goes through.
    out = await ex.call("browser_declare_action", {"action_type": "publish_post", "title": "Post hello",
                                                   "site": "127.0.0.1", "content": "Hello from Autopilot"}, "t6")
    assert "authorization_id=" in out.content, out.content
    auth_id = out.content.split("authorization_id=")[1].split()[0]
    snap = (await ex.call("browser_snapshot", {}, "t7")).content
    post_ref = next(int(l.split("]")[0][1:]) for l in snap.splitlines() if 'button "Post"' in l)
    out = await ex.call("browser_click", {"ref": post_ref, "authorization_id": auth_id}, "t8")
    assert not out.is_error and "POSTED:Hello from Autopilot" in out.content

    # Screenshots work (used for approval previews).
    shot = (await ex.call("browser_screenshot", {}, "t9")).content
    assert isinstance(shot, list) and shot[0]["type"] == "image", shot
    await get_controller().close_run(run_id)


async def test_blocked_site(site):
    cid, run_id = await setup_run(block_site="127.0.0.1")
    ex = ToolExecutor(MeteredClaude(client=FakeAnthropic(lambda kw: [])), cid, run_id)
    out = await ex.call("browser_open", {"url": site}, "t1")
    assert out.is_error and "blocked" in out.content.lower()
