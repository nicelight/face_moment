from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4


class CandidateObjectStore(Protocol):
    """The minimal private-object capability needed by inventory staging."""

    def put(self, *, key: str, body: bytes) -> None: ...

    def read(self, *, key: str) -> bytes: ...

    def delete(self, *, key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class StagedCandidate:
    """An inventory-internal reference to one request-owned private object."""

    key: str


class CandidateStager:
    """Stage and clean one opaque private candidate without persistence."""

    def __init__(
        self,
        object_store: CandidateObjectStore,
        *,
        key_prefix: str = "candidates",
    ) -> None:
        normalized_prefix = key_prefix.strip("/")
        if not normalized_prefix:
            raise ValueError("key_prefix must not be empty")
        self._object_store = object_store
        self._key_prefix = normalized_prefix
        self._candidate: StagedCandidate | None = None

    def stage(self, candidate_bytes: bytes) -> StagedCandidate:
        if self._candidate is not None:
            raise RuntimeError("one candidate may be staged per request")
        candidate = StagedCandidate(key=f"{self._key_prefix}/{uuid4().hex}")
        self._object_store.put(key=candidate.key, body=candidate_bytes)
        self._candidate = candidate
        return candidate

    def read(self, candidate: StagedCandidate) -> bytes:
        self._require_owned(candidate)
        return self._object_store.read(key=candidate.key)

    def cleanup(self, candidate: StagedCandidate) -> None:
        self._require_owned(candidate)
        self._object_store.delete(key=candidate.key)

    def _require_owned(self, candidate: StagedCandidate) -> None:
        if self._candidate is not candidate:
            raise ValueError("candidate is not owned by this request")
