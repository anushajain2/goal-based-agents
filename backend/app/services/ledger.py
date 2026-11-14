"""Budget ledger.

Every cost is recorded against its campaign: the agent's own Claude usage (the bulk of it)
and any external spend (ads, purchases). Before anything that costs money runs, its
worst-case cost is *reserved*; if the reservation would exceed the total budget or the
daily cap, it is refused and the caller pauses. After the fact the reservation is
*settled* at the actual cost. This makes overspending impossible rather than unlikely.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Campaign, LedgerEntry, LedgerKind, LedgerStatus, utcnow

MTOK = Decimal(1_000_000)

# USD per million tokens: (input, output, cache write (5 min), cache read)
PRICES: dict[str, tuple[Decimal, Decimal, Decimal, Decimal]] = {
    "claude-opus-5-5": (Decimal(4), Decimal(20), Decimal(5), Decimal("0.20")),
    "claude-opus-5": (Decimal(5), Decimal(25), Decimal("6.25"), Decimal("0.50")),
    "claude-opus-4-8": (Decimal(5), Decimal(25), Decimal("6.25"), Decimal("0.50")),
    "claude-sonnet-5-5": (Decimal(2), Decimal(10), Decimal("2.50"), Decimal("0.10")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50"), Decimal("0.125"), Decimal("0.01")),
}
WEB_SEARCH_USD_PER_REQUEST = Decimal("0.01")  # $10 per 1,000 searches


class BudgetExceeded(Exception):
    def __init__(self, message: str, remaining: Decimal):
        super().__init__(message)
        self.remaining = remaining


def _q(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def prices_for(model: str) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    # Unknown model (e.g. a fallback we did not anticipate): price at the most expensive
    # known rate so the ledger errs on the side of over-counting.
    return PRICES.get(model) or max(PRICES.values(), key=lambda p: p[1])


def _get(obj, name: str, default=0):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default) or default
    return getattr(obj, name, default) or default


def cost_from_usage(model: str, usage) -> Decimal:
    """Actual cost of one Messages API response, from its `usage` block."""
    p_in, p_out, p_cw, p_cr = prices_for(model)
    cost = (
        Decimal(_get(usage, "input_tokens")) * p_in
        + Decimal(_get(usage, "output_tokens")) * p_out
        + Decimal(_get(usage, "cache_creation_input_tokens")) * p_cw
        + Decimal(_get(usage, "cache_read_input_tokens")) * p_cr
    ) / MTOK
    server = _get(usage, "server_tool_use", None)
    cost += Decimal(_get(server, "web_search_requests")) * WEB_SEARCH_USD_PER_REQUEST
    return _q(cost)


def worst_case_cost(model: str, est_input_tokens: int, max_tokens: int, max_web_searches: int = 0) -> Decimal:
    """Upper bound for a call: every input token uncached, every output token used."""
    p_in, p_out, p_cw, _ = prices_for(model)
    cost = (Decimal(est_input_tokens) * max(p_in, p_cw) + Decimal(max_tokens) * p_out) / MTOK
    cost += Decimal(max_web_searches) * WEB_SEARCH_USD_PER_REQUEST
    return _q(cost)


@dataclass
class BudgetState:
    total: Decimal
    settled: Decimal
    reserved: Decimal
    ai_usage: Decimal
    spend: Decimal
    today: Decimal
    daily_cap: Decimal | None

    @property
    def committed(self) -> Decimal:
        return self.settled + self.reserved

    @property
    def remaining(self) -> Decimal:
        return max(Decimal(0), self.total - self.committed)

    @property
    def remaining_today(self) -> Decimal | None:
        if self.daily_cap is None:
            return None
        return max(Decimal(0), self.daily_cap - self.today)

    @property
    def available(self) -> Decimal:
        """What can still be committed right now (respects the daily cap)."""
        today = self.remaining_today
        return self.remaining if today is None else min(self.remaining, today)

    def as_dict(self) -> dict:
        return {
            "total": float(self.total),
            "spent": float(self.settled),
            "reserved": float(self.reserved),
            "ai_usage": float(self.ai_usage),
            "other_spend": float(self.spend),
            "remaining": float(self.remaining),
            "today": float(self.today),
            "daily_cap": float(self.daily_cap) if self.daily_cap is not None else None,
        }


async def budget_state(session: AsyncSession, campaign: Campaign) -> BudgetState:
    active = LedgerEntry.status.in_([LedgerStatus.settled.value, LedgerStatus.reserved.value])
    rows = (
        await session.execute(
            select(LedgerEntry.kind, LedgerEntry.status, func.coalesce(func.sum(LedgerEntry.amount_usd), 0))
            .where(LedgerEntry.campaign_id == campaign.id, active)
            .group_by(LedgerEntry.kind, LedgerEntry.status)
        )
    ).all()
    settled = reserved = ai = spend = Decimal(0)
    for kind, status, amount in rows:
        amount = Decimal(amount)
        if status == LedgerStatus.settled.value:
            settled += amount
        else:
            reserved += amount
        if kind == LedgerKind.ai_usage.value:
            ai += amount
        else:
            spend += amount

    start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    today = (
        await session.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount_usd), 0)).where(
                LedgerEntry.campaign_id == campaign.id, active, LedgerEntry.created_at >= start_of_day
            )
        )
    ).scalar_one()
    return BudgetState(
        total=Decimal(campaign.budget_total),
        settled=settled,
        reserved=reserved,
        ai_usage=ai,
        spend=spend,
        today=Decimal(today),
        daily_cap=Decimal(campaign.daily_cap) if campaign.daily_cap is not None else None,
    )


async def reserve(
    session: AsyncSession,
    campaign_id: str,
    kind: LedgerKind,
    amount: Decimal,
    description: str,
    *,
    run_id: str | None = None,
    meta: dict | None = None,
) -> LedgerEntry:
    """Reserve `amount` or raise BudgetExceeded. Locks the campaign row to serialize reservations."""
    campaign = (
        await session.execute(select(Campaign).where(Campaign.id == campaign_id).with_for_update())
    ).scalar_one()
    state = await budget_state(session, campaign)
    amount = _q(Decimal(amount))
    if amount > state.available:
        which = "daily cap" if state.remaining_today is not None and amount > state.remaining_today else "budget"
        raise BudgetExceeded(
            f"Not enough {which} left: need ${amount:.4f}, available ${state.available:.4f}", state.available
        )
    entry = LedgerEntry(
        campaign_id=campaign_id,
        run_id=run_id,
        kind=kind.value,
        status=LedgerStatus.reserved.value,
        amount_usd=amount,
        description=description[:300],
        meta=meta or {},
    )
    session.add(entry)
    await session.flush()
    return entry


async def settle(session: AsyncSession, entry: LedgerEntry, actual: Decimal, meta: dict | None = None) -> None:
    entry.amount_usd = _q(Decimal(actual))
    entry.status = LedgerStatus.settled.value
    entry.settled_at = utcnow()
    if meta:
        entry.meta = {**(entry.meta or {}), **meta}
    await session.flush()


async def release(session: AsyncSession, entry: LedgerEntry) -> None:
    entry.status = LedgerStatus.released.value
    entry.settled_at = utcnow()
    await session.flush()
