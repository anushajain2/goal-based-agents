"""Live updates via Postgres LISTEN/NOTIFY.

Writers call `notify()` inside their transaction; Postgres delivers the notification on
commit, so listeners never see an event for data that was rolled back. The API's SSE
endpoint listens on one channel and fans events out to browser clients.
"""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CHANNEL = "autopilot_events"


async def notify(session: AsyncSession, campaign_id: str | None, event_type: str, **data) -> None:
    payload = json.dumps({"campaign_id": campaign_id, "type": event_type, **data}, default=str)
    await session.execute(text("SELECT pg_notify(:channel, :payload)"), {"channel": CHANNEL, "payload": payload})
