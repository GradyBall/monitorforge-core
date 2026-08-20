from datetime import datetime

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
