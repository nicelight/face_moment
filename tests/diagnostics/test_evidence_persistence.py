from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.diagnostics.evidence import (
    DiagnosticEvidence,
    DiagnosticEvidenceProvider,
    DiagnosticEvidenceRepository,
)
from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings


@pytest.fixture
def disposable_evidence_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    base_settings = Settings.from_env()
    probe_database = f"task084_{uuid.uuid4().hex}"
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


def _manifest(attempt_id: uuid.UUID) -> dict[str, object]:
    return {
        "schema_version": 1,
        "identity": {
            "attempt_id": str(attempt_id),
            "client_attempt_id": str(uuid.uuid4()),
        },
        "client": {
            "trigger_source": "sensor",
            "client_release": "kiosk-2026.08",
            "detector_id": "blazeface",
            "model_version": "full-range-1",
            "jpeg_quality": 82,
            "camera_device_id": "camera-fixture",
            "proposal_count": 1,
        },
        "serving": {
            "release_id": "server-2026.08",
            "pipeline_revision_id": str(uuid.uuid4()),
            "pipeline_code": "opencv_sface",
            "settings_revision": 4,
            "threshold": 0.72,
            "quality_settings": {"minimum_edge": 48},
        },
        "detections": [
            {
                "occurrence_index": 0,
                "rank": 1,
                "reference_quality_score": 0.91,
                "quality_gate_passed": True,
                "rejection_reason": None,
                "matches": [
                    {
                        "photo_id": str(uuid.uuid4()),
                        "cosine_similarity": 0.73,
                        "phash64": 1,
                    }
                ],
            }
        ],
        "result": None,
        "display": None,
        "artifacts": [],
    }


def test_migration_shape_and_round_trip(disposable_evidence_engine: Engine) -> None:
    inspector = inspect(disposable_evidence_engine)
    columns = {
        column["name"]
        for column in inspector.get_columns("diagnostic_evidence", schema=APP_SCHEMA)
    }
    assert columns == {
        "id",
        "attempt_id",
        "schema_version",
        "completeness",
        "gap_reason",
        "issue_tags",
        "ordinary_manifest",
        "promoted_subset",
        "created_at",
        "updated_at",
        "finalized_at",
        "promoted_at",
        "ordinary_expired_at",
    }
    assert not DiagnosticEvidence.__table__.foreign_keys
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(
            "diagnostic_evidence", schema=APP_SCHEMA
        )
    } == {"uq_diagnostic_evidence_attempt_schema_version"}

    alembic_config = Config("alembic.ini")
    alembic_command.downgrade(alembic_config, "0015_promo_attempt_client_timing")
    assert "diagnostic_evidence" not in inspect(
        disposable_evidence_engine
    ).get_table_names(schema=APP_SCHEMA)
    alembic_command.upgrade(alembic_config, "head")
    assert "diagnostic_evidence" in inspect(
        disposable_evidence_engine
    ).get_table_names(schema=APP_SCHEMA)


def test_partial_complete_restart_and_expiry_are_idempotent(
    disposable_evidence_engine: Engine,
) -> None:
    attempt_id = uuid.uuid4()
    partial = _manifest(attempt_id)
    partial["display"] = {"status": "pending"}
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)

    with Session(disposable_evidence_engine) as session:
        repository = DiagnosticEvidenceRepository(session)
        evidence = repository.write_bundle(
            attempt_id=attempt_id,
            ordinary_manifest=partial,
            completeness="incomplete",
            gap_reason="response_receipt_missing",
            now=now,
        )
        session.commit()
        evidence_id = evidence.id
        assert evidence.completeness == "incomplete"
        assert evidence.issue_tags == [
            "evidence_incomplete",
            "response_receipt_missing",
        ]

    with Session(disposable_evidence_engine) as session:
        repository = DiagnosticEvidenceRepository(session)
        repeated = repository.write_bundle(
            attempt_id=attempt_id,
            ordinary_manifest={**partial, "client": {"changed": True}},
            completeness="incomplete",
            gap_reason="response_receipt_missing",
            now=now,
        )
        assert repeated.id == evidence_id
        finalized = repository.finalize(
            attempt_id=attempt_id,
            ordinary_manifest={
                **partial,
                "display": {"status": "confirmed"},
            },
            now=now,
        )
        assert finalized.completeness == "complete"
        assert finalized.gap_reason is None
        session.commit()

    restarted_engine = create_engine(disposable_evidence_engine.url, pool_pre_ping=True)
    try:
        with Session(restarted_engine) as session:
            persisted = DiagnosticEvidenceRepository(session).require(attempt_id)
            assert persisted.id == evidence_id
            assert persisted.completeness == "complete"
            assert persisted.ordinary_manifest is not None
            assert persisted.ordinary_manifest["display"] == {"status": "confirmed"}
            assert persisted.finalized_at is not None
    finally:
        restarted_engine.dispose()

    with Session(disposable_evidence_engine) as session:
        repository = DiagnosticEvidenceRepository(session)
        assert repository.expire_ordinary(attempt_id=attempt_id, now=now)
        assert not repository.expire_ordinary(attempt_id=attempt_id, now=now)
        session.commit()

    with Session(disposable_evidence_engine) as session:
        persisted = DiagnosticEvidenceRepository(session).require(attempt_id)
        assert persisted.ordinary_manifest is None
        assert persisted.ordinary_expired_at == now


def test_provider_rejects_ordinary_protected_fields_and_accepts_curated_promotion(
    disposable_evidence_engine: Engine,
) -> None:
    ordinary_attempt_id = uuid.uuid4()
    protected_manifest = _manifest(ordinary_attempt_id)
    protected_manifest["client"] = {
        "trigger_source": "sensor",
        "participant_name": "must-not-be-stored",
    }

    with Session(disposable_evidence_engine) as session:
        provider = DiagnosticEvidenceProvider(session)
        rejected = provider.write(
            attempt_id=ordinary_attempt_id,
            ordinary_manifest=protected_manifest,
            completeness="incomplete",
            gap_reason="display_event_missing",
        )
        assert not rejected.accepted
        assert rejected.error_code == "invalid_or_conflicting_evidence"
        assert DiagnosticEvidenceRepository(session).get(ordinary_attempt_id) is None

        oversized_detection_manifest = _manifest(ordinary_attempt_id)
        oversized_detection_manifest["detections"] = [
            {"occurrence_index": index} for index in range(6)
        ]
        oversized = provider.write(
            attempt_id=ordinary_attempt_id,
            ordinary_manifest=oversized_detection_manifest,
            completeness="incomplete",
            gap_reason="display_event_missing",
        )
        assert not oversized.accepted
        assert oversized.error_code == "invalid_or_conflicting_evidence"
        assert DiagnosticEvidenceRepository(session).get(ordinary_attempt_id) is None

    promoted_attempt_id = uuid.uuid4()
    promoted_manifest = _manifest(promoted_attempt_id)
    with Session(disposable_evidence_engine) as session:
        provider = DiagnosticEvidenceProvider(session)
        created = provider.write(
            attempt_id=promoted_attempt_id,
            ordinary_manifest=promoted_manifest,
            completeness="incomplete",
            gap_reason="display_event_missing",
        )
        assert created.accepted
        session.commit()

    with Session(disposable_evidence_engine) as session:
        finalized = DiagnosticEvidenceProvider(session).finalize(
            attempt_id=promoted_attempt_id,
            ordinary_manifest=promoted_manifest,
        )
        assert finalized.accepted
        session.commit()

    curated = {
        "schema_version": 1,
        "media_refs": ["private/photo-1"],
        "parameters": {"threshold": 0.72},
        "scores": [0.91],
    }
    with Session(disposable_evidence_engine) as session:
        provider = DiagnosticEvidenceProvider(session)
        rejected_promotion = provider.promote_subset(
            attempt_id=promoted_attempt_id,
            promoted_subset={"schema_version": 1, "ordinary_manifest": {}},
        )
        assert not rejected_promotion.accepted
        assert rejected_promotion.error_code == "invalid_or_conflicting_evidence"
        rejected_nested_promotion = provider.promote_subset(
            attempt_id=promoted_attempt_id,
            promoted_subset={
                "schema_version": 1,
                "curated": {
                    "details": [
                        {"ordinary_manifest": {"result": {}}},
                    ],
                },
            },
        )
        assert not rejected_nested_promotion.accepted
        assert rejected_nested_promotion.error_code == "invalid_or_conflicting_evidence"
        rejected_unvalidated_annotation = provider.promote_subset(
            attempt_id=promoted_attempt_id,
            promoted_subset={
                "schema_version": 1,
                "participant_name": "caller-supplied name",
                "annotations": ["caller-supplied annotation"],
            },
        )
        assert not rejected_unvalidated_annotation.accepted
        assert (
            rejected_unvalidated_annotation.error_code
            == "invalid_or_conflicting_evidence"
        )
        persisted_after_nested_rejection = DiagnosticEvidenceRepository(session).require(
            promoted_attempt_id
        )
        assert persisted_after_nested_rejection.promoted_subset is None
        rejected_complete_finalization = provider.finalize(
            attempt_id=promoted_attempt_id,
            ordinary_manifest={
                **promoted_manifest,
                "client": {"annotation": "must-not-be-stored"},
            },
        )
        assert not rejected_complete_finalization.accepted
        assert rejected_complete_finalization.error_code == "invalid_or_conflicting_evidence"
        persisted_after_rejections = DiagnosticEvidenceRepository(session).require(
            promoted_attempt_id
        )
        assert persisted_after_rejections.completeness == "complete"
        assert persisted_after_rejections.ordinary_manifest == promoted_manifest
        promoted = provider.promote_subset(
            attempt_id=promoted_attempt_id,
            promoted_subset=curated,
        )
        assert promoted.accepted
        session.commit()

    with Session(disposable_evidence_engine) as session:
        persisted = DiagnosticEvidenceRepository(session).require(promoted_attempt_id)
        assert persisted.ordinary_manifest is not None
        assert "participant_name" not in json_keys(persisted.ordinary_manifest)
        assert persisted.promoted_subset == curated
        assert persisted.promoted_at is not None


def json_keys(value: dict[str, object]) -> set[str]:
    keys: set[str] = set()

    def collect(current: object) -> None:
        if isinstance(current, dict):
            keys.update(str(key) for key in current)
            for child in current.values():
                collect(child)
        elif isinstance(current, list):
            for child in current:
                collect(child)

    collect(value)
    return keys
