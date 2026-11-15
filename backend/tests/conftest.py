import os
import tempfile

# SQLite by default (nothing to install). To test against Postgres:
#   TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/autopilot_test pytest
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/test.db"
)
os.environ["COMPOSIO_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = "test-key"

import pytest
from sqlalchemy import text

from app import models  # noqa: F401
from app.db import Base, get_engine, is_sqlite


@pytest.fixture(scope="session", autouse=True)
async def _schema():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean():
    yield
    async with get_engine().begin() as conn:
        if is_sqlite():
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(table.delete())
        else:
            tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
            await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _reset_sign_in_throttle():
    from app import auth

    auth._attempts.clear()
    yield


@pytest.fixture(autouse=True)
def _capture_sign_in_codes(monkeypatch):
    from app import auth
    from tests.helpers import SENT_CODES

    async def fake_send(to: str, code: str) -> str:
        SENT_CODES[to] = code
        return "email"

    monkeypatch.setattr(auth, "send_login_code", fake_send)
    SENT_CODES.clear()
    yield
