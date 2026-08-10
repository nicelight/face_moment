from __future__ import annotations

from uuid import uuid4

import pytest

from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.candidate_staging import CandidateStager, StagedCandidate


def test_private_request_owned_candidate_stage_read_and_repeated_cleanup() -> None:
    """Prove one disposable request-owned object is the only scoped change."""
    settings = Settings.from_env()
    ensure_bucket(settings)
    object_store = PrivateObjectStore(settings)
    prefix = f"task-011-{uuid4().hex}/"
    candidate_stager = CandidateStager(object_store, key_prefix=prefix)
    marker = b"task-011-synthetic-candidate-bytes"
    candidate = None

    assert object_store.list_keys(prefix=prefix) == set()
    try:
        candidate = candidate_stager.stage(marker)

        assert candidate.key.startswith(prefix)
        assert candidate.key.removeprefix(prefix).isalnum()
        assert marker not in candidate.key.encode()
        assert object_store.list_keys(prefix=prefix) == {candidate.key}
        assert candidate_stager.read(candidate) == marker
        with pytest.raises(ValueError, match="not owned"):
            candidate_stager.cleanup(StagedCandidate(key=f"{prefix}{uuid4().hex}"))
        assert object_store.list_keys(prefix=prefix) == {candidate.key}

        candidate_stager.cleanup(candidate)
        candidate_stager.cleanup(candidate)

        assert object_store.list_keys(prefix=prefix) == set()
    finally:
        if candidate is not None:
            candidate_stager.cleanup(candidate)
