from __future__ import annotations

from face_moment.inventory.http import _photo_upload_page_html


def test_uploader_polls_only_an_accepted_photo_and_renders_api_truth() -> None:
    page = _photo_upload_page_html()

    assert "async function pollProcessingStatus(photoId, row)" in page
    assert 'fetch(`/api/inventory/photos/${photoId}/processing`' in page
    assert "pollProcessingStatus(payload.photo.photo_id, row);" in page
    assert 'payload.processing_status === "ready"' in page
    assert 'payload.searchable ? "searchable" : "ready"' in page
    assert 'payload.searchable ? "" : "not searchable"' in page
    assert 'payload.processing_status === "failed"' in page
    assert "payload.failure_reason || \"\"" in page
    assert 'payload.processing_status === "no_faces"' in page
    assert 'new Set(["ready", "no_faces", "failed"])' in page
