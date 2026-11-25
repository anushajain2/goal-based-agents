"""Setup's last step: what the company is missing, each finding tied to a goal it can turn on."""

import re

from app.agent.llm import MeteredClaude
from app.agent.org_setup import run_org_setup
from tests.fakes import FakeAnthropic
from tests.test_org_setup import PLAN, client, fake_site, goal, research_script, start_setup, with_key  # noqa: F401


def scanner(kw):
    prompt = kw["messages"][0]["content"]
    demos = re.search(r"- (\w+): Book 15 demos with Heads of Ops", prompt).group(1)
    return {
        "findings": [
            {"team_kind": "marketing", "title": "Rare, low-traction LinkedIn posts",
             "evidence": "4 company posts since June; most have under 10 reactions.",
             "impact": "Buyers check you on LinkedIn before replying to outreach.",
             "estimate": "$20k-60k a year in pipeline", "assumption": "2-3 inbound leads a month at your price",
             "confidence": "medium", "source_urls": ["https://news.test/acme", "https://made-up.test/x"],
             "goal_id": "", "new_goal": goal("Post twice a week on LinkedIn", "Marketing & demand gen",
                                             primary_metric="posts")},
            {"team_kind": "sales", "title": "No comparison pages", "evidence": "No page compares Acme with Routeco.",
             "impact": "Buyers searching 'Routeco alternative' find competitors first.", "estimate": "",
             "assumption": "", "confidence": "high", "source_urls": [], "goal_id": demos, "new_goal": None},
            {"team_kind": "finance", "title": "Pricing hidden", "evidence": "No pricing page.",
             "impact": "Some buyers leave.", "estimate": "", "assumption": "", "confidence": "low",
             "source_urls": [], "goal_id": "not-a-goal", "new_goal": goal("Publish pricing", "Finance & admin")},
            {"team_kind": "pr", "title": "", "evidence": "", "impact": "", "estimate": "", "assumption": "",
             "confidence": "low", "source_urls": [], "goal_id": "", "new_goal": None},  # empty: dropped
        ],
        "deeper": [{"tool": "hubspot", "check": "Leads nobody followed up"}],
    }


async def test_scan_ties_each_gap_to_a_goal(with_key, fake_site):
    async with client() as c:
        setup_id = await start_setup(c)
        fake = FakeAnthropic(research_script, org_planner=lambda kw: PLAN, scanner=scanner, searches=2)
        await run_org_setup(setup_id, MeteredClaude(client=fake))

        st = (await c.get("/api/org/setup")).json()
        assert st["setup"]["status"] == "done"
        scan_step = st["setup"]["steps"][-1]
        assert (scan_step["key"], scan_step["status"]) == ("scan", "done")
        assert scan_step["detail"] == "3 things you could do better"

        found = st["org"]["profile"]["opportunities"]
        linkedin, compare, pricing = found["findings"]
        assert found["deeper"] == [{"tool": "hubspot", "label": "HubSpot", "check": "Leads nobody followed up"}]

        goals = {g["id"]: g for g in (await c.get("/api/campaigns")).json()}
        # A new draft goal on the Marketing team's AI employee, counted among the goals setup made.
        new = goals[linkedin["goal_id"]]
        assert new["name"] == "Post twice a week on LinkedIn" and new["status"] == "draft"
        assert linkedin["goal_id"] in st["setup"]["created"]["goals"]
        assert linkedin["estimate"] == "$20k-60k a year in pipeline"
        assert linkedin["sources"] == ["https://news.test/acme"]  # only sources the scan really saw
        # Linked to a goal setup already planned.
        assert goals[compare["goal_id"]]["name"] == "Book 15 demos with Heads of Ops"
        # No Finance team: no goal invented, and no made-up goal id kept.
        assert pricing["goal_id"] is None
        assert not any(g["name"] == "Publish pricing" for g in goals.values())

        # Never judges people: the scan is told so.
        investigate = next(x for x in fake.calls if x.get("system", "").startswith("You are a sharp growth"))
        assert "Never judge, rank or name individual employees" in investigate["system"]
        assert {t["name"] for t in investigate["tools"]} == {"web_search", "web_fetch"}
