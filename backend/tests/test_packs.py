"""The role catalog and company packs: valid, and used to start a team."""

from app.agent import packs
from app.agent.org_setup import tidy_plan
from app.catalog import TOOLS
from app.org import CATEGORY_KEYS, PRESET_NAMES
from app.services.policy import ACTION_TYPES


def test_every_role_and_pack_is_valid():
    for r in packs.ROLES.values():
        assert r.kind in PRESET_NAMES, r.key
        assert r.title and r.agent_name and r.objective and r.does and r.asks, r.key
        assert all(t in TOOLS or t == "web" for t in r.tools), r.key
        assert r.goals, r.key
        for g in r.goals:
            assert not any(ch.isdigit() for ch in g.name), g.name  # ongoing goals: the number is the target
            assert g.category in CATEGORY_KEYS and g.target > 0 and g.period in ("week", "month", "quarter")
            assert g.steps and all(a in ACTION_TYPES and (tool in TOOLS or tool in ("web", "none")) for _, a, tool in g.steps)
    for p in packs.PACKS.values():
        assert set(p.stages) <= set(packs.SIZE_ORDER) and p.stages.get("tiny")
        assert all(k in packs.ROLES for keys in p.stages.values() for k in keys), p.key
        assert all(kind in PRESET_NAMES for kind, _ in p.later)


def test_the_type_of_company_is_guessed_from_its_words():
    cases = {
        "Route-planning SaaS platform for logistics teams. Book a demo.": "startup",
        "Bootstrapped indie hacker: a Chrome extension with a free trial": "solo_saas",
        "Performance marketing agency. Our clients and case studies; monthly retainers.": "agency",
        "Boutique law firm: our attorneys advise founders on tax and contracts": "services",
        "Clean skincare. Free shipping over $50, easy returns. Add to cart.": "ecommerce",
        "A family bakery in town": "general",
    }
    for text, expected in cases.items():
        assert packs.classify(text)[0] == expected, text


def test_bigger_companies_get_more_of_the_pack():
    tiny = [r.key for r in packs.roles_for("startup", "tiny")]
    mid = [r.key for r in packs.roles_for("startup", "mid")]
    assert tiny[0] == "sdr" and "renewals" not in tiny
    assert mid[: len(tiny)] == tiny and "renewals" in mid and "compliance" in mid


def test_a_starter_plan_has_ai_employees_with_goals():
    plan = tidy_plan(packs.starter_plan("ecommerce", "small"))
    kinds = [d["kind"] for d in plan["departments"]]
    assert kinds[:2] == ["marketing", "support"]
    marketing = plan["departments"][0]
    assert [a["role"] for a in marketing["agents"]] == ["paid_ads", "content", "influencer"]  # up to three per team
    assert all(a["goals"] for a in marketing["agents"])
    assert sum(len(d["agents"]) for d in plan["departments"]) <= 9  # small company limit
    assert plan["profile"]["company_type"] == "ecommerce"


def test_the_planner_sees_the_catalog_and_the_template():
    text = packs.catalog_text()
    assert "Customer Support (kind support)" in text and "support_agent" in text and "Founder's Office" in text
    brief = packs.pack_brief("agency", ["agency", "retainer"])
    assert "Agency" in brief and "agency_bd" in brief and "from: agency, retainer" in brief
