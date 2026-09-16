"""Real PostgreSQL/API proof of venue-scoped settings and admission snapshots."""

import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from face_moment.inventory.admission import AtomicPhotoAdmission
from face_moment.inventory.photo_persistence import Photo
from face_moment.serving_control.ingest_target import IngestTargetRepository, Spa
from tests.inventory.test_atomic_admission import _candidate
from tests.serving_control.test_active_search_date import (
    _Fixture, _login, _request, active_search_date_fixture,
)


@pytest.mark.parametrize("role", ["operator", "developer"])
def test_thresholds_are_independent_and_new_uploads_snapshot_them(
    active_search_date_fixture: _Fixture, role: str,
) -> None:
    f = active_search_date_fixture
    cookies = _login(f.app, getattr(f, role))
    headers = {"X-CSRF-Token": cookies["fm_staff_csrf"]}
    path = f"/api/serving/spas/{f.spa_id}/detector-thresholds"
    with Session(f.engine) as session:
        target = IngestTargetRepository(session).resolve_ingest_target(f.spa_id)
        session.rollback()
        old = AtomicPhotoAdmission(session).publish(
            ingest_target=target, uploader_id=uuid.uuid4(), candidate=_candidate(uuid.uuid4().hex),
        )
        old_id = old.id
    for kind, value in (("photo_yunet", 0.72), ("capture_blazeface", 0.6)):
        code, response_headers, body = _request(f.app, "PUT", f"{path}/{kind}",
            cookies=cookies, headers=headers, body={"threshold": value})
        assert code == 200 and body == {"threshold": value}
        assert response_headers["cache-control"] == "no-store"
    with Session(f.engine) as session:
        spa = session.get(Spa, f.spa_id)
        assert (spa.photo_yunet_threshold, spa.capture_blazeface_threshold) == (0.72, 0.6)
        other = session.get(Spa, f.inaccessible_spa_id)
        assert (other.photo_yunet_threshold, other.capture_blazeface_threshold) == (0.7, 0.5)
        assert session.get(Photo, old_id).photo_yunet_threshold == 0.7
        session.rollback()
        # Admission reloads the venue under its lock, even with an old target.
        new = AtomicPhotoAdmission(session).publish(
            ingest_target=target, uploader_id=uuid.uuid4(), candidate=_candidate(uuid.uuid4().hex),
        )
        assert new.photo_yunet_threshold == 0.72
    code, _, page = _request(f.app, "GET", "/staff/spas", cookies=cookies)
    assert code == 200
    assert 'value="0.72" required disabled' in page
    assert 'value="0.6" required disabled' in page
    assert 'data-manual-search hidden' in page


def test_threshold_writes_require_admin_csrf_and_valid_value(active_search_date_fixture: _Fixture) -> None:
    f = active_search_date_fixture
    admin = _login(f.app, f.operator)
    photographer = _login(f.app, f.photographer)
    path = f"/api/serving/spas/{f.spa_id}/detector-thresholds/photo_yunet"
    for cookies, csrf, code in (({}, "", 401), (admin, "bad", 403),
                              (photographer, photographer["fm_staff_csrf"], 403)):
        assert _request(f.app, "PUT", path, cookies=cookies,
            headers={"X-CSRF-Token": csrf}, body={"threshold": 0.72})[0] == code
    for value in (0, -0.1, 1.1, True, "0.72", None):
        assert _request(f.app, "PUT", path, cookies=admin,
            headers={"X-CSRF-Token": admin["fm_staff_csrf"]}, body={"threshold": value})[0] == 422
    assert _request(f.app, "PUT", path.replace(str(f.spa_id), str(f.inaccessible_spa_id)),
        cookies=admin, headers={"X-CSRF-Token": admin["fm_staff_csrf"]}, body={"threshold": 0.72})[0] == 403
    with Session(f.engine) as session:
        assert session.get(Spa, f.spa_id).photo_yunet_threshold == 0.7


def test_threshold_migration_preserves_existing_photos(active_search_date_fixture: _Fixture) -> None:
    f = active_search_date_fixture
    with Session(f.engine) as session:
        target = IngestTargetRepository(session).resolve_ingest_target(f.spa_id)
        session.rollback()
        photo = AtomicPhotoAdmission(session).publish(ingest_target=target,
            uploader_id=uuid.uuid4(), candidate=_candidate(uuid.uuid4().hex))
        photo_id, checksum = photo.id, photo.checksum_sha256
    command.downgrade(Config("alembic.ini"), "0023_search_date_ranges")
    command.upgrade(Config("alembic.ini"), "head")
    with Session(f.engine) as session:
        photo = session.get(Photo, photo_id)
        assert photo.checksum_sha256 == checksum
        assert photo.photo_yunet_threshold == 0.9
        spa = session.get(Spa, f.spa_id)
        assert (spa.photo_yunet_threshold, spa.capture_blazeface_threshold) == (0.9, 0.5)
