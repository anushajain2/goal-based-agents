"""One HTTP client for every market check, so tests can swap the network for a fake one."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

# Tests set this to an httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None

UA = "Mozilla/5.0 (compatible; AutopilotBot/1.0; company health check)"


def client(timeout: float = 20.0, follow: bool = True) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(timeout, connect=8.0),
                             headers={"User-Agent": UA}, follow_redirects=follow)


async def get_json(url: str, params: dict | None = None, headers: dict | None = None,
                   timeout: float = 20.0) -> Any | None:
    """GET and parse JSON. None on any failure (a missing number never breaks the scan)."""
    try:
        async with client(timeout) as c:
            r = await c.get(url, params=params, headers=headers)
            if r.status_code >= 400:
                log.info("market check %s returned %s", urlparse(url).netloc, r.status_code)
                return None
            return r.json()
    except Exception as e:  # network, timeouts, bad JSON
        log.info("market check %s failed: %s", urlparse(url).netloc, e)
        return None


async def post_json(url: str, json: Any, headers: dict | None = None, auth: tuple[str, str] | None = None,
                    params: dict | None = None, timeout: float = 60.0) -> Any | None:
    try:
        async with client(timeout) as c:
            r = await c.post(url, json=json, headers=headers, auth=auth, params=params)
            if r.status_code >= 400:
                log.info("market check %s returned %s", urlparse(url).netloc, r.status_code)
                return None
            return r.json()
    except Exception as e:
        log.info("market check %s failed: %s", urlparse(url).netloc, e)
        return None


def host(url_or_domain: str) -> str:
    raw = (url_or_domain or "").strip().lower()
    if not raw:
        return ""
    netloc = urlparse(raw if "://" in raw else "https://" + raw).netloc
    return netloc.split(":")[0].removeprefix("www.")


def same_site(a: str, b: str) -> bool:
    """example.com matches blog.example.com."""
    return bool(a and b) and (a == b or a.endswith("." + b) or b.endswith("." + a))
