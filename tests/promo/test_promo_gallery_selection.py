"""Initial optional Promo gallery selection; first-slide truth is unchanged."""
from __future__ import annotations

from face_moment.promo.result_assembly import assemble_result
from tests.promo.test_result_assembly import _detection, _match, _photo, _search_result


def test_initial_gallery_keeps_teasers_and_extends_to_twelve_unique_matches() -> None:
    matches = tuple(_match(i, .99 - i / 1000, (1 << i) - 1) for i in range(1, 17))
    assembly = assemble_result(_search_result(_detection(1, matches)))
    gallery = getattr(assembly, 'gallery_photos', ())
    assert len(gallery) == 12, 'initial result must include twelve selected gallery Photos'
    assert tuple(item.photo_id for item in gallery[:4]) == assembly.teaser_photo_ids
    assert len({item.photo_id for item in gallery}) == 12
    assert all(item.kind == 'matched' for item in gallery)
    assert assembly.n == 16
    assert assembly.session_result_photo_ids == tuple(_photo(i) for i in range(1, 17))


def test_farthest_first_continues_from_the_fixed_four_with_stable_ties() -> None:
    matches = tuple(_match(i, .99 - i / 1000, (1 << i) - 1) for i in range(1, 17))
    result = assemble_result(_search_result(_detection(1, matches), _detection(2, matches[:2])))
    assert [item.photo_id.int for item in result.gallery_photos] == [1, 16, 8, 12, 4, 6, 10, 14, 2, 3, 5, 7]
    assert result.n == 16
    equal = assemble_result(_search_result(_detection(1, tuple(_match(i, .9, 0) for i in range(10, 0, -1)))))
    assert [item.photo_id.int for item in equal.gallery_photos] == list(range(1, 11))


def test_commons_fill_only_missing_cells_without_repeats_or_union_changes() -> None:
    from face_moment.promo.result_assembly import fill_gallery_with_commons
    for count in range(4, 12):
        result = assemble_result(_search_result(_detection(1, tuple(_match(i, .9, i) for i in range(1, count + 1)))))
        before = (result.teaser_photo_ids, result.session_result_photo_ids, result.n)
        filled = fill_gallery_with_commons(result.gallery_photos, tuple(_photo(i) for i in (1, 100, 100, *range(101, 115))))
        assert len(filled) == len({item.photo_id for item in filled}) == 12
        assert filled[:count] == result.gallery_photos
        assert [item.photo_id.int for item in filled[count:]] == list(range(100, 112 - count))
        assert all(item.kind == 'common' for item in filled[count:])
        assert before == (result.teaser_photo_ids, result.session_result_photo_ids, result.n)
        assert fill_gallery_with_commons(result.gallery_photos, ()) == result.gallery_photos


def test_commons_never_rescue_insufficient_or_rejected_personal_matches() -> None:
    from face_moment.promo.result_assembly import fill_gallery_with_commons
    result = assemble_result(_search_result(
        _detection(1, tuple(_match(i, .9, i) for i in range(1, 4))),
        _detection(2, tuple(_match(i, .99, i) for i in range(4, 20)), passed=False),
    ))
    assert result.outcome == 'insufficient_results' and result.n == 3
    assert fill_gallery_with_commons(result.gallery_photos, tuple(_photo(i) for i in range(100, 120))) == ()


def test_common_provider_reads_only_active_same_venue_revision_with_bounded_capacity() -> None:
    from datetime import date, datetime, timezone
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.orm import Session
    from face_moment.infrastructure.settings import Settings
    from face_moment.processing.promo_common_photos import read_promo_common_photos
    from face_moment.processing.public_selfie_search import read_public_common_photos
    from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
    from face_moment.serving_control.ingest_target import IngestTargetRepository
    from tests.disposable_postgresql import disposable_postgresql_engine
    from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY
    from tests.processing.test_realtime_search import _add_photo

    with disposable_postgresql_engine('task140_gallery') as engine:
        database_name = engine.url.database
        with Session(engine) as session:
            revisions = [PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=code, validated_at=datetime.now(timezone.utc), **PIPELINE_COMPATIBILITY,
            ).id for code in (PipelineCode.OPENCV_SFACE, PipelineCode.INSIGHTFACE_BUFFALO_M)]
            venues = [IngestTargetRepository(session).configure_public_spa(
                name=f'gallery venue {i}', timezone='Asia/Dushanbe', serving_pipeline_revision_id=revisions[0], is_free=False,
            ).spa_id for i in range(2)]
            expected = []; dated = []
            for i in range(12):
                photo, _ = _add_photo(session, marker=f'common-{i}', spa_id=venues[0], revision_id=revisions[0],
                    embedding=(1.,) + (0.,)*127, prefix='task140/', visit_date=date(2001 if i % 2 else 2026, 1, 1),
                    state_status='no_faces', has_preview=False)
                expected.append(photo)
                if i % 2 == 0: dated.append(photo)
            for label, venue, revision, active, state in (
                ('foreign', venues[1], revisions[0], True, 'no_faces'),
                ('inactive', venues[0], revisions[0], False, 'no_faces'),
                ('revision', venues[0], revisions[1], True, 'no_faces'),
                ('ready', venues[0], revisions[0], True, 'ready'),
                ('pending', venues[0], revisions[0], True, 'pending'),
            ):
                _add_photo(session, marker=label, spa_id=venue, revision_id=revision,
                    embedding=(1.,) + (0.,)*127, prefix='task140/', is_active=active, state_status=state)
            session.commit()
            statements = []
            def capture(connection, cursor, statement, parameters, context, executemany):
                statements.append(statement)
            event.listen(engine, 'before_cursor_execute', capture)
            try:
                expected.sort()
                for capacity in (0, 1, 4, 8):
                    actual = read_promo_common_photos(session, spa_id=venues[0], pipeline_revision_id=revisions[0], limit=capacity)
                    assert actual == tuple(expected[:capacity])
                    assert actual == read_promo_common_photos(session, spa_id=venues[0], pipeline_revision_id=revisions[0], limit=capacity)
                assert read_promo_common_photos(session, spa_id=venues[0], pipeline_revision_id=revisions[0],
                    limit=8, excluded_photo_ids=(expected[0],)) == tuple(expected[1:9])
                phone = read_public_common_photos(session, pipeline_revision_id=revisions[0], matched_dates=((venues[0], date(2026, 1, 1)),))
                assert {item.photo_id for item in phone} == set(dated)
                assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)
            finally:
                event.remove(engine, 'before_cursor_execute', capture)
    admin = create_engine(Settings.from_env().database_url)
    try:
        with admin.connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM pg_database WHERE datname=:name'), {'name': database_name}) == 0
    finally:
        admin.dispose()
