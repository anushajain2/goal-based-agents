"""Desktop helper: pairing, the helper's connection, and the private relay the worker uses.

    helper app  ──wss /api/helper/connect──▶  API  ◀──ws /api/helper/relay/{device}──  worker

The worker drives the helper's Chrome with the same browser code it uses for a local Chrome
(Chrome DevTools Protocol), so reading pages, the click guard and approvals all stay on the
server. Over the helper's single connection, each worker session is a numbered channel:

    API -> helper   {"t": "open", "c": 3}              open a DevTools connection to Chrome
    both ways       {"t": "d", "c": 3, "d": "<text>"}  one DevTools message
    API -> helper   {"t": "close", "c": 3}             the worker is done
    helper -> API   {"t": "closed", "c": 3, "error"?}  Chrome closed it (or couldn't open it)
    API -> helper   {"t": "open_url" | "manual_signin", "url": ...}, {"t": "manual_done"}
    helper -> API   {"t": "ping" | "status", "paused": bool}  every ~25 s and on change

Connections live in this process's memory, so the API runs as one instance (Render: one
instance of autopilot-api; scale the worker instead).
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth
from app.config import get_settings
from app.db import get_session, session_scope
from app.models import HelperDevice, Organization, utcnow
from app.org import Member, current_member
from app.services import helpers

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/helper", tags=["helper"])
PROTOCOL = 1


class HelperConn:
    def __init__(self, device_id: str, ws: WebSocket) -> None:
        self.device_id = device_id
        self.ws = ws
        self.channels: dict[int, WebSocket] = {}
        self._next = 0
        self._lock = asyncio.Lock()

    async def send(self, msg: dict) -> None:
        async with self._lock:
            await self.ws.send_text(json.dumps(msg))

    def open_channel(self, ws: WebSocket) -> int:
        self._next += 1
        self.channels[self._next] = ws
        return self._next

    async def close_all(self) -> None:
        for ws in list(self.channels.values()):
            with contextlib.suppress(Exception):
                await ws.close(code=1012)
        self.channels.clear()


class HelperHub:
    def __init__(self) -> None:
        self.conns: dict[str, HelperConn] = {}

    def get(self, device_id: str) -> HelperConn | None:
        return self.conns.get(device_id)

    async def drop(self, device_id: str) -> None:
        conn = self.conns.pop(device_id, None)
        if conn:
            await conn.close_all()
            with contextlib.suppress(Exception):
                await conn.ws.close(code=4401)


hub = HelperHub()


# --- pairing (from the app) ---------------------------------------------------------------

@router.post("/pairings")
async def create_pairing(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    code, pairing = await helpers.new_pairing(s, me.org_id, me.user.id)
    return {"code": code, "key": helpers.pair_key(code), "link": helpers.pair_link(code),
            "expires_at": pairing.expires_at.isoformat(), "download_url": get_settings().helper_download_url}


@router.get("/devices")
async def list_devices(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    return [helpers.device_json(d) for d in await helpers.devices(s, me.org_id)]


@router.delete("/devices/{device_id}")
async def remove_device(device_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    device = await s.get(HelperDevice, device_id)
    if not device or device.org_id != me.org_id or device.revoked_at:
        raise HTTPException(404, "Computer not found")
    if not me.is_admin and device.user_id != me.user.id:
        raise HTTPException(403, "Only an admin or the person who connected it can remove this computer.")
    device.revoked_at = utcnow()
    await s.commit()
    await hub.drop(device_id)
    return {"ok": True}


# --- pairing (from the helper app) --------------------------------------------------------------

class PairIn(BaseModel):
    code: str = Field(max_length=40)
    name: str = Field(default="Computer", max_length=120)
    platform: str | None = Field(default=None, max_length=40)
    version: str | None = Field(default=None, max_length=40)


@router.post("/pair")
async def pair(body: PairIn, request: Request, s: AsyncSession = Depends(get_session)):
    ip = request.client.host if request.client else "?"
    auth._throttle(f"helper-pair:{ip}", 10, 600, "Too many tries. Wait a few minutes and get a new code.")
    redeemed = await helpers.redeem(s, body.code, body.name, body.platform, body.version)
    if not redeemed:
        raise HTTPException(400, "That code didn't work. Codes last 10 minutes and work once; get a new one in Oton.")
    device, token = redeemed
    org = await s.get(Organization, device.org_id)
    await s.commit()
    return {"token": token, "device_id": device.id, "name": device.name, "org_name": org.name if org else "",
            "server": get_settings().helper_server_url, "app_url": get_settings().frontend_origin}


@router.get("/pair/{code}")
async def pair_hint(code: str):
    return {"message": "This is a pairing link for the Oton desktop helper. Open the helper and paste it there."}


# --- the helper's connection ------------------------------------------------------------------------

async def _touch(device_id: str, paused: bool | None = None, offline: bool = False) -> None:
    async with session_scope() as s:
        device = await s.get(HelperDevice, device_id)
        if not device:
            return
        if offline:  # seen just now, but no longer online
            device.last_seen_at = utcnow() - timedelta(seconds=get_settings().helper_online_seconds + 1)
        else:
            device.last_seen_at = utcnow()
        if paused is not None:
            device.paused = paused


@router.websocket("/connect")
async def helper_connect(ws: WebSocket):
    token = (ws.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    async with session_scope() as s:
        device = await helpers.device_for_token(s, token)
        if device:
            device.last_seen_at = utcnow()
            device.app_version = (ws.headers.get("x-helper-version") or device.app_version or "")[:40] or None
            org = await s.get(Organization, device.org_id)
            info = {"id": device.id, "name": device.name, "org_name": org.name if org else ""}
    if not device:
        await ws.close(code=4401)
        return
    await ws.accept()
    device_id = info["id"]
    old = hub.conns.get(device_id)
    if old:  # the same computer reconnected: the newest connection wins
        await old.close_all()
        with contextlib.suppress(Exception):
            await old.ws.close(code=4409)
    conn = HelperConn(device_id, ws)
    hub.conns[device_id] = conn
    log.info("desktop helper %s connected", device_id)
    try:
        await conn.send({"t": "hello", "protocol": PROTOCOL, "device": info})
        while True:
            msg = json.loads(await ws.receive_text())
            t = msg.get("t")
            if t == "d":
                target = conn.channels.get(msg.get("c"))
                if target:
                    try:
                        await target.send_text(msg.get("d") or "")
                    except Exception:  # noqa: BLE001 - that worker went away
                        conn.channels.pop(msg.get("c"), None)
            elif t == "closed":
                target = conn.channels.pop(msg.get("c"), None)
                if target:
                    with contextlib.suppress(Exception):
                        await target.close(code=1011 if msg.get("error") else 1000)
            elif t in ("ping", "status"):
                paused = msg.get("paused")
                await _touch(device_id, paused=bool(paused) if paused is not None else None)
                if t == "ping":
                    await conn.send({"t": "pong"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:  # noqa: BLE001
        log.warning("desktop helper %s connection error", device_id, exc_info=True)
    finally:
        if hub.conns.get(device_id) is conn:
            hub.conns.pop(device_id, None)
            await conn.close_all()
            await _touch(device_id, offline=True)
        log.info("desktop helper %s disconnected", device_id)


# --- the worker's side ---------------------------------------------------------------------------------

@router.websocket("/relay/{device_id}")
async def relay(ws: WebSocket, device_id: str):
    """A worker's DevTools connection to a helper's Chrome (private network only, keyed)."""
    if not hmac.compare_digest(ws.headers.get("x-relay-key") or "", helpers.relay_key()):
        await ws.close(code=4403)
        return
    conn = hub.get(device_id)
    if not conn:
        await ws.close(code=4404)
        return
    await ws.accept()
    ch = conn.open_channel(ws)
    try:
        await conn.send({"t": "open", "c": ch})
        while True:
            data = await ws.receive_text()
            await conn.send({"t": "d", "c": ch, "d": data})
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:  # noqa: BLE001 - the helper went away; the worker sees the socket close
        pass
    finally:
        if conn.channels.pop(ch, None) is not None:
            with contextlib.suppress(Exception):
                await conn.send({"t": "close", "c": ch})
        with contextlib.suppress(Exception):
            await ws.close()


async def send_to_helper(s: AsyncSession, org_id: str, msg: dict) -> HelperDevice:
    """Tell the organization's online helper to do something (open a site to sign in...)."""
    device = await helpers.online_device(s, org_id)
    conn = hub.get(device.id) if device else None
    if not device or not conn:
        raise HTTPException(409, "Your desktop helper isn't connected. Open the Oton helper on your computer "
                                 "(and un-pause it), then try again.")
    await conn.send(msg)
    return device
