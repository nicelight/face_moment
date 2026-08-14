from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from face_moment.inventory.candidate_staging import StagedCandidate
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import ValidatedJpegCandidate
from face_moment.processing.initial_pending import InitialPendingRepository
from face_moment.serving_control.ingest_target import IngestTarget


@dataclass(frozen=True, slots=True)
class AdmissionCandidate:
    """Validated inventory input for one request-owned staged candidate."""

    staged_candidate: StagedCandidate
    validated_jpeg: ValidatedJpegCandidate


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    """Public inventory outcome without a duplicate identity disclosure."""

    outcome: Literal["accepted", "duplicate"]
    photo: Photo | None

    @classmethod
    def accepted(cls, photo: Photo) -> AdmissionResult:
        return cls(outcome="accepted", photo=photo)

    @classmethod
    def duplicate(cls) -> AdmissionResult:
        return cls(outcome="duplicate", photo=None)


_DUPLICATE_CONSTRAINT = "uq_photos_spa_id_visit_date_checksum_sha256"


class AtomicPhotoAdmission:
    """Inventory-owned publication of one Photo and its initial pending state."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def publish(
        self,
        *,
        ingest_target: IngestTarget,
        uploader_id: uuid.UUID,
        candidate: AdmissionCandidate,
    ) -> Photo:
        """Commit the complete cross-slice admission pair or publish neither."""
        with self._session.begin():
            validated = candidate.validated_jpeg
            photo = Photo(
                spa_id=ingest_target.spa_id,
                visit_date=validated.visit_date,
                captured_at=validated.captured_at,
                captured_at_source=validated.captured_at_source,
                admission_pipeline_revision_id=ingest_target.pipeline_revision_id,
                uploader_id=uploader_id,
                checksum_sha256=validated.checksum_sha256,
                original_object_key=candidate.staged_candidate.key,
                original_byte_size=validated.byte_size,
                width=validated.width,
                height=validated.height,
                is_active=True,
            )
            self._session.add(photo)
            self._session.flush()
            self._session.refresh(photo)
            InitialPendingRepository(self._session).create_initial_pending(
                photo_id=photo.id,
                pipeline_revision_id=ingest_target.pipeline_revision_id,
            )
            self._after_pending_before_commit()
        return photo

    def admit(
        self,
        *,
        ingest_target: IngestTarget,
        uploader_id: uuid.UUID,
        candidate: AdmissionCandidate,
        cleanup_losing_candidate: Callable[[StagedCandidate], None],
    ) -> AdmissionResult:
        """Publish one candidate or clean only its known duplicate loser."""
        try:
            photo = self.publish(
                ingest_target=ingest_target,
                uploader_id=uploader_id,
                candidate=candidate,
            )
        except IntegrityError as error:
            if not self._is_duplicate_conflict(error):
                raise
            cleanup_losing_candidate(candidate.staged_candidate)
            return AdmissionResult.duplicate()
        return AdmissionResult.accepted(photo)

    def _after_pending_before_commit(self) -> None:
        """Test seam for proving rollback immediately before transaction commit."""

    @staticmethod
    def _is_duplicate_conflict(error: IntegrityError) -> bool:
        diagnostic = getattr(error.orig, "diag", None)
        return getattr(diagnostic, "constraint_name", None) == _DUPLICATE_CONSTRAINT
