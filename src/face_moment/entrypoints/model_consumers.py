from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
if TYPE_CHECKING:
    from face_moment.processing.model_admission import AdmittedModelAdapter


@dataclass(slots=True)
class ModelConsumerBinding:
    """Lifecycle-owned binding for one model-consuming process."""

    database_engine: Engine
    session_factory: Callable[[], Session]
    adapter: AdmittedModelAdapter

    def close(self) -> None:
        self.database_engine.dispose()


def bind_model_consumer(settings: Settings) -> ModelConsumerBinding:
    """Resolve the committed revision, then admit only its direct adapter."""

    from face_moment.processing.model_admission import admit_selected_model
    from face_moment.processing.revisions import PipelineRevisionRepository
    from face_moment.serving_control.ingest_target import IngestTargetRepository

    database_engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with Session(database_engine) as session:
            committed_target = IngestTargetRepository(
                session
            ).resolve_committed_serving_target()
            revision = PipelineRevisionRepository(session).resolve_eligible(
                committed_target.pipeline_revision_id
            )
        adapter = admit_selected_model(revision=revision, settings=settings)
    except Exception:
        database_engine.dispose()
        raise
    return ModelConsumerBinding(
        database_engine=database_engine,
        session_factory=lambda: Session(database_engine),
        adapter=adapter,
    )
