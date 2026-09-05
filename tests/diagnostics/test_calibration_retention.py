"""Disposable retention proof for terminal ordinary Calibration runs."""

from datetime import UTC, datetime, timedelta
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.diagnostics.calibration_runs import (
    CalibrationRun,
    CalibrationRunStatus,
)
from face_moment.promo.retention import (
    RetentionCleanupLatest,
    read_latest_retention_result,
    run_retention_cleanup,
)
from tests.disposable_postgresql import disposable_postgresql_engine


NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
CUTOFF = NOW - timedelta(days=90)


def test_cleanup_expires_only_old_terminal_calibration_runs_and_keeps_public_shape() -> None:
    old_complete = _run(status=CalibrationRunStatus.COMPLETE, created_at=CUTOFF - timedelta(microseconds=1))
    old_failed = _run(status=CalibrationRunStatus.FAILED, created_at=CUTOFF - timedelta(days=1))
    old_interrupted = _run(status=CalibrationRunStatus.INTERRUPTED, created_at=CUTOFF - timedelta(days=2))
    equal_complete = _run(status=CalibrationRunStatus.COMPLETE, created_at=CUTOFF)
    new_failed = _run(status=CalibrationRunStatus.FAILED, created_at=CUTOFF + timedelta(microseconds=1))
    requested = _run(status=CalibrationRunStatus.REQUESTED, created_at=CUTOFF - timedelta(days=3))
    running = _run(status=CalibrationRunStatus.RUNNING, created_at=CUTOFF - timedelta(days=4))
    old_complete_id = old_complete.id
    old_failed_id = old_failed.id
    old_interrupted_id = old_interrupted.id
    equal_complete_id = equal_complete.id
    new_failed_id = new_failed.id
    requested_id = requested.id
    running_id = running.id

    with disposable_postgresql_engine("task105_calibration_retention") as engine:
        with Session(engine) as session:
            session.add_all(
                [
                    old_complete,
                    old_failed,
                    old_interrupted,
                    equal_complete,
                    new_failed,
                    requested,
                    running,
                ]
            )
            session.commit()

        with Session(engine) as session:
            before = read_latest_retention_result(session)
            first = run_retention_cleanup(session, now=NOW)
            after = read_latest_retention_result(session)

            assert before == {"schema_version": 1, "status": "never_run", "result": None}
            assert first.exit_code == 0
            assert first.state == "succeeded"
            assert session.get(CalibrationRun, old_complete_id) is None
            assert session.get(CalibrationRun, old_failed_id) is None
            assert session.get(CalibrationRun, old_interrupted_id) is None
            assert session.get(CalibrationRun, equal_complete_id) is not None
            assert session.get(CalibrationRun, new_failed_id) is not None
            assert session.get(CalibrationRun, requested_id) is not None
            assert session.get(CalibrationRun, running_id) is not None
            assert after["status"] == "available"
            assert set(after["result"]["counts"]) == {
                "core_attempts_deleted",
                "ordinary_evidence_expired",
                "technical_logs_deleted",
                "private_artifacts_deleted",
                "promoted_subsets_preserved",
            }

        with Session(engine) as session:
            rerun = run_retention_cleanup(session, now=NOW)
            assert rerun.exit_code == 0
            assert rerun.state == "succeeded"
            assert session.scalars(select(RetentionCleanupLatest)).all()
            assert len(session.scalars(select(RetentionCleanupLatest)).all()) == 1
            assert session.get(CalibrationRun, equal_complete_id) is not None
            assert session.get(CalibrationRun, new_failed_id) is not None
            assert session.get(CalibrationRun, requested_id) is not None
            assert session.get(CalibrationRun, running_id) is not None


def _run(*, status: CalibrationRunStatus, created_at: datetime) -> CalibrationRun:
    terminal = status in {
        CalibrationRunStatus.COMPLETE,
        CalibrationRunStatus.FAILED,
        CalibrationRunStatus.INTERRUPTED,
    }
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "requested_by_staff_id": uuid.uuid4(),
        "status": status,
        "dataset_snapshot": {"photos": [], "attempts": []},
        "dataset_sha256": "0" * 64,
        "error_code": (
            "fixture_failure" if terminal and status != CalibrationRunStatus.COMPLETE else None
        ),
        "created_at": created_at,
        "started_at": (created_at if status != CalibrationRunStatus.REQUESTED else None),
        "finished_at": (created_at if terminal else None),
    }
    if status == CalibrationRunStatus.COMPLETE:
        values["result_bundle"] = {"pipeline_results": []}
    return CalibrationRun(
        **values,  # type: ignore[arg-type]
    )
