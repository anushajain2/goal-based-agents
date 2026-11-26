"""Desktop helpers: computers that lend AI employees a Chrome window.

Pairing: someone in the organization asks for a code in the app (valid 10 minutes, single use).
The helper app sends it to POST /api/helper/pair and gets its own long-lived token back. Only
hashes of codes and tokens are stored. Removing a computer in the app revokes its token at once.

Online: a connected helper pings every ~25 s; the API records last_seen_at. A helper that is
paused, revoked, or unseen for `helper_online_seconds` is offline, and website steps wait for it.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import HelperDevice, HelperPairing, utcnow

PAIRING_TTL = timedelta(minutes=10)
# No 0/O, 1/I/L: easy to read aloud and type.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _hash(kind: str, value: str) -> str:
    return hmac.new(get_settings().secret(), f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def normalize_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch in _ALPHABET)


def relay_key() -> str:
    """Shared by the API and the worker (both know SECRET_KEY) for the private relay."""
    return _hash("relay", "helper-relay")


def pair_key(code: str) -> str:
    """One string the helper needs: where to connect and the code. Pasted, or opened as a link."""
    return f"{get_settings().helper_server_url}/api/helper/pair/{code}"


def pair_link(code: str) -> str:
    return "autopilot://pair?key=" + quote(pair_key(code), safe="")


async def new_pairing(s: AsyncSession, org_id: str, user_id: str | None) -> tuple[str, HelperPairing]:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    code = f"{raw[:4]}-{raw[4:]}"
    pairing = HelperPairing(org_id=org_id, user_id=user_id, code_hash=_hash("pair", raw),
                            expires_at=utcnow() + PAIRING_TTL)
    s.add(pairing)
    await s.flush()
    return code, pairing


async def redeem(s: AsyncSession, code: str, name: str, platform: str | None,
                 version: str | None) -> tuple[HelperDevice, str] | None:
    """Swap a pairing code for a device and its token (shown once, to the helper)."""
    raw = normalize_code(code)
    if len(raw) != 8:
        return None
    pairing = (await s.execute(select(HelperPairing).where(HelperPairing.code_hash == _hash("pair", raw))
                               .with_for_update())).scalar_one_or_none()
    if not pairing or pairing.used_at or pairing.expires_at < utcnow():
        return None
    pairing.used_at = utcnow()
    token = "aph_" + secrets.token_urlsafe(32)
    device = HelperDevice(org_id=pairing.org_id, user_id=pairing.user_id, name=(name or "Computer")[:120],
                          platform=(platform or None) and platform[:40], app_version=(version or None) and version[:40],
                          token_hash=_hash("device", token))
    s.add(device)
    await s.flush()
    return device, token


async def device_for_token(s: AsyncSession, token: str) -> HelperDevice | None:
    if not token or not token.startswith("aph_"):
        return None
    device = (await s.execute(select(HelperDevice).where(HelperDevice.token_hash == _hash("device", token)))
              ).scalar_one_or_none()
    return device if device and not device.revoked_at else None


def is_online(device: HelperDevice) -> bool:
    if device.revoked_at or device.paused or not device.last_seen_at:
        return False
    return (utcnow() - device.last_seen_at).total_seconds() <= get_settings().helper_online_seconds


async def devices(s: AsyncSession, org_id: str) -> list[HelperDevice]:
    return list((await s.execute(
        select(HelperDevice).where(HelperDevice.org_id == org_id, HelperDevice.revoked_at.is_(None))
        .order_by(HelperDevice.last_seen_at.desc().nulls_last(), HelperDevice.created_at.desc())
    )).scalars())


async def online_device(s: AsyncSession, org_id: str) -> HelperDevice | None:
    """The computer website steps run on: the most recently seen online one."""
    return next((d for d in await devices(s, org_id) if is_online(d)), None)


def device_json(d: HelperDevice) -> dict:
    return {
        "id": d.id, "name": d.name, "platform": d.platform, "app_version": d.app_version,
        "online": is_online(d), "paused": d.paused,
        "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
        "created_at": d.created_at.isoformat(),
    }
