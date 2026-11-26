"""Connections: Composio apps, Agent Chrome sign-ins, and system status."""

from __future__ import annotations

from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.browser import chrome
from app.config import get_settings
from app.connectors.composio_hub import hub_for_org
from app.db import get_session
from app.api.helper import send_to_helper
from app.models import Campaign, RequestKind, RequestStatus, Screenshot, SiteSignIn, UserRequest
from app.services import helpers
from app.org import Member, current_member

# Everything here needs a signed-in member of an organization. App connections are shared by the
# whole organization (the company's accounts), like the AI employees that use them.
router = APIRouter(prefix="/api", tags=["connections"], dependencies=[Depends(current_member)])


class UrlIn(BaseModel):
    url: str


@router.get("/status")
async def status(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    settings = get_settings()
    hub = await hub_for_org(me.org_id, s)
    return {
        "anthropic_configured": bool(settings.anthropic_api_key),
        "composio_enabled": hub.enabled,
        "composio_source": hub.source,  # "platform", "org" (its own key) or None
        "github_sign_in": bool(settings.github_client_id and settings.github_client_secret),
        "agent_chrome": settings.agent_chrome_enabled,
        "helper": await _helper_status(s, me.org_id) if not settings.agent_chrome_enabled else None,
        "chrome_path": chrome.find_chrome() if settings.agent_chrome_enabled else None,
        "agent_chrome_running": await chrome.cdp_ready() if settings.agent_chrome_enabled else False,
        "manual_signin_mode": chrome.manual_mode_active() if settings.agent_chrome_enabled else False,
        "models": {
            "planner": settings.planner_model,
            "worker": settings.worker_model,
            "checker": settings.checker_model,
        },
    }


@router.get("/apps")
async def apps(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    hub = await hub_for_org(me.org_id, s)
    if not hub.enabled:
        return {"enabled": False, "apps": []}
    return {"enabled": True, "apps": await hub.list_apps()}


@router.get("/connections")
async def connections(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    hub = await hub_for_org(me.org_id, s)
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
    latest: dict[str, object] = {}
    for site, at in list(sites) + list((await s.execute(
            select(SiteSignIn.site, SiteSignIn.signed_in_at).where(SiteSignIn.org_id == me.org_id))).all()):
        if site and (site not in latest or (at and (latest[site] is None or at > latest[site]))):
            latest[site] = at
    return {
        "composio_enabled": hub.enabled,
        "composio_source": hub.source,
        "apps": app_conns,
        "error": error,
        "sites": [{"site": site, "signed_in_at": at.isoformat() if at else None} for site, at in latest.items()],
    }


@router.post("/connections/{app}/connect")
async def connect_app(app: str, back: str = "/connections", s: AsyncSession = Depends(get_session),
                      me: Member = Depends(current_member)):
    hub = await hub_for_org(me.org_id, s)
    if not hub.enabled:
        raise HTTPException(400, "App connections aren't set up yet. Add a Composio key under Connections.")
    back = back if back.startswith("/") and not back.startswith("//") else "/connections"
    return await hub.connect_link(app, me.org_id, callback_url=get_settings().frontend_origin + back)


# --- everything the organization's goals use, in one place -----------------------------------

@router.get("/connections/overview")
async def overview(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    """Every tool the organization's goals use (live, paused or suggested), whether it's connected,
    which goals need it, and what those goals do with it on their own or only after an OK."""
    from app.agent.playbook import tools_needed
    from app.api.plan import signed_in_sites
    from app.models import Integration, McpServer
    from app.services.policy import ACTION_TYPES, domain_of

    hub = await hub_for_org(me.org_id, s)
    connected: set[str] = set()
    error = None
    if hub.enabled:
        try:
            connected = {a["app"] for a in await hub.connected_apps(me.org_id) if (a.get("status") or "").upper() == "ACTIVE"}
        except Exception as e:  # noqa: BLE001
            error = f"Couldn't reach Composio: {type(e).__name__}"
    sites = await signed_in_sites(s, me.org_id)
    linked = {k for (k,) in (await s.execute(select(Integration.kind).where(Integration.org_id == me.org_id))).all()}
    goals = (await s.execute(select(Campaign).where(
        Campaign.org_id == me.org_id, Campaign.status.in_(["active", "paused", "draft", "out_of_budget"]))
        .order_by(Campaign.created_at))).scalars().all()
    tools: dict[str, dict] = {}
    for g in goals:
        steps = (g.playbook or {}).get("steps") or []
        for t in tools_needed(g):
            e = tools.setdefault(t["key"], {**{k: t[k] for k in ("key", "label", "app", "site", "login_url", "kind")},
                                            "goals": [], "required": False, "on_its_own": [], "needs_ok": []})
            e["goals"].append({"id": g.id, "name": g.name, "status": g.status})
            e["required"] = e["required"] or (t["required"] and g.status != "draft")
            for i in t["steps"]:
                st = steps[i - 1] if 0 < i <= len(steps) else None
                if not st:
                    continue
                kind = ACTION_TYPES.get(st["action_type"])
                label = (kind.label if kind else st["action_type"]).lower()
                bucket = "on_its_own" if kind and kind.default == "auto" else "needs_ok"
                if label not in e[bucket]:
                    e[bucket].append(label)
    out = []
    for t in tools.values():
        if t["kind"] in ("github", "postgres"):
            state = "connected" if t["kind"] in linked else "missing"
        else:
            state = ("connected" if t["app"] and t["app"] in connected
                     else "signed_in" if t["site"] and domain_of(t["site"]) in sites else "missing")
        live = sum(1 for g in t["goals"] if g["status"] != "draft")
        out.append({**t, "status": state, "live_goals": live, "can_connect_app": bool(hub.enabled and t["app"])})
    # Missing tools that live goals need first, then the rest; connected ones last.
    out.sort(key=lambda t: (t["status"] != "missing", -t["live_goals"], t["label"]))
    servers = (await s.execute(select(McpServer).where(McpServer.org_id == me.org_id))).scalars().all()
    return {
        "tools": out,
        "summary": {"needed": len(out), "connected": sum(1 for t in out if t["status"] != "missing"),
                    "missing_live": sum(1 for t in out if t["status"] == "missing" and t["live_goals"])},
        "composio": {"enabled": hub.enabled, "source": hub.source, "error": error},
        "github_sign_in": bool(get_settings().github_client_id and get_settings().github_client_secret),
        "code_and_data": sorted(k for k in linked if k in ("github", "postgres")),
        "mcp_servers": len(servers),
    }


async def _helper_status(s: AsyncSession, org_id: str) -> dict:
    devices = await helpers.devices(s, org_id)
    online = next((d for d in devices if helpers.is_online(d)), None)
    return {"paired": len(devices), "online": bool(online), "device": (online or (devices[0] if devices else None)) and
            helpers.device_json(online or devices[0]), "download_url": get_settings().helper_download_url}


def _url(raw: str) -> str:
    return raw if "://" in raw else "https://" + raw


@router.post("/browser/open")
async def browser_open(body: UrlIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    """Open a page in Agent Chrome (e.g. to sign in to a site ahead of time). Hosted: in the
    Chrome window of the organization's desktop helper."""
    if not get_settings().agent_chrome_enabled:
        device = await send_to_helper(s, me.org_id, {"t": "open_url", "url": _url(body.url)})
        return {"ok": True, "where": device.name}
    try:
        await chrome.ensure_agent_chrome()
    except chrome.ChromeUnavailable as e:
        raise HTTPException(400, str(e)) from e
    url = body.url if "://" in body.url else "https://" + body.url
    async with httpx.AsyncClient(timeout=5) as client:
        await client.put(chrome.cdp_url() + "/json/new?" + quote(url, safe=":/?=&%"))
    return {"ok": True}


@router.post("/browser/manual-signin")
async def manual_signin(body: UrlIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    """For sites that refuse sign-ins in a remote-controlled browser (e.g. Google)."""
    if not get_settings().agent_chrome_enabled:
        device = await send_to_helper(s, me.org_id, {"t": "manual_signin", "url": _url(body.url)})
        return {"ok": True, "where": device.name}
    url = body.url if "://" in body.url else "https://" + body.url
    try:
        await chrome.start_manual_signin(url)
    except chrome.ChromeUnavailable as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@router.post("/browser/manual-signin/done")
async def manual_signin_done(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    if not get_settings().agent_chrome_enabled:
        await send_to_helper(s, me.org_id, {"t": "manual_done"})
        return {"ok": True}
    await chrome.finish_manual_signin()
    return {"ok": True}


@router.get("/screenshots/{name}")
async def screenshot(name: str, s: AsyncSession = Depends(get_session)):
    if "/" in name or ".." in name:
        raise HTTPException(400, "Bad name")
    shot = await s.get(Screenshot, name)
    if shot:
        return Response(shot.data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
    path = get_settings().screenshots_dir / name  # taken before screenshots moved to the database
    if not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path)
