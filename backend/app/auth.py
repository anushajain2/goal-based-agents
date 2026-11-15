"""Accounts and sign-in, without passwords.

Two ways in:

* **Continue with Google**: the OAuth 2.0 authorization-code flow with PKCE, a random `state`
  (stops forged sign-in links) and `nonce` (stops replayed ID tokens). The ID token comes
  straight from Google's token endpoint over TLS, and we check who issued it, who it is for,
  its expiry, the nonce, and that Google has verified the email address.
* **Email me a code**: a 6-digit code, valid for 10 minutes, at most 5 tries, at most 5 codes
  an hour per address. Only a keyed hash of the code is stored.

Either way the browser gets a random session token in an httpOnly cookie (page scripts can't
read it); only its SHA-256 hash is stored. The first account on a fresh install takes over
any goals created before accounts existed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session, session_scope
from app.models import AuthSession, Campaign, ExclusionRule, LoginCode, PermissionGrant, User, utcnow
from app.services.mailer import send_login_code

COOKIE = "autopilot_session"
OAUTH_COOKIE = "autopilot_oauth"
SESSION_DAYS = 30
CODE_MINUTES = 10
CODE_MAX_ATTEMPTS = 5
CODES_PER_HOUR = 5

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _code_hash(email: str, code: str) -> str:
    return hmac.new(get_settings().secret(), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def safe_next(next_path: str | None) -> str:
    """Only redirect back into the app, never to another site."""
    return next_path if next_path and next_path.startswith("/") and not next_path.startswith("//") else "/home"


# --- light brute-force protection (per process) -----------------------------------------

_attempts: dict[str, list[float]] = defaultdict(list)


def _throttle(key: str, limit: int, window: float, message: str) -> None:
    now = time.monotonic()
    recent = [t for t in _attempts[key] if now - t < window]
    if len(recent) >= limit:
        _attempts[key] = recent
        raise HTTPException(429, message)
    recent.append(now)
    _attempts[key] = recent


# --- users & sessions ----------------------------------------------------------------------

async def _find_or_create_user(
    s: AsyncSession, email: str, name: str = "", google_sub: str | None = None
) -> tuple[User, bool]:
    """Returns (user, created). Google accounts are linked to an existing account with the same email."""
    user = None
    if google_sub:
        user = (await s.execute(select(User).where(User.google_sub == google_sub))).scalar_one_or_none()
    if user is None:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user and google_sub and not user.google_sub:
            user.google_sub = google_sub
    if user:
        if name and not user.name:
            user.name = name
        return user, False
    first_user = (await s.execute(select(func.count()).select_from(User))).scalar_one() == 0
    user = User(email=email, name=name, google_sub=google_sub)
    s.add(user)
    await s.flush()
    if first_user:
        # Goals and rules made before accounts existed now belong to the first account.
        for model in (Campaign, ExclusionRule, PermissionGrant):
            await s.execute(update(model).where(model.owner_id.is_(None)).values(owner_id=user.id))
    return user, True


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or get_settings().frontend_origin.startswith("https")


async def _start_session(s: AsyncSession, response: Response, user: User, request: Request) -> None:
    token = secrets.token_urlsafe(32)
    s.add(AuthSession(token_hash=_token_hash(token), user_id=user.id,
                      expires_at=utcnow() + timedelta(days=SESSION_DAYS)))
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=_secure(request), path="/")


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


# --- common endpoints ----------------------------------------------------------------------

@router.get("/options")
async def options():
    """Which sign-in methods are available (the login page shows only these)."""
    settings = get_settings()
    return {"google": settings.google_enabled, "email_delivery": "email" if settings.smtp_enabled else "console"}


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return user_json(user)


class ProfileIn(BaseModel):
    name: str = Field(max_length=200)


@router.patch("/me")
async def update_me(body: ProfileIn, user: User = Depends(current_user)):
    user.name = body.name.strip()
    return user_json(user)


@router.post("/logout")
async def logout(response: Response, autopilot_session: str | None = Cookie(default=None),
                 s: AsyncSession = Depends(get_session)):
    if autopilot_session:
        await s.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(autopilot_session)))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


# --- email codes -----------------------------------------------------------------------------

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class EmailIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=EMAIL_PATTERN)


class CodeIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=EMAIL_PATTERN)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


@router.post("/email/start")
async def email_start(body: EmailIn, request: Request, s: AsyncSession = Depends(get_session)):
    email = body.email.strip().lower()
    ip = request.client.host if request.client else "?"
    _throttle(f"email-ip:{ip}", 20, 3600, "Too many codes requested. Please wait a while and try again.")
    sent_last_hour = (
        await s.execute(
            select(func.count()).select_from(LoginCode)
            .where(LoginCode.email == email, LoginCode.created_at > utcnow() - timedelta(hours=1))
        )
    ).scalar_one()
    if sent_last_hour >= CODES_PER_HOUR:
        raise HTTPException(429, "We've sent several codes to this address already. Please wait a while and try again.")
    code = f"{secrets.randbelow(10**6):06d}"
    # Only the newest code works. Older ones are marked used (not deleted) so they still count
    # toward the hourly limit.
    await s.execute(
        update(LoginCode).where(LoginCode.email == email, LoginCode.used_at.is_(None)).values(used_at=utcnow())
    )
    s.add(LoginCode(email=email, code_hash=_code_hash(email, code),
                    expires_at=utcnow() + timedelta(minutes=CODE_MINUTES)))
    await s.flush()
    try:
        delivery = await send_login_code(email, code)
    except Exception as e:
        import logging

        logging.getLogger("autopilot.mail").exception("sending sign-in code failed")
        raise HTTPException(502, "We couldn't send the email. Please try again, or use another way to sign in.") from e
    return {"sent": True, "delivery": delivery}


@router.post("/email/verify")
async def email_verify(body: CodeIn, request: Request, s: AsyncSession = Depends(get_session)):
    email = body.email.strip().lower()
    row = (
        await s.execute(
            select(LoginCode).where(LoginCode.email == email, LoginCode.used_at.is_(None))
            .order_by(LoginCode.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if not row or row.expires_at < utcnow():
        return JSONResponse({"detail": "That code has expired. Request a new one."}, status_code=400)
    if row.attempts >= CODE_MAX_ATTEMPTS:
        return JSONResponse({"detail": "Too many wrong tries. Request a new code."}, status_code=400)
    if not hmac.compare_digest(row.code_hash, _code_hash(email, body.code)):
        # Returned (not raised) so the attempt count is saved.
        row.attempts += 1
        left = CODE_MAX_ATTEMPTS - row.attempts
        msg = "That code isn't right." + (f" {left} {'try' if left == 1 else 'tries'} left." if left else " Request a new code.")
        return JSONResponse({"detail": msg}, status_code=400)
    row.used_at = utcnow()
    user, created = await _find_or_create_user(s, email)
    response = JSONResponse({**user_json(user), "new": created})
    await _start_session(s, response, user, request)
    return response


# --- Google ------------------------------------------------------------------------------------

def _sign(data: dict) -> str:
    raw = _b64url(json.dumps(data, separators=(",", ":")).encode())
    sig = _b64url(hmac.new(get_settings().secret(), raw.encode(), hashlib.sha256).digest())
    return f"{raw}.{sig}"


def _unsign(value: str | None) -> dict | None:
    if not value or "." not in value:
        return None
    raw, sig = value.rsplit(".", 1)
    expected = _b64url(hmac.new(get_settings().secret(), raw.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    data = json.loads(_b64url_decode(raw))
    return data if data.get("exp", 0) > time.time() else None


def _redirect_uri() -> str:
    return get_settings().frontend_origin.rstrip("/") + "/api/auth/google/callback"


@router.get("/google/start")
async def google_start(request: Request, next: str | None = None):
    settings = get_settings()
    if not settings.google_enabled:
        raise HTTPException(404, "Google sign-in isn't set up")
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    response = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)
    response.set_cookie(
        OAUTH_COOKIE,
        _sign({"state": state, "nonce": nonce, "verifier": verifier, "next": safe_next(next), "exp": time.time() + 600}),
        max_age=600, httponly=True, samesite="lax", secure=_secure(request), path="/api/auth/google",
    )
    return response


async def exchange_google_code(code: str, verifier: str) -> dict:
    """Swap the authorization code for tokens at Google's token endpoint."""
    s = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
            "redirect_uri": _redirect_uri(), "grant_type": "authorization_code", "code_verifier": verifier,
        })
    r.raise_for_status()
    return r.json()


def _login_error(message: str, request: Request) -> RedirectResponse:
    response = RedirectResponse(f"/login?{urlencode({'error': message})}", status_code=302)
    response.delete_cookie(OAUTH_COOKIE, path="/api/auth/google")
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
    autopilot_oauth: str | None = Cookie(default=None), s: AsyncSession = Depends(get_session),
):
    saved = _unsign(autopilot_oauth)
    if error:
        return _login_error("Google sign-in was cancelled.", request)
    if not saved or not state or not hmac.compare_digest(saved["state"], state) or not code:
        return _login_error("That sign-in link has expired. Please try again.", request)
    try:
        tokens = await exchange_google_code(code, saved["verifier"])
        claims = json.loads(_b64url_decode(tokens["id_token"].split(".")[1]))
    except Exception:  # noqa: BLE001
        return _login_error("Google sign-in didn't work. Please try again.", request)

    settings = get_settings()
    if (
        claims.get("iss") not in GOOGLE_ISSUERS
        or claims.get("aud") != settings.google_client_id
        or float(claims.get("exp", 0)) < time.time()
        or not hmac.compare_digest(str(claims.get("nonce", "")), saved["nonce"])
        or not claims.get("sub")
    ):
        return _login_error("Google sign-in couldn't be verified. Please try again.", request)
    if not claims.get("email") or claims.get("email_verified") not in (True, "true"):
        return _login_error("Your Google account's email isn't verified, so we can't use it to sign in.", request)

    user, _ = await _find_or_create_user(
        s, str(claims["email"]).lower(), name=str(claims.get("name") or ""), google_sub=str(claims["sub"])
    )
    response = RedirectResponse(saved["next"], status_code=302)
    response.delete_cookie(OAUTH_COOKIE, path="/api/auth/google")
    await _start_session(s, response, user, request)
    return response
