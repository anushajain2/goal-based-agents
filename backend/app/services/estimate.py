"""How a goal's budget is worked out, in a way people can check.

    budget ≈ number of work sessions × cost of one session + money it may spend (ads, purchases)

The cost of one session is the average of the organization's own recent sessions once there
are a few of them, and a typical figure until then. The budget stays a hard limit: when it
runs out, work pauses.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AgentRun, Campaign, LedgerEntry, LedgerKind, RunStatus

DEFAULT_DAYS = 30
MIN_HISTORY = 3


async def session_cost(s: AsyncSession, org_id: str | None, campaign_id: str | None = None) -> tuple[float, str, int]:
    """(cost per session, "history" | "typical", sessions it's based on)."""
    q = (
        select(AgentRun.id, func.sum(LedgerEntry.amount_usd))
        .join(LedgerEntry, LedgerEntry.run_id == AgentRun.id)
        .join(Campaign, Campaign.id == AgentRun.campaign_id)
        .where(AgentRun.status == RunStatus.completed.value, LedgerEntry.kind == LedgerKind.ai_usage.value,
               LedgerEntry.status == "settled")
        .group_by(AgentRun.id).order_by(func.max(AgentRun.updated_at).desc()).limit(30)
    )
    q = q.where(Campaign.id == campaign_id) if campaign_id else q.where(Campaign.org_id == org_id)
    costs = [float(c or 0) for _, c in (await s.execute(q)).all()]
    if len(costs) >= MIN_HISTORY:
        return round(sum(costs) / len(costs), 3), "history", len(costs)
    return get_settings().est_session_cost_usd, "typical", 0


def compute(per_session: float, cycle_hours: float, days: float, paid_spend: float = 0.0,
            basis: str = "typical", history_sessions: int = 0) -> dict:
    cycle_hours = max(float(cycle_hours or 6), 0.5)
    days = max(float(days or DEFAULT_DAYS), 1)
    sessions = math.ceil(days * 24 / cycle_hours)
    ai = sessions * per_session
    paid = max(float(paid_spend or 0), 0)
    suggested = max(5, math.ceil((ai + paid) / 5) * 5)  # round up to the next $5
    return {
        "per_session_usd": round(per_session, 3), "sessions": sessions, "cycle_hours": cycle_hours, "days": days,
        "ai_usd": round(ai, 2), "paid_spend_usd": round(paid, 2), "suggested_usd": suggested,
        "basis": basis, "history_sessions": history_sessions,
    }


async def estimate(s: AsyncSession, org_id: str | None, cycle_hours: float, days: float | None = None,
                   paid_spend: float = 0.0) -> dict:
    per, basis, n = await session_cost(s, org_id)
    return compute(per, cycle_hours, days or DEFAULT_DAYS, paid_spend, basis, n)


def days_until(end: datetime | None) -> float:
    if not end:
        return DEFAULT_DAYS
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return max(1.0, (end - datetime.now(UTC)).total_seconds() / 86400)


async def pace(s: AsyncSession, campaign: Campaign, remaining: Decimal) -> dict | None:
    """Once a goal has run a few sessions: what each actually costs, and how far the rest goes."""
    per, basis, n = await session_cost(s, campaign.org_id, campaign.id)
    if basis != "history" or per <= 0:
        return None
    sessions_left = int(Decimal(str(remaining)) // Decimal(str(per)))
    return {"per_session_usd": per, "sessions_measured": n, "sessions_left": sessions_left,
            "days_left": round(sessions_left * campaign.cycle_hours / 24, 1)}
