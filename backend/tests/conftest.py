import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://autopilot:autopilot@localhost:5433/autopilot_test"
)
os.environ["COMPOSIO_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = "test-key"

import pytest
from sqlalchemy import text

from app import models  # noqa: F401
from app.db import Base, get_engine


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
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
