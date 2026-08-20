"""Sensors, variables, and deployments."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import relationship

from monitorforge_core.db import db

from .base import SoftDeleteMixin, TimestampMixin, UUIDMixin, UserTrackingMixin

DeploymentStatus = ENUM(
    "active", "inactive", "maintenance", "retired", name="deployment_status", schema="core"
)

# A deployment's reporting resolution. Distinct resolutions of the "same"
# variable at the same station (e.g. a logger's daily-total table vs its
# hourly-total table) are different series, not the same one at different
# sample rates -- binding them to one deployment causes false conflicts
# where a daily total and an hourly total for the same channel name land
# on the same (deployment, variable, timestamp) key. Each resolution gets
# its own deployment.
ResolutionType = ENUM(
    "30s", "1m", "5m", "15m", "hourly", "8h", "daily", "other", name="resolution_type", schema="core"
)


class Sensor(db.Model, TimestampMixin, UUIDMixin, SoftDeleteMixin, UserTrackingMixin):
    """A physical sensor, independent of where/when it was deployed."""

    __tablename__ = "sensors"
    __table_args__ = (
        CheckConstraint(
            "lower_bound IS NULL OR upper_bound IS NULL OR lower_bound < upper_bound",
            name="bounds_order",
        ),
        Index("sensors_serial_idx", "serial_number"),
        Index("sensors_family_idx", "variable_family"),
        {"schema": "core"},
    )

    sensor_id = Column(Integer, primary_key=True, autoincrement=True)
    model = Column(Text)
    serial_number = Column(Text, unique=True, nullable=False, index=True)
    manufacturer = Column(Text)
    variable_family = Column(Text, index=True)
    lower_bound = Column(Float)
    upper_bound = Column(Float)
    is_active = Column(Boolean, default=True)

    deployments = relationship("SensorDeployment", back_populates="sensor")

    def __repr__(self):
        return f"<Sensor(serial='{self.serial_number}', family='{self.variable_family}')>"


class Variable(db.Model, TimestampMixin, UUIDMixin, SoftDeleteMixin, UserTrackingMixin):
    """A canonical measured quantity (e.g. water_content, precip_mm_hourly)."""

    __tablename__ = "variables"
    __table_args__ = (
        Index("vars_code_idx", "code"),
        Index("vars_unit_idx", "unit_id"),
        {"schema": "core"},
    )

    variable_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    code = Column(Text, unique=True, nullable=False, index=True)
    unit_id = Column(Integer, ForeignKey("meta.units.unit_id"), index=True)
    description = Column(Text)
    min_value = Column(Float)
    max_value = Column(Float)
    is_active = Column(Boolean, default=True)

    unit = relationship("Unit")
    measurements = relationship("Measurement", back_populates="variable")

    def __repr__(self):
        return f"<Variable(code='{self.code}', name='{self.name}')>"


class SensorDeployment(db.Model, TimestampMixin, UUIDMixin, SoftDeleteMixin, UserTrackingMixin):
    """A sensor installed at a station for a span of time.

    Unlike Peñasquito's schema, a deployment requires a station but not an
    area/plot — not every project groups stations into large-area polygons.
    """

    __tablename__ = "sensor_deployments"
    __table_args__ = (
        CheckConstraint("depth_cm IS NULL OR depth_cm >= 0", name="depth_nonneg"),
        Index("deploy_active_idx", "sensor_id", "removed_at"),
        Index("deployments_station_idx", "station_id"),
        Index("deployments_status_idx", "status"),
        {"schema": "core"},
    )

    deployment_id = Column(Integer, primary_key=True, autoincrement=True)
    sensor_id = Column(Integer, ForeignKey("core.sensors.sensor_id"), nullable=False, index=True)
    station_id = Column(Integer, ForeignKey("core.monitoring_stations.station_id"), nullable=False, index=True)
    depth_cm = Column(Float, index=True)
    position_code = Column(Text)
    resolution = Column(ResolutionType, index=True)
    installed_at = Column(DateTime(timezone=True), nullable=False)
    removed_at = Column(DateTime(timezone=True))
    status = Column(DeploymentStatus, nullable=False, default="active", index=True)
    notes = Column(Text)

    sensor = relationship("Sensor", back_populates="deployments")
    station = relationship("MonitoringStation", back_populates="deployments")
    measurements = relationship("Measurement", back_populates="deployment")
    calibrations = relationship("SensorCalibration", back_populates="deployment")
    date_change_history = relationship(
        "DeploymentDateChange",
        back_populates="deployment",
        order_by="desc(DeploymentDateChange.changed_at)",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<SensorDeployment(id={self.deployment_id}, sensor_id={self.sensor_id}, status='{self.status}')>"


class DeploymentDateChange(db.Model, TimestampMixin, UUIDMixin):
    """Audit trail for deployment date edits."""

    __tablename__ = "deployment_date_changes"
    __table_args__ = (
        Index("deployment_date_changes_deployment_idx", "deployment_id", "changed_at"),
        {"schema": "core"},
    )

    deployment_date_change_id = Column(Integer, primary_key=True, autoincrement=True)
    deployment_id = Column(Integer, ForeignKey("core.sensor_deployments.deployment_id"), nullable=False, index=True)
    changed_at = Column(DateTime(timezone=True), nullable=False)
    changed_by = Column(Text)
    reason = Column(Text)
    old_installed_at = Column(DateTime(timezone=True))
    new_installed_at = Column(DateTime(timezone=True))
    old_removed_at = Column(DateTime(timezone=True))
    new_removed_at = Column(DateTime(timezone=True))

    deployment = relationship("SensorDeployment", back_populates="date_change_history")

    def __repr__(self):
        return f"<DeploymentDateChange(deployment={self.deployment_id}, changed_at={self.changed_at})>"
