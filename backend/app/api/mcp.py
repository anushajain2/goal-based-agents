"""Custom tools: MCP servers the organization connects for its AI employees."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.mcp_client import McpClient, McpError
from app.db import get_session
from app.models import McpServer, utcnow
from app.org import Member, current_member, require_admin
from app.services.policy import ACTION_TYPES
from app.services.secrets_box import seal, unseal

router = APIRouter(prefix="/api/mcp-servers", tags=["mcp"])


def server_json(m: McpServer) -> dict:
    return {
        "id": m.id, "name": m.name, "url": m.url, "has_key": bool(m.auth_encrypted),
        "tools": [{"name": t["name"], "description": t.get("description", ""), "kind": t.get("kind", "other_write"),
                   "kind_label": ACTION_TYPES.get(t.get("kind", ""), ACTION_TYPES["other_write"]).label,
                   "asks_first": t.get("kind") not in ("read_data", "research")} for t in m.tools or []],
        "error": m.last_error, "checked_at": m.checked_at.isoformat() if m.checked_at else None,
    }


async def refresh(m: McpServer) -> None:
    try:
        async with McpClient(m.url, unseal(m.auth_encrypted)) as client:
            m.tools = await client.list_tools()
        m.last_error = None
    except McpError as e:
        m.last_error = str(e)
    m.checked_at = utcnow()


@router.get("")
async def list_servers(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    rows = (await s.execute(select(McpServer).where(McpServer.org_id == me.org_id)
                            .order_by(McpServer.created_at))).scalars()
    return [server_json(m) for m in rows]


class ServerIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=8, max_length=500, pattern=r"^https?://")
    auth_header: str | None = Field(default=None, max_length=4000)


@router.post("")
async def add_server(body: ServerIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    name = re.sub(r"[^a-z0-9_-]+", "-", body.name.strip().lower()).strip("-")[:40] or "server"
    taken = (await s.execute(select(McpServer.id).where(McpServer.org_id == me.org_id, McpServer.name == name))).first()
    if taken:
        raise HTTPException(409, f'There is already a server called "{name}".')
    auth = (body.auth_header or "").strip()
    if auth and ":" not in auth:
        auth = f"Authorization: Bearer {auth}"  # a bare key: the usual header
    m = McpServer(org_id=me.org_id, name=name, url=body.url.strip(), auth_encrypted=seal(auth) if auth else None,
                  created_by=me.user.id)
    await refresh(m)
    s.add(m)
    await s.flush()
    return server_json(m)


async def _server(s: AsyncSession, me: Member, server_id: str) -> McpServer:
    m = await s.get(McpServer, server_id)
    if not m or m.org_id != me.org_id:
        raise HTTPException(404, "Server not found")
    return m


@router.post("/{server_id}/refresh")
async def refresh_server(server_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    m = await _server(s, me, server_id)
    await refresh(m)
    return server_json(m)


@router.delete("/{server_id}")
async def delete_server(server_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    await s.delete(await _server(s, me, server_id))
    return {"ok": True}
