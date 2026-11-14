"""Server-Sent Events: one Postgres LISTEN connection, fanned out to every browser tab."""

from __future__ import annotations

import asyncio
import json
import logging

import asyncpg
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.services.events import CHANNEL

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["events"])


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._conn: asyncpg.Connection | None = None

    async def start(self) -> None:
        dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
        try:
            self._conn = await asyncpg.connect(dsn)
            await self._conn.add_listener(CHANNEL, self._on_notify)
        except Exception:  # noqa: BLE001 - the UI falls back to polling
            log.warning("could not start LISTEN for live updates", exc_info=True)

    async def stop(self) -> None:
        if self._conn:
            await self._conn.close()

    def _on_notify(self, _conn, _pid, _channel, payload: str) -> None:
        try:
            event = json.loads(payload)
        except ValueError:
            return
        for q in list(self._subscribers):
            if q.qsize() < 1000:
                q.put_nowait(event)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)


broadcaster = Broadcaster()


@router.get("/events")
async def events(request: Request, campaign_id: str | None = None):
    q = broadcaster.subscribe()

    async def stream():
        try:
            yield {"event": "ready", "data": "{}"}
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if campaign_id and event.get("campaign_id") not in (campaign_id, None):
                    continue
                yield {"event": event.get("type", "message"), "data": json.dumps(event)}
        finally:
            broadcaster.unsubscribe(q)

    return EventSourceResponse(stream())
