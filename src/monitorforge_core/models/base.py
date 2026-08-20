"""Base mixins shared by canonical schema models."""

import uuid

from sqlalchemy import BigInteger, Column, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

# BIGINT on Postgres; SQLite's autoincrement rowid alias requires a bare
# INTEGER primary key, so this falls back to that on SQLite (used by tests).
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class TimestampMixin:
    """created_at / updated_at, server-generated."""

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class UUIDMixin:
    """Stable external identifier, independent of the integer primary key."""

    uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)


class SoftDeleteMixin:
    """deleted_at marker; rows are never physically removed."""

    deleted_at = Column(DateTime(timezone=True), nullable=True)


class UserTrackingMixin:
    """created_by / updated_by attribution."""

    created_by = Column(Text, nullable=True)
    updated_by = Column(Text, nullable=True)
