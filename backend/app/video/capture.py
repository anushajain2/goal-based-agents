"""What a visitor sees on a company's website, captured for a launch video.

A headless Chrome opens the home page the way a visitor would: it waits for the page to render,
dismisses cookie banners, scrolls so content that animates in on scroll appears, then takes
screenshots of the first screen and the sections below it at video resolution. It also reads the
brand: exact colours from the page's CSS, the heading font, the logo, and the copy (headline,
headings, buttons, quotes).

Everything read from the site is data. Requests to private or internal addresses are blocked, so a
site can't point the browser at our own network.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from app.config import get_settings

log = logging.getLogger(__name__)

VIEWPORTS = {"landscape": (1440, 900), "vertical": (430, 932), "square": (1080, 1080)}
MAX_SHOTS = 5
ACCEPT = ["Accept all", "Accept", "Allow all", "I agree", "Agree", "Got it", "OK", "Okay", "Alle akzeptieren", "Akzeptieren",
          "Tout accepter", "Accepter", "Aceptar"]


@dataclass
class Capture:
    url: str
    title: str = ""
    description: str = ""
    headline: str = ""
    headings: list[str] = field(default_factory=list)
    buttons: list[str] = field(default_factory=list)
    quotes: list[str] = field(default_factory=list)
    colors: dict = field(default_factory=dict)  # bg, fg, accent, accent2, muted
    dark: bool = False
    font: str | None = None
    logo: str | None = None  # file name in the job folder
    shots: list[dict] = field(default_factory=list)  # {src, width, height, y}


_resolved: dict[str, bool] = {}


async def _public(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if url.startswith(("data:", "blob:")):
        return True
    if not get_settings().production:
        return True  # on your own computer, local sites are fine
    if host in _resolved:
        return _resolved[host]
    ok = True
    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost")):
        ok = False
    else:
        try:
            try:
                addrs = [str(ipaddress.ip_address(host))]
            except ValueError:
                infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
                addrs = [i[4][0] for i in infos]
            ok = all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs)
        except (socket.gaierror, ValueError):
            ok = True  # unresolvable here; the request itself will fail
    _resolved[host] = ok
    return ok


_READ_BRAND = r"""
() => {
  const css = (el, p) => el ? getComputedStyle(el).getPropertyValue(p) : "";
  const rgb = (s) => { const m = (s || "").match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const [r, g, b, a] = m[1].split(",").map((x) => parseFloat(x)); if (a === 0) return null;
    return "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join(""); };
  const text = (el) => (el?.innerText || "").replace(/\s+/g, " ").trim();
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  let bg = rgb(css(document.body, "background-color")) || rgb(css(document.documentElement, "background-color"));
  if (!bg) { const main = document.querySelector("main, #__next, #root, .page, header"); bg = rgb(css(main, "background-color")) || "#ffffff"; }
  const h1 = document.querySelector("h1");
  const fg = rgb(css(h1 || document.body, "color")) || "#111111";
  const counts = {};
  for (const el of document.querySelectorAll("a, button, [role=button]")) {
    if (!visible(el)) continue;
    const c = rgb(css(el, "background-color"));
    if (!c || c === bg || c === "#ffffff" || c === "#000000") continue;
    const r = el.getBoundingClientRect();
    counts[c] = (counts[c] || 0) + (r.top < innerHeight ? 3 : 1);
  }
  const accents = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([c]) => c);
  const links = [...document.querySelectorAll("a")].map((a) => rgb(css(a, "color"))).filter((c) => c && c !== fg);
  const muted = rgb(css(document.querySelector("p"), "color"));
  const family = (css(h1 || document.body, "font-family") || "").split(",")[0].replace(/["']/g, "").trim();
  const buttons = [...document.querySelectorAll("a, button")].filter(visible)
    .filter((el) => rgb(css(el, "background-color")) || /btn|button|cta/i.test(el.className || ""))
    .map(text).filter((t) => t && t.length < 40);
  const quotes = [...document.querySelectorAll("blockquote, [class*=testimonial] p, [class*=quote] p, figure figcaption")]
    .map(text).filter((t) => t.length > 30 && t.length < 260).slice(0, 4);
  const logoEl = document.querySelector("header img[alt*=logo i], header img[src*=logo i], header [class*=logo i] img, header [class*=logo i] svg, a[href='/'] img, a[href='/'] svg, header svg");
  let logoBox = null;
  if (logoEl && visible(logoEl)) { const r = logoEl.getBoundingClientRect(); if (r.width > 16 && r.height > 12 && r.width < 500) logoBox = { x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height }; }
  return {
    title: document.title, description: document.querySelector("meta[name=description]")?.content || document.querySelector("meta[property='og:description']")?.content || "",
    headline: text(h1), headings: [...document.querySelectorAll("h2, h3")].filter(visible).map(text).filter((t) => t && t.length < 120).slice(0, 12),
    buttons: [...new Set(buttons)].slice(0, 10), quotes,
    colors: { bg, fg, accent: accents[0] || links[0] || fg, accent2: accents[1] || links[0] || accents[0] || fg, muted: muted || fg },
    font: family, logoBox, height: document.documentElement.scrollHeight,
  };
}
"""

_GENERIC_FONTS = {"", "inherit", "serif", "sans-serif", "system-ui", "-apple-system", "blinkmacsystemfont", "arial", "helvetica",
                  "helvetica neue", "segoe ui", "roboto", "ui-sans-serif", "times new roman", "georgia"}


def _luma(hex_: str) -> float:
    h = hex_.lstrip("#")
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return 1.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


async def capture(url: str, job: Path, fmt: str = "landscape") -> Capture:
    """Visit the site and write screenshots (and the logo) into `job`."""
    from playwright.async_api import async_playwright

    if "://" not in url:
        url = "https://" + url
    job.mkdir(parents=True, exist_ok=True)
    vw, vh = VIEWPORTS.get(fmt, VIEWPORTS["landscape"])
    cap = Capture(url=url)
    async with async_playwright() as pw:
        exe = get_settings().chrome_path or None
        browser = await pw.chromium.launch(executable_path=exe, args=["--no-sandbox"] if exe else None)
        try:
            ctx = await browser.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=2,
                                            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                                                       "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
                                            locale="en-US")

            async def guard(route):
                if await _public(route.request.url):
                    await route.continue_()
                else:
                    await route.abort()
            await ctx.route("**/*", guard)
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:  # noqa: BLE001 - busy sites never go idle
                pass
            await _dismiss_banners(page)
            # Scroll through once so lazy and scroll-animated content appears, then back to the top.
            height = await page.evaluate("document.documentElement.scrollHeight")
            for y in range(0, min(height, vh * 8), int(vh * 0.6)):
                await page.evaluate(f"window.scrollTo(0, {y})")
                await page.wait_for_timeout(180)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(700)

            brand = await page.evaluate(_READ_BRAND)
            cap.title, cap.description = brand["title"][:200], brand["description"][:400]
            cap.headline, cap.headings = brand["headline"][:200], brand["headings"]
            cap.buttons, cap.quotes = brand["buttons"], brand["quotes"]
            cap.colors = brand["colors"]
            cap.dark = _luma(cap.colors.get("bg", "#ffffff")) < 0.4
            fam = (brand.get("font") or "").strip()
            cap.font = fam if fam.lower() not in _GENERIC_FONTS and not fam.startswith("__") else None

            if brand.get("logoBox"):
                b = brand["logoBox"]
                try:
                    await page.screenshot(path=str(job / "logo.png"), clip={"x": b["x"], "y": b["y"], "width": b["w"], "height": b["h"]},
                                          omit_background=True)
                    cap.logo = "logo.png"
                except Exception:  # noqa: BLE001
                    cap.logo = None

            # Screens: the first one, then distinct sections further down.
            height = await page.evaluate("document.documentElement.scrollHeight")
            ys = [0] + [y for y in range(int(vh * 0.9), max(0, height - vh // 2), int(vh * 0.95))]
            for i, y in enumerate(ys[:MAX_SHOTS]):
                await page.evaluate(f"window.scrollTo(0, {y})")
                await page.wait_for_timeout(450)
                name = f"shot{i}.jpg"
                await page.screenshot(path=str(job / name), type="jpeg", quality=88)
                cap.shots.append({"src": name, "width": vw * 2, "height": vh * 2, "y": y})
        finally:
            await browser.close()
    return cap


async def _dismiss_banners(page) -> None:
    for label in ACCEPT:
        try:
            btn = page.get_by_role("button", name=label, exact=True)
            if await btn.count():
                await btn.first.click(timeout=1500)
                await page.wait_for_timeout(400)
                return
        except Exception:  # noqa: BLE001
            continue
