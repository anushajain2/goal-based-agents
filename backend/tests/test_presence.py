"""Market presence, measured: real Google results by country and the website/domain scorecard,
against a fake internet."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.config import get_settings
from app.services import presence
from app.services.presence import http

QA, QB = "route planning software", "fleet routing tool"
COMPS = [{"name": "Routeco", "domain": "routeco.test"}]
MARKETS = [{"label": "Germany", "gl": "de", "hl": "de"}, {"label": "Netherlands", "gl": "nl", "hl": "nl"}]


def organic(*urls):
    return {"organic_results": [{"title": u, "link": u} for u in urls]}


def handler(request: httpx.Request) -> httpx.Response:
    u, p = request.url, request.url.params
    if u.host == "serpapi.com":
        engine = p.get("engine")
        if engine == "google_ads_transparency_center":
            return httpx.Response(200, json={"search_information": {"total_results": 42 if p["text"] == "routeco.test" else 0}})
        if engine == "google_play":
            return httpx.Response(200, json={"organic_results": []})
        q, gl = p.get("q"), p.get("gl")
        if "site:reddit.com" in q:
            return httpx.Response(200, json={"search_information": {"total_results": 300 if "Routeco" in q else 4}})
        if p.get("location"):  # local results
            return httpx.Response(200, json={"local_results": {"places": [
                {"title": "Routeco Depot", "rating": 4.8, "reviews": 210, "links": {"website": "https://routeco.test"}}]}})
        if (q, gl) == (QA, "de"):
            return httpx.Response(200, json={**organic("https://routeco.test/a", "https://www.acme.test/routing"),
                                             "ai_overview": {"text_blocks": [{"snippet": "Popular options include Routeco."}],
                                                             "references": [{"link": "https://routeco.test/a"}]}})
        if (q, gl) == (QA, "nl"):
            return httpx.Response(200, json=organic("https://routeco.test/nl", "https://other.test/"))
        return httpx.Response(200, json=organic("https://acme.test/", "https://routeco.test/"))
    if u.host == "api.dataforseo.com":
        if "search_volume" in u.path:
            return httpx.Response(200, json={"tasks": [{"result": [{"keyword": QA, "search_volume": 1900},
                                                                   {"keyword": QB, "search_volume": 320}]}]})
        return httpx.Response(200, json={"tasks": [{"result": [{"items": [{"keyword": QA, "keyword_difficulty": 54}]}]}]})
    if "pagespeedonline" in u.path:
        fast = "routeco" in p["url"]
        s = 0.92 if fast else 0.38
        return httpx.Response(200, json={"lighthouseResult": {
            "categories": {"performance": {"score": s}, "accessibility": {"score": 0.95 if fast else 0.71},
                           "seo": {"score": 0.9}, "best-practices": {"score": 0.9}},
            "audits": {"largest-contentful-paint": {"numericValue": 1800 if fast else 7400}}}})
    if u.host == "dns.google":
        name, kind = p["name"], p["type"]
        if name == "acme.test" and kind == "MX":
            return httpx.Response(200, json={"Answer": [{"data": "10 mx.acme.test."}]})
        if name == "acme.test" and kind == "TXT":
            return httpx.Response(200, json={"Answer": [{"data": '"v=spf1 include:_spf.google.com ~all"'}]})
        return httpx.Response(200, json={"Status": 3})
    if u.host == "rdap.org":
        when = (datetime.now(UTC) + timedelta(days=20, hours=1)).isoformat().replace("+00:00", "Z")
        return httpx.Response(200, json={"events": [{"eventAction": "expiration", "eventDate": when}]})
    if u.host == "tranco-list.eu":
        return httpx.Response(200, json={"ranks": [{"rank": 150000}]} if "routeco" in u.path else {"ranks": []})
    if u.host == "openpagerank.com":
        return httpx.Response(200, json={"response": [{"domain": "acme.test", "page_rank_decimal": 2.1},
                                                      {"domain": "routeco.test", "page_rank_decimal": 4.8}]})
    if u.host == "en.wikipedia.org":
        hit = "Routeco" in p["srsearch"]
        return httpx.Response(200, json={"query": {"search": [{"title": "Routeco"}] if hit else []}})
    if u.host == "www.googleapis.com" and "youtube" in u.path:
        if u.path.endswith("/search") and p.get("type") == "channel":
            items = [{"id": {"channelId": "UC1"}, "snippet": {"channelTitle": "Routeco"}}] if p["q"] == "Routeco" else []
            return httpx.Response(200, json={"items": items})
        if u.path.endswith("/channels"):
            return httpx.Response(200, json={"items": [{"statistics": {"subscriberCount": "5400", "videoCount": "80"}}]})
        return httpx.Response(200, json={"items": [{"snippet": {"publishedAt": "2026-11-01T10:00:00Z"}}]})
    if u.host == "api.openai.com":
        return httpx.Response(200, json={"output_text": '{"answers": [{"query": "route planning software", "recommendations": '
                                                       '[{"name": "Routeco", "domain": "routeco.test"}]}]}'})
    if u.host in ("acme.test", "www.acme.test"):
        if u.scheme == "http":
            return httpx.Response(301, headers={"location": "https://acme.test/"})
        if u.path == "/old-page":
            return httpx.Response(404)
        page = ('<html><head><script src="https://www.googletagmanager.com/gtag/js?id=G-1"></script>'
                '<script src="https://connect.facebook.net/en_US/fbevents.js"></script></head><body>'
                '<a href="/about">About</a><a href="/old-page">Old</a><a href="https://outside.test/x">Out</a>'
                '<a href="https://www.linkedin.com/company/acme-routing/">LinkedIn</a><a href="https://x.com/acmeroutes">X</a>'
                '</body></html>')
        return httpx.Response(200, html=page)
    if u.host == "routeco.test":
        return httpx.Response(200, html='<script src="https://widget.intercom.io/w/x"></script>'
                                       '<a href="https://calendly.com/routeco/demo">Book</a>'
                                       '<iframe src="https://www.youtube.com/embed/launch"></iframe>'
                                       '<a href="https://twitter.com/routeco">X</a>')
    if u.host == "api.x.com":
        if "/users/by/username/" in u.path:
            handle = u.path.rsplit("/", 1)[1]
            return httpx.Response(200, json={"data": {"id": handle, "public_metrics": {"followers_count": 9000 if handle == "routeco" else 120}}})
        if u.path.endswith("/tweets"):
            assert request.headers["authorization"] == "Bearer xt" and p["exclude"] == "retweets,replies"
            busy = "routeco" in u.path
            posts = [{"public_metrics": {"like_count": 40, "reply_count": 8, "retweet_count": 2, "quote_count": 0}}] * (10 if busy else 3)
            if not busy:
                posts = [{"public_metrics": {"like_count": 5, "reply_count": 1, "retweet_count": 0, "quote_count": 0}}] * 3
            return httpx.Response(200, json={"data": posts, "includes": {"media": [{"type": "video"}] if busy else []}})
    if u.host in ("outside.test", "www.linkedin.com", "x.com"):
        return httpx.Response(200, html="ok")
    return httpx.Response(404)


@pytest.fixture
def internet(monkeypatch):
    s = get_settings()
    for key, value in (("serpapi_key", "k"), ("dataforseo_login", "u"), ("dataforseo_password", "p"),
                       ("google_api_key", "g"), ("openpagerank_key", "o"), ("openai_api_key", "x"), ("x_bearer_token", "xt")):
        monkeypatch.setattr(s, key, value)
    monkeypatch.setattr(http, "transport", httpx.MockTransport(handler))


async def test_measures_google_by_country_and_scores_against_competitors(internet):
    m = await presence.measure("Acme", "https://acme.test", COMPS,
                               [{"query": QA, "intent": "ops lead"}, {"query": QB, "intent": "dispatcher"}], MARKETS,
                               {"query": "route planning", "cities": ["Berlin", "Munich"], "gl": "de", "hl": "de"})
    g = {(r["query"], r["market"]): r for r in m["google"]}
    de, nl = g[(QA, "Germany")], g[(QA, "Netherlands")]
    assert (de["rank"], de["competitors_ahead"], de["volume"], de["difficulty"]) == (2, ["Routeco"], 1900, 54)
    assert de["ai_overview"] == {"shown": True, "mentioned": False, "competitors": ["Routeco"]}
    assert (nl["rank"], nl["ai_overview"]) == (None, None)
    assert g[(QB, "Germany")]["rank"] == 1
    assert [(r["city"], r["rank"]) for r in m["local"]] == [("Berlin", None), ("Munich", None)]
    assert m["assistants"] == [{"assistant": "ChatGPT", "query": QA, "rank": None,
                                "recommended": [{"name": "Routeco", "domain": "routeco.test", "you": False, "competitor": True}]}]
    assert m["email"]["spf"] and not m["email"]["dmarc"] and not m["email"]["dkim"]
    assert m["security"]["redirects_to_https"] and 19 <= m["security"]["domain_days"] <= 20
    assert m["links"]["broken_count"] == 1 and m["links"]["broken"][0]["url"] == "https://acme.test/old-page"
    assert m["calls"]["serpapi"] >= 6 and presence.cost(m["calls"]) > 0

    rows = {r["key"]: r for r in presence.scorecard(m)}
    assert rows["speed"]["you"] == {"display": "38/100 · loads in 7.4s", "status": "bad"}
    assert rows["speed"]["others"] == [{"name": "Routeco", "display": "92/100 · loads in 1.8s"}]
    assert rows["authority"]["you"]["status"] == "bad"
    assert rows["popularity"]["you"]["display"] == "Not in the top 1M"
    assert rows["ads_google"]["others"] == [{"name": "Routeco", "display": "42 ads"}]
    assert rows["youtube"]["you"]["display"] == "No channel" and rows["youtube"]["you"]["status"] == "bad"
    assert rows["wikipedia"]["you"]["status"] == "bad"
    assert rows["reddit"]["you"]["status"] == "bad"
    assert rows["chat"]["you"]["status"] == "bad" and rows["chat"]["others"][0]["display"] == "Intercom"
    assert rows["booking"]["you"]["status"] == "bad"
    assert "ad pixels without a cookie consent tool" in rows["tracking"]["you"]["display"]
    assert rows["email_auth"]["you"]["display"].startswith("SPF ✓ · DKIM ✗ · DMARC ✗")
    assert rows["security"]["you"]["status"] == "bad"  # domain renews in 20 days
    assert rows["broken_links"]["you"]["display"].startswith("1 broken of 5 links")
    assert rows["maps"]["you"]["status"] == "bad"
    text = presence.summary(m, list(rows.values()))
    assert 'Google Germany "route planning software": #2, 1,900 searches a month, difficulty 54/100' in text


async def test_without_keys_only_free_checks_run():
    m = await presence.measure("Acme", "https://acme.test", COMPS, [{"query": QA, "intent": ""}], MARKETS, None)
    assert m["google"] == [] and m["assistants"] == [] and m["calls"] == {"serpapi": 0, "dataforseo": 0, "assistants": 0, "x": 0}
    assert presence.cost(m["calls"]) == 0


async def test_social_profiles_launch_video_and_x_against_competitors(internet):
    m = await presence.measure("Acme", "https://acme.test", COMPS, [{"query": QA, "intent": ""}], MARKETS[:1], None)
    you, them = m["sites"]["acme.test"], m["sites"]["routeco.test"]
    assert you["socials"] == {"linkedin": "linkedin.com/company/acme-routing", "x": "acmeroutes"} and you["videos"] == []
    assert them["videos"] == ["YouTube"] and them["socials"]["x"] == "routeco"
    assert you["x"] == {"handle": "acmeroutes", "followers": 120, "posts_30d": 3, "engagement_30d": 18, "videos_30d": 0}
    assert them["x"]["posts_30d"] == 10 and them["x"]["engagement_30d"] == 500 and them["x"]["videos_30d"] == 1
    assert m["calls"]["x"] == 2

    rows = {r["key"]: r for r in presence.scorecard(m)}
    assert rows["video"]["you"] == {"display": "None", "status": "bad"} and rows["video"]["others"][0]["display"] == "YouTube"
    assert rows["x_activity"]["you"] == {"display": "3 posts · 18 likes, replies and reposts", "status": "bad"}
    assert rows["x_activity"]["others"][0]["display"] == "10 posts · 500 likes, replies and reposts · 1 videos"
    text = presence.summary(m, list(rows.values()))
    assert "Social profiles linked from Acme's site (acme.test): linkedin: linkedin.com/company/acme-routing, x: acmeroutes" in text
