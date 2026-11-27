"""LinkedIn and X post counts from Apify, against a fake Apify."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.agent.opportunities import social_rows
from app.config import get_settings
from app.services.presence import http, social

NOW = datetime.now(UTC)


def ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


LINKEDIN = [  # what harvestapi/linkedin-company-posts returns (fields we ask for)
    {"type": "post", "linkedinUrl": "https://linkedin.com/posts/a1", "query": {"targetUrl": "https://www.linkedin.com/company/acme"},
     "postedAt": {"timestamp": int(ago(2).timestamp() * 1000)}, "engagement": {"likes": 10, "comments": 2},
     "postVideo": {"videoUrl": "https://v"}},
    {"type": "post", "linkedinUrl": "https://linkedin.com/posts/a2", "query": {"targetUrl": "https://www.linkedin.com/company/acme"},
     "postedAt": {"date": ago(10).isoformat()}, "engagement": {"likes": 5, "comments": 0}},
    {"type": "post", "linkedinUrl": "https://linkedin.com/posts/old", "query": {"targetUrl": "https://www.linkedin.com/company/acme"},
     "postedAt": {"date": ago(40).isoformat()}, "engagement": {"likes": 99, "comments": 9}},
    {"type": "post", "linkedinUrl": "https://linkedin.com/posts/r1", "query": {"targetUrl": "https://www.linkedin.com/in/rita"},
     "postedAt": {"date": ago(1).isoformat()}, "engagement": {"likes": 300, "comments": 40}},
]
X = [  # what apidojo/tweet-scraper returns
    {"url": "https://x.com/routeco/status/1", "createdAt": ago(3).strftime("%a %b %d %H:%M:%S +0000 %Y"),
     "author": {"userName": "RouteCo"}, "isRetweet": False, "isReply": False, "likeCount": 7, "replyCount": 1},
    {"url": "https://x.com/routeco/status/2", "createdAt": ago(4).strftime("%a %b %d %H:%M:%S +0000 %Y"),
     "author": {"userName": "routeco"}, "isRetweet": True, "isReply": False, "likeCount": 500, "replyCount": 0},
]


@pytest.fixture
def apify(monkeypatch):
    monkeypatch.setattr(get_settings(), "apify_token", "test-token")
    seen: dict = {"inputs": {}, "auth": set()}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.apify.com"
        seen["auth"].add(request.headers.get("authorization"))
        path = request.url.path
        if path.endswith("/runs"):
            actor = path.split("/")[3]
            seen["inputs"][actor] = json.loads(request.content)
            return httpx.Response(201, json={"data": {"id": actor, "status": "SUCCEEDED", "defaultDatasetId": actor}})
        if path.startswith("/v2/datasets/"):
            actor = path.split("/")[3]
            if seen.get("fail") == actor:
                return httpx.Response(500)
            return httpx.Response(200, json=LINKEDIN if "linkedin" in actor else X)
        return httpx.Response(404)

    monkeypatch.setattr(http, "transport", httpx.MockTransport(handler))
    return seen


ACCOUNTS = [
    {"company": "Acme", "who": "company", "name": "Acme", "platform": "linkedin", "url": "linkedin.com/company/Acme/",
     "coverage": "blocked", "posts_30d": None, "engagement_30d": None, "note": "Login wall"},
    {"company": "Acme", "who": "company", "name": "Acme", "platform": "x", "url": "https://x.com/acme",
     "coverage": "blocked", "posts_30d": None, "engagement_30d": None, "note": ""},
    {"company": "Routeco", "who": "company", "name": "Routeco", "platform": "x", "url": "@RouteCo",
     "coverage": "partial", "posts_30d": 2, "engagement_30d": 3, "note": ""},
    {"company": "Routeco", "who": "founder", "name": "Rita Route", "platform": "linkedin",
     "url": "https://www.linkedin.com/in/rita?trk=x", "coverage": "blocked", "posts_30d": None, "engagement_30d": None, "note": ""},
    {"company": "Routeco", "who": "company", "name": "Routeco", "platform": "linkedin", "url": "",
     "coverage": "blocked", "posts_30d": None, "engagement_30d": None, "note": "Not found"},
]


async def test_counts_each_accounts_posts_from_the_last_30_days(apify):
    accounts, cost = await social.count_posts(ACCOUNTS)
    acme_li, acme_x, route_x, rita, route_li = accounts
    # Only posts from the last 30 days; likes plus comments.
    assert (acme_li["posts_30d"], acme_li["engagement_30d"], acme_li["coverage"]) == (2, 17, "verified")
    assert acme_li["videos_30d"] == 1 and "2 public posts" in acme_li["note"] and "1 with video" in acme_li["note"]
    assert (rita["posts_30d"], rita["engagement_30d"]) == (1, 340)
    # A retweet isn't the account's own post; handles match whatever their case.
    assert (route_x["posts_30d"], route_x["engagement_30d"], route_x["coverage"]) == (1, 8, "verified")
    # An account with no posts in 30 days is a real zero, not unknown.
    assert (acme_x["posts_30d"], acme_x["coverage"], acme_x["note"]) == (0, "verified", "No posts in the last 30 days")
    # An account with no URL is left as it was.
    assert route_li == ACCOUNTS[4]
    # One LinkedIn run (companies and people together) and one X run, own posts only.
    li_in = apify["inputs"]["harvestapi~linkedin-company-posts"]
    assert li_in["targetUrls"] == ["https://www.linkedin.com/company/acme", "https://www.linkedin.com/in/rita"]
    assert li_in["includeReposts"] is False and li_in["postedLimit"] == "month"
    x_in = apify["inputs"]["apidojo~tweet-scraper"]
    assert [t.split(" since:")[0] for t in x_in["searchTerms"]] == ["from:acme", "from:routeco"]
    assert all("-filter:retweets" in t and "-filter:replies" in t for t in x_in["searchTerms"])
    # The token goes in a header, never the URL; the cost is counted.
    assert apify["auth"] == {"Bearer test-token"}
    assert cost == Decimal("0.001") * 2 + Decimal("0.002") * 3 + Decimal("0.0004") * 1


async def test_a_failed_run_leaves_those_accounts_alone(apify):
    apify["fail"] = "apidojo~tweet-scraper"
    accounts, _ = await social.count_posts(ACCOUNTS)
    assert accounts[0]["posts_30d"] == 2  # LinkedIn still counted
    assert accounts[1] == ACCOUNTS[1] and accounts[2] == ACCOUNTS[2]


async def test_without_a_token_nothing_is_called(monkeypatch):
    monkeypatch.setattr(get_settings(), "apify_token", None)

    def handler(request):
        raise AssertionError("no network without a token")

    monkeypatch.setattr(http, "transport", httpx.MockTransport(handler))
    assert await social.count_posts(ACCOUNTS) == (ACCOUNTS, Decimal(0))


async def test_scorecard_says_the_numbers_were_counted(apify):
    accounts, _ = await social.count_posts(ACCOUNTS)
    rows = social_rows({"accounts": accounts}, "Acme", [{"name": "Routeco", "domain": "routeco.test"}])
    li = next(r for r in rows if r["key"] == "social_linkedin")
    assert li["you"]["display"] == "2 posts · 17 likes and comments"
    assert li["note"] == "Counted from each account's public posts"


def test_urls_and_handles():
    assert social.linkedin_url("https://uk.linkedin.com/company/Acme-Inc/about/") == "https://www.linkedin.com/company/acme-inc"
    assert social.linkedin_url("https://example.com") is None
    assert social.x_handle("https://twitter.com/Acme_HQ?lang=en") == "acme_hq"
    assert social.x_handle("@acme") == "acme" and social.x_handle("x.com/intent/tweet") is None
