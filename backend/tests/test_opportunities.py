"""Setup's last step: what the company is missing, each finding tied to goals it can turn on."""

import re

from app.agent import checks
from app.agent.llm import MeteredClaude
from app.agent.opportunities import SEARCH_SYSTEM, host
from app.agent.org_setup import run_org_setup
from tests.fakes import FakeAnthropic
from tests.test_org_setup import PLAN, client, fake_site, goal, research_script, start_setup, with_key  # noqa: F401

Q1, Q2, Q3 = "route planning software for logistics", "acme routing reviews", "best fleet routing tool europe"


def pick(kw):
    return {"checks": [{"key": "review_gap", "score": 4, "why": "Few G2 reviews", "expect": "12 vs 240 reviews"},
                       {"key": "search_rank", "score": 5, "why": "Crowded search market", "expect": "Not on page 1"},
                       {"key": "proof_gap", "score": 2, "why": "Has case studies", "expect": "Probably fine"},  # too weak to run
                       {"key": "ai_answers", "score": 5, "why": "", "expect": ""},
                       {"key": "not_a_check", "score": 5, "why": "", "expect": ""}],
            "queries": [{"query": Q1, "intent": "Ops lead comparing tools"},
                        {"query": Q2, "intent": "has the company's name: dropped"},
                        {"query": Q3, "intent": "Buyer in the EU"}],
            "competitors": [{"name": "Routeco", "domain": "https://www.routeco.test/"},
                            {"name": "Acme itself", "domain": "acme.test"}]}  # their own site: dropped


def result(url):
    return {"type": "web_search_result", "url": url, "title": url}


def script(kw):
    if kw.get("system") == SEARCH_SYSTEM:  # the real searches
        return [{"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": Q1}},
                {"type": "web_search_tool_result", "tool_use_id": "s1", "content": [
                    result("https://www.routeco.test/routing"), result("https://other.test/x"),
                    result("https://blog.acme.test/guide")]},
                {"type": "server_tool_use", "id": "s2", "name": "web_search", "input": {"query": Q3}},
                {"type": "web_search_tool_result", "tool_use_id": "s2", "content": [
                    result("https://x.test/"), result("https://routeco.test/eu")]},
                {"type": "text", "text": "done"}]
    return research_script(kw)


def ai(kw):
    return {"answers": [{"query": Q1, "recommendations": [{"name": "Routeco", "domain": "routeco.test"},
                                                          {"name": "Other", "domain": "other.test"}]},
                        {"query": Q3, "recommendations": [{"name": "Routeco", "domain": "routeco.test"},
                                                          {"name": "Acme", "domain": "acme.test"}]}]}


def findings(kw):
    prompt = kw["messages"][0]["content"]
    demos = re.search(r"- (\w+): Book 15 demos with Heads of Ops", prompt).group(1)
    seo = [{"name": "Page 1 for 3 long-tail searches", "outcome": "Page 1 for 3 specific searches", "weeks": 6,
            "paid_items": [], "goal": goal("SEO step 1: long-tail pages", "Marketing & demand gen")},
           {"name": "Top 3 for the main search", "outcome": "Top 3 for 'route planning software'", "weeks": 24,
            "paid_items": [{"item": "Backlink outreach and PR placements", "usd": 600}],
            "goal": goal("SEO step 2: win the main search", "Marketing & demand gen")}]
    tiny = [{"name": "Fix titles", "outcome": "", "weeks": 1, "paid_items": [],
             "goal": goal("Fix page titles", "Marketing & demand gen", cycle_hours=24)},
            {"name": "Fix more titles", "outcome": "", "weeks": 1, "paid_items": [],
             "goal": goal("Fix more page titles", "Marketing & demand gen", cycle_hours=24)}]
    return {"findings": [
        {"check": "search_rank", "team_kind": "marketing", "title": "Competitors outrank you",
         "evidence": "Rank 3 for 'route planning software for logistics'; not in the top 2 for the EU search.",
         "impact": "Most buyers click the first results.", "estimate": "", "assumption": "", "confidence": "high",
         "source_urls": ["https://www.routeco.test/routing"], "goal_id": "", "new_goal": None, "milestones": seo},
        {"check": "review_gap", "team_kind": "sales", "title": "No comparison pages", "evidence": "None found.",
         "impact": "Switchers find competitors.", "estimate": "", "assumption": "", "confidence": "high",
         "source_urls": [], "goal_id": demos, "new_goal": None, "milestones": []},
        {"check": "", "team_kind": "marketing", "title": "Page titles", "evidence": "12 pages share one title.",
         "impact": "Search engines can't tell them apart.", "estimate": "", "assumption": "", "confidence": "medium",
         "source_urls": [], "goal_id": "", "new_goal": None, "milestones": tiny},
        {"check": "", "team_kind": "finance", "title": "Pricing hidden", "evidence": "No pricing page.",
         "impact": "Some buyers leave.", "estimate": "", "assumption": "", "confidence": "low", "source_urls": [],
         "goal_id": "not-a-goal", "new_goal": goal("Publish pricing", "Finance & admin"), "milestones": []},
    ]}


async def test_checks_suit_the_type_of_company():
    shop = {c.key for c in checks.for_company("ecommerce")}
    assert {"product_pages", "delivery_promise", "abandoned_checkouts"} <= shop
    assert "security_trust" not in shop  # a B2B thing
    assert "tenders" in {c.key for c in checks.for_company("general")}
    assert all(c.method not in ("tool", "measure") for c in checks.runnable("startup"))
    # Every check Claude can choose is concrete: its number, how it's checked, the fix, an example.
    assert all(c.metric and len(c.steps) >= 2 and c.fix and c.example for c in checks.runnable(None))


async def test_scan_measures_search_and_ai_and_prices_milestones(with_key, fake_site):
    async with client() as c:
        setup_id = await start_setup(c)
        fake = FakeAnthropic(script, org_planner=lambda kw: PLAN, routes={"checks": pick, "answers": ai},
                             scanner=findings, searches=2)
        await run_org_setup(setup_id, MeteredClaude(client=fake))

        st = (await c.get("/api/org/setup")).json()
        assert st["setup"]["status"] == "done"
        assert st["setup"]["steps"][-1]["detail"] == "Ran 3 checks plus measurements · 4 things you could do better"
        opp = st["org"]["profile"]["opportunities"]

        # Searches never use the company's name; its own site isn't a competitor.
        vis = opp["visibility"]
        assert vis["domain"] == "acme.test"
        assert [x["name"] for x in vis["competitors"]] == ["Routeco"]
        q1, q3 = vis["search"]
        assert (q1["query"], q1["rank"], q1["competitors_ahead"]) == (Q1, 3, ["Routeco"])  # blog.acme.test counts
        assert (q3["query"], q3["rank"]) == (Q3, None)
        assert [r["who"] for r in q3["results"]] == ["", "Routeco"]
        assert [a["rank"] for a in vis["ai"]] == [None, 2]
        search_call = next(x for x in fake.calls if x.get("system") == SEARCH_SYSTEM)
        assert Q2 not in search_call["messages"][0]["content"]
        # Claude scored the checks; the strongest ran (highest first), the weak one didn't.
        assert [(x["key"], x["score"]) for x in opp["checks"]] == [("search_rank", 5), ("ai_answers", 5), ("review_gap", 4)]
        assert opp["checks"][2]["expect"] == "12 vs 240 reviews"

        seo, compare, titles, pricing = opp["findings"]
        goals = {g["id"]: g for g in (await c.get("/api/campaigns")).json()}
        # A big fix comes in priced steps: AI work sessions plus itemised spend.
        one, two = seo["milestones"]
        assert one["total_usd"] == 55 and one["paid_usd"] == 0  # 6 weeks of 6-hourly sessions at $0.30
        assert two["paid_items"] == [{"item": "Backlink outreach and PR placements", "usd": 600.0}]
        assert two["total_usd"] == 805 and seo["total_usd"] == 860
        assert "spec" in two and two["goal_id"] is None  # later steps aren't goals until someone asks
        first = goals[one["goal_id"]]
        assert first["status"] == "draft" and first["budget"]["total"] == 55
        assert seo["goal_id"] == one["goal_id"] and one["goal_id"] in st["setup"]["created"]["goals"]
        # Linked to a goal setup already planned.
        assert goals[compare["goal_id"]]["name"] == "Book 15 demos with Heads of Ops"
        # Cheap work isn't split into steps.
        assert len(titles["milestones"]) == 1
        # No Finance team and no close one (Operations, Founder's office): nothing invented.
        assert pricing["goal_id"] is None and not any(g["name"] == "Publish pricing" for g in goals.values())
        # Connect to unlock, per team; a check becomes a goal for its team, once.
        unlock = {u["team_kind"]: u for u in opp["unlock"]}
        assert {"finance", "sales", "it"} <= set(unlock)
        assert any(c["key"] == "overdue_invoices" and c["tool"] == "quickbooks" for c in unlock["finance"]["checks"])
        r = await c.post("/api/org/unlock/lead_followup")
        assert r.status_code == 200, r.text
        lead_goal = r.json()["goal_id"]
        assert (await c.post("/api/org/unlock/lead_followup")).json()["goal_id"] == lead_goal
        g = next(x for x in (await c.get("/api/campaigns")).json() if x["id"] == lead_goal)
        assert (g["name"], g["status"]) == ("Follow up every lead and stalled deal", "draft")
        full = (await c.get(f"/api/campaigns/{lead_goal}")).json()
        assert [st["tool"] for st in full["playbook"]["steps"]] == ["hubspot", "none", "hubspot"]
        assert (await c.post("/api/org/unlock/overdue_invoices")).status_code == 404  # no Finance team yet
        assert (await c.post("/api/org/unlock/search_rank")).status_code == 404  # not a connect-to-unlock check

        # Going further: step 2 becomes a draft goal with its full price, once.
        r = await c.post("/api/org/opportunities/0/milestones/1/goal")
        assert r.status_code == 200, r.text
        later = r.json()["goal_id"]
        assert (await c.post("/api/org/opportunities/0/milestones/1/goal")).json()["goal_id"] == later
        g2 = next(g for g in (await c.get("/api/campaigns")).json() if g["id"] == later)
        assert g2["name"] == "SEO step 2: win the main search" and g2["status"] == "draft"
        assert g2["budget"]["total"] == 805
        st = (await c.get("/api/org/setup")).json()
        assert st["org"]["profile"]["opportunities"]["findings"][0]["milestones"][1]["goal_id"] == later
        assert (await c.post("/api/org/opportunities/3/milestones/0/goal")).status_code == 404


def test_host_matching():
    assert host("https://www.Acme.test/pricing") == "acme.test"
    assert host("acme.test") == "acme.test"
    assert host("") == ""


async def test_with_google_set_up_the_scan_uses_real_rankings_by_country(with_key, fake_site, monkeypatch):
    import httpx

    from app.config import get_settings
    from app.services.presence import http
    from tests.test_presence import QA, handler

    monkeypatch.setattr(get_settings(), "serpapi_key", "k")
    monkeypatch.setattr(http, "transport", httpx.MockTransport(handler))

    def pick_de_nl(kw):
        return {"checks": [{"key": "search_rank", "score": 5, "why": "", "expect": ""},
                           {"key": "ai_answers", "score": 4, "why": "", "expect": ""}],
                "queries": [{"query": QA, "intent": "Ops lead"}],
                "competitors": [{"name": "Routeco", "domain": "routeco.test"}],
                "markets": [{"country": "Germany", "gl": "DE", "hl": "de"}, {"country": "Netherlands", "gl": "nl", "hl": "nl"}],
                "local": {"query": "", "cities": []}}

    def answers(kw):
        return {"answers": [{"query": QA, "recommendations": [{"name": "Routeco", "domain": "routeco.test"}]}]}

    async with client() as c:
        setup_id = await start_setup(c)
        fake = FakeAnthropic(script, org_planner=lambda kw: PLAN, routes={"checks": pick_de_nl, "answers": answers},
                             scanner=lambda kw: {"findings": [], "deeper": []})
        await run_org_setup(setup_id, MeteredClaude(client=fake))
        opp = (await c.get("/api/org/setup")).json()["org"]["profile"]["opportunities"]
        vis = opp["visibility"]
        assert vis["source"] == "google" and vis["markets"] == ["Germany", "Netherlands"]
        assert [(r["market"], r["rank"]) for r in vis["search"]] == [("Germany", 2), ("Netherlands", None)]
        assert not any(x.get("system") == SEARCH_SYSTEM for x in fake.calls)  # Google instead of Claude's search
        assert vis["highlights"][0] == f'You\'re #2 in Germany for "{QA}" but not in the top 2 in Netherlands, where Routeco leads.'
        assert {r["key"] for r in opp["scorecard"]} >= {"speed", "email_auth", "broken_links"}
        structure = next(x for x in fake.calls if "findings" in (x.get("output_config") or {}).get("format", {}).get("schema", {}).get("properties", {}))
        assert "Mobile speed: you 38/100" in structure["messages"][0]["content"]


def test_the_five_shown_are_the_strongest_and_include_another_team_only_if_strong():
    from app.agent.opportunities import SHOW, balanced

    gtm = [{"team_kind": "marketing", "title": str(i), "pull": 4} for i in range(6)]
    strong = {"team_kind": "it", "title": "email lands in spam", "pull": 4}
    weak = {"team_kind": "legal", "title": "no imprint", "pull": 2}
    picked = balanced(gtm + [weak, strong])
    assert len(picked) == SHOW and picked[-1] is strong
    assert balanced(gtm + [weak]) == gtm[:SHOW]  # a weak one isn't added for variety
    ranked = balanced([{"team_kind": "sales", "title": "a", "pull": 2}, {"team_kind": "sales", "title": "b", "pull": 5}])
    assert [f["title"] for f in ranked] == ["b", "a"]


async def test_a_fix_goes_to_the_closest_team_when_its_own_is_missing(with_key, fake_site):
    from app.agent.opportunities import create_goal
    from tests.helpers import org_of

    async with client() as c:
        setup_id = await start_setup(c)
        await run_org_setup(setup_id, MeteredClaude(client=FakeAnthropic(script, org_planner=lambda kw: {
            **PLAN, "departments": [{"kind": "engineering", "name": "Engineering", "why": "", "agents": [
                {"role": "", "name": "Eng Agent", "title": "", "objective": "", "goals": [goal("Ship fixes")]}]}]})))
        org = await org_of(c)
        g = {k: v for k, v in goal("Add a DMARC record").items()}
        from app.agent.org_setup import _tidy_goal
        spec = _tidy_goal(g)
        spec["budget_basis"], spec["budget_usd"] = {"suggested_usd": 5}, 5
        goal_id = await create_goal(org["org"]["id"], None, "it", spec)
        assert goal_id  # no IT team: Engineering takes it
        made = next(x for x in (await c.get("/api/campaigns")).json() if x["id"] == goal_id)
        assert made["agent"]["name"] == "Eng Agent"
