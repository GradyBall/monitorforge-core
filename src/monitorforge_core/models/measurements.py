"""Measurements, derived values, calibration, and upload audit trail."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from monitorforge_core.db import db

from .base import BigIntPK, SoftDeleteMixin, TimestampMixin, UUIDMixin, UserTrackingMixin


class Measurement(db.Model, TimestampMixin):
    """Raw time-series measurement, as received (post-binding, pre-QC-decision)."""

    __tablename__ = "measurements"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id", "variable_id", "ts", name="measurements_unique_deployment_variable_ts"
        ),
        Index("measurements_deploy_ts_idx", "deployment_id", "ts", postgresql_ops={"ts": "DESC"}),
        Index("measurements_variable_idx", "variable_id"),
        Index("measurements_flag_idx", "flag_id"),
        Index("measurements_qc_status_idx", "qc_status"),
        {"schema": "core"},
    )

    measurement_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    deployment_id = Column(Integer, ForeignKey("core.sensor_deployments.deployment_id"), nullable=False, index=True)
    variable_id = Column(Integer, ForeignKey("core.variables.variable_id"), nullable=False, index=True)
    ts = Column(DateTime(timezone=False), nullable=False, index=True)
    source_value = Column(Float)
    flag_id = Column(Integer, ForeignKey("meta.quality_flags.flag_id"), index=True)
    qc_status = Column(Text, default="pending", nullable=False, index=True)

    deployment = relationship("SensorDeployment", back_populates="measurements")
    variable = relationship("Variable", back_populates="measurements")
    flag = relationship("QualityFlag")
    derived_measurements = relationship("DerivedMeasurement", back_populates="source_measurement")

    def __repr__(self):
        return f"<Measurement(deployment={self.deployment_id}, var={self.variable_id}, ts={self.ts})>"


class MeasurementValueChange(db.Model):
    """Immutable audit event for a manual correction to a raw measurement."""

    __tablename__ = "measurement_value_changes"
    __table_args__ = (
        Index("measurement_value_changes_measurement_idx", "measurement_id", "edited_at"),
        {"schema": "core"},
    )

    measurement_value_change_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    measurement_id = Column(
        BigInteger, ForeignKey("core.measurements.measurement_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    old_source_value = Column(Float)
    new_source_value = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    edited_by = Column(Text)
    edited_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    measurement = relationship("Measurement")


class CalculationRun(db.Model, TimestampMixin):
    """Tracks a batch of derived-value calculation or recalculation."""

    __tablename__ = "calculation_runs"
    __table_args__ = (
        Index("calculation_runs_status_idx", "status"),
        Index("calculation_runs_started_at_idx", "started_at", postgresql_ops={"started_at": "DESC"}),
        {"schema": "core"},
    )

    calculation_run_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    run_type = Column(Text, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    status = Column(Text, nullable=False)
    formula_version = Column(Text)
    notes = Column(Text)

    derived_measurements = relationship("DerivedMeasurement", back_populates="calculation_run")


class DerivedMeasurement(db.Model, TimestampMixin):
    """A calibrated or otherwise derived value, computed from a source measurement."""

    __tablename__ = "derived_measurements"
    __table_args__ = (
        Index("derived_measurements_source_idx", "source_measurement_id"),
        Index(
            "derived_measurements_deploy_var_ts_idx",
            "deployment_id",
            "derived_variable_id",
            "ts",
            postgresql_ops={"ts": "DESC"},
        ),
        Index("derived_measurements_status_idx", "qc_status"),
        {"schema": "core"},
    )

    derived_measurement_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    source_measurement_id = Column(BigInteger, ForeignKey("core.measurements.measurement_id"), nullable=False, index=True)
    deployment_id = Column(Integer, ForeignKey("core.sensor_deployments.deployment_id"), nullable=False, index=True)
    source_variable_id = Column(Integer, ForeignKey("core.variables.variable_id"), nullable=False, index=True)
    derived_variable_id = Column(Integer, ForeignKey("core.variables.variable_id"), nullable=False, index=True)
    ts = Column(DateTime(timezone=False), nullable=False, index=True)
    value = Column(Float, nullable=False)
    derivation_type = Column(Text, nullable=False)
    calibration_id = Column(Integer, ForeignKey("core.sensor_calibrations.calibration_id"), index=True)
    calculation_run_id = Column(BigInteger, ForeignKey("core.calculation_runs.calculation_run_id"), index=True)
    flag_id = Column(Integer, ForeignKey("meta.quality_flags.flag_id"), index=True)
    qc_status = Column(Text, default="pending", nullable=False, index=True)
    is_current = Column(Boolean, default=True, nullable=False, index=True)

    source_measurement = relationship("Measurement", back_populates="derived_measurements")
    deployment = relationship("SensorDeployment")
    source_variable = relationship("Variable", foreign_keys=[source_variable_id])
    derived_variable = relationship("Variable", foreign_keys=[derived_variable_id])
    calibration = relationship("SensorCalibration")
    calculation_run = relationship("CalculationRun", back_populates="derived_measurements")
    flag = relationship("QualityFlag")


class SensorCalibration(db.Model, TimestampMixin, UUIDMixin, SoftDeleteMixin, UserTrackingMixin):
    """A calibration valid for a deployment over a time range (forward-only)."""

    __tablename__ = "sensor_calibrations"
    __table_args__ = (
        Index("calibrations_deploy_ts_idx", "deployment_id", "calibration_ts", postgresql_ops={"calibration_ts": "DESC"}),
        {"schema": "core"},
    )

    calibration_id = Column(Integer, primary_key=True, autoincrement=True)
    deployment_id = Column(Integer, ForeignKey("core.sensor_deployments.deployment_id"), nullable=False, index=True)
    variable_id = Column(Integer, ForeignKey("core.variables.variable_id"), index=True)
    calibration_ts = Column(DateTime(timezone=True), nullable=False)
    k_factor = Column(Float, default=1.0)
    offset_val = Column(Float, default=0.0)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_to = Column(DateTime(timezone=True))
    performed_by = Column(Text)
    notes = Column(Text)

    deployment = relationship("SensorDeployment", back_populates="calibrations")
    variable = relationship("Variable")

    def __repr__(self):
        return f"<SensorCalibration(deployment={self.deployment_id}, valid_from={self.valid_from})>"


class Upload(db.Model, TimestampMixin):
    """Audit record for a single upload/ingestion attempt (one call to the writer)."""

    __tablename__ = "uploads"
    __table_args__ = (
        Index("uploads_uploaded_at_idx", "uploaded_at", postgresql_ops={"uploaded_at": "DESC"}),
        Index("uploads_status_idx", "status"),
        {"schema": "core"},
    )

    upload_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    filename = Column(Text, nullable=False)
    uploaded_by = Column(Text)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    source_timezone = Column(Text, nullable=False)
    rows_read = Column(Integer, nullable=False, default=0)
    rows_inserted = Column(Integer, nullable=False, default=0)
    duplicates_skipped = Column(Integer, nullable=False, default=0)
    conflicts_skipped = Column(Integer, nullable=False, default=0)
    invalid_rows = Column(Integer, nullable=False, default=0)
    status = Column(Text, nullable=False, default="completed")
    message = Column(Text)

    row_issues = relationship(
        "UploadRowIssue", back_populates="upload", cascade="all, delete-orphan", order_by="UploadRowIssue.issue_id.asc()"
    )

    def __repr__(self):
        return f"<Upload(upload_id={self.upload_id}, filename='{self.filename}', status='{self.status}')>"


class UploadRowIssue(db.Model, TimestampMixin):
    """A row-level problem encountered during a single upload (duplicate, conflict, invalid)."""

    __tablename__ = "upload_row_issues"
    __table_args__ = (
        Index("upload_row_issues_upload_idx", "upload_id", "issue_type"),
        {"schema": "core"},
    )

    issue_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    upload_id = Column(BigInteger, ForeignKey("core.uploads.upload_id", ondelete="CASCADE"), nullable=False, index=True)
    deployment_id = Column(Integer, ForeignKey("core.sensor_deployments.deployment_id"), index=True)
    variable_id = Column(Integer, ForeignKey("core.variables.variable_id"), index=True)
    ts = Column(DateTime(timezone=False), index=True)
    incoming_value = Column(Float)
    existing_value = Column(Float)
    issue_type = Column(Text, nullable=False, index=True)
    message = Column(Text)

    upload = relationship("Upload", back_populates="row_issues")
    deployment = relationship("SensorDeployment")
    variable = relationship("Variable")

    def __repr__(self):
        return f"<UploadRowIssue(upload_id={self.upload_id}, issue_type='{self.issue_type}')>"
