"""Agent Chrome: your installed Chrome, with its own profile, controlled over CDP.

* The profile lives in data/agent-chrome-profile, so sign-ins persist across restarts.
  You sign in once per site; the agent never sees or types passwords.
* Chrome 136+ refuses remote debugging on the default profile, which is why this is a
  separate profile (and safer: the agent only reaches accounts you sign into here).
* Chrome is started detached, so it survives worker restarts; any process can reconnect
  to it through the debugging port.
* "Manual sign-in mode" relaunches the same profile *without* remote control, for sites
  (e.g. Google) that refuse sign-ins in a remotely-controlled browser. When you are done,
  normal mode resumes and the saved sign-in carries over.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

_CANDIDATES = {
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ],
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe"),
    ],
    "linux": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
}


def find_chrome() -> str | None:
    settings = get_settings()
    if settings.chrome_path:
        return settings.chrome_path
    for candidate in _CANDIDATES.get(sys.platform, _CANDIDATES["linux"]):
        path = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if path:
            return path
    return None


def _pid_file(mode: str) -> Path:
    return get_settings().chrome_profile_dir.parent / f"agent-chrome-{mode}.pid"


def _read_pid(mode: str) -> int | None:
    try:
        return int(_pid_file(mode).read_text().strip())
    except (OSError, ValueError):
        return None


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


async def _terminate(mode: str) -> None:
    pid = _read_pid(mode)
    if _alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(50):
            if not _alive(pid):
                break
            await asyncio.sleep(0.1)
    _pid_file(mode).unlink(missing_ok=True)


def cdp_url() -> str:
    return f"http://127.0.0.1:{get_settings().chrome_debug_port}"


async def cdp_ready() -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            r = await client.get(cdp_url() + "/json/version")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


def manual_mode_active() -> bool:
    return _alive(_read_pid("manual"))


def _launch(args: list[str], mode: str) -> int:
    settings = get_settings()
    settings.chrome_profile_dir.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(args, **kwargs)
    _pid_file(mode).write_text(str(proc.pid))
    return proc.pid


def _base_args(chrome: str) -> list[str]:
    settings = get_settings()
    args = [
        chrome,
        f"--user-data-dir={settings.chrome_profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,900",
        # Don't announce "controlled by automation" to websites, and keep pages working normally
        # while the window is behind other windows.
        "--disable-blink-features=AutomationControlled",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
    ]
    if settings.browser_headless:
        args += ["--headless=new", "--no-sandbox"]
    return args


class ChromeUnavailable(Exception):
    pass


async def ensure_agent_chrome() -> str:
    """Make sure Agent Chrome is running with remote control on; return the CDP URL."""
    if await cdp_ready():
        return cdp_url()
    if manual_mode_active():
        raise ChromeUnavailable(
            "Agent Chrome is in manual sign-in mode. Finish signing in and click Done in Autopilot."
        )
    chrome = find_chrome()
    if not chrome:
        raise ChromeUnavailable("Google Chrome was not found. Install it or set CHROME_PATH in .env.")
    await _terminate("agent")
    port = get_settings().chrome_debug_port
    _launch(_base_args(chrome) + [f"--remote-debugging-port={port}", "about:blank"], "agent")
    for _ in range(100):
        if await cdp_ready():
            return cdp_url()
        await asyncio.sleep(0.2)
    raise ChromeUnavailable("Agent Chrome did not start (is another Chrome using the same profile?).")


async def start_manual_signin(url: str) -> None:
    """Close the remote-controlled window and open the same profile normally at `url`."""
    chrome = find_chrome()
    if not chrome:
        raise ChromeUnavailable("Google Chrome was not found. Install it or set CHROME_PATH in .env.")
    await stop_agent_chrome()
    await _terminate("manual")
    _launch(_base_args(chrome) + [url], "manual")


async def finish_manual_signin() -> None:
    await _terminate("manual")


async def stop_agent_chrome() -> None:
    if await cdp_ready():
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(cdp_url())
                cdp = await browser.new_browser_cdp_session()
                # Ask Chrome to quit cleanly so cookies/sign-ins are flushed to disk.
                await cdp.send("Browser.close")
        except Exception:
            log.debug("graceful Chrome close failed", exc_info=True)
        for _ in range(30):
            if not await cdp_ready():
                break
            await asyncio.sleep(0.1)
    await _terminate("agent")
