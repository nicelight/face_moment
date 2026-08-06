---
description: Canonical compatible Photo-processing data, worker, derivative and recovery specification.
status: active
last_updated: 2026-08-06
source_of_truth:
  - .memory-bank/domains/photo-processing.md
---
# Photo Processing

## Scope And Ownership

This specification owns compatible background processing after
[Photo Admission](photo-admission.md) has atomically created one Photo and its
serving-revision `pending` row. `processing` owns pipeline revisions, the Photo
pipeline lifecycle, derived media, face rows and the processing application
boundary. It reads immutable Photo/visibility and serving projections through
the accepted edges in the [Boundary Map](../contracts/boundary-map.md).

`inventory` owns Photo identity, visibility and the staff-visible outcome;
`serving_control` owns the selected serving revision. HTTP/UI handlers,
infrastructure adapters, generic helpers and the composition root MUST NOT
claim work, publish processing state, or reproduce compatible-searchability
rules.

## Pipeline Revision And Engine Contract

The existing `face_moment.pipeline_revisions` row is extended into the
immutable compatibility identity for one engine implementation:

| Field | Contract |
|---|---|
| `id` | UUID primary key used by every state, face and serving reference. |
| `pipeline_code` | Exactly `opencv_sface` or `insightface_buffalo_m`. |
| `detector_id`, `detector_version` | Required configured detector identity. |
| `recognizer_id`, `recognizer_version` | Required configured recognizer identity. |
| `weights_sha256` | Required SHA-256 over the configured model asset set. |
| `preprocessing_version`, `alignment_version` | Required native preparation identity. |
| `normalization_version` | Required embedding-normalization identity. |
| `embedding_dimension` | Required positive dimension. |
| `created_at`, `validated_at` | Server timestamps; only a validated immutable revision may be selected for serving. |

Once referenced by a Photo pipeline state, the compatibility fields MUST NOT
change. A changed detector, recognizer, weights, preprocessing, alignment,
normalization or dimension creates a new revision.

The owner-local `FaceEngine` boundary extends the existing Foundation seam with
its revision identity, embedding dimension and one `process_photo` operation
returning pipeline-native face results. The same implementations remain
reusable by later realtime query processing rather than creating a second
engine abstraction. `opencv_sface` uses YuNet detection plus
`FaceRecognizerSF.alignCrop`/SFace. `insightface_buffalo_m` uses its own SCRFD,
landmarks, alignment and Buffalo M `normed_embedding` path. Bboxes, landmarks,
crops and alignment results MUST NOT cross between these implementations.
Configured model assets are verified against the revision before work is
accepted; the worker does not download, silently replace or auto-select models.

## Persisted Processing Shape

All rows use the shared `face_moment` PostgreSQL schema, one SQLAlchemy
`Base/MetaData` and the single linear Alembic stream. Models and repositories
remain under `processing`.

### `face_moment.photo_pipeline_states`

The existing composite key remains `(photo_id, pipeline_revision_id)`.

| Field | Contract |
|---|---|
| `status` | Exactly `pending`, `processing`, `ready`, `no_faces` or `failed`. |
| `attempt_count` | Non-negative; incremented by the atomic claim. The initial retry limit is three attempts. |
| `status_changed_at` | Required server timestamp of the current transition. |
| `searchable_at` | Set only when `ready` is published; immutable thereafter. |
| `last_error` | Nullable bounded operator-safe failure text; never contains credentials, model paths, object keys or traceback payloads. |
| `preview_object_key`, `thumbnail_object_key` | Nullable private deterministic derivative keys; both are present for `ready`, absent for `no_faces`. |

`ready` is valid only when both derivatives and at least one complete compatible
face row are publishable. `no_faces` is valid only when the engine completed
successfully with no faces. `failed` is terminal after the third failed claim.
Pending/processing rows and every terminal row remain durable until the owning
inventory purge explicitly commands processing cleanup.

### `face_moment.photo_faces`

One row represents one pipeline-specific detection on one Photo:

| Field | Contract |
|---|---|
| `id` | Server-generated UUID primary key. |
| `photo_id`, `pipeline_revision_id`, `face_index` | Required identity with a unique composite constraint. |
| `bbox_x`, `bbox_y`, `bbox_w`, `bbox_h` | Required finite pixel coordinates; width and height are positive and bounded by the decoded image. |
| `landmarks_json` | Required pipeline-native finite landmark coordinates; its shape is validated by the owning engine adapter. |
| `detection_confidence` | Required finite engine-native confidence. |
| `quality_score`, `blur_score`, `brightness_score` | Nullable finite diagnostic/quality values when the engine produces them. |
| `pose_yaw`, `pose_pitch`, `pose_roll` | Nullable finite degrees when the engine produces them. |
| `embedding` | Required normalized pgvector value without ANN index; dimension MUST equal the referenced revision. |
| `created_at` | Server timestamp of terminal publication. |

Different revisions produce independent rows even when they detect the same
physical person. No person identity, cross-revision link, shared crop or
clustering row is introduced.

### `face_moment.processing_runtime_status`

One well-known singleton row supplies only the durable operational facts that
cannot be reconstructed after a process restart:

| Field | Contract |
|---|---|
| `worker_started_at` | Nullable until first successful worker startup; then the latest startup timestamp. |
| `last_recovery_at` | Nullable until first startup recovery; then the latest recovery timestamp. |
| `last_recovered_count` | Number of `processing` rows returned to `pending` in that recovery transaction. |
| `current_operation` | Exactly `idle`, `photo_processing`, `calibration`, `hard_purge` or `retention_cleanup`. |
| `operation_started_at` | Nullable; set only while the named operation is active. |

The row is not a jobs table, scheduler or operation history. It grants no
claim, priority, preemption or retry authority. Later owners publish their
accepted operation state through their own records and use this narrow worker
projection only to serialize access to the one configured worker.

## Claiming, Processing And Publication

Worker startup performs one transaction that returns every unfinished
`processing` row to `pending`, updates its state timestamp, and records the
recovery count/time while setting `current_operation=idle` and clearing
`operation_started_at`. It then processes one operation at a time.

For Photo work:

1. Atomically select the oldest eligible serving `pending` row, transition it
   to `processing`, increment `attempt_count`, and set current operation to
   `photo_processing`. With one configured worker, no lease, claim token,
   fencing, `SKIP LOCKED` or extra jobs table is used.
2. Outside the claim transaction, load the immutable private original and the
   referenced validated engine, then run only that engine's native Photo path.
3. When faces exist, create the low-quality preview and thumbnail and write
   them to deterministic private keys derived from
   `(photo_id, pipeline_revision_id, artifact_kind)`. Encoding bounds and
   quality are positive deployment configuration with deterministic test
   values; originals are not rewritten and no watermark is added.
4. In one terminal PostgreSQL transaction, replace the complete face set and
   publish `ready` plus derivative keys and `searchable_at`, or publish
   `no_faces` with no faces/derivative keys. A terminal repeat is a no-op.
5. On an execution error before the retry limit, return the row to `pending`
   with a bounded safe `last_error`; on the third failed claim publish
   `failed`. Clear the worker operation after the outcome transaction.

The full face-set replacement and deterministic derivative keys make the path
idempotent. A crash after derivative upload but before terminal commit may
leave private replaceable objects; restart begins from the original and
converges without duplicate face rows or distributed transaction machinery.

## Searchable Truth And SLO Projection

For one Photo, `searchable=true` only when all of the following are current:

- the Photo remains active;
- its state is `ready` with both private derivative keys and at least one valid
  face row;
- the state revision equals the СПА's selected serving revision.

Other revisions and every `pending|processing|no_faces|failed` state are not
searchable. `processing` publishes the owned state/timestamp/face projection;
`inventory` combines it with Photo visibility and serving selection for staff
reads. Neither consumer writes processing-owned rows.

The `ingest_to_searchable` calculation uses every independently accepted Photo
in the requested controlled interval for its admission-time serving revision:

- success: `searchable_at - photo.accepted_at < 15 minutes` and the complete
  compatible `ready` publication exists;
- breach: terminal non-searchable, still non-searchable at age 15 minutes, or
  `ready` at 15 minutes or later;
- open: not yet searchable and younger than 15 minutes at evaluation time.

Rejects and duplicates have no Photo and are absent. Non-serving states are
absent. The projection reports population, success, breach and open counts plus
`success / population`; it reports the 95% verdict only when `open = 0`.
Developer-triggered Calibration may delay the queue, but its population and
effect stay in these same counts; no exclusion or scheduling exception is
created.

## Errors, Capacity And Invariants

- A missing original, incompatible/unvalidated revision, engine failure,
  invalid face value or derivative failure follows the bounded retry path and
  can become terminal `failed`; it MUST NOT publish partial `ready` state.
- PostgreSQL and MinIO free capacity are observed independently through
  configured infrastructure probes. Each probe reports `ok`, `low` or
  `unavailable`, available bytes, its configured positive low threshold and
  observation time. Tests bind explicit thresholds; this contract invents no
  product capacity target.
- The simplest deployment probe uses configured read-only filesystem views of
  the two primary volumes and `statvfs`-equivalent values. It MUST NOT expose
  data files, credentials, object keys or add a monitoring service.
- Only the single background-worker entrypoint performs claims. Backend/API
  code may read projections but MUST NOT run inference or publish transitions.
- Photo deletion never cascades across ownership; `inventory` later commands
  idempotent processing cleanup before deleting its own rows/media.

## Migration And Verification Targets

- One revision extends the current linear head; isolated verification covers
  direct `down_revision`, upgrade, downgrade, re-upgrade, constraints and data
  preservation without requiring a mutable future exact head.
- Engine-adapter proof shows SFace and Buffalo M take their own configured
  native preprocessing/alignment paths and reject revision/dimension mismatch.
- Lifecycle proof drives `ready`, `no_faces`, transient retry and exhausted
  `failed`, and proves only complete compatible `ready` is searchable.
- An injected crash after derivative publication and before terminal commit,
  repeated processing, and worker restart prove one face set, deterministic
  derivatives, preserved population and restart-from-beginning convergence.
- Controlled-clock SLO proof reconciles every accepted Photo into exactly one
  success, breach or open classification and includes delayed Calibration
  backlog without special exclusion.
- Capacity probes independently demonstrate normal, configured-low and
  unavailable PostgreSQL/MinIO observations in disposable state without
  disclosing storage contents.
