"""Checks on a company's own website and domain, measured rather than guessed.

  pagespeed     Google PageSpeed Insights: mobile speed, accessibility, SEO basics (Google's own data)
  email_auth    SPF, DKIM and DMARC records, read from public DNS (whether email lands in inboxes)
  security      HTTPS, the certificate's and the domain's expiry dates, HSTS
  page_tools    what the home page runs: analytics, ad pixels, cookie consent, chat, booking, forms
  broken_links  a small crawl of the site, with every link checked
"""

from __future__ import annotations

import asyncio
import re
import ssl
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

from app.config import get_settings
from app.services.website import UnsafeURL, _assert_public, _get

from .http import client, get_json, host

PSI = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
DOH = "https://dns.google/resolve"
DKIM_SELECTORS = ["google", "selector1", "selector2", "k1", "k2", "default", "s1", "s2", "mail", "dkim", "mxvault"]
MAX_PAGES = 20
MAX_LINKS = 120


async def pagespeed(url: str) -> dict | None:
    """Scores 0-100 for mobile speed, accessibility, SEO and best practices, plus load time."""
    params = [("url", url), ("strategy", "mobile")] + [("category", c) for c in
                                                       ("performance", "accessibility", "seo", "best-practices")]
    key = get_settings().google_api_key
    if key:
        params.append(("key", key))
    data = await get_json(PSI, params=params, timeout=90.0)
    if not data:
        return None
    lh = data.get("lighthouseResult") or {}
    cats = lh.get("categories") or {}

    def score(k: str) -> int | None:
        v = (cats.get(k) or {}).get("score")
        return round(v * 100) if isinstance(v, (int, float)) else None

    lcp = ((lh.get("audits") or {}).get("largest-contentful-paint") or {}).get("numericValue")
    return {"performance": score("performance"), "accessibility": score("accessibility"), "seo": score("seo"),
            "best_practices": score("best-practices"), "lcp_s": round(lcp / 1000, 1) if isinstance(lcp, (int, float)) else None}


async def _txt(name: str, kind: str = "TXT") -> list[str] | None:
    data = await get_json(DOH, params={"name": name, "type": kind}, timeout=10.0)
    if data is None:
        return None
    return [str(a.get("data", "")).strip('"').replace('" "', "") for a in data.get("Answer") or []]


async def email_auth(domain: str) -> dict | None:
    """Whether mail from the domain is authenticated: SPF, DKIM (common selectors) and DMARC."""
    mx, spf_txt, dmarc_txt = await asyncio.gather(_txt(domain, "MX"), _txt(domain), _txt(f"_dmarc.{domain}"))
    if mx is None and spf_txt is None:
        return None
    spf = next((t for t in spf_txt or [] if t.lower().startswith("v=spf1")), None)
    dmarc = next((t for t in dmarc_txt or [] if t.lower().startswith("v=dmarc1")), None)
    policy = None
    if dmarc:
        m = re.search(r"\bp=(\w+)", dmarc, re.I)
        policy = m.group(1).lower() if m else None
    dkim_hits = await asyncio.gather(*[_txt(f"{sel}._domainkey.{domain}") for sel in DKIM_SELECTORS])
    dkim = [sel for sel, recs in zip(DKIM_SELECTORS, dkim_hits) if recs and any("p=" in r or "k=" in r for r in recs)]
    return {"mx": bool(mx), "spf": bool(spf), "dkim": bool(dkim), "dkim_selectors": dkim, "dmarc": bool(dmarc),
            "dmarc_policy": policy}


async def cert_days(domain: str) -> int | None:
    """Days until the website's certificate expires."""
    try:
        await _assert_public(f"https://{domain}")
        ctx = ssl.create_default_context()
        _, writer = await asyncio.wait_for(asyncio.open_connection(domain, 443, ssl=ctx, server_hostname=domain), 10)
        cert = writer.get_extra_info("peercert") or {}
        writer.close()
        if not cert.get("notAfter"):
            return None
        expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), UTC)
        return (expires - datetime.now(UTC)).days
    except Exception:
        return None


def registrable(domain: str) -> str:
    parts = domain.split(".")
    if len(parts) > 2 and parts[-2] in ("co", "com", "org", "net", "ac", "gov", "edu") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


async def domain_days(domain: str) -> int | None:
    """Days until the domain registration expires, from RDAP."""
    data = await get_json(f"https://rdap.org/domain/{registrable(domain)}", timeout=15.0)
    for e in (data or {}).get("events") or []:
        if e.get("eventAction") == "expiration" and e.get("eventDate"):
            try:
                when = datetime.fromisoformat(e["eventDate"].replace("Z", "+00:00"))
                return (when - datetime.now(UTC)).days
            except ValueError:
                return None
    return None


async def security(domain: str) -> dict:
    https_ok, redirects, hsts = False, False, False
    try:
        await _assert_public(f"https://{domain}")
        async with client(15.0, follow=False) as c:
            r = await c.get(f"https://{domain}/")
            https_ok = r.status_code < 400 or r.is_redirect
            hsts = "strict-transport-security" in r.headers
            plain = await c.get(f"http://{domain}/")
            redirects = plain.is_redirect and plain.headers.get("location", "").startswith("https://")
    except Exception:
        pass
    cert, expires = await asyncio.gather(cert_days(domain), domain_days(domain))
    return {"https": https_ok, "redirects_to_https": redirects, "hsts": hsts, "cert_days": cert, "domain_days": expires}


# What a page runs, by the scripts and links it loads.
TOOLS: dict[str, dict[str, list[str]]] = {
    "analytics": {"Google Analytics": ["googletagmanager.com/gtag/js", "google-analytics.com"],
                  "Google Tag Manager": ["googletagmanager.com/gtm.js"], "Plausible": ["plausible.io/js"],
                  "Matomo": ["matomo.js", "piwik.js"], "Segment": ["cdn.segment.com"], "Hotjar": ["static.hotjar.com"],
                  "Mixpanel": ["cdn.mxpnl.com", "mixpanel"], "PostHog": ["posthog"]},
    "ad_pixels": {"Meta Pixel": ["connect.facebook.net", "fbq("], "LinkedIn Insight": ["snap.licdn.com"],
                  "Google Ads": ["googleadservices.com", "AW-"], "TikTok Pixel": ["analytics.tiktok.com"]},
    "consent": {"Cookiebot": ["cookiebot"], "OneTrust": ["onetrust", "cookielaw.org"], "Usercentrics": ["usercentrics"],
                "CookieYes": ["cookieyes"], "Termly": ["termly.io"], "iubenda": ["iubenda"], "Didomi": ["didomi"],
                "Osano": ["osano"], "Complianz": ["complianz"]},
    "chat": {"Intercom": ["widget.intercom.io", "intercomcdn"], "Drift": ["js.driftt.com"], "Crisp": ["client.crisp.chat"],
             "HubSpot chat": ["js.usemessages.com"], "Zendesk": ["static.zdassets.com"], "Tawk.to": ["embed.tawk.to"],
             "LiveChat": ["cdn.livechatinc.com"], "Tidio": ["code.tidio.co"]},
    "booking": {"Calendly": ["calendly.com"], "Cal.com": ["cal.com/"], "HubSpot meetings": ["meetings.hubspot.com"],
                "SavvyCal": ["savvycal.com"], "Chili Piper": ["chilipiper.com"]},
    "forms": {"HubSpot": ["js.hsforms.net", "js.hs-scripts.com"], "Pardot": ["pi.pardot.com"], "Marketo": ["munchkin.marketo"],
              "Typeform": ["typeform.com"], "Tally": ["tally.so"]},
}


def page_tools(html: str) -> dict[str, list[str]]:
    low = (html or "").lower()
    return {kind: [name for name, marks in tools.items() if any(m.lower() in low for m in marks)]
            for kind, tools in TOOLS.items()}


async def home_html(url: str) -> str | None:
    try:
        async with client(20.0, follow=False) as c:
            got = await _get(c, url)
            return got[1] if got else None
    except (UnsafeURL, Exception):
        return None


HREF = re.compile(r"""<a\s[^>]*href\s*=\s*["']([^"'#]+)""", re.I)


async def broken_links(url: str) -> dict | None:
    """Crawl up to MAX_PAGES pages of the site and check up to MAX_LINKS links found on them."""
    site = host(url)
    pages, seen_pages, links = [url], set(), {}  # link -> page it was found on
    try:
        async with client(15.0, follow=False) as c:
            while pages and len(seen_pages) < MAX_PAGES:
                page = pages.pop(0)
                if page in seen_pages:
                    continue
                seen_pages.add(page)
                try:
                    got = await _get(c, page)
                except (UnsafeURL, Exception):
                    got = None
                if not got:
                    continue
                final, html = got
                for raw in HREF.findall(html):
                    link = urljoin(final, raw.strip()).split("#")[0]
                    if urlparse(link).scheme not in ("http", "https"):
                        continue
                    if len(links) < MAX_LINKS:
                        links.setdefault(link, final)
                    if host(link) == site and link not in seen_pages and len(pages) < MAX_PAGES * 3:
                        pages.append(link)
            sem = asyncio.Semaphore(8)

            async def check(link: str) -> tuple[str, int | None]:
                async with sem:
                    try:
                        await _assert_public(link)
                        r = await c.head(link)
                        if r.status_code in (405, 501):
                            r = await c.get(link)
                        if r.is_redirect and r.headers.get("location"):
                            target = urljoin(link, r.headers["location"])
                            await _assert_public(target)
                            r = await c.head(target)
                        return link, r.status_code
                    except UnsafeURL:
                        return link, 0
                    except Exception:
                        return link, None

            results = await asyncio.gather(*[check(link) for link in links])
    except Exception:
        return None
    broken = []
    for link, status in results:
        internal = host(link) == site
        # 401/403/429 usually mean "no bots", not a broken page; unreachable outside sites are skipped.
        if (status in (404, 410) or (status or 0) >= 500) or (status is None and internal):
            broken.append({"url": link, "status": status, "on": links[link], "internal": internal})
    return {"pages": len(seen_pages), "checked": len(results), "broken": broken[:25], "broken_count": len(broken)}
