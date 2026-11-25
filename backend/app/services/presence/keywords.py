"""Search volume and keyword difficulty through DataForSEO: how many people search each query a
month in a country, and how hard it is to rank for (0-100). Makes SEO estimates real."""

from __future__ import annotations

from app.config import get_settings

from .http import post_json

BASE = "https://api.dataforseo.com/v3"


def enabled() -> bool:
    s = get_settings()
    return bool(s.dataforseo_login and s.dataforseo_password)


async def volumes(keywords: list[str], country: str, language: str) -> tuple[dict[str, dict], int]:
    """{keyword: {"volume": int|None, "difficulty": int|None}} and the number of paid calls made."""
    s = get_settings()
    if not enabled() or not keywords:
        return {}, 0
    auth = (s.dataforseo_login, s.dataforseo_password)
    task = [{"keywords": keywords, "location_name": country, "language_code": language}]
    out: dict[str, dict] = {k: {"volume": None, "difficulty": None} for k in keywords}
    vol = await post_json(f"{BASE}/keywords_data/google_ads/search_volume/live", task, auth=auth)
    for t in (vol or {}).get("tasks") or []:
        for r in t.get("result") or []:
            if r.get("keyword") in out:
                out[r["keyword"]]["volume"] = r.get("search_volume")
    diff = await post_json(f"{BASE}/dataforseo_labs/google/bulk_keyword_difficulty/live",
                           [{"keywords": keywords, "location_name": country, "language_code": language}], auth=auth)
    for t in (diff or {}).get("tasks") or []:
        for r in t.get("result") or []:
            for item in r.get("items") or []:
                if item.get("keyword") in out:
                    out[item["keyword"]]["difficulty"] = item.get("keyword_difficulty")
    return out, 2
