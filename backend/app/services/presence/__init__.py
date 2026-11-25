"""Market presence, measured: where a company shows up and how its website and domain hold up,
next to its competitors. Used by setup's "What you're missing out on" (app/agent/opportunities.py).

Every source is the platform's own (keys in .env, see app/config.py). A source without a key is
skipped, and a failed call just leaves its number out; nothing here ever breaks setup.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from app.config import get_settings

from . import assistants, google, keywords, public, site
from .http import host, same_site

SERP_CONCURRENCY = 5


def sources() -> dict[str, bool]:
    s = get_settings()
    return {"google": google.enabled(), "keywords": keywords.enabled(), "pagespeed": True, "youtube": bool(s.google_api_key),
            "authority": bool(s.openpagerank_key), "meta_ads": bool(s.meta_ad_library_token),
            "assistants": bool(assistants.configured())}


def rank(results: list[dict], mine: str, competitors: list[dict]) -> tuple[int | None, list[dict], list[str]]:
    """(the company's position, the results labelled you/competitor, competitors above it)."""
    rows, pos = [], None
    for i, r in enumerate(results, start=1):
        d = r.get("domain") or host(r.get("url", ""))
        who = "you" if same_site(d, mine) else next((c["name"] for c in competitors if same_site(d, host(c["domain"]))), "")
        if who == "you" and pos is None:
            pos = i
        rows.append({"title": (r.get("title") or d)[:120], "url": r.get("url", ""), "domain": d, "who": who})
    ahead: list[str] = []
    for row in rows[: (pos - 1) if pos else len(rows)]:
        if row["who"] and row["who"] != "you" and row["who"] not in ahead:
            ahead.append(row["who"])
    return pos, rows, ahead


def recommendation_rank(recs: list[dict], name: str, mine: str, competitors: list[dict]) -> tuple[int | None, list[dict]]:
    out, pos = [], None
    for i, r in enumerate(recs[:5], start=1):
        d = host(r.get("domain", ""))
        me = same_site(d, mine) or public._norm(r.get("name", "")) == public._norm(name)
        if me and pos is None:
            pos = i
        out.append({"name": str(r.get("name", ""))[:80], "domain": d, "you": me,
                    "competitor": any(same_site(d, host(c["domain"])) for c in competitors if d)})
    return pos, out


async def measure(name: str, website: str, competitors: list[dict], queries: list[dict], markets: list[dict],
                  local: dict | None) -> dict:
    """Everything measurable about the company and its competitors. Returns the raw measurements,
    the paid calls made (for the setup cost) and nothing that isn't backed by a source."""
    mine = host(website)
    url = website if website.startswith("http") else f"https://{mine}"
    comps = competitors[:3]
    sem = asyncio.Semaphore(SERP_CONCURRENCY)
    calls = {"serpapi": 0, "dataforseo": 0, "assistants": 0}

    async def serp(coro):
        async with sem:
            calls["serpapi"] += 1
            return await coro

    async def google_rankings() -> list[dict]:
        if not google.enabled() or not mine:
            return []
        jobs = [(q, m) for m in markets[:3] for q in queries[:4]]
        found = await asyncio.gather(*[serp(google.search(q["query"], m["gl"], m["hl"])) for q, m in jobs])
        out = []
        for (q, m), res in zip(jobs, found):
            if res is None:
                continue
            pos, rows, ahead = rank(res["organic"], mine, comps)
            ai = res.get("ai_overview")
            if ai:
                ai = {"shown": True, "mentioned": any(same_site(d, mine) for d in ai["domains"]) or name.lower() in ai["text"].lower(),
                      "competitors": [c["name"] for c in comps if any(same_site(d, host(c["domain"])) for d in ai["domains"])
                                      or c["name"].lower() in ai["text"].lower()]}
            out.append({"query": q["query"], "intent": q.get("intent", ""), "market": m["label"], "gl": m["gl"],
                        "rank": pos, "checked": len(rows), "results": rows[:6], "competitors_ahead": ahead,
                        "ai_overview": ai, "source": "google"})
        return out

    async def search_volumes() -> dict:
        out = {}
        for m in markets[:3]:
            got, n = await keywords.volumes([q["query"] for q in queries[:4]], m["label"], m["hl"])
            calls["dataforseo"] += n
            for k, v in got.items():
                out[(k, m["label"])] = v
        return out

    async def local_pack() -> list[dict]:
        if not (local and local.get("query") and local.get("cities") and google.enabled()):
            return []
        cities = local["cities"][:3]
        found = await asyncio.gather(*[serp(google.search(f"{local['query']} {c}", local.get("gl", "us"), local.get("hl", "en"), c))
                                       for c in cities])
        out = []
        for city, res in zip(cities, found):
            places = (res or {}).get("local") or []
            if not places:
                continue
            pos = next((i for i, p in enumerate(places, 1) if same_site(p["website"], mine)
                        or public._norm(p["title"]).startswith(public._norm(name))), None)
            rows = [{**p, "you": i == pos, "competitor": any(same_site(p["website"], host(c["domain"])) for c in comps)}
                    for i, p in enumerate(places[:5], 1)]
            out.append({"query": f"{local['query']} {city}", "city": city, "rank": pos, "results": rows})
        return out

    async def other_assistants() -> list[dict]:
        out = []
        for who in assistants.configured():
            calls["assistants"] += 1
            answers = await assistants.ask(who, [q["query"] for q in queries[:4]])
            by_q = {a.get("query", "").strip().lower(): a.get("recommendations") or [] for a in answers}
            for i, q in enumerate(queries[:4]):
                recs = by_q.get(q["query"].lower()) or ((answers[i].get("recommendations") or []) if i < len(answers) else [])
                if not recs:
                    continue
                pos, named = recommendation_rank(recs, name, mine, comps)
                out.append({"assistant": who, "query": q["query"], "rank": pos, "recommended": named})
        return out

    async def per_site(d: str, label: str, me: bool) -> dict:
        home = f"https://{d}" if not me else url
        tasks = {
            "pagespeed": site.pagespeed(home),
            "popularity": public.popularity(d),
            "html": site.home_html(home),
            "app": public.app_store(label, d, (markets[0]["gl"] if markets else "us")),
            "youtube": public.youtube(label),
            "wikipedia": public.wikipedia(label),
        }
        if google.enabled():
            tasks["ads_google"] = serp(google.ads_count(d))
            tasks["reddit"] = serp(google.reddit_mentions(label))
            if me:
                tasks["play"] = serp(google.play_app(label, markets[0]["gl"] if markets else "us"))
        if get_settings().meta_ad_library_token:
            tasks["ads_meta"] = public.meta_ads(label, markets[0]["gl"] if markets else "de")
        values = await asyncio.gather(*tasks.values())
        got = dict(zip(tasks.keys(), values))
        html = got.pop("html")
        got["tools"] = site.page_tools(html) if html else None
        return got

    async def own_domain() -> dict:
        if not mine:
            return {}
        email, sec, links = await asyncio.gather(site.email_auth(mine), site.security(mine), site.broken_links(url))
        return {"email": email, "security": sec, "links": links}

    domains = [mine] + [host(c["domain"]) for c in comps]
    (ranked, volumes, local_rows, others, own, auth, *sites) = await asyncio.gather(
        google_rankings(), search_volumes(), local_pack(), other_assistants(), own_domain(),
        public.authority([d for d in domains if d]),
        *([per_site(mine, name, True)] if mine else []), *[per_site(host(c["domain"]), c["name"], False) for c in comps])
    for row in ranked:
        v = volumes.get((row["query"], row["market"])) or {}
        row["volume"], row["difficulty"] = v.get("volume"), v.get("difficulty")
    names = ([name] if mine else []) + [c["name"] for c in comps]
    per = {d: {"name": n, **s, "authority": auth.get(d)} for d, n, s in zip([d for d in domains if d], names, sites)}
    return {"domain": mine, "google": ranked, "local": local_rows, "assistants": others, "sites": per, **own, "calls": calls}


def cost(calls: dict) -> Decimal:
    s = get_settings()
    return Decimal(str(round(calls.get("serpapi", 0) * s.serpapi_cost_usd + calls.get("dataforseo", 0) * s.dataforseo_cost_usd
                             + calls.get("assistants", 0) * s.assistant_cost_usd, 4)))


# --- the scorecard ------------------------------------------------------------------------------

def scorecard(m: dict) -> list[dict]:
    """Rows of "you vs competitors", each with a plain verdict. Only rows backed by a measurement."""
    mine = m.get("domain")
    sites = m.get("sites") or {}
    you = sites.get(mine) or {}
    others = [(d, s) for d, s in sites.items() if d != mine]
    rows: list[dict] = []

    def row(key, label, team, fmt, verdict=None, only_you=False, note=""):
        mine_v = fmt(you) if you else None
        theirs = [] if only_you else [{"name": s["name"], "display": fmt(s)} for _, s in others if fmt(s) is not None]
        if mine_v is None and not theirs:
            return
        rows.append({"key": key, "label": label, "team": team, "you": {"display": mine_v if mine_v is not None else "None found",
                     "status": verdict(you, [s for _, s in others]) if verdict else "ok"}, "others": theirs, "note": note})

    def ps(k):
        return lambda s: f"{s['pagespeed'][k]}/100" if (s.get("pagespeed") or {}).get(k) is not None else None

    def worse(k, floor):
        def v(me, them):
            mv = (me.get("pagespeed") or {}).get(k)
            if mv is None:
                return "ok"
            best = max([(t.get("pagespeed") or {}).get(k) or 0 for t in them] or [0])
            return "bad" if mv < floor or mv + 10 < best else "good" if mv >= 90 else "ok"
        return v

    def speed(s):
        p = s.get("pagespeed") or {}
        if p.get("performance") is None:
            return None
        return f"{p['performance']}/100" + (f" · loads in {p['lcp_s']}s" if p.get("lcp_s") else "")

    row("speed", "Mobile speed", "engineering", speed, worse("performance", 50), note="Google PageSpeed, mobile")
    row("accessibility", "Accessibility", "engineering", ps("accessibility"), worse("accessibility", 80))
    row("seo_basics", "SEO basics", "marketing", ps("seo"), worse("seo", 85))
    row("authority", "Domain authority", "marketing", lambda s: f"{s['authority']}/10" if s.get("authority") is not None else None,
        lambda me, them: "bad" if (me.get("authority") or 0) + 1 < max([t.get("authority") or 0 for t in them] or [0]) else "ok",
        note="Open PageRank")
    row("popularity", "Site popularity", "marketing",
        lambda s: f"#{s['popularity']:,} worldwide" if s.get("popularity") else ("Not in the top 1M" if "popularity" in s else None),
        lambda me, them: "bad" if not me.get("popularity") and any(t.get("popularity") for t in them) else "ok", note="Tranco list")
    row("ads_google", "Google ads running", "marketing", lambda s: f"{s['ads_google']} ads" if s.get("ads_google") is not None else None,
        lambda me, them: "bad" if not me.get("ads_google") and any(t.get("ads_google") for t in them) else "ok")
    row("ads_meta", "Facebook & Instagram ads", "marketing", lambda s: f"{s['ads_meta']} active" if s.get("ads_meta") is not None else None,
        lambda me, them: "bad" if not me.get("ads_meta") and any(t.get("ads_meta") for t in them) else "ok")

    def yt(s):
        y = s.get("youtube")
        if not y:
            return None
        if not y.get("channel"):
            return "No channel"
        return f"{(y.get('subscribers') or 0):,} subscribers" + (f" · last video {y['last_upload']}" if y.get("last_upload") else "")
    row("youtube", "YouTube", "marketing", yt,
        lambda me, them: "bad" if not (me.get("youtube") or {}).get("channel") and any((t.get("youtube") or {}).get("channel") for t in them) else "ok")

    def app(s):
        a = s.get("app") or s.get("play")
        if not a:
            return None
        return f"{a.get('rating') or '-'}★" + (f" ({a['ratings']:,} ratings)" if a.get("ratings") else "") + f" · {a.get('store')}"
    row("apps", "Mobile app rating", "product", app)
    row("wikipedia", "On Wikipedia", "pr", lambda s: ("Yes" if s["wikipedia"].get("wikipedia") else "No") if s.get("wikipedia") else None,
        lambda me, them: "bad" if not (me.get("wikipedia") or {}).get("wikipedia") and any((t.get("wikipedia") or {}).get("wikipedia") for t in them) else "ok",
        note="AI assistants learn about companies from it")
    row("reddit", "Reddit mentions", "community", lambda s: f"{s['reddit']:,}" if s.get("reddit") is not None else None,
        lambda me, them: "bad" if (me.get("reddit") or 0) * 3 < max([t.get("reddit") or 0 for t in them] or [0]) else "ok",
        note="AI assistants lean on Reddit")

    def tools(kind, label):
        def f(s):
            t = (s.get("tools") or {}).get(kind)
            return (", ".join(t) or "None") if s.get("tools") is not None else None
        return f
    row("chat", "Live chat on the site", "support", tools("chat", "chat"),
        lambda me, them: "bad" if not (me.get("tools") or {}).get("chat") and any((t.get("tools") or {}).get("chat") for t in them) else "ok")
    row("booking", "Book a meeting online", "sales", tools("booking", "booking"),
        lambda me, them: "bad" if not (me.get("tools") or {}).get("booking") and any((t.get("tools") or {}).get("booking") for t in them) else "ok")

    t = you.get("tools")
    if t is not None:
        problems = []
        if not t["analytics"]:
            problems.append("no analytics")
        if t["ad_pixels"] and not t["consent"]:
            problems.append("ad pixels without a cookie consent tool")
        shown = ", ".join(t["analytics"] + t["ad_pixels"]) or "Nothing found"
        rows.append({"key": "tracking", "label": "Tracking", "team": "marketing",
                     "you": {"display": shown + (f" · {'; '.join(problems)}" if problems else ""), "status": "bad" if problems else "good"},
                     "others": [], "note": "Analytics, ad pixels and cookie consent"})
    e = m.get("email")
    if e:
        bits = [("SPF", e["spf"]), ("DKIM", e["dkim"]), ("DMARC", e["dmarc"])]
        shown = " · ".join(f"{k} {'✓' if v else '✗'}" for k, v in bits) + (f" (policy: {e['dmarc_policy']})" if e.get("dmarc_policy") else "")
        weak = not all(v for _, v in bits) or e.get("dmarc_policy") == "none"
        rows.append({"key": "email_auth", "label": "Email authentication", "team": "it", "you": {"display": shown, "status": "bad" if weak else "good"},
                     "others": [], "note": "Without these, outreach and invoices land in spam"})
    sec = m.get("security")
    if sec:
        bits, bad = [], not sec["https"]
        bits.append("HTTPS ✓" if sec["https"] else "No HTTPS")
        if sec.get("cert_days") is not None:
            bits.append(f"certificate: {sec['cert_days']} days left")
            bad |= sec["cert_days"] < 14
        if sec.get("domain_days") is not None:
            bits.append(f"domain renews in {sec['domain_days']} days")
            bad |= sec["domain_days"] < 30
        if not sec.get("hsts"):
            bits.append("no HSTS")
        rows.append({"key": "security", "label": "Website security", "team": "it", "you": {"display": " · ".join(bits), "status": "bad" if bad else "good"},
                     "others": [], "note": ""})
    links = m.get("links")
    if links:
        n = links["broken_count"]
        rows.append({"key": "broken_links", "label": "Broken links", "team": "engineering",
                     "you": {"display": f"{n} broken of {links['checked']} links on {links['pages']} pages", "status": "bad" if n else "good"},
                     "others": [], "note": ""})
    local = m.get("local") or []
    if local:
        shown = "; ".join(f"{r['city']}: {'#' + str(r['rank']) if r['rank'] else 'not in the map results'}" for r in local)
        rows.append({"key": "maps", "label": "Google Maps results", "team": "marketing",
                     "you": {"display": shown, "status": "bad" if any(not r["rank"] for r in local) else "good"},
                     "others": [], "note": ""})
    return rows


def summary(m: dict, rows: list[dict]) -> str:
    """The measurements as text for Claude to turn into findings."""
    lines = [f"- {r['label']}: you {r['you']['display']} ({r['you']['status']})"
             + (f"; competitors: " + ", ".join(f"{o['name']} {o['display']}" for o in r["others"]) if r["others"] else "")
             for r in rows]
    for g in m.get("google") or []:
        where = f"#{g['rank']}" if g["rank"] else f"not in the top {g['checked']}"
        extra = f", {g['volume']:,} searches a month" if g.get("volume") else ""
        extra += f", difficulty {g['difficulty']}/100" if g.get("difficulty") is not None else ""
        ai = g.get("ai_overview")
        ai_text = (" AI Overview " + ("mentions you" if ai["mentioned"] else "doesn't mention you")) if ai else ""
        lines.append(f"- Google {g['market']} \"{g['query']}\": {where}{extra}. Ahead: {', '.join(g['competitors_ahead']) or 'none'}.{ai_text}")
    for a in m.get("assistants") or []:
        lines.append(f"- {a['assistant']} asked \"{a['query']}\": " + (f"recommends you #{a['rank']}" if a["rank"] else "doesn't recommend you")
                     + f" (recommends {', '.join(r['name'] for r in a['recommended'][:3])})")
    for b in (m.get("links") or {}).get("broken") or []:
        lines.append(f"- Broken link {b['url']} ({b['status'] or 'unreachable'}) on {b['on']}")
    return "\n".join(lines)
