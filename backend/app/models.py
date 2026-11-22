"""Database models.

Money is stored as Numeric (Decimal) in USD. Every table that the UI renders as a feed
(activity) uses a monotonically increasing integer id so clients can resume from the
last id they saw.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.dbtypes import BigIntPK, JSONType, UTCDateTime


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


Money = Numeric(14, 6)


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    out_of_budget = "out_of_budget"
    completed = "completed"


class RunStatus(str, enum.Enum):
    queued = "queued"  # ready for a worker to pick up (new or resumed)
    running = "running"  # a worker holds it
    waiting = "waiting"  # paused on one or more user requests (approval / login / connect)
    completed = "completed"
    failed = "failed"
    stopped = "stopped"  # campaign paused / budget exhausted / cancelled


class RequestKind(str, enum.Enum):
    action = "action"  # "I'm going to post this - can I go ahead?"
    login = "login"  # "Please sign in to X in Agent Chrome"
    connect = "connect"  # "Please connect your HubSpot account" (Composio OAuth link)


class RequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class LedgerKind(str, enum.Enum):
    ai_usage = "ai_usage"
    spend = "spend"


class LedgerStatus(str, enum.Enum):
    reserved = "reserved"
    settled = "settled"
    released = "released"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)  # stored lower-case
    name: Mapped[str] = mapped_column(String(200), default="")
    # Google account id ("sub"), set when the user signs in with Google.
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    # Unused since sign-in became passwordless; kept so older databases upgrade cleanly.
    password_hash: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class LoginCode(Base):
    """A one-time sign-in code sent by email. Only a keyed hash of the code is stored."""

    __tablename__ = "login_codes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AuthSession(Base):
    """A signed-in browser. Only a hash of the token is stored; the token lives in an httpOnly cookie."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())


class Role(str, enum.Enum):
    owner = "owner"  # everything, including other admins
    admin = "admin"  # manage departments, people, AI employees; approve anything
    member = "member"  # approve for their departments; manage their departments' goals


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")  # in the founders' own words
    # What setup research learned (see agent/org_setup.py): summary, stage, team, customers...
    profile: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class OrgSetup(Base):
    """One run of "research the company, then set up its AI team" (done by the worker)."""

    __tablename__ = "org_setups"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued|running|done|failed
    # [{key, label, status: pending|running|done|failed|skipped, detail}]
    steps: Mapped[list] = mapped_column(JSONType, default=list)
    research: Mapped[str] = mapped_column(Text, default="")  # the research brief, with sources
    plan: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # departments and goals proposed
    created: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # ids of what was set up
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class Membership(Base):
    """A person in an organization. (One organization per person for now.)"""

    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    role: Mapped[str] = mapped_column(String(20), default=Role.member.value)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    # Library category this department covers (sales, marketing, research...), used to suggest
    # which AI employee should take a new goal. Empty for custom departments.
    kind: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class DepartmentMember(Base):
    """A person who belongs to a department, and so approves its AI employees' work."""

    __tablename__ = "department_members"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


class Agent(Base):
    """An AI employee. Belongs to one department; goals are assigned to it."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(160), default="")  # e.g. "Outbound sales"
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Invitation(Base):
    """Someone invited by email. They join automatically the first time they sign in with it."""

    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(20), default=Role.member.value)
    department_ids: Mapped[list] = mapped_column(JSONType, default=list)
    invited_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    # Who created it. (Before organizations existed, this was the only owner.)
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    org_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # The AI employee working on it.
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    goal_type: Mapped[str] = mapped_column(String(50))  # sales | followers | traffic | leads | awareness | custom
    goal_description: Mapped[str] = mapped_column(Text)
    primary_metric: Mapped[str] = mapped_column(String(120))
    # When a result counts as done, in plain words (e.g. "Meeting held on calendar").
    done_when: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), default="")  # use-case category, e.g. "Sales"
    use_case: Mapped[str] = mapped_column(String(120), default="")  # sub-category, e.g. "Cold outbound"
    client_name: Mapped[str] = mapped_column(String(200), default="")  # agencies: who this goal is for
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    context: Mapped[str] = mapped_column(Text, default="")  # product, audience, voice, links
    origin: Mapped[str] = mapped_column(String(20), default="")  # "setup" = suggested by setup research
    suggested_reason: Mapped[str] = mapped_column(Text, default="")  # why setup suggested this goal
    channels: Mapped[list] = mapped_column(JSONType, default=list)  # app/site hints, e.g. ["twitter", "linkedin"]

    budget_total: Mapped[Decimal] = mapped_column(Money)
    daily_cap: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=CampaignStatus.draft.value)
    strategy: Mapped[str] = mapped_column(Text, default="")  # agent-maintained, plain English
    cycle_hours: Mapped[float] = mapped_column(Float, default=6.0)
    next_cycle_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    cycles_completed: Mapped[int] = mapped_column(Integer, default=0)
    # Bumped whenever guardrails change so a running agent picks up the change immediately.
    guardrail_version: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    exclusions: Mapped[list[ExclusionRule]] = relationship(back_populates="campaign", cascade="all, delete")


class ExclusionRule(Base):
    """Something the agent must not do.

    kind = action_type  -> hard block on a category (e.g. send_message), enforced in code
    kind = app          -> hard block on a connected app (e.g. "linkedin")
    kind = site         -> hard block on a website domain (e.g. "reddit.com")
    kind = text         -> free-text rule, given to the agent and checked by an AI reviewer
    campaign_id NULL    -> applies to every goal of that owner
    """

    __tablename__ = "exclusion_rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    # Legacy (single-user) owner. Scope is now: campaign_id (one goal), else department_id
    # (every goal in that department), else the whole organization.
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    org_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    campaign: Mapped[Campaign | None] = relationship(back_populates="exclusions")


class PermissionGrant(Base):
    """A standing "go ahead and don't ask me next time" permission.

    campaign_id NULL means the grant covers all of the owner's goals. `scope` optionally narrows it to
    one app or site (e.g. publish_post on "twitter" only). Spending grants carry a per-action
    limit; actions above it still ask.
    """

    __tablename__ = "permission_grants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    org_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    granted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True, index=True
    )
    action_type: Mapped[str] = mapped_column(String(50))
    scope: Mapped[str | None] = mapped_column(String(200), nullable=True)
    spend_limit_usd: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AgentRun(Base):
    """One optimization cycle. `messages` is the append-only Claude conversation."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    cycle_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.queued.value, index=True)
    messages: Mapped[list] = mapped_column(JSONType, default=list)
    # Set while waiting on user requests: the tool calls of the latest assistant turn and
    # the results gathered so far (see agent/runner.py).
    pending: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    guardrail_version_seen: Mapped[int] = mapped_column(Integer, default=0)
    # Fixed at the start of a run so the tool list never changes mid-conversation.
    uses_apps: Mapped[bool] = mapped_column(Boolean, default=False)
    nudges: Mapped[int] = mapped_column(Integer, default=0)
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class UserRequest(Base):
    """Something the agent needs from the user: an approval, a sign-in, or an app connection."""

    __tablename__ = "user_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    tool_use_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=RequestStatus.pending.value, index=True)
    # Routed to the people in this department (the AI employee's department).
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    action_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    scope: Mapped[str | None] = mapped_column(String(200), nullable=True)  # app slug or site domain
    title: Mapped[str] = mapped_column(String(300))
    rationale: Mapped[str] = mapped_column(Text, default="")
    # What exactly will happen: {"content": "...", "target": "...", "fields": {...}, "url": "...",
    # "screenshot": "file.png"}. `editable` lists keys of preview.fields the user may edit.
    preview: Mapped[dict] = mapped_column(JSONType, default=dict)
    est_spend_usd: Mapped[Decimal | None] = mapped_column(Money, nullable=True)

    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_fields: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    remember: Mapped[bool] = mapped_column(Boolean, default=False)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class BrowserAuthorization(Base):
    """Approval token that lets browser 'commit' clicks (Post / Send / Buy...) through the guard."""

    __tablename__ = "browser_authorizations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    uses_remaining: Mapped[int] = mapped_column(Integer, default=3)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Activity(Base):
    """The user-facing log: one row per key action."""

    __tablename__ = "activity"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # action | blocked | request | decision | cycle | strategy | metric | note | budget | error | system
    kind: Mapped[str] = mapped_column(String(20))
    action_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(100), nullable=True)  # app slug / site / "web"
    title: Mapped[str] = mapped_column(String(400))
    # done | failed | blocked | waiting | approved | rejected | info
    status: Mapped[str] = mapped_column(String(20), default="done")
    cost_usd: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    __table_args__ = (Index("ix_activity_campaign_id_id", "campaign_id", "id"),)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    amount_usd: Mapped[Decimal] = mapped_column(Money)
    description: Mapped[str] = mapped_column(String(300))
    meta: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    metric: Mapped[str] = mapped_column(String(120))
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
