from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints import background_worker, common, realtime
from face_moment.entrypoints.model_consumers import (
    ModelConsumerBinding,
    bind_model_consumer,
)
from face_moment.infrastructure.settings import Settings
from face_moment.processing.model_admission import (
    AdmittedModelAdapter,
    ModelAdmissionError,
    admit_selected_model,
)
from face_moment.processing.revisions import (
    EligiblePipelineRevision,
    PipelineCode,
    PipelineRevision,
    PipelineRevisionRepository,
)
from face_moment.processing.sface_adapter import SFaceModelAssets, SFacePhotoAdapter
from face_moment.processing import worker_runtime
from face_moment.serving_control import IngestTargetRepository
from face_moment.serving_control.ingest_target import Spa


@dataclass
class _RecordingAdapter:
    pipeline_revision_id: uuid.UUID
    warmed: bool = False

    @property
    def ready(self) -> bool:
        return self.warmed

    def warmup(self) -> None:
        self.warmed = True

    def process_for_terminal(self, _photo: np.ndarray[Any, Any]) -> tuple[object, ...]:
        return ()


def _assets(tmp_path: Path) -> SFaceModelAssets:
    detector_path = tmp_path / "yunet.onnx"
    recognizer_path = tmp_path / "sface.onnx"
    detector_path.write_bytes(b"task-026-yunet")
    recognizer_path.write_bytes(b"task-026-sface")
    return SFaceModelAssets(
        detector_path=detector_path,
        detector_id="yunet",
        detector_version="2024mar",
        recognizer_path=recognizer_path,
        recognizer_id="sface",
        recognizer_version="2021dec",
        preprocessing_version="opencv-bgr-v1",
        alignment_version="opencv-aligncrop-v1",
        normalization_version="l2-v1",
    )


def _revision(
    assets: SFaceModelAssets,
    *,
    pipeline_code: PipelineCode = PipelineCode.OPENCV_SFACE,
    embedding_dimension: int = 3,
) -> EligiblePipelineRevision:
    return EligiblePipelineRevision(
        id=uuid.uuid4(),
        pipeline_code=pipeline_code,
        detector_id=assets.detector_id,
        detector_version=assets.detector_version,
        recognizer_id=assets.recognizer_id,
        recognizer_version=assets.recognizer_version,
        weights_sha256=assets.weights_sha256(),
        preprocessing_version=assets.preprocessing_version,
        alignment_version=assets.alignment_version,
        normalization_version=assets.normalization_version,
        embedding_dimension=embedding_dimension,
        created_at=datetime.now(UTC),
        validated_at=datetime.now(UTC),
    )


def _set_sface_environment(
    monkeypatch: pytest.MonkeyPatch, assets: SFaceModelAssets, *, dimension: int = 3
) -> Settings:
    monkeypatch.setenv("SFACE_DETECTOR_PATH", str(assets.detector_path))
    monkeypatch.setenv("SFACE_DETECTOR_ID", assets.detector_id)
    monkeypatch.setenv("SFACE_DETECTOR_VERSION", assets.detector_version)
    monkeypatch.setenv("SFACE_RECOGNIZER_PATH", str(assets.recognizer_path))
    monkeypatch.setenv("SFACE_RECOGNIZER_ID", assets.recognizer_id)
    monkeypatch.setenv("SFACE_RECOGNIZER_VERSION", assets.recognizer_version)
    monkeypatch.setenv("SFACE_PREPROCESSING_VERSION", assets.preprocessing_version)
    monkeypatch.setenv("SFACE_ALIGNMENT_VERSION", assets.alignment_version)
    monkeypatch.setenv("SFACE_NORMALIZATION_VERSION", assets.normalization_version)
    monkeypatch.setenv("SFACE_EMBEDDING_DIMENSION", str(dimension))
    return Settings.from_env()


def _patch_sface_loader(
    monkeypatch: pytest.MonkeyPatch, created: list[_RecordingAdapter]
) -> None:
    def load(*, revision: EligiblePipelineRevision, assets: SFaceModelAssets) -> _RecordingAdapter:
        assert assets.detector_path.is_file()
        assert assets.recognizer_path.is_file()
        adapter = _RecordingAdapter(revision.id)
        created.append(adapter)
        return adapter

    monkeypatch.setattr(SFacePhotoAdapter, "from_configured_assets", load)


def test_admission_verifies_matching_direct_assets_before_warmup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = _assets(tmp_path)
    revision = _revision(assets)
    settings = _set_sface_environment(monkeypatch, assets)
    created: list[_RecordingAdapter] = []
    _patch_sface_loader(monkeypatch, created)

    adapter = admit_selected_model(revision=revision, settings=settings)

    assert adapter.ready is True
    assert adapter.pipeline_revision_id == revision.id
    assert [item.pipeline_revision_id for item in created] == [revision.id]


@pytest.mark.parametrize("case", ["missing", "identity", "hash", "dimension"])
def test_admission_rejects_mismatched_or_missing_selected_sface_assets(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = _assets(tmp_path)
    revision = _revision(assets)
    settings = _set_sface_environment(monkeypatch, assets)
    created: list[_RecordingAdapter] = []
    _patch_sface_loader(monkeypatch, created)

    if case == "missing":
        monkeypatch.setenv("SFACE_DETECTOR_PATH", str(tmp_path / "missing.onnx"))
    elif case == "identity":
        monkeypatch.setenv("SFACE_DETECTOR_ID", "other-pipeline-detector")
    elif case == "hash":
        assets.recognizer_path.write_bytes(b"other-pipeline-weights")
    else:
        monkeypatch.setenv("SFACE_EMBEDDING_DIMENSION", "4")

    with pytest.raises(ModelAdmissionError):
        admit_selected_model(revision=revision, settings=Settings.from_env())

    assert created == []


def test_admission_rejects_other_pipeline_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = _assets(tmp_path)
    settings = _set_sface_environment(monkeypatch, assets)
    created: list[_RecordingAdapter] = []
    _patch_sface_loader(monkeypatch, created)

    with pytest.raises(ModelAdmissionError):
        admit_selected_model(
            revision=_revision(
                assets, pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M
            ),
            settings=settings,
        )

    assert created == []


@pytest.fixture
def disposable_model_database(monkeypatch: pytest.MonkeyPatch) -> Engine:
    base_settings = Settings.from_env()
    database_name = f"task026_{uuid.uuid4().hex}"
    database_url = make_url(base_settings.database_url).set(database=database_name)
    admin_engine = create_engine(
        base_settings.database_url, pool_pre_ping=True, isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {database_name}"))
    monkeypatch.setenv("DATABASE_URL", database_url.render_as_string(hide_password=False))
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)"))
        admin_engine.dispose()


def test_binding_reads_one_committed_selected_revision_then_admits_it(
    disposable_model_database: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assets = _assets(tmp_path)
    settings = _set_sface_environment(monkeypatch, assets)
    created: list[_RecordingAdapter] = []
    _patch_sface_loader(monkeypatch, created)

    with Session(disposable_model_database) as session:
        revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=datetime.now(UTC),
            detector_id=assets.detector_id,
            detector_version=assets.detector_version,
            recognizer_id=assets.recognizer_id,
            recognizer_version=assets.recognizer_version,
            weights_sha256=assets.weights_sha256(),
            preprocessing_version=assets.preprocessing_version,
            alignment_version=assets.alignment_version,
            normalization_version=assets.normalization_version,
            embedding_dimension=3,
        )
        IngestTargetRepository(session).configure_spa(
            name=f"task-026-{uuid.uuid4().hex}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=revision.id,
        )
        session.commit()

    binding = bind_model_consumer(settings)
    try:
        assert binding.adapter.pipeline_revision_id == revision.id
        assert binding.adapter.ready is True
        assert [item.pipeline_revision_id for item in created] == [revision.id]
    finally:
        binding.close()


def test_binding_rejects_absent_or_ineligible_committed_selection_before_admission(
    disposable_model_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings.from_env()

    with pytest.raises(LookupError):
        bind_model_consumer(settings)

    with Session(disposable_model_database) as session:
        revision = PipelineRevision(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            detector_id="ineligible-detector",
            detector_version="v1",
            recognizer_id="ineligible-recognizer",
            recognizer_version="v1",
            weights_sha256="0" * 64,
            preprocessing_version="ineligible-preprocessing-v1",
            alignment_version="ineligible-alignment-v1",
            normalization_version="ineligible-normalization-v1",
            embedding_dimension=3,
            validated_at=None,
        )
        session.add(revision)
        session.flush()
        session.add(
            Spa(
                name=f"task-026-ineligible-{uuid.uuid4().hex}",
                timezone="Asia/Dushanbe",
                active=True,
                serving_pipeline_revision_id=revision.id,
            )
        )
        session.commit()

    with pytest.raises(LookupError):
        bind_model_consumer(settings)


async def _health_during_lifespan(app: Any) -> dict[str, object]:
    async with app.router.lifespan_context(app):
        endpoint = next(
            route.endpoint
            for route in app.routes
            if getattr(route, "path", None) == "/healthz"
        )
        return endpoint()


def test_both_model_consumer_roles_bind_before_reporting_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings.from_env()
    adapter = _RecordingAdapter(uuid.uuid4(), warmed=True)

    def bind(_settings: Settings) -> ModelConsumerBinding:
        return ModelConsumerBinding(
            database_engine=create_engine(settings.database_url),
            session_factory=lambda: Session(),
            adapter=adapter,
        )

    async def no_work(
        self: object, *, stop_event: asyncio.Event, **_kwargs: object
    ) -> None:
        await stop_event.wait()

    monkeypatch.setattr(common, "wait_for_dependencies", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(realtime, "bind_model_consumer", bind)
    monkeypatch.setattr(background_worker, "bind_model_consumer", bind)
    monkeypatch.setattr(worker_runtime.BackgroundPhotoWorker, "recover_startup", lambda _self: 0)
    monkeypatch.setattr(worker_runtime.BackgroundPhotoWorker, "run_until_stopped", no_work)

    realtime_health = asyncio.run(_health_during_lifespan(realtime.create_app()))
    worker_health = asyncio.run(_health_during_lifespan(background_worker.create_app()))

    assert realtime_health == {
        "role": "RealtimeFaceService",
        "ready": True,
        "production_model_loaded": True,
    }
    assert worker_health["production_model_loaded"] is True
    assert worker_health["recovery_completed"] is True


def test_worker_loop_failure_clears_readiness_and_fails_role_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings.from_env()
    adapter = _RecordingAdapter(uuid.uuid4(), warmed=True)

    def bind(_settings: Settings) -> ModelConsumerBinding:
        return ModelConsumerBinding(
            database_engine=create_engine(settings.database_url),
            session_factory=lambda: Session(),
            adapter=adapter,
        )

    started = asyncio.Event()
    release_failure = asyncio.Event()

    async def fail_after_readiness(self: object, **_kwargs: object) -> None:
        started.set()
        await release_failure.wait()
        raise RuntimeError("fixture worker loop failure")

    async def observe_worker_failure() -> dict[str, object]:
        app = background_worker.create_app()
        endpoint = next(
            route.endpoint
            for route in app.routes
            if getattr(route, "path", None) == "/healthz"
        )
        observed: dict[str, object] = {}
        try:
            async with app.router.lifespan_context(app):
                await started.wait()
                release_failure.set()
                for _ in range(3):
                    await asyncio.sleep(0)
                observed = endpoint()
        except BaseException:
            return observed or endpoint()
        return observed

    monkeypatch.setattr(common, "wait_for_dependencies", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(background_worker, "bind_model_consumer", bind)
    monkeypatch.setattr(worker_runtime.BackgroundPhotoWorker, "recover_startup", lambda _self: 0)
    monkeypatch.setattr(
        worker_runtime.BackgroundPhotoWorker, "run_until_stopped", fail_after_readiness
    )

    health = asyncio.run(observe_worker_failure())

    assert health["ready"] is False


def test_both_roles_fail_closed_before_readiness_when_binding_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_settings: Settings) -> ModelConsumerBinding:
        raise ModelAdmissionError("fixture mismatch")

    monkeypatch.setattr(common, "wait_for_dependencies", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(realtime, "bind_model_consumer", fail)
    monkeypatch.setattr(background_worker, "bind_model_consumer", fail)

    with pytest.raises(ModelAdmissionError):
        asyncio.run(_health_during_lifespan(realtime.create_app()))
    with pytest.raises(ModelAdmissionError):
        asyncio.run(_health_during_lifespan(background_worker.create_app()))
