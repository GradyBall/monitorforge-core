"""Typed shapes that connect a project's parser/binder to the shared writer.

Each project (Peñasquito, Bisbee, ...) writes its own parser (raw file ->
list[RawObservation]) and its own binder (RawObservation -> BoundObservation,
using that project's sensor/channel knowledge). Neither step is provided by
this package -- see README.md for why. What this package provides is the
shape both steps must agree on, and a writer (``monitorforge_core.ingestion``)
that only needs the second shape.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RawObservation:
    """One value read from a source file, before any sensor/channel knowledge is applied.

    Produced by a project's format-specific parser (.dat, .csv, .html, ...).
    """

    ts: datetime
    raw_code: str
    raw_value: float | None
    source_row: int | None = None


@dataclass(frozen=True, slots=True)
class BoundObservation:
    """One value resolved to a specific deployment and variable, ready to write.

    Produced by a project's binder from a RawObservation, using that
    project's own sensor-mapping/channel-binding logic.
    """

    deployment_id: int
    variable_id: int
    ts: datetime
    value: float | None  # None = missing/unreadable reading; the writer logs it as an invalid row
