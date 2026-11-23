"""Connections an organization sets up itself: a GitHub repository (by signing in with GitHub, or a
token), a read-only Postgres database, and optionally its own Composio key for app connections."""

from __future__ import annotations

import json
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.connectors import github as github_mod
from app.connectors.composio_hub import ComposioHub
from app.connectors.database import QueryError, check_connection
from app.connectors.github import GitHub, GitHubError
from app.db import get_session
from app.models import Integration
from app.org import Member, current_member, require_admin
from app.services.secrets_box import seal, unseal

GITHUB_WEB = "https://github.com"
STATE_MAX_AGE = 15 * 60

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


def integration_json(i: Integration) -> dict:
    return {"id": i.id, "kind": i.kind, "name": i.name, "config": i.config or {}, "error": i.last_error,
            "created_at": i.created_at.isoformat()}


@router.get("")
async def list_integrations(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    rows = (await s.execute(select(Integration).where(Integration.org_id == me.org_id).order_by(Integration.created_at))).scalars()
    return [integration_json(i) for i in rows]


async def _replace(s: AsyncSession, org_id: str, *kinds: str) -> None:
    await s.execute(delete(Integration).where(Integration.org_id == org_id, Integration.kind.in_(kinds)))


# --- the organization's own Composio key (optional; the platform's key is used otherwise) -------

class ComposioIn(BaseModel):
    api_key: str = Field(min_length=10, max_length=300)


async def check_composio_key(key: str, org_id: str) -> None:
    """Raises if Composio doesn't accept the key."""
    await ComposioHub(key, "org").connected_apps(org_id)


@router.post("/composio")
async def use_own_composio(body: ComposioIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    key = body.api_key.strip()
    try:
        await check_composio_key(key, me.org_id)
    except Exception as e:  # noqa: BLE001 - any failure means the key can't be used
        raise HTTPException(400, f"Composio didn't accept that key ({type(e).__name__}).") from e
    await _replace(s, me.org_id, "composio")
    i = Integration(org_id=me.org_id, kind="composio", name="Composio (your own key)", secret_encrypted=seal(key),
                    config={"key_hint": key[-4:]}, created_by=me.user.id)
    s.add(i)
    await s.flush()
    return integration_json(i)


# --- GitHub: sign in with GitHub, then pick a repository -------------------------------------

def _github_app() -> tuple[str, str]:
    st = get_settings()
    if not (st.github_client_id and st.github_client_secret):
        raise HTTPException(400, "GitHub sign-in isn't set up on this Autopilot. Use a token instead.")
    return st.github_client_id, st.github_client_secret


@router.get("/github/sign-in")
async def github_sign_in(me: Member = Depends(current_member)):
    """The GitHub page that asks the person to let Autopilot work on their repositories."""
    require_admin(me)
    client_id, _ = _github_app()
    state = seal(json.dumps({"org": me.org_id, "user": me.user.id, "t": int(time.time())}))
    redirect = get_settings().frontend_origin.rstrip("/") + "/api/integrations/github/callback"
    return {"url": f"{GITHUB_WEB}/login/oauth/authorize?" + urlencode(
        {"client_id": client_id, "redirect_uri": redirect, "scope": "repo", "state": state, "allow_signup": "false"})}


@router.get("/github/callback")
async def github_callback(code: str = "", state: str = "", error: str = "",
                          s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    back = get_settings().frontend_origin.rstrip("/") + "/connections"
    if error or not code:
        return RedirectResponse(back + "?github=cancelled")
    try:
        data = json.loads(unseal(state) or "{}")
    except ValueError:
        data = {}
    if data.get("org") != me.org_id or data.get("user") != me.user.id or time.time() - data.get("t", 0) > STATE_MAX_AGE:
        return RedirectResponse(back + "?github=expired")
    client_id, secret = _github_app()
    try:
        async with httpx.AsyncClient(timeout=20, transport=github_mod.TRANSPORT) as client:
            r = await client.post(f"{GITHUB_WEB}/login/oauth/access_token", headers={"Accept": "application/json"},
                                  data={"client_id": client_id, "client_secret": secret, "code": code})
        token = r.json().get("access_token")
    except (httpx.HTTPError, ValueError):
        token = None
    if not token:
        return RedirectResponse(back + "?github=failed")
    await _replace(s, me.org_id, "github_pending")
    s.add(Integration(org_id=me.org_id, kind="github_pending", name="GitHub (choose a repository)",
                      secret_encrypted=seal(token), config={}, created_by=me.user.id))
    return RedirectResponse(back + "?github=choose")


async def _pending_token(s: AsyncSession, org_id: str) -> str:
    row = (await s.execute(select(Integration).where(Integration.org_id == org_id, Integration.kind == "github_pending")
                           .limit(1))).scalar_one_or_none()
    token = unseal(row.secret_encrypted) if row else None
    if not token:
        raise HTTPException(400, "Sign in with GitHub first.")
    return token


@router.get("/github/repos")
async def github_repos(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    try:
        return await GitHub(await _pending_token(s, me.org_id), "-/-").my_repos()
    except GitHubError as e:
        raise HTTPException(400, str(e)) from e


class RepoIn(BaseModel):
    repo: str = Field(min_length=3, max_length=200, pattern=r"^[\w.-]+/[\w.-]+$")


@router.post("/github/repo")
async def github_choose_repo(body: RepoIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    token = await _pending_token(s, me.org_id)
    try:
        info = await GitHub(token, body.repo).repo_info()
    except GitHubError as e:
        raise HTTPException(400, str(e)) from e
    await _replace(s, me.org_id, "github", "github_pending")
    i = Integration(org_id=me.org_id, kind="github", name=info["full_name"], secret_encrypted=seal(token),
                    config={"repo": info["full_name"], "default_branch": info["default_branch"], "via": "sign_in"},
                    created_by=me.user.id)
    s.add(i)
    await s.flush()
    return integration_json(i)


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
