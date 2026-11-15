"""Accounts and sign-in.

* Passwords are hashed with scrypt (memory-hard, standard library) and a per-user salt.
* A sign-in creates a random session token, sent to the browser in an httpOnly cookie that
  page scripts cannot read. Only a SHA-256 hash of the token is stored, so a database leak
  does not leak usable sessions.
* The first account created on a fresh install takes ownership of any goals created before
  accounts existed (single-user installs upgrading to this version).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session, session_scope
from app.models import AuthSession, Campaign, ExclusionRule, PermissionGrant, User, utcnow

COOKIE = "autopilot_session"
SESSION_DAYS = 30
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}

router = APIRouter(prefix="/api/auth", tags=["auth"])


# --- passwords & tokens ------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, digest_b64 = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# Same cost as a real check, so response time doesn't reveal whether an email has an account.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


# --- simple brute-force protection (per process) ----------------------------------------

_attempts: dict[str, list[float]] = defaultdict(list)
_WINDOW, _MAX_ATTEMPTS = 15 * 60, 10


def _throttle(key: str) -> None:
    now = time.monotonic()
    recent = [t for t in _attempts[key] if now - t < _WINDOW]
    _attempts[key] = recent
    if len(recent) >= _MAX_ATTEMPTS:
        raise HTTPException(429, "Too many sign-in attempts. Please wait a few minutes and try again.")
    recent.append(now)


# --- sessions ----------------------------------------------------------------------------

async def _start_session(s: AsyncSession, response: Response, user: User, request: Request) -> None:
    token = secrets.token_urlsafe(32)
    s.add(AuthSession(token_hash=_token_hash(token), user_id=user.id,
                      expires_at=utcnow() + timedelta(days=SESSION_DAYS)))
    secure = request.url.scheme == "https" or get_settings().frontend_origin.startswith("https")
    response.set_cookie(
        COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=secure, path="/",
    )


async def current_user(
    autopilot_session: str | None = Cookie(default=None), s: AsyncSession = Depends(get_session)
) -> User:
    """FastAPI dependency: the signed-in user, or 401."""
    if not autopilot_session:
        raise HTTPException(401, "Please sign in")
    row = (
        await s.execute(
            select(User, AuthSession)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(AuthSession.token_hash == _token_hash(autopilot_session))
        )
    ).first()
    if not row or row[1].expires_at < utcnow():
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    return row[0]


async def current_user_brief(autopilot_session: str | None = Cookie(default=None)) -> str:
    """Like current_user, but for long-lived responses (live updates): checks the session in its
    own short transaction instead of holding one open for the whole stream. Returns the user id."""
    if not autopilot_session:
        raise HTTPException(401, "Please sign in")
    async with session_scope() as s:
        row = (
            await s.execute(
                select(AuthSession.user_id, AuthSession.expires_at)
                .where(AuthSession.token_hash == _token_hash(autopilot_session))
            )
        ).first()
    if not row or row[1] < utcnow():
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    return row[0]


def user_json(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name}


# --- endpoints -----------------------------------------------------------------------------

class SignupIn(BaseModel):
    name: str = Field(default="", max_length=200)
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


@router.post("/signup")
async def signup(body: SignupIn, request: Request, response: Response, s: AsyncSession = Depends(get_session)):
    _throttle("signup:" + (request.client.host if request.client else "?"))
    email = body.email.strip().lower()
    if (await s.execute(select(User.id).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, "An account with this email already exists. Try signing in.")
    first_user = (await s.execute(select(func.count()).select_from(User))).scalar_one() == 0
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    s.add(user)
    await s.flush()
    if first_user:
        # Goals and rules made before accounts existed now belong to the first account.
        for model in (Campaign, ExclusionRule, PermissionGrant):
            await s.execute(update(model).where(model.owner_id.is_(None)).values(owner_id=user.id))
    await _start_session(s, response, user, request)
    return user_json(user)


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, s: AsyncSession = Depends(get_session)):
    email = body.email.strip().lower()
    _throttle("login:" + email)
    user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        raise HTTPException(401, "That email and password don't match.")
    _attempts.pop("login:" + email, None)
    await _start_session(s, response, user, request)
    return user_json(user)


@router.post("/logout")
async def logout(response: Response, autopilot_session: str | None = Cookie(default=None),
                 s: AsyncSession = Depends(get_session)):
    if autopilot_session:
        await s.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(autopilot_session)))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return user_json(user)
