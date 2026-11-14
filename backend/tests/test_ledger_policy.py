from decimal import Decimal

import pytest

from app.db import session_scope
from app.models import Campaign, ExclusionRule, LedgerKind, PermissionGrant
from app.services import ledger, policy


async def _campaign(budget="10", daily=None) -> str:
    async with session_scope() as s:
        c = Campaign(name="t", goal_type="followers", goal_description="g", primary_metric="followers",
                     budget_total=Decimal(budget), daily_cap=Decimal(daily) if daily else None)
        s.add(c)
        await s.flush()
        return c.id


def test_cost_from_usage_opus():
    usage = {"input_tokens": 1_000_000, "output_tokens": 100_000, "cache_read_input_tokens": 1_000_000,
             "cache_creation_input_tokens": 0, "server_tool_use": {"web_search_requests": 3}}
    # $4 input + $2 output + $0.20 cache read + $0.03 search
    assert ledger.cost_from_usage("claude-opus-5-5", usage) == Decimal("6.230000")


def test_unknown_model_priced_at_most_expensive():
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    assert ledger.cost_from_usage("some-new-model", usage) == Decimal("5.000000")


async def test_reserve_respects_budget_and_settle():
    cid = await _campaign("1.00")
    async with session_scope() as s:
        e = await ledger.reserve(s, cid, LedgerKind.ai_usage, Decimal("0.60"), "call")
    async with session_scope() as s:
        with pytest.raises(ledger.BudgetExceeded):
            await ledger.reserve(s, cid, LedgerKind.ai_usage, Decimal("0.50"), "call 2")
    async with session_scope() as s:
        await ledger.settle(s, await s.get(type(e), e.id), Decimal("0.10"))
    async with session_scope() as s:
        await ledger.reserve(s, cid, LedgerKind.spend, Decimal("0.50"), "ad")
        state = await ledger.budget_state(s, await s.get(Campaign, cid))
        assert state.settled == Decimal("0.10") and state.reserved == Decimal("0.50")
        assert state.remaining == Decimal("0.40")


async def test_daily_cap():
    cid = await _campaign("100", daily="1")
    async with session_scope() as s:
        await ledger.reserve(s, cid, LedgerKind.ai_usage, Decimal("0.9"), "x")
    async with session_scope() as s:
        with pytest.raises(ledger.BudgetExceeded, match="daily cap"):
            await ledger.reserve(s, cid, LedgerKind.ai_usage, Decimal("0.2"), "y")


@pytest.mark.parametrize(
    "slug,expected",
    [
        ("TWITTER_CREATION_OF_A_POST", "publish_post"),
        ("TWITTER_USER_LOOKUP_BY_USERNAME", "read_data"),
        ("GMAIL_SEND_EMAIL", "send_message"),
        ("GMAIL_CREATE_EMAIL_DRAFT", "create_draft"),
        ("TWITTER_FOLLOW_USER", "engage"),
        ("GOOGLEADS_CREATE_CAMPAIGN", "spend_money"),
        ("NOTION_DELETE_BLOCK", "delete_content"),
        ("LINKEDIN_LIST_POSTS", "read_data"),
        ("WORDPRESS_CREATE_POST", "publish_post"),
        ("HUBSPOT_UPDATE_CONTACT", "modify_account"),
        ("SOMEAPP_FROBNICATE", "other_write"),
    ],
)
def test_classify_app_action(slug, expected):
    assert policy.classify_app_action(slug) == expected


def test_destructive_tag_wins():
    assert policy.classify_app_action("FOO_DO_THING", ["destructiveHint"]) == "delete_content"


async def test_decide_blocks_grants_and_spend_limits():
    cid = await _campaign()
    async with session_scope() as s:
        s.add(ExclusionRule(campaign_id=cid, kind="action_type", value="send_message"))
        s.add(ExclusionRule(campaign_id=None, kind="site", value="reddit.com"))
        s.add(PermissionGrant(campaign_id=cid, action_type="publish_post", scope="x.com"))
        s.add(PermissionGrant(campaign_id=None, action_type="spend_money", spend_limit_usd=Decimal(5)))
    async with session_scope() as s:
        d = await policy.decide(s, cid, action_type="send_message")
        assert d.outcome == "block"
        d = await policy.decide(s, cid, action_type="research", site="https://old.reddit.com/r/x")
        assert d.outcome == "block"
        assert (await policy.decide(s, cid, action_type="research", site="x.com")).outcome == "allow"
        assert (await policy.decide(s, cid, action_type="publish_post", site="https://www.x.com/home")).outcome == "allow"
        assert (await policy.decide(s, cid, action_type="publish_post", site="linkedin.com")).outcome == "ask"
        assert (await policy.decide(s, cid, action_type="spend_money", est_spend_usd=Decimal(4))).outcome == "allow"
        assert (await policy.decide(s, cid, action_type="spend_money", est_spend_usd=Decimal(6))).outcome == "ask"
        assert (await policy.decide(s, cid, action_type="engage")).outcome == "ask"
