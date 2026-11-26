"""WhatsApp: connect your number, choose what you get there, and Meta's webhook.

    GET    /api/whatsapp/me        is it available, is my number connected, my preferences
    POST   /api/whatsapp/link      a one-time code (and wa.me link) to send from my phone
    PUT    /api/whatsapp/me        what I get on WhatsApp (approvals, heads-ups, questions)
    DELETE /api/whatsapp/me        disconnect
    GET    /api/whatsapp/webhook   Meta's verification handshake
    POST   /api/whatsapp/webhook   messages and taps from WhatsApp (signed by Meta)
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.config import get_settings
from app.db import get_session
from app.models import User
from app.services import whatsapp

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


def _me(user: User) -> dict:
    st = get_settings()
    return {
        "available": whatsapp.enabled(),
        "connected": bool(user.whatsapp_number),
        "number": whatsapp.masked(user.whatsapp_number),
        "connected_at": user.whatsapp_linked_at.isoformat() if user.whatsapp_linked_at else None,
        "prefs": whatsapp.prefs_of(user),
        "business_number": st.whatsapp_business_number if whatsapp.enabled() else None,
    }


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return _me(user)


@router.post("/link")
async def link(s: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    if not whatsapp.enabled():
        raise HTTPException(400, "WhatsApp isn't set up on this Oton yet.")
    u = await s.get(User, user.id)
    return {**whatsapp.start_link(u), **_me(u)}


class PrefsIn(BaseModel):
    approvals: bool | None = None
    heads_ups: bool | None = None
    questions: bool | None = None


@router.put("/me")
async def set_prefs(body: PrefsIn, s: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    u = await s.get(User, user.id)
    u.whatsapp_prefs = {**whatsapp.prefs_of(u), **body.model_dump(exclude_none=True)}
    return _me(u)


@router.delete("/me")
async def disconnect(s: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    u = await s.get(User, user.id)
    whatsapp.unlink(u)
    return _me(u)


@router.get("/webhook")
async def verify(request: Request):
    q = request.query_params
    token = get_settings().whatsapp_verify_token
    if q.get("hub.mode") == "subscribe" and token and q.get("hub.verify_token") == token:
        return PlainTextResponse(q.get("hub.challenge") or "")
    raise HTTPException(403, "Verification failed")


@router.post("/webhook")
async def webhook(request: Request, s: AsyncSession = Depends(get_session)):
    raw = await request.body()
    if not whatsapp.check_signature(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(403, "Bad signature")
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "Not JSON") from None
    try:
        await whatsapp.handle_webhook(s, data)
    except Exception:  # noqa: BLE001 - answer 200 so Meta doesn't retry a message that keeps failing
        log.exception("WhatsApp webhook failed")
        await s.rollback()
    return {"ok": True}
