"""Real Google results through SerpApi: rankings by country and city, AI Overviews, local (Maps)
results, Google Play apps, the Ads Transparency Center, and how often a brand comes up on Reddit."""

from __future__ import annotations

from app.config import get_settings

from .http import get_json, host

BASE = "https://serpapi.com/search.json"


def enabled() -> bool:
    return bool(get_settings().serpapi_key)


async def _call(params: dict) -> dict | None:
    key = get_settings().serpapi_key
    if not key:
        return None
    return await get_json(BASE, params={**params, "api_key": key}, timeout=40.0)


async def search(q: str, gl: str = "us", hl: str = "en", location: str | None = None,
                 device: str = "desktop") -> dict | None:
    """Organic results in order, the AI Overview (shown, sources, text) and local results."""
    params = {"engine": "google", "q": q, "gl": gl, "hl": hl, "num": 10, "device": device}
    if location:
        params["location"] = location
    data = await _call(params)
    if data is None:
        return None
    organic = [{"title": r.get("title") or "", "url": r["link"], "domain": host(r["link"])}
               for r in data.get("organic_results") or [] if r.get("link")]
    overview = data.get("ai_overview") or None
    if overview and overview.get("page_token") and not overview.get("text_blocks"):
        overview = (await _call({"engine": "google_ai_overview", "page_token": overview["page_token"]}) or {}).get("ai_overview")
    ai = None
    if overview:
        refs = overview.get("references") or []
        text = " ".join(_block_text(b) for b in overview.get("text_blocks") or [])
        ai = {"shown": True, "domains": [host(r.get("link", "")) for r in refs if r.get("link")], "text": text[:2000]}
    local = data.get("local_results") or {}
    places = local.get("places") if isinstance(local, dict) else local
    return {
        "organic": organic,
        "ai_overview": ai,
        "local": [_place(p) for p in places or []],
        "total_results": (data.get("search_information") or {}).get("total_results"),
    }


def _block_text(b: dict) -> str:
    parts = [b.get("snippet") or ""]
    for item in b.get("list") or []:
        parts.append(item.get("snippet") or item.get("title") or "")
    return " ".join(p for p in parts if p)


def _place(p: dict) -> dict:
    links = p.get("links") or {}
    return {"title": p.get("title") or "", "rating": p.get("rating"), "reviews": p.get("reviews"),
            "website": host(links.get("website") or p.get("website") or "")}


async def ads_count(domain: str, region: str | None = None) -> int | None:
    """How many ads a domain has in Google's Ads Transparency Center."""
    params = {"engine": "google_ads_transparency_center", "text": domain}
    if region:
        params["region"] = region
    data = await _call(params)
    if data is None:
        return None
    total = (data.get("search_information") or {}).get("total_results")
    return int(total) if isinstance(total, (int, float)) else len(data.get("ad_creatives") or [])


async def play_app(name: str, gl: str = "us") -> dict | None:
    """The company's Android app on Google Play, if it has one: rating and title."""
    data = await _call({"engine": "google_play", "q": name, "store": "apps", "gl": gl})
    if data is None:
        return None
    items = []
    for block in data.get("organic_results") or []:
        items += block.get("items") or []
    for it in items[:10]:
        author = (it.get("author") or "").lower()
        if name.lower() in author or name.lower() in (it.get("title") or "").lower():
            return {"title": it.get("title"), "rating": it.get("rating"), "store": "Google Play"}
    return None


async def reddit_mentions(brand: str) -> int | None:
    data = await _call({"engine": "google", "q": f'"{brand}" site:reddit.com', "num": 10})
    if data is None:
        return None
    total = (data.get("search_information") or {}).get("total_results")
    return int(total) if isinstance(total, (int, float)) else len(data.get("organic_results") or [])
