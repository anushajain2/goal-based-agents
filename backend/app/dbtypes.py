"""Column types that work the same on SQLite (local default) and Postgres (for scaling)."""

from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator

# JSONB on Postgres, plain JSON elsewhere.
JSONType = JSON().with_variant(JSONB(), "postgresql")

# SQLite only auto-increments INTEGER primary keys.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes everywhere.

    SQLite has no timezone support, so values are stored as naive UTC there and given
    their UTC timezone back when read.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        if dialect.name == "sqlite":
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
