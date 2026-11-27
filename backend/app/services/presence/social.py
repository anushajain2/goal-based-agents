"""Real post counts for LinkedIn and X accounts, from Apify.

LinkedIn and X show almost nothing to a logged-out reader, so reading public pages leaves most
accounts uncounted. With APIFY_TOKEN set, each account's last 30 days of posts are fetched by
two Apify Store actors (no cookies, no one's account used) and counted exactly:

* LinkedIn (company pages and people): harvestapi/linkedin-company-posts, which takes both.
* X: apidojo/tweet-scraper, one search per handle for its own posts since the start date.

Both runs go at once; a run that fails leaves those accounts as they were.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from email.utils import parsedate_to_datetime

from app.config import get_settings

from .http import get_json, post_json

log = logging.getLogger(__name__)

API = "https://api.apify.com/v2"
LINKEDIN_ACTOR = "harvestapi~linkedin-company-posts"
X_ACTOR = "apidojo~tweet-scraper"
# What a run costs, from the actors' Store prices (pay per result), for the setup cost shown.
LINKEDIN_PER_POST = Decimal("0.002")
X_PER_TWEET = Decimal("0.0004")
PER_RUN = Decimal("0.001")
DAYS = 30
MAX_POSTS = 60  # per account: enough for anyone posting twice a day
WAIT_SECONDS = 150


def enabled() -> bool:
    return bool(get_settings().apify_token)


def linkedin_url(url: str) -> str | None:
    """A LinkedIn company or person URL in one form, or None."""
    m = re.search(r"linkedin\.com/(company|school|showcase|in)/([^/?#\s]+)", url or "", re.IGNORECASE)
    return f"https://www.linkedin.com/{m.group(1).lower()}/{m.group(2).strip().lower()}" if m else None


def x_handle(url: str) -> str | None:
    raw = (url or "").strip()
    m = re.search(r"(?:x|twitter)\.com/@?([A-Za-z0-9_]{1,15})", raw, re.IGNORECASE)
    if m:
        h = m.group(1)
    elif re.fullmatch(r"@?[A-Za-z0-9_]{1,15}", raw):
        h = raw.lstrip("@")
    else:
        return None
    return None if h.lower() in {"intent", "share", "home", "i", "search", "hashtag"} else h.lower()


async def _run(actor: str, run_input: dict, fields: str) -> list[dict] | None:
    """Run an actor, wait for it, and return its items (None if it didn't finish)."""
    headers = {"Authorization": f"Bearer {get_settings().apify_token}"}
    started = await post_json(f"{API}/acts/{actor}/runs", run_input, headers=headers,
                              params={"waitForFinish": 60}, timeout=75.0)
    run = (started or {}).get("data") or {}
    waited = 60
    while run.get("id") and run.get("status") in {"READY", "RUNNING"} and waited < WAIT_SECONDS:
        polled = await get_json(f"{API}/actor-runs/{run['id']}", params={"waitForFinish": 45},
                                headers=headers, timeout=60.0)
        run = (polled or {}).get("data") or run
        waited += 45
    if run.get("status") != "SUCCEEDED":
        log.info("apify %s ended %s", actor, run.get("status") or "without starting")
        return None
    items = await get_json(f"{API}/datasets/{run['defaultDatasetId']}/items", headers=headers, timeout=60.0,
                           params={"clean": "true", "fields": fields, "limit": 5000})
    return items if isinstance(items, list) else None


def _when(value) -> datetime | None:
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=UTC)
        if isinstance(value, str) and value[:4].isdigit():
            return datetime.fromisoformat(value)
        if isinstance(value, str):
            return parsedate_to_datetime(value)  # X: "Fri Nov 27 08:54:10 +0000 2026"
    except (ValueError, TypeError, OverflowError):
        return None
    return None


def _get(item: dict, dotted: str):
    if dotted in item:  # "fields" flattens nested names
        return item[dotted]
    cur = item
    for part in dotted.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def _num(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


async def _linkedin(urls: list[str], since: datetime) -> dict[str, list[dict]] | None:
    items = await _run(LINKEDIN_ACTOR, {
        "targetUrls": urls, "maxPosts": MAX_POSTS, "postedLimit": "month",
        "includeReposts": False, "includeQuotePosts": True, "scrapeReactions": False, "scrapeComments": False,
    }, "type,linkedinUrl,postedAt,engagement,postVideo,query")
    if items is None:
        return None
    out: dict[str, list[dict]] = {u: [] for u in urls}
    for it in items:
        target = linkedin_url(str(_get(it, "query.targetUrl") or ""))
        when = _when(_get(it, "postedAt.timestamp") or _get(it, "postedAt.date"))
        if target not in out or (it.get("type") and it.get("type") != "post") or not when or when < since:
            continue
        out[target].append({"url": it.get("linkedinUrl") or "", "at": when, "video": bool(_get(it, "postVideo.videoUrl")),
                            "engagement": _num(_get(it, "engagement.likes")) + _num(_get(it, "engagement.comments"))})
    return out


async def _x(handles: list[str], since: datetime) -> dict[str, list[dict]] | None:
    day = since.date().isoformat()
    items = await _run(X_ACTOR, {
        "searchTerms": [f"from:{h} since:{day} -filter:replies -filter:retweets" for h in handles],
        "maxItems": MAX_POSTS * len(handles), "sort": "Latest",
    }, "url,createdAt,isRetweet,isReply,likeCount,replyCount,author,extendedEntities")
    if items is None:
        return None
    out: dict[str, list[dict]] = {h: [] for h in handles}
    for it in items:
        who = str(_get(it, "author.userName") or "").lower()
        when = _when(it.get("createdAt"))
        if who not in out or it.get("isRetweet") or it.get("isReply") or not when or when < since:
            continue
        media = _get(it, "extendedEntities.media") or []
        out[who].append({"url": it.get("url") or "", "at": when,
                         "video": any(isinstance(m, dict) and m.get("type") == "video" for m in media),
                         "engagement": _num(it.get("likeCount")) + _num(it.get("replyCount"))})
    return out


def _x_of(a: dict, linked_x: set[str] | None) -> str | None:
    """The account's X handle, if it's an x.com URL or a handle a company's site links to."""
    url = str(a.get("url") or "")
    h = x_handle(url)
    if h and (re.search(r"(?:x|twitter)\.com/", url, re.I) or h in (linked_x or set())):
        return h
    return None


async def count_posts(accounts: list[dict], linked_x: set[str] | None = None) -> tuple[list[dict], Decimal]:
    """The same accounts, with posts_30d and engagement_30d counted from their actual posts.

    Accounts Apify can't place (no usable URL, or a bare X handle no site links to) or whose
    run failed come back unchanged."""
    if not enabled():
        return accounts, Decimal(0)
    since = datetime.now(UTC) - timedelta(days=DAYS)
    li = sorted({u for a in accounts if a.get("platform") == "linkedin" and (u := linkedin_url(a.get("url") or ""))})
    xs = sorted({h for a in accounts if a.get("platform") == "x" and (h := _x_of(a, linked_x))})

    async def none():
        return None

    li_posts, x_posts = await asyncio.gather(_linkedin(li, since) if li else none(), _x(xs, since) if xs else none(),
                                             return_exceptions=True)
    li_posts = li_posts if isinstance(li_posts, dict) else None
    x_posts = x_posts if isinstance(x_posts, dict) else None
    cost = Decimal(0)
    if li_posts is not None:
        cost += PER_RUN + LINKEDIN_PER_POST * sum(len(v) for v in li_posts.values())
    if x_posts is not None:
        cost += PER_RUN + X_PER_TWEET * sum(len(v) for v in x_posts.values())

    out = []
    for a in accounts:
        key, found = None, None
        if a.get("platform") == "linkedin" and li_posts is not None:
            key = linkedin_url(a.get("url") or "")
            found = li_posts.get(key) if key else None
        elif a.get("platform") == "x" and x_posts is not None:
            key = _x_of(a, linked_x)
            found = x_posts.get(key) if key else None
        if found is None:
            out.append(a)
            continue
        videos = sum(1 for p in found if p["video"])
        out.append({**a, "url": a.get("url") or key, "coverage": "partial" if len(found) >= MAX_POSTS else "verified",
                    "posts_30d": len(found), "engagement_30d": sum(p["engagement"] for p in found),
                    "videos_30d": videos, "source": "apify",
                    "note": (f"Counted from {len(found)} public post{'s' if len(found) != 1 else ''} in the last {DAYS} days"
                             + (f", {videos} with video" if videos else "") if found
                             else f"No posts in the last {DAYS} days")})
    return out, cost
