"""Live updates.

On Postgres, writers call `notify()` inside their transaction and Postgres delivers it on
commit (LISTEN/NOTIFY). On SQLite there is no such channel: `notify()` does nothing and
the API instead watches the database for changes (see api/events.py).
"""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CHANNEL = "autopilot_events"


async def notify(session: AsyncSession, campaign_id: str | None, event_type: str, **data) -> None:
    if session.bind.dialect.name != "postgresql":
        return
    payload = json.dumps({"campaign_id": campaign_id, "type": event_type, **data}, default=str)
    await session.execute(text("SELECT pg_notify(:channel, :payload)"), {"channel": CHANNEL, "payload": payload})
