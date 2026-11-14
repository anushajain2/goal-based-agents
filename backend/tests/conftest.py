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
