"""Idempotent writer: BoundObservation list -> Measurement rows + Upload audit record.

This is the one piece of the upload pipeline that is genuinely the same
across projects: given values that have already been parsed and bound to a
(deployment, variable, timestamp), writing them safely doesn't depend on
what sensor vocabulary or file format produced them.

Duplicate/conflict semantics:
  - Same (deployment_id, variable_id, ts) already exists with the same
    value -> duplicate, skipped, not an error (re-uploading the same file
    is safe).
  - Same key exists with a *different* value -> conflict. Not overwritten
    automatically; logged as an UploadRowIssue for manual review. Silently
    overwriting a value nobody asked to change is how QC work gets undone.
  - value is None -> invalid row, logged, skipped.
"""

import math
from dataclasses import dataclass

from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from monitorforge_core.contracts import BoundObservation
from monitorforge_core.models import Measurement, Upload, UploadRowIssue

# Keys per existing-row lookup query. Postgres's SQL parser stack overflows
# somewhere in the low thousands of tuple_(...).in_(...) literals; this
# stays comfortably under that with room for very large deployment/variable
# key values.
_LOOKUP_CHUNK_SIZE = 500


@dataclass(frozen=True, slots=True)
class WriteResult:
    upload: Upload
    rows_inserted: int
    duplicates_skipped: int
    conflicts_skipped: int
    invalid_rows: int


def write_measurements(
    session: Session,
    observations: list[BoundObservation],
    *,
    filename: str,
    source_timezone: str,
    uploaded_by: str | None = None,
) -> WriteResult:
    """Write bound observations to the DB, returning the Upload audit record.

    Commits the session. Callers that need this inside a larger transaction
    should not call this twice within the same request.
    """
    upload = Upload(
        filename=filename,
        uploaded_by=uploaded_by,
        source_timezone=source_timezone,
        rows_read=len(observations),
        status="completed",
    )
    session.add(upload)
    session.flush()  # assigns upload.upload_id

    valid = [obs for obs in observations if obs.value is not None and not math.isnan(obs.value)]
    invalid_rows = len(observations) - len(valid)

    existing_by_key: dict[tuple[int, int, object], float | None] = {}
    if valid:
        keys = [(obs.deployment_id, obs.variable_id, obs.ts) for obs in valid]
        # Chunked: a single tuple_(...).in_(keys) query with one literal per
        # key blows Postgres's SQL parser stack ("stack depth limit
        # exceeded") once a batch reaches a few thousand rows -- this isn't
        # a theoretical concern, it reproduces on a single real logger file.
        for chunk_start in range(0, len(keys), _LOOKUP_CHUNK_SIZE):
            chunk = keys[chunk_start : chunk_start + _LOOKUP_CHUNK_SIZE]
            existing_rows = (
                session.query(
                    Measurement.deployment_id, Measurement.variable_id, Measurement.ts, Measurement.source_value
                )
                .filter(tuple_(Measurement.deployment_id, Measurement.variable_id, Measurement.ts).in_(chunk))
                .all()
            )
            existing_by_key.update(
                {
                    (deployment_id, variable_id, ts): source_value
                    for deployment_id, variable_id, ts, source_value in existing_rows
                }
            )

    rows_inserted = 0
    duplicates_skipped = 0
    conflicts_skipped = 0
    row_issues: list[UploadRowIssue] = []

    for obs in valid:
        key = (obs.deployment_id, obs.variable_id, obs.ts)
        if key not in existing_by_key:
            session.add(
                Measurement(
                    deployment_id=obs.deployment_id,
                    variable_id=obs.variable_id,
                    ts=obs.ts,
                    source_value=obs.value,
                )
            )
            existing_by_key[key] = obs.value  # guard against duplicate keys within this same batch
            rows_inserted += 1
            continue

        existing_value = existing_by_key[key]
        if existing_value is not None and math.isclose(existing_value, obs.value, rel_tol=1e-9, abs_tol=1e-9):
            duplicates_skipped += 1
            continue

        conflicts_skipped += 1
        row_issues.append(
            UploadRowIssue(
                upload_id=upload.upload_id,
                deployment_id=obs.deployment_id,
                variable_id=obs.variable_id,
                ts=obs.ts,
                incoming_value=obs.value,
                existing_value=existing_value,
                issue_type="conflict",
                message="A measurement already exists for this deployment/variable/timestamp with a different value.",
            )
        )

    for obs in observations:
        if obs.value is None or (isinstance(obs.value, float) and math.isnan(obs.value)):
            row_issues.append(
                UploadRowIssue(
                    upload_id=upload.upload_id,
                    deployment_id=obs.deployment_id,
                    variable_id=obs.variable_id,
                    ts=obs.ts,
                    incoming_value=None,
                    issue_type="invalid_value",
                    message="Observation had no numeric value.",
                )
            )

    session.add_all(row_issues)

    upload.rows_inserted = rows_inserted
    upload.duplicates_skipped = duplicates_skipped
    upload.conflicts_skipped = conflicts_skipped
    upload.invalid_rows = invalid_rows

    session.commit()

    return WriteResult(
        upload=upload,
        rows_inserted=rows_inserted,
        duplicates_skipped=duplicates_skipped,
        conflicts_skipped=conflicts_skipped,
        invalid_rows=invalid_rows,
    )
