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
    The reviewer can only make things stricter (block, or ask instead of going ahead).
  * Grants change `ask` for one action type, optionally narrowed to one app/site, on one
    goal, a department or the whole organization. A grant has a mode:
        auto      - goes ahead without asking ("approve & don't ask again")
        heads_up  - goes ahead after a short heads-up unless someone stops it
        ask       - asks every time, overriding looser grants (e.g. a founder's personal
                    account, or a type that was stopped too often on this goal)
    When several grants apply, the strictest wins. An auto or heads_up grant may carry a
    daily cap: past it, the action asks instead (see services/autonomy.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Campaign, ExclusionRule, PermissionGrant


def _org_of(campaign_id: str):
    return select(Campaign.org_id).where(Campaign.id == campaign_id).scalar_subquery()


def _department_of(campaign_id: str):
    return (
        select(Agent.department_id).join(Campaign, Campaign.agent_id == Agent.id)
        .where(Campaign.id == campaign_id).scalar_subquery()
    )


def applies_to(model, campaign_id: str):
    """Rules/permissions that cover this goal: set on the goal itself, on its AI employee's
    department, or on the whole organization."""
    return or_(
        model.campaign_id == campaign_id,
        and_(model.campaign_id.is_(None), model.department_id.is_not(None),
             model.department_id == _department_of(campaign_id)),
        and_(model.campaign_id.is_(None), model.department_id.is_(None),
             model.org_id.is_not_distinct_from(_org_of(campaign_id))),
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
        ActionType("engage", "Like and follow", "Like, follow, repost or bookmark.", "ask", 3),
        ActionType("reply", "Reply and comment", "Reply to people or comment on posts and threads.", "ask", 4),
        ActionType("publish_post", "Publish posts", "Publish a post, tweet, thread or update publicly.", "ask", 4),
        ActionType("publish_article", "Publish articles", "Publish a blog post, article or page.", "ask", 4),
        ActionType("send_message", "Send messages", "Send emails, DMs or messages to people.", "ask", 5),
        ActionType("modify_account", "Change account settings", "Edit profiles, bios, settings or listings.", "ask", 5),
        ActionType("delete_content", "Delete content", "Delete or remove posts, files or records.", "ask", 6),
        ActionType("spend_money", "Spend money", "Run ads, buy things or make any payment.", "ask", 7),
        ActionType("propose_code", "Propose code", "Open a pull request on a new branch. Nothing ships until it's merged.", "auto", 2),
        ActionType("merge_content", "Merge content changes",
                   "Merge a small pull request that only changes copy, articles or images and passes its checks.", "ask", 5),
        ActionType("merge_code", "Merge code", "Merge a pull request into the main code.", "ask", 6),
        ActionType("other_write", "Other changes", "Any other action that changes something.", "ask", 5),
    ]
}

READ_ONLY = {"research", "read_data"}

# Grant modes, loosest first. The strictest applicable one wins.
GRANT_MODES = ("auto", "heads_up", "ask")
_STRICTNESS = {m: i for i, m in enumerate(GRANT_MODES)}


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
    (re.compile(r"(COMMENT|REPLY)"), "reply"),
    (re.compile(r"(LIKE|FOLLOW|RETWEET|REPOST|REACT|UPVOTE|BOOKMARK|SUBSCRIBE|JOIN|STAR)"), "engage"),
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


def _grant_matches(grant: PermissionGrant, action_type: str, scope: str | None,
                   est_spend_usd: Decimal | None) -> bool:
    if grant.scope and (not scope or grant.scope.lower() != scope.lower()):
        return False
    mode = grant.mode or "auto"
    if action_type == "spend_money" and mode != "ask":
        if grant.spend_limit_usd is None or est_spend_usd is None:
            return False
        if Decimal(est_spend_usd) > Decimal(grant.spend_limit_usd):
            return False
    return True


def strictest(grants: list[PermissionGrant]) -> PermissionGrant | None:
    """Of several grants that apply, the strictest wins (ask > heads_up > auto); on a tie, the
    one with a daily cap (and the lower cap)."""
    if not grants:
        return None
    return max(grants, key=lambda g: (_STRICTNESS.get(g.mode or "auto", 0),
                                      g.daily_cap is not None, -(g.daily_cap or 0)))


async def grants_for(session: AsyncSession, campaign_id: str, action_type: str) -> list[PermissionGrant]:
    return list((await session.execute(
        select(PermissionGrant).where(
            PermissionGrant.action_type == action_type,
            PermissionGrant.revoked_at.is_(None),
            applies_to(PermissionGrant, campaign_id),
        )
    )).scalars())


async def find_grant(
    session: AsyncSession,
    campaign_id: str,
    action_type: str,
    scope: str | None,
    est_spend_usd: Decimal | None = None,
) -> PermissionGrant | None:
    grants = await grants_for(session, campaign_id, action_type)
    return strictest([g for g in grants if _grant_matches(g, action_type, scope, est_spend_usd)])


async def used_today(session: AsyncSession, campaign_id: str, action_type: str) -> int:
    """How many times this goal did this kind of action without asking in the last 24 hours."""
    from app.models import AutonomousAction, utcnow

    return (await session.execute(
        select(func.count()).select_from(AutonomousAction).where(
            AutonomousAction.campaign_id == campaign_id, AutonomousAction.action_type == action_type,
            AutonomousAction.created_at > utcnow() - timedelta(hours=24),
        )
    )).scalar_one()


@dataclass
class Decision:
    outcome: str  # "allow" | "heads_up" | "ask" | "block"
    action_type: str
    reason: str = ""
    grant_id: str | None = None
    rule_id: str | None = None

    @property
    def autonomous(self) -> bool:
        """Goes ahead without a person saying yes first (a grant, not a default like research)."""
        return self.outcome in ("allow", "heads_up") and self.grant_id is not None


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
    """Hard blocks first, then default policy, then grants, then daily caps. (AI rule check runs
    separately, and can only make the outcome stricter.)"""
    if action_type not in ACTION_TYPES:
        action_type = "other_write"
    rules = rules if rules is not None else await exclusions_for(session, campaign_id)
    block = check_hard_blocks(rules, action_type=action_type, app=app, site=site)
    if block:
        return Decision("block", action_type, block.reason, rule_id=block.rule_id)
    if ACTION_TYPES[action_type].default == "auto":
        return Decision("allow", action_type, "Allowed by default.")
    grant = await find_grant(session, campaign_id, action_type, app or (domain_of(site) if site else None), est_spend_usd)
    if not grant:
        return Decision("ask", action_type, "Needs your approval.")
    mode = grant.mode or "auto"
    if mode == "ask":
        why = {"downgrade": "It was stopped or flagged recently, so it asks first again.",
               "personal": "This is a personal account, so it always asks first."}.get(grant.source or "", "Set to ask first.")
        return Decision("ask", action_type, why, grant_id=grant.id)
    if grant.daily_cap is not None and await used_today(session, campaign_id, action_type) >= grant.daily_cap:
        label = ACTION_TYPES[action_type].label.lower()
        return Decision("ask", action_type,
                        f"It already did {grant.daily_cap} \"{label}\" on its own in the last 24 hours (the daily limit), so it's asking you.",
                        grant_id=grant.id)
    if mode == "heads_up":
        return Decision("heads_up", action_type, "Goes ahead after a heads-up unless someone stops it.", grant_id=grant.id)
    return Decision("allow", action_type, "You allowed this without asking.", grant_id=grant.id)
