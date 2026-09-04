"""Processing-owned result isolation for offline Calibration."""

import uuid

from face_moment.processing.offline_calibration import (
    OfflineCalibrationResult,
    result_bundle_from_offline,
)


def test_offline_results_remain_separate_by_pipeline_revision() -> None:
    photo_id = uuid.uuid4()
    attempt_id = uuid.uuid4()
    sface_id = uuid.uuid4()
    buffalo_id = uuid.uuid4()

    bundle = result_bundle_from_offline(
        sface=OfflineCalibrationResult(sface_id, ((photo_id, 1),), (attempt_id,)),
        buffalo=OfflineCalibrationResult(buffalo_id, ((photo_id, 2),), (attempt_id,)),
    )

    results = bundle["pipeline_results"]
    assert results == [
        {
            "pipeline_revision_id": str(sface_id),
            "attempt_ids": [str(attempt_id)],
            "photos": [{"photo_id": str(photo_id), "face_count": 1}],
        },
        {
            "pipeline_revision_id": str(buffalo_id),
            "attempt_ids": [str(attempt_id)],
            "photos": [{"photo_id": str(photo_id), "face_count": 2}],
        },
    ]
