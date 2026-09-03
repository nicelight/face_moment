from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta, timezone
import hashlib
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.diagnostics import DiagnosticEvidence, DiagnosticEvidenceProvider
from face_moment.diagnostics.evidence import DiagnosticEvidenceRepository
from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings
from face_moment.promo.attempt import PromoAttempt
from face_moment.promo.retention import (
    RetentionCleanupLatest,
    read_latest_retention_result,
    run_retention_cleanup,
)
from face_moment.promo.session import PromoSession


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
ADVISORY_LOCK_KEY = 7_391_042_611_827


@pytest.fixture
def disposable_retention_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    base_settings = Settings.from_env()
    probe_database = f"task086_{uuid.uuid4().hex}"
    probe_url = make_url(base_settings.database_url).set(database=probe_database)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {probe_database}")
    monkeypatch.setenv("DATABASE_URL", probe_url.render_as_string(hide_password=False))
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)"
            )
        admin_engine.dispose()


class MemoryObjectStore:
    def __init__(self, engine: Engine, observed_attempt_id: uuid.UUID) -> None:
        self.engine = engine
        self.observed_attempt_id = observed_attempt_id
        self.keys: set[str] = set()
        self.observed_manifests: list[dict[str, object] | None] = []
        self.observed_raw_manifests: list[dict[str, object] | None] = []
        self.observed_expired_at: list[datetime | None] = []

    def delete(self, *, key: str) -> None:
        self.observe_owner_state()
        self.keys.discard(key)

    def observe_owner_state(self) -> None:
        with Session(self.engine) as session:
            evidence = session.scalar(
                select(DiagnosticEvidence).where(
                    DiagnosticEvidence.attempt_id == self.observed_attempt_id
                )
            )
            if evidence is None:
                self.observed_manifests.append(None)
                self.observed_raw_manifests.append(None)
                self.observed_expired_at.append(None)
                return
            self.observed_raw_manifests.append(evidence.ordinary_manifest)
            self.observed_expired_at.append(evidence.ordinary_expired_at)
            self.observed_manifests.append(
                None
                if evidence.ordinary_expired_at is not None
                else evidence.ordinary_manifest
            )


class FailOnceObjectStore(MemoryObjectStore):
    def __init__(self, engine: Engine, observed_attempt_id: uuid.UUID, key: str) -> None:
        super().__init__(engine, observed_attempt_id)
        self.keys.add(key)
        self.key = key
        self.calls = 0

    def delete(self, *, key: str) -> None:
        assert key == self.key
        self.observe_owner_state()
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("task086 disposable object delete failure")
        self.keys.discard(key)


def test_migration_shape_and_owner_ordered_cleanup_converge(
    disposable_retention_engine: Engine,
) -> None:
    engine = disposable_retention_engine
    inspector = inspect(engine)
    columns = {
        column["name"]
        for column in inspector.get_columns(
            "retention_cleanup_latest", schema=APP_SCHEMA
        )
    }
    assert columns == {
        "singleton_key",
        "run_id",
        "status",
        "started_at",
        "finished_at",
        "technical_logs_before",
        "attempts_and_evidence_before",
        "core_attempts_deleted",
        "ordinary_evidence_expired",
        "technical_logs_deleted",
        "private_artifacts_deleted",
        "promoted_subsets_preserved",
        "error",
    }
    assert len(inspector.get_pk_constraint("retention_cleanup_latest", schema=APP_SCHEMA)["constrained_columns"]) == 1

    old_no_evidence = _attempt(NOW - timedelta(days=90, microseconds=1))
    old_ordinary = _attempt(NOW - timedelta(days=91))
    old_promoted = _attempt(NOW - timedelta(days=92))
    old_incomplete = _attempt(NOW - timedelta(days=93))
    at_cutoff = _attempt(NOW - timedelta(days=90))
    recent = _attempt(NOW - timedelta(days=1))
    old_no_evidence_id = old_no_evidence.id
    old_ordinary_id = old_ordinary.id
    old_promoted_id = old_promoted.id
    old_incomplete_id = old_incomplete.id
    at_cutoff_id = at_cutoff.id
    recent_id = recent.id
    with Session(engine) as session:
        session.add_all(
            [
                old_no_evidence,
                old_ordinary,
                old_promoted,
                old_incomplete,
                at_cutoff,
                recent,
                _session_for(old_ordinary),
            ]
        )
        provider = DiagnosticEvidenceProvider(session)
        provider.write(
            attempt_id=old_ordinary.id,
            ordinary_manifest=_manifest(old_ordinary.id, artifact_key="task086/artifact"),
            completeness="complete",
            now=old_ordinary.created_at,
        )
        provider.write(
            attempt_id=old_promoted.id,
            ordinary_manifest=_manifest(old_promoted.id),
            completeness="incomplete",
            gap_reason="display_event_missing",
            now=old_promoted.created_at,
        )
        assert provider.promote_subset(
            attempt_id=old_promoted.id,
            promoted_subset={
                "schema_version": 1,
                "media_refs": ["task086/private/photo"],
                "scores": [0.91],
                "participant_name": "curated only",
            },
            now=old_promoted.created_at,
        ).accepted
        provider.write(
            attempt_id=old_incomplete.id,
            ordinary_manifest=_manifest(old_incomplete.id),
            completeness="incomplete",
            gap_reason="response_receipt_missing",
            now=old_incomplete.created_at,
        )
        session.commit()

    store = MemoryObjectStore(engine, old_ordinary_id)
    store.keys.add("task086/artifact")
    with Session(engine) as session:
        outcome = run_retention_cleanup(session, now=NOW, object_store=store)
        assert outcome.exit_code == 0
        assert outcome.state == "succeeded"
        assert outcome.core_attempts_deleted == 4
        assert outcome.ordinary_evidence_expired == 3
        assert outcome.private_artifacts_deleted == 1
        assert outcome.promoted_subsets_preserved == 1

    assert store.keys == set()
    assert store.observed_manifests == [None]
    assert store.observed_expired_at == [NOW]
    assert store.observed_raw_manifests[0] is not None
    with Session(engine) as session:
        assert session.get(PromoAttempt, old_no_evidence_id) is None
        assert session.get(PromoAttempt, old_ordinary_id) is None
        assert session.get(PromoAttempt, old_promoted_id) is None
        assert session.get(PromoAttempt, old_incomplete_id) is None
        assert session.get(PromoAttempt, at_cutoff_id) is not None
        assert session.get(PromoAttempt, recent_id) is not None
        assert DiagnosticEvidenceRepository(session).get(old_promoted_id) is not None
        promoted = DiagnosticEvidenceRepository(session).require(old_promoted_id)
        assert promoted.ordinary_manifest is None
        assert promoted.promoted_subset == {
            "schema_version": 1,
            "media_refs": ["task086/private/photo"],
            "scores": [0.91],
            "participant_name": "curated only",
        }
        assert session.scalar(select(PromoSession).where(PromoSession.attempt_id == old_ordinary_id)) is None
        latest = session.get(RetentionCleanupLatest, 1)
        assert latest is not None
        assert latest.status == "succeeded"
        assert latest.technical_logs_deleted == 0
        assert read_latest_retention_result(session)["status"] == "available"

    with Session(engine) as session:
        rerun = run_retention_cleanup(session, now=NOW, object_store=store)
        assert rerun.exit_code == 0
        assert rerun.core_attempts_deleted == 0
        assert rerun.ordinary_evidence_expired == 0
        assert rerun.promoted_subsets_preserved == 0
        assert session.scalar(select(RetentionCleanupLatest)) is not None
        assert len(session.scalars(select(RetentionCleanupLatest)).all()) == 1


def test_failed_private_delete_preserves_retry_state_until_rerun_converges(
    disposable_retention_engine: Engine,
) -> None:
    engine = disposable_retention_engine
    attempt = _attempt(NOW - timedelta(days=91))
    artifact_key = "task086/retry/private-artifact"
    promoted_key = "task086/retry/promoted-artifact"
    attempt_id = attempt.id
    manifest = _manifest(
        attempt_id,
        artifact_keys=(artifact_key, promoted_key),
    )
    promoted_subset = {
        "schema_version": 1,
        "media_refs": [promoted_key],
        "scores": [0.91],
        "participant_name": "curated only",
    }
    with Session(engine) as session:
        session.add(attempt)
        provider = DiagnosticEvidenceProvider(session)
        provider.write(
            attempt_id=attempt_id,
            ordinary_manifest=manifest,
            completeness="complete",
            now=attempt.created_at,
        )
        assert provider.promote_subset(
            attempt_id=attempt_id,
            promoted_subset=promoted_subset,
            now=attempt.created_at,
        ).accepted
        session.commit()

    store = FailOnceObjectStore(engine, attempt_id, artifact_key)
    store.keys.add(promoted_key)
    with Session(engine) as session:
        failed = run_retention_cleanup(session, now=NOW, object_store=store)
        assert failed.exit_code == 1
        assert failed.state == "failed"

    with Session(engine) as session:
        evidence = DiagnosticEvidenceRepository(session).require(attempt_id)
        latest = session.get(RetentionCleanupLatest, 1)
        assert latest is not None
        assert latest.status == "failed"
        assert session.get(PromoAttempt, attempt_id) is not None
        assert evidence.ordinary_expired_at == NOW
        assert evidence.ordinary_manifest == manifest
        assert evidence.promoted_subset == promoted_subset

    assert store.calls == 1
    assert store.keys == {artifact_key, promoted_key}
    assert store.observed_manifests == [None]
    assert store.observed_expired_at == [NOW]
    assert store.observed_raw_manifests == [manifest]

    with Session(engine) as session:
        rerun = run_retention_cleanup(session, now=NOW, object_store=store)
        assert rerun.exit_code == 0
        assert rerun.state == "succeeded"
        assert rerun.core_attempts_deleted == 1
        assert rerun.private_artifacts_deleted == 1
        assert rerun.promoted_subsets_preserved == 1

    assert store.calls == 2
    assert store.keys == {promoted_key}
    with Session(engine) as session:
        assert session.get(PromoAttempt, attempt_id) is None
        evidence = DiagnosticEvidenceRepository(session).require(attempt_id)
        assert evidence.ordinary_manifest is None
        assert evidence.ordinary_expired_at == NOW
        assert evidence.promoted_subset == promoted_subset
        latest_rows = session.scalars(select(RetentionCleanupLatest)).all()
        assert len(latest_rows) == 1
        assert latest_rows[0].status == "succeeded"
        assert latest_rows[0].promoted_subsets_preserved == 1


def test_failure_is_sanitized_and_overlap_does_not_replace_latest(
    disposable_retention_engine: Engine,
) -> None:
    engine = disposable_retention_engine
    old_attempt = _attempt(NOW - timedelta(days=91))
    old_attempt_id = old_attempt.id
    with Session(engine) as session:
        session.add(old_attempt)
        session.commit()

    class FailingDiagnostics:
        def expire_server_events(self, *, cutoff: datetime) -> int:
            del cutoff
            return 0

        def expire(
            self,
            _attempt_ids: Iterable[uuid.UUID],
            **_: object,
        ) -> object:
            raise RuntimeError("secret traceback and participant payload")

    with Session(engine) as session:
        failed = run_retention_cleanup(
            session,
            now=NOW,
            diagnostics=FailingDiagnostics(),  # type: ignore[arg-type]
        )
        assert failed.exit_code == 1
        assert failed.state == "failed"
        assert failed.error == "owner cleanup failed"

    with Session(engine) as session:
        latest = session.get(RetentionCleanupLatest, 1)
        assert latest is not None
        assert latest.status == "failed"
        assert latest.error == "owner cleanup failed"
        assert session.get(PromoAttempt, old_attempt_id) is not None

    first = Session(engine)
    second = Session(engine)
    try:
        first.execute(text("SELECT pg_advisory_lock(:lock_key)"), {"lock_key": ADVISORY_LOCK_KEY})
        before = read_latest_retention_result(second)
        overlapping = run_retention_cleanup(second, now=NOW)
        assert overlapping.exit_code == 2
        assert overlapping.state == "overlap"
        assert read_latest_retention_result(second) == before
    finally:
        first.execute(text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": ADVISORY_LOCK_KEY})
        first.rollback()
        first.close()
        second.close()


def _attempt(created_at: datetime) -> PromoAttempt:
    return PromoAttempt(
        id=uuid.uuid4(),
        spa_id=uuid.uuid4(),
        client_attempt_id=uuid.uuid4(),
        trigger_source="test",
        client_release="task086-test",
        detector_id="task086-detector",
        model_version="task086-model",
        jpeg_quality=82,
        camera_device_id="task086-camera",
        reference_series_ready_at=created_at,
        local_detection_completed_ms=10,
        request_started_ms=20,
        proposal_count=1,
        settings_revision=1,
        visit_date=None,
        pipeline_revision_id=uuid.uuid4(),
        pipeline_code="opencv_sface",
        query_source="reference",
        release_id="task086-release",
        threshold=0.72,
        quality_settings={"version": 1},
        deadline_ms=3000,
        created_at=created_at,
        updated_at=created_at,
    )


def _session_for(attempt: PromoAttempt) -> PromoSession:
    photos = [uuid.uuid4() for _ in range(4)]
    return PromoSession(
        id=uuid.uuid4(),
        attempt_id=attempt.id,
        spa_id=attempt.spa_id,
        visit_date=None,
        session_result_photo_ids=photos,
        teaser_photo_ids=photos,
        n=4,
        qr_ticket_hash_sha256=hashlib.sha256(b"task086-ticket").digest(),
        qr_issued_at=attempt.created_at,
        qr_first_open_expires_at=attempt.created_at + timedelta(minutes=30),
        created_at=attempt.created_at,
    )


def _manifest(
    attempt_id: uuid.UUID,
    *,
    artifact_key: str | None = None,
    artifact_keys: Iterable[str] | None = None,
) -> dict[str, object]:
    keys = (
        tuple(artifact_keys)
        if artifact_keys is not None
        else (() if artifact_key is None else (artifact_key,))
    )
    artifacts = [
        {"object_key": key, "kind": "diagnostic"}
        for key in keys
    ]
    return {
        "schema_version": 1,
        "identity": {"attempt_id": str(attempt_id)},
        "client": {"client_release": "task086-test"},
        "serving": {"pipeline_code": "opencv_sface"},
        "result": None,
        "display": None,
        "artifacts": artifacts,
    }
