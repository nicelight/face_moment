"""Task-123 supplier persistence/default and bounded migration proof."""
from datetime import datetime, timezone
import inspect

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control.ingest_target import IngestTargetRepository
from face_moment.serving_control.public_search_context import read_public_venues
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


def test_owner_explicit_public_creation_and_new_session_free_mode():
    assert inspect.signature(IngestTargetRepository.configure_public_spa).parameters['is_free'].default is inspect.Parameter.empty
    with disposable_postgresql_engine('task123_free') as engine:
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime.now(timezone.utc), **PIPELINE_COMPATIBILITY)
            owner = IngestTargetRepository(session)
            paid = owner.configure_spa(timezone='UTC', serving_pipeline_revision_id=revision.id)
            free = owner.configure_public_spa(timezone='UTC', serving_pipeline_revision_id=revision.id, is_free=True)
            for bad in (0, 1, None, 'true'):
                with pytest.raises(ValueError):
                    owner.set_spa_free_mode(paid.spa_id, is_free=bad)
            session.commit()
        with Session(engine) as session:
            projection = {v.id: v for v in read_public_venues(session)}
            assert projection[paid.spa_id].is_free is False and projection[free.spa_id].is_free is True
            assert IngestTargetRepository(session).set_spa_free_mode(paid.spa_id, is_free=True) is True
            session.commit()
            # Published values remain immutable even after owner persistence changes.
            assert projection[paid.spa_id].is_free is False
        with Session(engine) as session:
            assert {v.id: v.is_free for v in read_public_venues(session)} == {paid.spa_id: True, free.spa_id: True}
            IngestTargetRepository(session).set_spa_free_mode(free.spa_id, is_free=False); session.commit()
        with Session(engine) as session:
            assert {v.id: v.is_free for v in read_public_venues(session)} == {paid.spa_id: True, free.spa_id: False}


def test_task_revisions_roundtrip_preserve_existing_venue_settings_photos():
    from tests.processing.test_realtime_search import _add_photo
    import numpy as np
    with disposable_postgresql_engine('task123_migration') as engine:
        with Session(engine) as session:
            rev = PipelineRevisionRepository(session).publish_eligible(pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime.now(timezone.utc), **PIPELINE_COMPATIBILITY)
            spa = IngestTargetRepository(session).configure_public_spa(name='preserved venue', timezone='UTC',
                serving_pipeline_revision_id=rev.id, is_free=True)
            photo, _ = _add_photo(session, marker='preserved-photo', spa_id=spa.spa_id, revision_id=rev.id,
                embedding=tuple(np.eye(1,128)[0]), prefix='task123-migration/')
            session.commit()
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE public.task123_marker (value text NOT NULL)'))
            connection.execute(text("INSERT INTO public.task123_marker VALUES ('preserve')"))
            prior = connection.execute(text('SELECT id,name,timezone,settings_revision,serving_pipeline_revision_id FROM face_moment.spas')).one()
        config = Config('alembic.ini')
        command.downgrade(config, '0029_global_photo_tariff')
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT to_regclass('face_moment.public_search_results')")) is None
            assert not connection.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_schema='face_moment' AND table_name='spas' AND column_name='is_free'"))
        command.upgrade(config, '0031_public_search_results')
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT is_free FROM face_moment.spas')) is False
            assert connection.execute(text('SELECT id,name,timezone,settings_revision,serving_pipeline_revision_id FROM face_moment.spas')).one() == prior
            assert connection.scalar(text('SELECT id FROM face_moment.photos WHERE id=:id'), {'id':photo}) == photo
            assert connection.scalar(text('SELECT value FROM public.task123_marker')) == 'preserve'
            assert connection.scalar(text("SELECT to_regclass('face_moment.browser_search_profiles')")) is not None
        from alembic.script import ScriptDirectory
        graph = ScriptDirectory.from_config(config)
        assert graph.get_revision('0030_venue_free_mode').down_revision == '0029_global_photo_tariff'
        assert graph.get_revision('0031_public_search_results').down_revision == '0030_venue_free_mode'
