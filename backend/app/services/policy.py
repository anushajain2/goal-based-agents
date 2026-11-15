"""What the agent may do, and when it has to ask.

Every outward action the agent takes is classified into an *action type*. Each type has
a default policy:

    auto   - runs without asking (reading, research, drafts)
    ask    - needs the user's approval each time, unless a standing grant exists

On top of the defaults:
  * Hard blocks (exclusion rules of kind action_type / app / site) are enforced here, in
    code. The agent cannot get around them.
  * Free-text rules (exclusion rules of kind text) plus the built-in rules are checked by
    a separate AI reviewer (see services/rule_check.py). That is best-effort, not a proof.
  * Grants ("approve & don't ask again") turn `ask` into `auto` for one action type,
    optionally narrowed to one app/site, for one campaign or all of them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Campaign, ExclusionRule, PermissionGrant


def _owner_of(campaign_id: str):
    return select(Campaign.owner_id).where(Campaign.id == campaign_id).scalar_subquery()


def applies_to(model, campaign_id: str):
    """Rows for this goal, plus the owner's rows that apply to all of their goals."""
    return or_(
        model.campaign_id == campaign_id,
        and_(model.campaign_id.is_(None), model.owner_id.is_not_distinct_from(_owner_of(campaign_id))),
    )


@dataclass(frozen=True)
class ActionType:
    key: str
    label: str
    description: str
    default: str  # "auto" | "ask"
    risk: int  # higher = riskier; used to pick the stricter of two classifications


ACTION_TYPES: dict[str, ActionType] = {
    a.key: a
    for a in [
        ActionType("research", "Research the web", "Search and read public web pages.", "auto", 0),
        ActionType("read_data", "Read app data", "Read analytics, posts, followers, orders, etc.", "auto", 0),
        ActionType("create_draft", "Create drafts", "Create drafts or private notes that nobody else sees.", "auto", 1),
        ActionType("engage", "Engage", "Like, follow, repost, reply or comment.", "ask", 3),
        ActionType("publish_post", "Publish posts", "Publish a post, tweet, thread or update publicly.", "ask", 4),
        ActionType("publish_article", "Publish articles", "Publish a blog post, article or page.", "ask", 4),
        ActionType("send_message", "Send messages", "Send emails, DMs or messages to people.", "ask", 5),
        ActionType("modify_account", "Change account settings", "Edit profiles, bios, settings or listings.", "ask", 5),
        ActionType("delete_content", "Delete content", "Delete or remove posts, files or records.", "ask", 6),
        ActionType("spend_money", "Spend money", "Run ads, buy things or make any payment.", "ask", 7),
        ActionType("other_write", "Other changes", "Any other action that changes something.", "ask", 5),
    ]
}

READ_ONLY = {"research", "read_data"}


def stricter(a: str, b: str) -> str:
    ta, tb = ACTION_TYPES.get(a, ACTION_TYPES["other_write"]), ACTION_TYPES.get(b, ACTION_TYPES["other_write"])
    return ta.key if ta.risk >= tb.risk else tb.key


# --- Classifying app (Composio) actions -------------------------------------------------

_READ_VERBS = re.compile(
    r"_(GET|LIST|SEARCH|FETCH|FIND|RETRIEVE|READ|LOOKUP|COUNT|DESCRIBE|CHECK|QUERY|VIEW|EXPORT|DOWNLOAD)(_|$)"
)
_RULES: list[tuple[re.Pattern, str]] = [
    # Any write in an ads platform spends money, as does anything payment-like.
    (re.compile(r"^(GOOGLE_?ADS|FACEBOOK_?ADS|META_?ADS|LINKEDIN_?ADS|TIKTOK_?ADS|REDDIT_?ADS|TWITTER_?ADS|X_?ADS|"
                r"BING_?ADS|MICROSOFT_?ADS|SNAPCHAT_?ADS|PINTEREST_?ADS|AMAZON_?ADS)_"), "spend_money"),
    (re.compile(r"(PAY|PAYMENT|CHARGE|PURCHASE|CHECKOUT|INVOICE|BUDGET|_BID|_ADS?_|AD_?SET|AD_?CAMPAIGN|ADVERTIS|"
                r"BOOST|PROMOTE|ORDER_CREATE|CREATE_ORDER|SUBSCRIPTION)"), "spend_money"),
    (re.compile(r"(DELETE|REMOVE|DESTROY|TRASH|ARCHIVE|UNPUBLISH|PURGE)"), "delete_content"),
    (re.compile(r"(SEND|REPLY_TO_EMAIL|DIRECT_MESSAGE|_DM|MESSAGE_CREATE|CREATE_MESSAGE|POST_MESSAGE|_MAIL_|EMAIL_SEND|FORWARD)"), "send_message"),
    (re.compile(r"(DRAFT)"), "create_draft"),
    (re.compile(r"(LIKE|FOLLOW|RETWEET|REPOST|REACT|UPVOTE|COMMENT|REPLY|BOOKMARK|SUBSCRIBE|JOIN|STAR)"), "engage"),
    (re.compile(r"(ARTICLE|BLOG|PAGE|STORY|NEWSLETTER).*(CREATE|PUBLISH|POST)|(CREATE|PUBLISH|POST).*(ARTICLE|BLOG|PAGE|STORY|NEWSLETTER)"), "publish_article"),
    (re.compile(r"(TWEET|POST|PUBLISH|SHARE|UPLOAD|THREAD|CREATION_OF_A_POST|MEDIA_CREATE)"), "publish_post"),
    (re.compile(r"(UPDATE|EDIT|PATCH|SET_|MODIFY|CHANGE|PROFILE|SETTINGS|RENAME)"), "modify_account"),
]


def classify_app_action(slug: str, tags: list[str] | None = None) -> str:
    """Heuristic classification of a Composio tool slug like TWITTER_CREATION_OF_A_POST."""
    s = slug.upper()
    tags_l = {t.lower() for t in (tags or [])}
    if "destructivehint" in tags_l:
        base = "delete_content"
    elif "readonlyhint" in tags_l or _READ_VERBS.search(s):
        return "read_data"
    else:
        base = None
    for pattern, action_type in _RULES:
        if pattern.search(s):
            return stricter(action_type, base) if base else action_type
    return base or "other_write"


# --- Exclusions & grants ---------------------------------------------------------------

def domain_of(url_or_domain: str) -> str:
    value = url_or_domain.strip().lower()
    host = urlparse(value if "://" in value else f"https://{value}").hostname or value
    return host.removeprefix("www.")


def _site_matches(rule_value: str, domain: str) -> bool:
    rule = domain_of(rule_value)
    return domain == rule or domain.endswith("." + rule)


async def exclusions_for(session: AsyncSession, campaign_id: str) -> list[ExclusionRule]:
    return list(
        (
            await session.execute(
                select(ExclusionRule).where(applies_to(ExclusionRule, campaign_id))
            )
        ).scalars()
    )


@dataclass
class Block:
    reason: str
    rule_id: str | None = None


def check_hard_blocks(
    rules: list[ExclusionRule], *, action_type: str, app: str | None = None, site: str | None = None
) -> Block | None:
    for rule in rules:
        if rule.kind == "action_type" and rule.value == action_type:
            label = ACTION_TYPES.get(action_type, ACTION_TYPES["other_write"]).label
            return Block(f'"{label}" is turned off in your guardrails.', rule.id)
        if rule.kind == "app" and app and rule.value.lower() == app.lower():
            return Block(f'The app "{app}" is blocked in your guardrails.', rule.id)
        if rule.kind == "site" and site and _site_matches(rule.value, domain_of(site)):
            return Block(f'The site "{rule.value}" is blocked in your guardrails.', rule.id)
    return None


def text_rules(rules: list[ExclusionRule]) -> list[str]:
    return [r.value for r in rules if r.kind == "text"]


async def find_grant(
    session: AsyncSession,
    campaign_id: str,
    action_type: str,
    scope: str | None,
    est_spend_usd: Decimal | None = None,
) -> PermissionGrant | None:
    grants = (
        await session.execute(
            select(PermissionGrant).where(
                PermissionGrant.action_type == action_type,
                PermissionGrant.revoked_at.is_(None),
                applies_to(PermissionGrant, campaign_id),
            )
        )
    ).scalars()
    for grant in grants:
        if grant.scope and (not scope or grant.scope.lower() != scope.lower()):
            continue
        if action_type == "spend_money":
            if grant.spend_limit_usd is None or est_spend_usd is None:
                continue
            if Decimal(est_spend_usd) > Decimal(grant.spend_limit_usd):
                continue
        return grant
    return None


@dataclass
class Decision:
    outcome: str  # "allow" | "ask" | "block"
    action_type: str
    reason: str = ""
    grant_id: str | None = None
    rule_id: str | None = None


async def decide(
    session: AsyncSession,
    campaign_id: str,
    *,
    action_type: str,
    app: str | None = None,
    site: str | None = None,
    est_spend_usd: Decimal | None = None,
    rules: list[ExclusionRule] | None = None,
) -> Decision:
    """Hard blocks first, then default policy, then grants. (AI rule check runs separately.)"""
    if action_type not in ACTION_TYPES:
        action_type = "other_write"
    rules = rules if rules is not None else await exclusions_for(session, campaign_id)
    block = check_hard_blocks(rules, action_type=action_type, app=app, site=site)
    if block:
        return Decision("block", action_type, block.reason, rule_id=block.rule_id)
    if ACTION_TYPES[action_type].default == "auto":
        return Decision("allow", action_type, "Allowed by default.")
    grant = await find_grant(session, campaign_id, action_type, app or (domain_of(site) if site else None), est_spend_usd)
    if grant:
        return Decision("allow", action_type, "You allowed this without asking.", grant_id=grant.id)
    return Decision("ask", action_type, "Needs your approval.")
