"""Connections: Composio apps, Agent Chrome sign-ins, and system status."""

from __future__ import annotations

from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.browser import chrome
from app.config import get_settings
from app.connectors.composio_hub import get_hub
from app.db import get_session
from app.models import Campaign, RequestKind, RequestStatus, UserRequest
from app.org import Member, current_member

# Everything here needs a signed-in member of an organization. App connections are shared by the
# whole organization (the company's accounts), like the AI employees that use them.
router = APIRouter(prefix="/api", tags=["connections"], dependencies=[Depends(current_member)])


class UrlIn(BaseModel):
    url: str


@router.get("/status")
async def status():
    settings = get_settings()
    return {
        "anthropic_configured": bool(settings.anthropic_api_key),
        "composio_enabled": settings.composio_enabled,
        "chrome_path": chrome.find_chrome(),
        "agent_chrome_running": await chrome.cdp_ready(),
        "manual_signin_mode": chrome.manual_mode_active(),
        "models": {
            "planner": settings.planner_model,
            "worker": settings.worker_model,
            "checker": settings.checker_model,
        },
    }


@router.get("/apps")
async def apps():
    hub = get_hub()
    if not hub.enabled:
        return {"enabled": False, "apps": []}
    return {"enabled": True, "apps": await hub.list_apps()}


@router.get("/connections")
async def connections(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    hub = get_hub()
    app_conns: list[dict] = []
    error = None
    if hub.enabled:
        try:
            app_conns = await hub.connected_apps(me.org_id)
        except Exception as e:  # noqa: BLE001
            error = f"Could not reach Composio: {e}"
    sites = (
        await s.execute(
            select(UserRequest.scope, func.max(UserRequest.decided_at))
            .join(Campaign, Campaign.id == UserRequest.campaign_id)
            .where(Campaign.org_id == me.org_id, UserRequest.kind == RequestKind.login.value,
                   UserRequest.status == RequestStatus.approved.value)
            .group_by(UserRequest.scope)
        )
    ).all()
    return {
        "composio_enabled": hub.enabled,
        "apps": app_conns,
        "error": error,
        "sites": [{"site": site, "signed_in_at": at.isoformat() if at else None} for site, at in sites],
    }


@router.post("/connections/{app}/connect")
async def connect_app(app: str, me: Member = Depends(current_member)):
    hub = get_hub()
    if not hub.enabled:
        raise HTTPException(400, "Add COMPOSIO_API_KEY to .env to use app connectors")
    return await hub.connect_link(app, me.org_id, callback_url=get_settings().frontend_origin + "/settings")


@router.post("/browser/open")
async def browser_open(body: UrlIn):
    """Open a page in Agent Chrome (e.g. to sign in to a site ahead of time)."""
    try:
        await chrome.ensure_agent_chrome()
    except chrome.ChromeUnavailable as e:
        raise HTTPException(400, str(e)) from e
    url = body.url if "://" in body.url else "https://" + body.url
    async with httpx.AsyncClient(timeout=5) as client:
        await client.put(chrome.cdp_url() + "/json/new?" + quote(url, safe=":/?=&%"))
    return {"ok": True}


@router.post("/browser/manual-signin")
async def manual_signin(body: UrlIn):
    """For sites that refuse sign-ins in a remote-controlled browser (e.g. Google)."""
    url = body.url if "://" in body.url else "https://" + body.url
    try:
        await chrome.start_manual_signin(url)
    except chrome.ChromeUnavailable as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@router.post("/browser/manual-signin/done")
async def manual_signin_done():
    await chrome.finish_manual_signin()
    return {"ok": True}


@router.get("/screenshots/{name}")
async def screenshot(name: str):
    if "/" in name or ".." in name:
        raise HTTPException(400, "Bad name")
    path = get_settings().screenshots_dir / name
    if not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path)
