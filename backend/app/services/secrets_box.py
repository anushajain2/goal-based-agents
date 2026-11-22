"""Encrypt small secrets (like an MCP server's API key) at rest with the app's secret key."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _box() -> Fernet:
    key = hashlib.sha256(b"autopilot-secrets:" + get_settings().secret()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def seal(value: str) -> str:
    return _box().encrypt(value.encode()).decode()


def unseal(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _box().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
