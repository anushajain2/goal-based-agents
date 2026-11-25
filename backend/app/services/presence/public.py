"""Public sources about a company's presence, compared with its competitors.

  app_store     Apple's public lookup: the company's iOS app, rating and number of ratings
  youtube       YouTube Data API: subscribers, videos and the date of the latest upload
  wikipedia     whether Wikipedia and Wikidata know the company (AI assistants learn from them)
  popularity    Tranco's ranking of the most visited sites (free, no key)
  authority     Open PageRank's domain authority, 0-10
  meta_ads      ads running on Facebook and Instagram in an EU country (Meta Ad Library)
"""

from __future__ import annotations

import json
import re

from app.config import get_settings

from .http import get_json, host, same_site


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


async def app_store(name: str, domain: str, country: str = "us") -> dict | None:
    data = await get_json("https://itunes.apple.com/search",
                          params={"term": name, "entity": "software", "limit": 8, "country": country})
    for r in (data or {}).get("results") or []:
        seller = _norm(r.get("sellerName", ""))
        if same_site(host(r.get("sellerUrl", "")), domain) or (seller and seller.startswith(_norm(name))):
            return {"title": r.get("trackName"), "rating": round(r["averageUserRating"], 1) if r.get("averageUserRating") else None,
                    "ratings": r.get("userRatingCount"), "updated": (r.get("currentVersionReleaseDate") or "")[:10],
                    "store": "App Store"}
    return None


async def youtube(name: str) -> dict | None:
    key = get_settings().google_api_key
    if not key:
        return None
    found = await get_json("https://www.googleapis.com/youtube/v3/search",
                           params={"part": "snippet", "type": "channel", "q": name, "maxResults": 3, "key": key})
    channel = next((i for i in (found or {}).get("items") or []
                    if _norm(name) in _norm((i.get("snippet") or {}).get("channelTitle", ""))), None)
    if not channel:
        return {"channel": False}
    cid = channel["id"]["channelId"]
    stats = await get_json("https://www.googleapis.com/youtube/v3/channels",
                           params={"part": "statistics", "id": cid, "key": key})
    latest = await get_json("https://www.googleapis.com/youtube/v3/search",
                            params={"part": "snippet", "channelId": cid, "order": "date", "maxResults": 1, "type": "video", "key": key})
    st = ((stats or {}).get("items") or [{}])[0].get("statistics") or {}
    last = ((latest or {}).get("items") or [{}])[0].get("snippet", {}).get("publishedAt", "")[:10]

    def num(v):
        return int(v) if str(v or "").isdigit() else None

    return {"channel": True, "subscribers": num(st.get("subscriberCount")), "videos": num(st.get("videoCount")),
            "last_upload": last or None}


async def wikipedia(name: str) -> dict:
    wp = await get_json("https://en.wikipedia.org/w/api.php",
                        params={"action": "query", "list": "search", "srsearch": f'"{name}"', "format": "json", "srlimit": 3})
    title = next((x["title"] for x in ((wp or {}).get("query") or {}).get("search") or []
                  if _norm(x.get("title", "")).startswith(_norm(name))), None)
    wd = await get_json("https://www.wikidata.org/w/api.php",
                        params={"action": "wbsearchentities", "search": name, "language": "en", "format": "json", "limit": 3})
    item = next((x for x in (wd or {}).get("search") or [] if _norm(x.get("label", "")) == _norm(name)), None)
    return {"wikipedia": title, "wikidata": (item or {}).get("id")}


async def popularity(domain: str) -> int | None:
    """Rank among the world's most visited sites (lower is bigger); None when not in the list."""
    data = await get_json(f"https://tranco-list.eu/api/ranks/domain/{domain}", timeout=15.0)
    ranks = (data or {}).get("ranks") or []
    return ranks[0].get("rank") if ranks else None


async def authority(domains: list[str]) -> dict[str, float | None]:
    key = get_settings().openpagerank_key
    if not key or not domains:
        return {}
    data = await get_json("https://openpagerank.com/api/v1.0/getPageRank",
                          params=[("domains[]", d) for d in domains], headers={"API-OPR": key})
    out: dict[str, float | None] = {}
    for r in (data or {}).get("response") or []:
        v = r.get("page_rank_decimal")
        out[r.get("domain", "")] = round(float(v), 1) if isinstance(v, (int, float)) else None
    return out


EU = {"at", "be", "bg", "hr", "cy", "cz", "dk", "ee", "fi", "fr", "de", "gr", "hu", "ie", "it", "lv", "lt", "lu", "mt", "nl",
      "pl", "pt", "ro", "sk", "si", "es", "se"}


async def meta_ads(brand: str, country: str) -> int | None:
    """Active Facebook/Instagram ads from pages named like the brand (Meta publishes all ads shown in the EU)."""
    token = get_settings().meta_ad_library_token
    if not token:
        return None
    country = country.lower() if country.lower() in EU else "de"
    data = await get_json("https://graph.facebook.com/v21.0/ads_archive", params={
        "search_terms": brand, "ad_reached_countries": json.dumps([country.upper()]), "ad_active_status": "ACTIVE",
        "fields": "page_name", "limit": 100, "access_token": token})
    if data is None:
        return None
    return sum(1 for a in data.get("data") or [] if _norm(brand) in _norm(a.get("page_name", "")))
