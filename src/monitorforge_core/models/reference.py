"""Reference/lookup tables: units, quality flags, activity types.

These are seeded per project (a project's specific flag taxonomy, unit
list, etc. lives in that project's seed data, not in this schema).
"""

from sqlalchemy import Column, Integer, Text

from monitorforge_core.db import db

from .base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Unit(db.Model, TimestampMixin, UUIDMixin, SoftDeleteMixin):
    __tablename__ = "units"
    __table_args__ = {"schema": "meta"}

    unit_id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(Text, unique=True, nullable=False, index=True)
    name = Column(Text, nullable=False)
    dimension = Column(Text)
    description = Column(Text)

    def __repr__(self):
        return f"<Unit(code='{self.code}', name='{self.name}')>"


class QualityFlag(db.Model, TimestampMixin, UUIDMixin, SoftDeleteMixin):
    __tablename__ = "quality_flags"
    __table_args__ = {"schema": "meta"}

    flag_id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(Text, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    severity = Column(Text, default="info")

    def __repr__(self):
        return f"<QualityFlag(code='{self.code}', severity='{self.severity}')>"


class ActivityType(db.Model, TimestampMixin, UUIDMixin, SoftDeleteMixin):
    __tablename__ = "activity_types"
    __table_args__ = {"schema": "meta"}

    activity_type_id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(Text, unique=True, nullable=False, index=True)
    name = Column(Text, nullable=False)
    description = Column(Text)

    def __repr__(self):
        return f"<ActivityType(code='{self.code}', name='{self.name}')>"
