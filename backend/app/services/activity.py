"""The user-facing activity log. One concise line per key action, details on click."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity
from app.services.events import notify


async def log(
    session: AsyncSession,
    campaign_id: str,
    kind: str,
    title: str,
    *,
    run_id: str | None = None,
    status: str = "done",
    action_type: str | None = None,
    channel: str | None = None,
    cost_usd: Decimal | float | None = None,
    details: dict | None = None,
) -> Activity:
    entry = Activity(
        campaign_id=campaign_id,
        run_id=run_id,
        kind=kind,
        title=title[:400],
        status=status,
        action_type=action_type,
        channel=channel,
        cost_usd=Decimal(str(cost_usd)) if cost_usd is not None else None,
        details=details or {},
    )
    session.add(entry)
    await session.flush()
    await notify(session, campaign_id, "activity", id=entry.id)
    return entry
