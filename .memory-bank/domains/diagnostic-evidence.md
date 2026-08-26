---
description: Diagnostics-owned evidence bundle, completeness, promotion and retention data contract.
status: active
last_updated: 2026-08-25
source_of_truth:
  - .memory-bank/domains/diagnostic-evidence.md
---
# Diagnostic Evidence

## Scope And Owner

`diagnostics` owns optional detailed evidence linked to the promo-owned core
Attempt. `promo` writes it only through the diagnostics application boundary;
the diagnostics repository MUST NOT mutate core Attempts, results or sessions.
Evidence failure never rolls back or changes participant behavior.

The runtime persistence path is PostgreSQL table
`face_moment.diagnostic_evidence` through the diagnostics repository. A row is
created only after material evidence exists. The absence of a row is not
replaced by an empty anchor: a terminal core Attempt with no row is projected
as `incomplete` with `evidence_absent`.

## PostgreSQL Shape And Owner Boundary

One next-linear Alembic revision creates:

| Field | Contract |
|---|---|
| `attempt_id` | Unique promo-owned server Attempt UUID used as a logical cross-owner reference. It has no ownership-crossing delete cascade. |
| `schema_version` | Positive integer; current value is `1`. |
| `completeness` | `incomplete \| complete`. |
| `gap_reason` | Required non-empty bounded text for `incomplete`; null for `complete`. |
| `issue_tags` | JSON array of unique bounded machine tags used by later diagnostics filtering. |
| `ordinary_manifest` | Nullable JSONB versioned evidence bundle; cleared by ordinary retention expiry. |
| `promoted_subset` | Nullable JSONB curated Calibration subset retained until explicit deletion. |
| `created_at`, `updated_at` | Server timestamps. |
| `finalized_at` | Nullable; set only when completeness becomes `complete`. |
| `promoted_at` | Nullable; present exactly when `promoted_subset` is present. |
| `ordinary_expired_at` | Nullable cleanup timestamp; once present, ordinary content cannot be restored by a stale write. |

The migration uses the shared `face_moment` schema, one `Base/MetaData` and the
current direct Alembic predecessor. Migration proof uses only a disposable
task-owned database and never downgrades operator/default state.

## Evidence Bundle Version 1

`ordinary_manifest` is a bounded object with these top-level sections:

| Section | Required content when applicable |
|---|---|
| `identity` | `attempt_id`, `client_attempt_id` and correlation-safe trigger identity. |
| `client` | Client release, detector/model, camera/config and admitted proposal metadata; no credential or authentication state. |
| `serving` | Release, immutable pipeline revision/code, threshold, quality settings, active date and settings revision copied from the core projection. |
| `detections` | Ordered selected/repeated occurrence observations, rank, quality/gate result, rejection reason and threshold-valid candidate observations. |
| `result` | Terminal outcome plus selected teaser IDs and complete union/`N` when a result exists. |
| `display` | Actually received display/QR event and client elapsed value when applicable. |
| `artifacts` | Optional private artifact descriptors only when a later accepted writer stores an artifact. |

Version 1 uses this exact structural shape; nullable `result`/`display` values
mean the corresponding outcome did not occur, while absent applicable data
requires `incomplete` and a gap:

```json
{
  "schema_version": 1,
  "identity": {
    "attempt_id": "server-attempt-uuid",
    "client_attempt_id": "client-attempt-uuid"
  },
  "client": {
    "trigger_source": "sensor",
    "client_release": "2026.08.1",
    "detector_id": "mediapipe_blazeface_full_range",
    "model_version": "blazeface-full-range-1",
    "jpeg_quality": 0.85,
    "camera_device_id": "browser-device-id",
    "proposal_count": 3
  },
  "serving": {
    "release_id": "face-moment-runtime",
    "visit_date": "2026-08-25",
    "pipeline_revision_id": "pipeline-uuid",
    "pipeline_code": "opencv_sface",
    "settings_revision": 4,
    "threshold": 0.42,
    "quality_settings": {}
  },
  "detections": [
    {
      "occurrence_index": 0,
      "rank": 1,
      "reference_quality_score": 0.91,
      "quality_gate_passed": true,
      "rejection_reason": null,
      "matches": [
        {
          "photo_id": "photo-uuid",
          "cosine_similarity": 0.73,
          "phash64": 1
        }
      ]
    }
  ],
  "result": {
    "outcome": "result",
    "teaser_photo_ids": [
      "photo-uuid-1",
      "photo-uuid-2",
      "photo-uuid-3",
      "photo-uuid-4"
    ],
    "session_result_photo_ids": [
      "photo-uuid-1",
      "photo-uuid-2",
      "photo-uuid-3",
      "photo-uuid-4"
    ],
    "n": 4
  },
  "display": {
    "status": "confirmed",
    "qr_fully_visible_elapsed_ms": 8420
  },
  "artifacts": []
}
```

The encoded UTF-8 JSON for each ordinary or promoted object MUST NOT exceed
`1 MiB`. `issue_tags` contains at most 32 unique lowercase snake-case tags of
at most 64 ASCII characters each; `gap_reason` is at most 255 characters.
Version 1 stores at most five detection observations and preserves every
threshold-valid match returned for each of them until the bundle-size bound;
exceeding that bound fails the best-effort write and remains explicit rather
than silently truncating a candidate pool. FT-007 writes `artifacts: []`.

Candidate observations may contain Photo UUID, finite score and deterministic
ranking inputs required for reproduction. Embeddings, credentials, auth
headers/cookies/tokens, commercial Photo originals, personalized session data,
request bodies, session replay, participant names and annotations MUST NOT be
stored in `ordinary_manifest`. Participant names and annotations are accepted
only by the separately authorized `promoted_subset` write boundary described
below; an ordinary write containing either field is rejected rather than
silently stripped.

Capture-derived reference images, normalized images and crops are not denied
solely because they contain image content, but FT-007 requires no capture-media
storage, cache, per-crop log or delivery mechanism. The current no-selfie flow
MUST NOT create a selfie descriptor or object.

## Completeness And Safe Writes

- Writes are idempotent by `(attempt_id, schema_version)` and merge only named
  diagnostics-owned sections through the repository.
- A partial write uses `incomplete` plus an explicit gap such as
  `search_evidence_missing`, `response_receipt_missing`,
  `display_event_missing` or `finalization_failed`.
- `complete` requires every section applicable to the actual core outcome;
  non-result Attempts do not invent result/display data.
- Finalization may move `incomplete -> complete`; an expired ordinary bundle
  never moves back to either state.
- Invalid/oversized/non-finite evidence is rejected inside diagnostics and is
  reported to the promo caller as a non-throwing failed evidence write.
- Issue tags are deterministic bounded labels derived from actual outcome,
  latency-stage and gap observations. They do not contain participant names or
  free-form log payloads.

Read projection composes this bundle with the immutable promo Attempt through
the accepted `diagnostics -> promo` boundary. Missing core detail after its
ordinary retention expiry remains truthfully unavailable; a promoted subset
does not recreate the expired ordinary Attempt.

## Promoted Subset

The repository exposes a diagnostics-owned promotion seam for later FT-010 and
FT-011 use. The stored subset contains only already available server-side media
descriptors, required crops when actually stored, versioned parameters,
scores, annotations and participant name. It MUST NOT retain the whole bundle,
unselected reference series, Promo screenshot, technical logs, credentials or
session data.

Promotion does not extend `ordinary_manifest` lifetime. Retention cleanup may
clear ordinary content while preserving `promoted_subset`, its provenance and
explicit-deletion lifecycle. FT-007 proves this seam with task-owned fixtures;
annotation UI and Calibration selection remain owned by FT-010/FT-011.

## Retention Cleanup Boundary

Given a fixed UTC cutoff, promo selects its own core Attempts strictly before
the cutoff and passes their UUIDs to diagnostics. For every supplied UUID,
diagnostics first makes any ordinary content unreadable, deletes any
diagnostics-owned private artifacts idempotently, clears ordinary fields and
returns:

- core Attempt UUIDs eligible for promo-owned deletion;
- evidence rows expired;
- promoted subsets preserved;
- private artifacts deleted or already absent;
- a sanitized failure when convergence could not complete.

Diagnostics never deletes promo rows. If no media was stored, artifact deletion
is a valid zero-count result, not a requirement to create storage. A rerun with
the same cutoff converges to the same inaccessible state and counts only newly
confirmed owner changes. Absence of a `diagnostic_evidence` row is an explicit
owner-local no-op confirmation, so an old ordinary core Attempt without an
evidence row remains eligible for promo deletion; retention MUST NOT discover
candidates by scanning only the evidence table.

## Verification Targets

- Migration/repository tests prove the exact owner table, constraints, unique
  logical Attempt link, partial/finalized transitions, expiry irreversibility
  and restart persistence without cross-owner cascade.
- Complete, partial, absent and failed-writer fixtures compare the unchanged
  core participant outcome with the resulting evidence projection and gap.
- Realtime fixtures preserve selected/repeated detections, candidate pools,
  teaser/union/`N`, versions and parameters without embeddings or forbidden
  protected data. Ordinary provider/integration fixtures reject participant
  names and annotations, while a separately authorized promoted-subset fixture
  admits only those curated fields without retaining the whole ordinary bundle.
- Inventory/security scans prove no required capture-media path, no selfie
  artifact and no credential/auth/session payload; zero stored media remains a
  conforming outcome.
- Retention fixtures clear ordinary bundles, delete an old core Attempt with no
  evidence row, preserve only the curated subset and prove safe rerun plus
  owner isolation.
