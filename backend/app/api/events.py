"""Server-Sent Events, fanned out to every browser tab.

Postgres: one LISTEN connection delivers each change as it is committed.
SQLite: a light poll (every 1.5 s) notices changes and tells the tabs to refresh.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sse_starlette.sse import EventSourceResponse

from app.auth import current_user_brief
from app.config import get_settings
from app.db import is_sqlite, session_scope
from app.services.events import CHANNEL

log = logging.getLogger(__name__)
# Signed-in users only. Events carry ids, not data; each tab refetches through the
# owner-scoped endpoints, so nobody sees another user's data.
router = APIRouter(prefix="/api", tags=["events"], dependencies=[Depends(current_user_brief)])


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._conn = None
        self._poller: asyncio.Task | None = None

    async def start(self) -> None:
        if is_sqlite():
            self._poller = asyncio.create_task(self._poll())
            return
        import asyncpg

        dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
        try:
            self._conn = await asyncpg.connect(dsn)
            await self._conn.add_listener(CHANNEL, self._on_notify)
        except Exception:
            log.warning("could not start LISTEN for live updates", exc_info=True)

    async def stop(self) -> None:
        if self._poller:
            self._poller.cancel()
        if self._conn:
            await self._conn.close()

    async def _poll(self) -> None:
        signature_sql = text(
            "SELECT (SELECT max(id) FROM activity), (SELECT max(id) FROM metric_snapshots),"
            " (SELECT max(updated_at) FROM campaigns), (SELECT max(updated_at) FROM agent_runs),"
            " (SELECT count(*) FROM user_requests WHERE status = 'pending')"
        )
        last = None
        while True:
            try:
                if self._subscribers:
                    async with session_scope() as s:
                        sig = tuple((await s.execute(signature_sql)).one())
                    if last is not None and sig != last:
                        self._broadcast({"type": "activity", "campaign_id": None})
                    last = sig
            except Exception:
                log.debug("live-update poll failed", exc_info=True)
            await asyncio.sleep(1.5)

    def _on_notify(self, _conn, _pid, _channel, payload: str) -> None:
        try:
            event = json.loads(payload)
        except ValueError:
            return
        self._broadcast(event)

    def _broadcast(self, event: dict) -> None:
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
                except TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if campaign_id and event.get("campaign_id") not in (campaign_id, None):
                    continue
                yield {"event": event.get("type", "message"), "data": json.dumps(event)}
        finally:
            broadcaster.unsubscribe(q)

    return EventSourceResponse(stream())
