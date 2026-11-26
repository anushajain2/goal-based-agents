"""A small client for MCP (Model Context Protocol) servers over Streamable HTTP.

Oton only needs two things from a server: its list of tools, and calling one. That is
three JSON-RPC requests (initialize, tools/list, tools/call), whose replies come back either as
JSON or as a short server-sent-event stream. Calling tools from here, instead of letting the
model provider call them, is what lets every call pass the approval gate first.
"""

from __future__ import annotations

import itertools
import json
from typing import Any

import httpx

from app.config import get_settings
from app.services.website import UnsafeURL, _assert_public

PROTOCOL_VERSION = "2025-06-18"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)
MAX_RESULT_CHARS = 20000
TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests point this at an in-process server


class McpError(Exception):
    pass


def kind_of(tool: dict) -> str:
    """Which kind of action a tool is, for the approval rules. Only tools the server marks as
    read-only run on their own; everything else counts as a change and asks first."""
    from app.services.policy import classify_app_action, stricter

    hints = tool.get("annotations") or {}
    if hints.get("readOnlyHint") is True:
        return "read_data"
    guess = classify_app_action("MCP_" + str(tool.get("name", "")).upper().replace("-", "_").replace(".", "_"))
    if guess == "read_data":  # a read-sounding name without the read-only mark: still ask
        guess = "other_write"
    if hints.get("destructiveHint") is True:
        guess = stricter(guess, "delete_content")
    return guess


class McpClient:
    def __init__(self, url: str, auth_header: str | None = None, http: httpx.AsyncClient | None = None):
        self.url = url
        self.headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if auth_header and ":" in auth_header:
            name, value = auth_header.split(":", 1)
            self.headers[name.strip()] = value.strip()
        self._http = http
        self._own_http = http is None
        self._ids = itertools.count(1)
        self.session_id: str | None = None
        self.server_info: dict = {}

    async def __aenter__(self) -> McpClient:
        if not get_settings().allow_private_mcp:
            try:
                await _assert_public(self.url)
            except UnsafeURL as e:
                raise McpError(str(e)) from e
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=TIMEOUT, transport=TRANSPORT)
        result = await self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "oton", "version": "1.0"},
        })
        self.server_info = result.get("serverInfo") or {}
        self.headers["MCP-Protocol-Version"] = result.get("protocolVersion") or PROTOCOL_VERSION
        await self._rpc("notifications/initialized", None, notify=True)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._own_http and self._http is not None:
            await self._http.aclose()

    async def _rpc(self, method: str, params: dict | None, *, notify: bool = False) -> dict:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        rid = None
        if not notify:
            rid = next(self._ids)
            payload["id"] = rid
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        try:
            r = await self._http.post(self.url, json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise McpError(f"Couldn't reach the MCP server ({type(e).__name__}).") from e
        if r.headers.get("mcp-session-id"):
            self.session_id = r.headers["mcp-session-id"]
        if notify:
            return {}
        if r.status_code in (401, 403):
            raise McpError("The MCP server refused the request: check its key.")
        if r.status_code >= 400:
            raise McpError(f"The MCP server answered with an error (HTTP {r.status_code}).")
        for message in self._messages(r):
            if message.get("id") == rid:
                if "error" in message:
                    raise McpError(str(message["error"].get("message") or message["error"])[:500])
                return message.get("result") or {}
        raise McpError("The MCP server didn't answer the request.")

    @staticmethod
    def _messages(r: httpx.Response) -> list[dict]:
        ctype = r.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            out, data = [], []
            for line in r.text.splitlines() + [""]:
                if line.startswith("data:"):
                    data.append(line[5:].lstrip())
                elif not line.strip() and data:
                    try:
                        parsed = json.loads("\n".join(data))
                        out += parsed if isinstance(parsed, list) else [parsed]
                    except json.JSONDecodeError:
                        pass
                    data = []
            return out
        try:
            parsed = r.json()
        except ValueError as e:
            raise McpError("The MCP server sent something that isn't JSON.") from e
        return parsed if isinstance(parsed, list) else [parsed]

    async def list_tools(self) -> list[dict]:
        tools, cursor = [], None
        for _ in range(10):
            result = await self._rpc("tools/list", {"cursor": cursor} if cursor else {})
            for t in result.get("tools") or []:
                tools.append({
                    "name": t.get("name", ""), "description": (t.get("description") or "")[:600],
                    "input_schema": t.get("inputSchema") or {"type": "object"},
                    "annotations": t.get("annotations") or {},
                })
            cursor = result.get("nextCursor")
            if not cursor:
                break
        for t in tools:
            t["kind"] = kind_of(t)
        return tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        parts = []
        for block in result.get("content") or []:
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            else:
                parts.append(f"[{block.get('type')} content]")
        if result.get("structuredContent") and not parts:
            parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
        text = "\n".join(parts)
        return {"is_error": bool(result.get("isError")), "text": text[:MAX_RESULT_CHARS]}
