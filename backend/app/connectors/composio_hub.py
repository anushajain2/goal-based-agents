"""App connectors via Composio (optional).

Composio provides ready-made actions for 1,000+ apps and handles their OAuth. We call it
from our own backend, never let the model reach it directly, so every write goes through
the policy pipeline (agent/actions.py) before `execute()` runs.

The Composio SDK is synchronous; calls are pushed to a thread so the event loop stays free.
One Composio key serves every organization: each organization's connected accounts are kept
apart under its own Composio user ("autopilot-<org id>"). The key is the platform's
(COMPOSIO_API_KEY in .env), or an organization can use its own, pasted in the app (stored
encrypted). With neither, `ComposioHub.enabled` is False and the agent falls back to Agent
Chrome for everything.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from app.config import get_settings
from app.services.policy import classify_app_action

log = logging.getLogger(__name__)


@dataclass
class AppAction:
    slug: str
    name: str
    description: str
    toolkit: str
    parameters: dict
    version: str | None
    tags: list[str]

    @property
    def action_type(self) -> str:
        return classify_app_action(self.slug, self.tags)

    def for_agent(self) -> dict:
        return {
            "slug": self.slug,
            "app": self.toolkit,
            "description": (self.description or self.name)[:600],
            "kind": self.action_type,
            "parameters": _compact_schema(self.parameters),
        }


def _compact_schema(schema: dict) -> dict:
    """Trim a JSON schema to what the agent needs (keeps tokens - and cost - down)."""
    if not isinstance(schema, dict):
        return {}
    props = {}
    for name, spec in (schema.get("properties") or {}).items():
        if not isinstance(spec, dict):
            continue
        entry = {k: spec[k] for k in ("type", "enum", "items", "default") if k in spec}
        if spec.get("description"):
            entry["description"] = str(spec["description"])[:200]
        props[name] = entry
    return {"properties": props, "required": schema.get("required", [])}


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_action(tool: Any) -> AppAction:
    toolkit = _get(tool, "toolkit") or {}
    return AppAction(
        slug=_get(tool, "slug"),
        name=_get(tool, "name") or _get(tool, "slug"),
        description=_get(tool, "description") or "",
        toolkit=(_get(toolkit, "slug") or "").lower(),
        parameters=_get(tool, "input_parameters") or {},
        version=_get(tool, "version"),
        tags=list(_get(tool, "tags") or []),
    )


class ComposioHub:
    def __init__(self, api_key: str | None = None, source: str = "platform") -> None:
        self.settings = get_settings()
        self.api_key = api_key if api_key is not None else self.settings.composio_api_key
        self.source = source if self.api_key else None  # "platform" | "org" | None
        self._schema_cache: dict[str, AppAction] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @cached_property
    def _client(self):
        from composio import Composio

        return Composio(api_key=self.api_key)

    def user_id(self, owner_id: str | None) -> str:
        """Composio keeps each Autopilot user's connected accounts separate."""
        return f"autopilot-{owner_id}" if owner_id else self.settings.composio_user_id

    async def search_actions(self, query: str, app: str | None = None, limit: int = 8) -> list[AppAction]:
        def _run():
            kwargs: dict[str, Any] = {"search": query, "limit": limit}
            if app:
                kwargs["toolkits"] = [app.lower()]
            return self._client.tools.get_raw_composio_tools(**kwargs)

        tools = await asyncio.to_thread(_run)
        actions = [_to_action(t) for t in tools]
        for a in actions:
            self._schema_cache[a.slug] = a
        return actions

    async def get_action(self, slug: str) -> AppAction:
        if slug in self._schema_cache:
            return self._schema_cache[slug]
        tool = await asyncio.to_thread(self._client.tools.get_raw_composio_tool_by_slug, slug)
        action = _to_action(tool)
        self._schema_cache[slug] = action
        return action

    async def execute(self, slug: str, arguments: dict, owner_id: str | None = None) -> dict:
        action = await self.get_action(slug)

        def _run():
            kwargs: dict[str, Any] = {"user_id": self.user_id(owner_id)}
            if action.version and action.version != "latest":
                kwargs["version"] = action.version
            else:
                kwargs["dangerously_skip_version_check"] = True
            return self._client.tools.execute(slug, arguments, **kwargs)

        result = await asyncio.to_thread(_run)
        return {
            "successful": bool(_get(result, "successful")),
            "data": _get(result, "data"),
            "error": _get(result, "error"),
        }

    async def connected_apps(self, owner_id: str | None = None) -> list[dict]:
        def _run():
            return self._client.connected_accounts.list(user_ids=[self.user_id(owner_id)])

        response = await asyncio.to_thread(_run)
        out = []
        for item in _get(response, "items") or []:
            out.append(
                {
                    "id": _get(item, "id"),
                    "app": (_get(_get(item, "toolkit") or {}, "slug") or "").lower(),
                    "status": _get(item, "status"),
                }
            )
        return out

    async def is_connected(self, app: str, owner_id: str | None = None) -> bool:
        return any(
            c["app"] == app.lower() and c["status"] == "ACTIVE" for c in await self.connected_apps(owner_id)
        )

    async def connect_link(self, app: str, owner_id: str | None = None, callback_url: str | None = None) -> dict:
        """Start Composio-managed OAuth for an app; returns the link the user opens."""

        def _run():
            client = self._client
            configs = client.auth_configs.list(toolkit_slug=app.lower())
            items = sorted(_get(configs, "items") or [], key=lambda x: str(_get(x, "created_at")), reverse=True)
            if items:
                auth_config_id = _get(items[0], "id")
            else:
                auth_config_id = _get(
                    client.auth_configs.create(app.lower(), {"type": "use_composio_managed_auth"}), "id"
                )
            request = client.connected_accounts.link(
                self.user_id(owner_id), auth_config_id, callback_url=callback_url, allow_multiple=True
            )
            return {"connection_id": request.id, "redirect_url": request.redirect_url}

        return await asyncio.to_thread(_run)

    async def list_apps(self, limit: int = 60) -> list[dict]:
        def _run():
            return self._client.toolkits.get()

        toolkits = await asyncio.to_thread(_run)
        out = []
        for tk in list(toolkits)[:limit]:
            meta = _get(tk, "meta") or {}
            out.append({"slug": _get(tk, "slug"), "name": _get(tk, "name"), "logo": _get(meta, "logo")})
        return out


_hubs: dict[tuple[str, str], ComposioHub] = {}


def get_hub(api_key: str | None = None, source: str = "platform") -> ComposioHub:
    """One hub (and SDK client) per key."""
    key = api_key if api_key is not None else (get_settings().composio_api_key or "")
    if (key, source) not in _hubs:
        _hubs[(key, source)] = ComposioHub(key, source)
    return _hubs[(key, source)]


async def hub_for_org(org_id: str | None, s=None) -> ComposioHub:
    """The organization's own Composio key if it added one, else the platform's. Pass the
    request's session when there is one (SQLite allows one writer at a time)."""
    if org_id:
        from sqlalchemy import select

        from app.db import session_scope
        from app.models import Integration
        from app.services.secrets_box import unseal

        q = select(Integration.secret_encrypted).where(Integration.org_id == org_id, Integration.kind == "composio").limit(1)
        if s is not None:
            row = (await s.execute(q)).scalar_one_or_none()
        else:
            async with session_scope() as own:
                row = (await own.execute(q)).scalar_one_or_none()
        key = unseal(row) if row else None
        if key:
            return get_hub(key, "org")
    return get_hub()
