from datetime import datetime, timedelta

from monitorforge_core.contracts import BoundObservation
from monitorforge_core.ingestion import write_measurements
from monitorforge_core.models import (
    MonitoringStation,
    Project,
    Sensor,
    SensorDeployment,
    Variable,
)


def _make_deployment(session):
    project = Project(name="Test Project", code="TEST")
    station = MonitoringStation(project=project, name="Station 1", code="S1", timezone="UTC")
    sensor = Sensor(serial_number="SN-1", variable_family="soil")
    variable = Variable(name="Water Content", code="water_content")
    deployment = SensorDeployment(
        sensor=sensor, station=station, installed_at=datetime(2024, 1, 1)
    )
    session.add_all([project, station, sensor, variable, deployment])
    session.commit()
    return deployment, variable


def test_write_new_observations_inserts_rows(session):
    deployment, variable = _make_deployment(session)
    obs = [
        BoundObservation(deployment.deployment_id, variable.variable_id, datetime(2024, 1, 1, 0, 0), 0.25),
        BoundObservation(deployment.deployment_id, variable.variable_id, datetime(2024, 1, 1, 1, 0), 0.26),
    ]

    result = write_measurements(session, obs, filename="test.dat", source_timezone="UTC")

    assert result.rows_inserted == 2
    assert result.duplicates_skipped == 0
    assert result.conflicts_skipped == 0
    assert result.invalid_rows == 0
    assert result.upload.rows_read == 2


def test_reuploading_identical_values_is_a_noop_duplicate(session):
    deployment, variable = _make_deployment(session)
    ts = datetime(2024, 1, 1, 0, 0)
    obs = [BoundObservation(deployment.deployment_id, variable.variable_id, ts, 0.25)]

    write_measurements(session, obs, filename="first.dat", source_timezone="UTC")
    result = write_measurements(session, obs, filename="second.dat", source_timezone="UTC")

    assert result.rows_inserted == 0
    assert result.duplicates_skipped == 1


def test_conflicting_value_is_logged_not_overwritten(session):
    deployment, variable = _make_deployment(session)
    ts = datetime(2024, 1, 1, 0, 0)

    write_measurements(
        session,
        [BoundObservation(deployment.deployment_id, variable.variable_id, ts, 0.25)],
        filename="first.dat",
        source_timezone="UTC",
    )
    result = write_measurements(
        session,
        [BoundObservation(deployment.deployment_id, variable.variable_id, ts, 0.99)],
        filename="second.dat",
        source_timezone="UTC",
    )

    assert result.rows_inserted == 0
    assert result.conflicts_skipped == 1
    assert result.upload.row_issues[0].issue_type == "conflict"
    assert result.upload.row_issues[0].existing_value == 0.25
    assert result.upload.row_issues[0].incoming_value == 0.99


def test_missing_value_logged_as_invalid(session):
    deployment, variable = _make_deployment(session)
    obs = [BoundObservation(deployment.deployment_id, variable.variable_id, datetime(2024, 1, 1), None)]

    result = write_measurements(session, obs, filename="test.dat", source_timezone="UTC")

    assert result.rows_inserted == 0
    assert result.invalid_rows == 1
    assert result.upload.row_issues[0].issue_type == "invalid_value"


def test_large_batch_spanning_multiple_lookup_chunks_stays_correct(session):
    """Regression test: a real PB-55 backfill (~20k rows) hit "stack depth
    limit exceeded" on Postgres because the existing-row lookup built one
    tuple_(...).in_(...) query with a literal per observation. The fix
    chunks that lookup -- this proves chunking doesn't break duplicate/
    conflict detection for keys that land in different chunks.
    """
    deployment, variable = _make_deployment(session)
    base_ts = datetime(2024, 1, 1)
    row_count = 1200  # several multiples of the 500-row lookup chunk size

    first_batch = [
        BoundObservation(deployment.deployment_id, variable.variable_id, base_ts + timedelta(minutes=i), float(i))
        for i in range(row_count)
    ]
    first_result = write_measurements(session, first_batch, filename="first.dat", source_timezone="UTC")
    assert first_result.rows_inserted == row_count

    # Re-upload: every row should be recognized as a duplicate, including
    # ones near chunk boundaries (index 499/500, 999/1000).
    second_result = write_measurements(session, first_batch, filename="second.dat", source_timezone="UTC")
    assert second_result.duplicates_skipped == row_count
    assert second_result.rows_inserted == 0

    # Conflict at an exact chunk boundary index.
    conflicting = [
        BoundObservation(deployment.deployment_id, variable.variable_id, base_ts + timedelta(minutes=500), 9999.0)
    ]
    third_result = write_measurements(session, conflicting, filename="third.dat", source_timezone="UTC")
    assert third_result.conflicts_skipped == 1
