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
import re
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
    logo_aspect: float | None = None  # width / height
    logo_bg: str | None = None  # the colour behind it on the site (part of the screenshot)
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
  // Any CSS colour (rgb, oklch, lab, color(...)) to #rrggbb by painting it; transparent is null.
  const cv = document.createElement("canvas"); cv.width = cv.height = 1;
  const cx = cv.getContext("2d", { willReadFrequently: true });
  const rgb = (s) => { s = (s || "").trim(); if (!s || s === "transparent") return null;
    cx.clearRect(0, 0, 1, 1); cx.fillStyle = "#000"; cx.fillStyle = s; cx.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = cx.getImageData(0, 0, 1, 1).data; if (a < 128) return null;
    return "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join(""); };
  const text = (el) => (el?.innerText || "").replace(/\s+/g, " ").trim();
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  // The background a visitor sees behind the headline: the nearest ancestor of the h1 that paints one
  // (the hero is often dark while the page body is light).
  const h1 = document.querySelector("h1");
  const paints = (el) => { for (let e = el; e; e = e.parentElement) { const c = rgb(css(e, "background-color")); if (c) return c; } return null; };
  const bodyBg = rgb(css(document.body, "background-color")) || rgb(css(document.documentElement, "background-color")) || "#ffffff";
  const fg = rgb(css(h1 || document.body, "color")) || "#111111";
  let bg = (h1 && paints(h1)) || bodyBg;
  const lum = (hex) => { const n = parseInt(hex.slice(1), 16); return (0.2126 * (n >> 16 & 255) + 0.7152 * (n >> 8 & 255) + 0.0722 * (n & 255)) / 255; };
  // Light text on a light "background" means the real backdrop is an image or gradient: call it dark.
  if (lum(fg) > 0.7 && lum(bg) > 0.6) bg = "#111111";
  if (lum(fg) < 0.3 && lum(bg) < 0.3) bg = "#ffffff";
  const sat = (hex) => { const n = parseInt(hex.slice(1), 16); const c = [n >> 16 & 255, n >> 8 & 255, n & 255];
    const mx = Math.max(...c), mn = Math.min(...c); return mx < 80 ? 0 : (mx - mn) / mx; }; // dark colours aren't accents
  const counts = {};
  for (const el of document.querySelectorAll("a, button, [role=button]")) {
    if (!visible(el)) continue;
    const c = rgb(css(el, "background-color"));
    if (!c || c === bg || sat(c) < 0.25) continue;
    const r = el.getBoundingClientRect();
    counts[c] = (counts[c] || 0) + (r.top < innerHeight ? 3 : 1);
  }
  const accents = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([c]) => c);
  const links = [...document.querySelectorAll("a, h1 span, h1 em, h2 span")].map((a) => rgb(css(a, "color"))).filter((c) => c && c !== fg && sat(c) >= 0.25);
  const muted = rgb(css(document.querySelector("p"), "color"));
  const family = (css(h1 || document.body, "font-family") || "").split(",")[0].replace(/["']/g, "").trim();
  const buttons = [...document.querySelectorAll("a, button")].filter(visible)
    .filter((el) => rgb(css(el, "background-color")) || /btn|button|cta/i.test(el.className || ""))
    .map(text).filter((t) => t && t.length < 40);
  const quotes = [...document.querySelectorAll("blockquote, [class*=testimonial] p, [class*=quote] p, figure figcaption")]
    .map(text).filter((t) => t.length > 30 && t.length < 260).slice(0, 4);
  const logoEl = document.querySelector("header img[alt*=logo i], header img[src*=logo i], header [class*=logo i] img, header [class*=logo i] svg, a[href='/'] img, a[href='/'] svg, header svg");
  let logoBox = null;
  if (logoEl && visible(logoEl)) { const r = logoEl.getBoundingClientRect(); if (r.width > 16 && r.height > 12 && r.width < 500) logoBox = { x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height, bg: paints(logoEl) || bodyBg }; }
  return {
    title: document.title, description: document.querySelector("meta[name=description]")?.content || document.querySelector("meta[property='og:description']")?.content || "",
    headline: text(h1), headings: [...document.querySelectorAll("h2, h3")].filter(visible).map(text).filter((t) => t && t.length < 120).slice(0, 12),
    buttons: [...new Set(buttons)].slice(0, 10), quotes,
    colors: { bg, fg, accent: accents[0] || links[0] || null, accent2: accents[1] || links[0] || null, muted: muted || null },
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
            fam = re.sub(r"\s+(Variable|VF)$", "", (brand.get("font") or "").strip())
            cap.font = fam if fam.lower() not in _GENERIC_FONTS and not fam.startswith("__") else None

            if brand.get("logoBox"):
                b = brand["logoBox"]
                try:
                    await page.screenshot(path=str(job / "logo.png"), clip={"x": b["x"], "y": b["y"], "width": b["w"], "height": b["h"]},
                                          omit_background=True)
                    cap.logo = "logo.png"
                    cap.logo_aspect = round(b["w"] / b["h"], 3) if b["h"] else None
                    cap.logo_bg = b.get("bg")
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
                # A 1x copy for Claude to look at when it writes the storyboard (smaller, same framing).
                await page.screenshot(path=str(job / f"look{i}.jpg"), type="jpeg", quality=70, scale="css")
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
