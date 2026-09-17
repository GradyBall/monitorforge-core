"""Legacy v0 typed shapes connecting already-bound observations to the writer.

These classes predate the staged hybrid architecture. New source-format adapters
and shared configuration-driven binding belong in the pipeline. A future versioned
handoff will add stable external identities, reference-data projection, units,
calibration/QC versions, and run provenance before resolving relational surrogate
IDs. These existing shapes remain for compatibility until that coordinated
producer/consumer migration is implemented.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RawObservation:
    """One value read from a source file, before any sensor/channel knowledge is applied.

    Currently produced by a format-specific parser. New adapters belong in the
    shared pipeline.
    """

    ts: datetime
    raw_code: str
    raw_value: float | None
    source_row: int | None = None


@dataclass(frozen=True, slots=True)
class BoundObservation:
    """One value resolved to a specific deployment and variable, ready to write.

    Legacy database-ID form produced after binding. The target pipeline handoff
    uses stable configuration identities and resolves database IDs through the
    reference-data projection.
    """

    deployment_id: int
    variable_id: int
    ts: datetime
    value: float | None  # None = missing/unreadable reading; the writer logs it as an invalid row
