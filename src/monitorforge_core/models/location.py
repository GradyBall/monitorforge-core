"""Location hierarchy: Project -> MonitoringArea (optional) -> MonitoringStation.

Generalized from Peñasquito's Project -> MonitoringPlot -> MonitoringStation.
"MonitoringArea" replaces "MonitoringPlot": a plot was specifically a 1x1
mile mining polygon, which not every project has. A station may belong
directly to a project without an intermediate area.
"""

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import relationship

from monitorforge_core.db import db

from .base import SoftDeleteMixin, TimestampMixin, UUIDMixin, UserTrackingMixin


class Project(db.Model, TimestampMixin, UUIDMixin, SoftDeleteMixin, UserTrackingMixin):
    """Top level of the location hierarchy."""

    __tablename__ = "projects"
    __table_args__ = {"schema": "core"}

    project_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    code = Column(Text, unique=True, index=True)
    description = Column(Text)
    is_active = Column(Boolean, default=True, index=True)

    areas = relationship("MonitoringArea", back_populates="project")
    stations = relationship("MonitoringStation", back_populates="project")

    def __repr__(self):
        return f"<Project(code='{self.code}', name='{self.name}')>"


class MonitoringArea(db.Model, TimestampMixin, UUIDMixin, SoftDeleteMixin, UserTrackingMixin):
    """Optional large-area grouping of stations (e.g. a heap-leach plot, a basin)."""

    __tablename__ = "monitoring_areas"
    __table_args__ = (
        Index("monitoring_areas_code_idx", "code"),
        Index("monitoring_areas_project_idx", "project_id"),
        Index("monitoring_areas_active_idx", "is_active"),
        {"schema": "core"},
    )

    area_id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("core.projects.project_id"), index=True)
    name = Column(Text, nullable=False)
    code = Column(Text, unique=True, index=True)
    description = Column(Text)
    is_active = Column(Boolean, default=True, index=True)

    project = relationship("Project", back_populates="areas")
    stations = relationship("MonitoringStation", back_populates="area")

    def __repr__(self):
        return f"<MonitoringArea(code='{self.code}', name='{self.name}')>"


class MonitoringStation(db.Model, TimestampMixin, UUIDMixin, SoftDeleteMixin, UserTrackingMixin):
    """A point location where sensors are deployed."""

    __tablename__ = "monitoring_stations"
    __table_args__ = (
        Index("monitoring_stations_code_idx", "code"),
        Index("monitoring_stations_project_idx", "project_id"),
        Index("monitoring_stations_area_idx", "area_id"),
        Index("monitoring_stations_type_idx", "station_type"),
        Index("monitoring_stations_active_idx", "is_active"),
        {"schema": "core"},
    )

    station_id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("core.projects.project_id"), nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("core.monitoring_areas.area_id"), index=True)
    name = Column(Text, nullable=False)
    code = Column(Text, nullable=False, index=True)
    latitude = Column(db.Float)
    longitude = Column(db.Float)
    elevation_m = Column(db.Float)
    timezone = Column(Text, nullable=False)
    description = Column(Text)
    station_type = Column(Text, index=True)
    is_active = Column(Boolean, default=True, index=True)

    project = relationship("Project", back_populates="stations")
    area = relationship("MonitoringArea", back_populates="stations")
    deployments = relationship("SensorDeployment", back_populates="station")

    def __repr__(self):
        return f"<MonitoringStation(code='{self.code}', name='{self.name}')>"
