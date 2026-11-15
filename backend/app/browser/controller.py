"""Page-level browser tools for the agent.

The agent reads pages as a compact text snapshot: visible text plus a numbered list of
interactive elements ("[12] button "Post""). It acts by number: click(12), type(7, ...).
That is cheaper and more reliable than working from screenshots; screenshots are used
when the layout matters and for approval previews.

Click guard: clicking anything that looks like a final "commit" button (Post, Send,
Publish, Buy, Pay, Delete, Follow...) or pressing Enter to submit a form requires an
`authorization_id` from an approved `browser_declare_action` request. The guard runs here,
in code, regardless of what the model says.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import uuid
from dataclasses import dataclass

from playwright.async_api import Browser, Page, Playwright, async_playwright

from app.browser import chrome
from app.config import get_settings

log = logging.getLogger(__name__)

COMMIT_WORDS = re.compile(
    r"\b(post|posts|tweet|send|publish|submit|share|reply|repost|retweet|buy|purchase|pay|checkout|"
    r"place order|order now|donate|subscribe|delete|remove|confirm|follow|like|comment|schedule|boost|"
    r"promote|launch|upload|save and publish|go live|sign up|apply)\b",
    re.IGNORECASE,
)

_SNAPSHOT_JS = r"""
(maxChars) => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity || '1') > 0;
  };
  document.querySelectorAll('[data-agent-ref]').forEach((e) => e.removeAttribute('data-agent-ref'));
  const sel = 'a[href],button,input:not([type=hidden]),textarea,select,summary,[role=button],[role=link],' +
    '[role=textbox],[role=checkbox],[role=radio],[role=tab],[role=menuitem],[role=option],[role=switch],' +
    '[role=combobox],[contenteditable=""],[contenteditable=true]';
  const nameOf = (el) => (el.getAttribute('aria-label') || el.getAttribute('title') ||
    el.getAttribute('placeholder') || el.innerText || el.getAttribute('alt') || el.getAttribute('name') ||
    (el.tagName === 'INPUT' && ['submit','button'].includes(el.type) ? el.value : '') || '')
    .trim().replace(/\s+/g, ' ').slice(0, 100);
  const lines = [];
  let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    if (n >= 200) break;
    if (!visible(el)) continue;
    n += 1;
    el.setAttribute('data-agent-ref', String(n));
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || (tag === 'a' ? 'link' : tag === 'input' ? (el.type || 'text') : tag);
    let extra = '';
    if (tag === 'input' || tag === 'textarea') {
      if (el.type === 'password') extra = ' [password field]';
      else if (el.value) extra = ` value="${String(el.value).slice(0, 60)}"`;
    }
    if (el.isContentEditable && tag !== 'input') extra = ` editable text="${(el.innerText || '').slice(0, 80)}"`;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') extra += ' [disabled]';
    if (tag === 'a' && el.href && !el.href.startsWith('javascript')) extra += ` -> ${el.href.slice(0, 120)}`;
    lines.push(`[${n}] ${role} "${nameOf(el)}"${extra}`);
  }
  const text = (document.body ? document.body.innerText : '').replace(/\n{3,}/g, '\n\n').slice(0, maxChars);
  return { title: document.title, url: location.href, elements: lines, text };
}
"""

_ELEMENT_INFO_JS = r"""
(el) => ({
  tag: el.tagName.toLowerCase(),
  type: (el.getAttribute('type') || '').toLowerCase(),
  role: el.getAttribute('role') || '',
  name: (el.getAttribute('aria-label') || el.innerText || el.value || el.getAttribute('title') || '')
        .trim().replace(/\s+/g, ' ').slice(0, 120),
  autocomplete: (el.getAttribute('autocomplete') || '').toLowerCase(),
  editable: el.isContentEditable || ['input', 'textarea'].includes(el.tagName.toLowerCase()),
  inForm: !!el.closest('form'),
  search: (el.getAttribute('type') === 'search') || /search/i.test(el.getAttribute('aria-label') || '') ||
          /search/i.test(el.getAttribute('placeholder') || '') || /search/i.test(el.getAttribute('name') || ''),
})
"""

_FOCUSED_INFO_JS = "() => { const el = document.activeElement; return el && el !== document.body ? (" + _ELEMENT_INFO_JS + ")(el) : null; }"


@dataclass
class GuardHit:
    label: str


class BrowserError(Exception):
    pass


def is_commit(info: dict) -> bool:
    if info.get("editable") and info.get("tag") != "input":
        return False
    if info.get("tag") == "input" and info.get("type") not in ("submit", "button", "image"):
        return False
    return bool(COMMIT_WORDS.search(info.get("name") or ""))


class BrowserController:
    """One per process. Each agent run gets its own tab, keyed by run id."""

    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._pages: dict[str, Page] = {}
        self._lock = asyncio.Lock()

    async def _connect(self) -> Browser:
        async with self._lock:
            if self._browser and self._browser.is_connected():
                return self._browser
            url = await chrome.ensure_agent_chrome()
            if self._pw is None:
                self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.connect_over_cdp(url)
            self._pages = {}
            return self._browser

    async def page(self, run_id: str) -> Page:
        page = self._pages.get(run_id)
        if page and not page.is_closed():
            return page
        browser = await self._connect()
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()
        await page.set_viewport_size({"width": 1280, "height": 860})
        self._pages[run_id] = page
        return page

    async def close_run(self, run_id: str) -> None:
        page = self._pages.pop(run_id, None)
        if page and not page.is_closed():
            try:
                await page.close()
            except Exception:  # noqa: BLE001
                pass

    # --- reading ---------------------------------------------------------------------

    async def snapshot(self, run_id: str, max_chars: int = 3500) -> str:
        page = await self.page(run_id)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:  # noqa: BLE001
            pass
        data = await page.evaluate(_SNAPSHOT_JS, max_chars)
        elements = "\n".join(data["elements"]) or "(no interactive elements found)"
        return (
            f"URL: {data['url']}\nTitle: {data['title']}\n\n"
            f"Interactive elements (use the number to act):\n{elements}\n\n"
            f"Visible text (truncated):\n{data['text']}"
        )

    async def screenshot(self, run_id: str) -> tuple[str, str]:
        """Returns (file name, base64 JPEG). Saved under data/screenshots for previews."""
        page = await self.page(run_id)
        shots = get_settings().screenshots_dir
        shots.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.jpg"
        data = await page.screenshot(type="jpeg", quality=60, path=str(shots / name))
        return name, base64.standard_b64encode(data).decode()

    # --- acting ----------------------------------------------------------------------

    async def open(self, run_id: str, url: str) -> str:
        if not re.match(r"^https?://", url):
            url = "https://" + url
        page = await self.page(run_id)
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await self._settle(page)
        return page.url

    async def current_url(self, run_id: str) -> str:
        return (await self.page(run_id)).url

    async def _element(self, run_id: str, ref: int):
        page = await self.page(run_id)
        loc = page.locator(f'[data-agent-ref="{int(ref)}"]')
        if await loc.count() == 0:
            raise BrowserError(f"Element [{ref}] is gone. Take a new snapshot and use the new numbers.")
        return page, loc.first

    async def element_info(self, run_id: str, ref: int) -> dict:
        _, loc = await self._element(run_id, ref)
        return await loc.evaluate(_ELEMENT_INFO_JS)

    async def focused_info(self, run_id: str) -> dict | None:
        page = await self.page(run_id)
        return await page.evaluate(_FOCUSED_INFO_JS)

    async def click(self, run_id: str, ref: int) -> None:
        page, loc = await self._element(run_id, ref)
        await loc.scroll_into_view_if_needed(timeout=5000)
        await loc.click(timeout=10000)
        await self._settle(page)

    async def type(self, run_id: str, ref: int, text: str, clear: bool = True) -> None:
        page, loc = await self._element(run_id, ref)
        await loc.click(timeout=10000)
        if clear:
            await page.keyboard.press("ControlOrMeta+A")
            await page.keyboard.press("Backspace")
        await page.keyboard.insert_text(text)
        await asyncio.sleep(0.3)

    async def press(self, run_id: str, key: str) -> None:
        page = await self.page(run_id)
        await page.keyboard.press(key)
        await self._settle(page)

    async def scroll(self, run_id: str, direction: str) -> None:
        page = await self.page(run_id)
        dy = {"down": 700, "up": -700}.get(direction, 700)
        await page.mouse.wheel(0, dy)
        await asyncio.sleep(0.6)

    async def back(self, run_id: str) -> None:
        page = await self.page(run_id)
        await page.go_back(wait_until="domcontentloaded", timeout=20000)

    async def _settle(self, page: Page) -> None:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(0.8)


_controller: BrowserController | None = None


def get_controller() -> BrowserController:
    global _controller
    if _controller is None:
        _controller = BrowserController()
    return _controller
