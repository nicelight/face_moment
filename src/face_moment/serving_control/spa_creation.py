"""Atomic venue creation shared by staff API and the deployment initializer."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.processing.model_admission import ModelAdmissionError, publish_initial_sface_revision
from face_moment.serving_control.ingest_target import IngestTarget, IngestTargetRepository, Spa
from face_moment.serving_control.realtime_context import RealtimeContextRepository


def initialize_default_spa(session: Session) -> IngestTarget | None:
    """Do nothing on an initialized database, including inactive venues."""
    repository = IngestTargetRepository(session)
    repository.lock_revision_configuration()
    if session.scalar(select(Spa.id).limit(1)) is not None:
        return None
    return create_initialized_spa(session, name="СПА Сибирь 1", timezone="Etc/GMT-7")


def create_initialized_spa(session: Session, *, name: str, timezone: str) -> IngestTarget:
    """Caller authorizes and commits; all three records share its transaction."""
    repository = IngestTargetRepository(session)
    repository.lock_revision_configuration()
    if session.scalar(select(Spa.id).limit(1)) is None:
        try:
            settings = Settings.from_env()
        except RuntimeError as error:
            raise ModelAdmissionError(str(error)) from error
        revision = publish_initial_sface_revision(session, settings=settings)
    else:
        revision = repository.resolve_committed_serving_revision()
    venue = repository.configure_spa(
        name=name, timezone=timezone, serving_pipeline_revision_id=revision.id,
    )
    RealtimeContextRepository(session).provision_reference_settings(
        spa_id=venue.spa_id, pipeline_code=revision.pipeline_code,
        reference_threshold=0.38, min_query_face_quality=0.5,
        quality_settings={"version": 1},
    )
    return venue
