"""Read-only SQL against an organization's own Postgres database, for analysis.

Three layers keep it read-only: only one SELECT-type statement is accepted, it runs inside a
READ ONLY transaction (the database itself refuses writes), and it has a statement timeout.
Use a read-only database user or a replica as well.
"""

from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid

import asyncpg

MAX_ROWS = 200
TIMEOUT_MS = 15_000
_ALLOWED = re.compile(r"^\s*(select|with|explain|show|values)\b", re.I)


class QueryError(Exception):
    pass


def check_sql(sql: str) -> str:
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise QueryError("Empty query.")
    if ";" in sql:
        raise QueryError("One statement at a time.")
    if not _ALLOWED.match(sql):
        raise QueryError("Only read queries (SELECT, WITH, EXPLAIN) are allowed.")
    return sql


def _plain(v):
    if isinstance(v, (dt.date, dt.datetime, dt.time)):
        return v.isoformat()
    if isinstance(v, (decimal.Decimal, uuid.UUID)):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(v))} bytes>"
    return v


async def run_read_only(url: str, sql: str) -> dict:
    sql = check_sql(sql)
    try:
        conn = await asyncpg.connect(url, timeout=10)
    except Exception as e:  # noqa: BLE001 - surface any connection problem plainly
        raise QueryError(f"Couldn't connect to the database ({type(e).__name__}).") from e
    try:
        async with conn.transaction(readonly=True):
            await conn.execute(f"SET LOCAL statement_timeout = {TIMEOUT_MS}")
            rows = await conn.fetch(sql)
    except asyncpg.PostgresError as e:
        raise QueryError(f"The database said: {e}".strip()[:500]) from e
    finally:
        await conn.close()
    out = [{k: _plain(v) for k, v in dict(r).items()} for r in rows[:MAX_ROWS]]
    return {"rows": out, "row_count": len(rows), "truncated": len(rows) > MAX_ROWS}


async def check_connection(url: str) -> list[str]:
    """Connect, and list a few tables so people see it worked."""
    result = await run_read_only(url, "select table_schema || '.' || table_name as t from information_schema.tables "
                                      "where table_schema not in ('pg_catalog', 'information_schema') order by 1 limit 50")
    return [r["t"] for r in result["rows"]]
