"""Code and data connections: a GitHub repository and a read-only Postgres database."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.database import QueryError, check_connection
from app.connectors.github import GitHub, GitHubError
from app.db import get_session
from app.models import Integration
from app.org import Member, current_member, require_admin
from app.services.secrets_box import seal

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


def integration_json(i: Integration) -> dict:
    return {"id": i.id, "kind": i.kind, "name": i.name, "config": i.config or {}, "error": i.last_error,
            "created_at": i.created_at.isoformat()}


@router.get("")
async def list_integrations(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    rows = (await s.execute(select(Integration).where(Integration.org_id == me.org_id).order_by(Integration.created_at))).scalars()
    return [integration_json(i) for i in rows]


class GitHubIn(BaseModel):
    repo: str = Field(min_length=3, max_length=200, pattern=r"^[\w.-]+/[\w.-]+$")
    token: str = Field(min_length=10, max_length=500)


@router.post("/github")
async def connect_github(body: GitHubIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    try:
        info = await GitHub(body.token.strip(), body.repo).repo_info()
    except GitHubError as e:
        raise HTTPException(400, str(e)) from e
    await s.execute(delete(Integration).where(Integration.org_id == me.org_id, Integration.kind == "github"))
    i = Integration(org_id=me.org_id, kind="github", name=info["full_name"], secret_encrypted=seal(body.token.strip()),
                    config={"repo": info["full_name"], "default_branch": info["default_branch"]}, created_by=me.user.id)
    s.add(i)
    await s.flush()
    return integration_json(i)


class DatabaseIn(BaseModel):
    name: str = Field(default="Database", min_length=1, max_length=120)
    url: str = Field(min_length=12, max_length=1000, pattern=r"^postgres(ql)?://")


@router.post("/postgres")
async def connect_database(body: DatabaseIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    try:
        tables = await check_connection(body.url.strip())
    except QueryError as e:
        raise HTTPException(400, str(e)) from e
    await s.execute(delete(Integration).where(Integration.org_id == me.org_id, Integration.kind == "postgres"))
    i = Integration(org_id=me.org_id, kind="postgres", name=body.name.strip(), secret_encrypted=seal(body.url.strip()),
                    config={"tables": tables[:50]}, created_by=me.user.id)
    s.add(i)
    await s.flush()
    return integration_json(i)


@router.delete("/{integration_id}")
async def disconnect(integration_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    i = await s.get(Integration, integration_id)
    if not i or i.org_id != me.org_id:
        raise HTTPException(404, "Not found")
    await s.delete(i)
    return {"ok": True}
