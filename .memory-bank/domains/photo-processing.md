---
description: Canonical compatible Photo-processing data, worker, derivative and recovery specification.
status: active
last_updated: 2026-08-14
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

### Compatibility identity

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

The FT-002 compatibility migration is a pre-production greenfield cutover. The
legacy four-field row contains no authoritative source for the new model,
weights or preparation identity, so the migration MUST verify that
`face_moment.pipeline_revisions` is empty before its first schema mutation and
MUST abort without changing schema or data when any row exists, referenced or
not. It MUST NOT fabricate compatibility values, delete or repoint references,
or infer a weights hash from `pipeline_code`. After a successful empty-table
upgrade, the owner-backed configuration path publishes fresh revisions with
the exact configured model-asset identity. Resetting disposable pre-pilot
state, when needed, is an explicit operator action outside the migration.

### Owner-local engine boundary

The owner-local `FaceEngine` boundary extends the existing Foundation seam with
its revision identity, embedding dimension and one `process_photo` operation
returning pipeline-native face results. The two direct implementations remain
reusable by later realtime query processing through this existing boundary;
the pilot adds no engine registry, plugin loader, adapter factory or second
engine abstraction.

### OpenCV SFace Photo adapter

The `opencv_sface` implementation MUST use YuNet detection followed by
`FaceRecognizerSF.alignCrop` and SFace recognition. Its bbox, landmarks, crop,
alignment and embedding dimension remain native to this implementation and
MUST NOT consume a Buffalo M result.

The direct processing-owned implementation is
`src/face_moment/processing/sface_adapter.py`; it is exposed through the
existing `FaceEngine` seam without a shared adapter registry or result format.

### InsightFace Buffalo M Photo adapter

The `insightface_buffalo_m` implementation MUST use its configured SCRFD,
landmarks, native alignment and Buffalo M `normed_embedding` path. Its bbox,
landmarks, crop, alignment and embedding dimension remain native to this
implementation and MUST NOT consume an OpenCV SFace result.

The direct processing-owned implementation is
`src/face_moment/processing/buffalo_adapter.py`; it is exposed through the
existing `FaceEngine` seam without a shared adapter registry or result format.

### Model-asset admission

Each direct adapter verifies the configured model assets and embedding
dimension against the immutable revision before accepting work. The worker
MUST NOT download, silently replace or auto-select models.

The pilot supplies model files from one operator-managed host directory mounted
read-only into each model-consuming process. Model files are not embedded in
the application image or stored in PostgreSQL. Deployment settings provide the
absolute in-container detector and recognizer paths; exact setting names and
path layout remain composition-root details.

At process startup, the composition root resolves the one active СПА's selected
validated revision from PostgreSQL, instantiates only that revision's direct
adapter and verifies the configured detector/recognizer identity, preparation
versions, embedding dimension and computed `weights_sha256` against the
persisted compatibility identity. Missing files, an absent or ineligible
selection, or any identity/hash mismatch keeps the process unavailable before
it claims or mutates processing work. It does not fall back to the other
pipeline.

A serving-revision change uses the accepted maintenance downtime: the operator
updates the read-only assets/settings as needed and restarts the model-consuming
processes. Startup then binds them to the committed revision. The pilot adds no
model registry, adapter factory, download/cache path, hot switch or simultaneous
preload of both pipelines.

## Persisted Processing Shape

All rows use the shared `face_moment` PostgreSQL schema, one SQLAlchemy
`Base/MetaData` and the single linear Alembic stream. Models and repositories
remain under `processing`.

### `face_moment.photo_pipeline_states`

The existing composite key remains `(photo_id, pipeline_revision_id)`. The
state whose revision equals the immutable
`Photo.admission_pipeline_revision_id` is the one and only admission-time
state for that Photo. Later state rows for other revisions remain independent
processing records; they never replace or multiply that lineage fact.

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

### Startup recovery

Worker startup performs one transaction that returns every unfinished
`processing` row to `pending`, updates its state timestamp, and records the
recovery count/time while setting `current_operation=idle` and clearing
`operation_started_at`.

### Atomic claim and bounded failure

Atomically select the oldest eligible serving `pending` row, transition it to
`processing`, increment `attempt_count`, and set current operation to
`photo_processing`. On an execution error before the retry limit, return the
row to `pending` with a bounded safe `last_error`; on the third failed claim
publish `failed`. The outcome transaction clears the worker operation. With one
configured worker, no lease, claim token, fencing, `SKIP LOCKED`, scheduler or
extra jobs table is used.

### Single-Photo orchestration

After a claim commits, load the immutable private original and referenced
validated adapter outside the claim transaction, run only that adapter's native
Photo path, pass any faces through deterministic derivative creation, and call
the owner-local terminal publication boundary. This orchestration owns no
second lifecycle, retry policy, model-selection policy or cross-store commit.

### Deterministic private derivatives

When faces exist, create the low-quality preview and thumbnail and write them
to deterministic private keys derived from
`(photo_id, pipeline_revision_id, artifact_kind)`. Encoding bounds and quality
are positive deployment configuration with deterministic test values;
originals are not rewritten, no watermark is added and MinIO remains private.

### Idempotent terminal publication

In one terminal PostgreSQL transaction, replace the complete face set and
publish `ready` plus derivative keys and `searchable_at`, or publish `no_faces`
with no faces/derivative keys. A terminal repeat is a no-op.

The full face-set replacement and deterministic derivative keys make the path
idempotent. A crash after derivative upload but before terminal commit may
leave private replaceable objects; restart begins from the original and
converges without duplicate face rows or distributed transaction machinery.

### Sequential worker runtime

After successful selected-revision model admission and adapter warmup, startup
recovery runs and the one configured `BackgroundPhotoWorker` processes one
operation at a time through the owner-local boundaries above. A selected
revision change stops further claims until the process is restarted and bound
to the new committed revision. Backend/API code never runs the loop. The
process adds no broker, priority/preemption scheduler, overlapping worker,
durable job row, model-selection policy or generic operation framework.

### Ordinary serving-revision guard

For a manual switch of one СПА from its exact current revision A to target B,
`processing` owns one read-only guard projection. Given the stable serving
context and A, it examines only Photos in that СПА whose immutable
`admission_pipeline_revision_id` is A and their exact `(photo_id, A)` state.
It blocks while any such state is `pending` or `processing`; `ready`,
`no_faces` and `failed` are terminal and do not block. The projection does not
claim work, create a B state, mutate an A state, select B or change any model
asset.

`serving_control` is the only caller that may turn this result into a revision
decision. The serving-selection update and admission's serving-context read
must serialize, so an admission commits fully under A before the guard or
obtains B only after B commits. A rejected guard preserves A and all Photo
state. Calibration/model comparison remains offline test-only and neither calls
nor bypasses this projection.

## Searchable Truth And SLO Projection

### Compatible searchable truth

For one Photo, `searchable=true` only when all of the following are current:

- the Photo remains active;
- its state is `ready` with both private derivative keys and at least one valid
  face row;
- the state revision equals the СПА's selected serving revision.

Other revisions and every `pending|processing|no_faces|failed` state are not
searchable. `processing` publishes the owned state/timestamp/face projection;
`inventory` combines it with Photo visibility and serving selection for staff
reads. Neither consumer writes processing-owned rows.

For the per-Photo staff status endpoint, `inventory` supplies the Photo's
immutable `admission_pipeline_revision_id` and `processing` returns only that
exact composite-key state. The response evaluates current-serving
compatibility for that selected admission state; it does not select a later
state from current serving, ordering, timestamps, status or attempt count.
Consequently an A-admitted Photo remains an A status response after serving
changes to B, and any additional B state cannot replace it or make the read
non-scalar.

### Controlled-interval ingest-to-searchable projection

The `ingest_to_searchable` calculation uses every independently accepted Photo
whose `accepted_at` is in the half-open controlled interval
`[accepted_from, accepted_before)`. It joins each Photo only to the state whose
`pipeline_revision_id` exactly equals its immutable
`admission_pipeline_revision_id`:

- success: `searchable_at - photo.accepted_at < 15 minutes` and the complete
  compatible `ready` publication exists;
- breach: terminal non-searchable, still non-searchable at age 15 minutes, or
  `ready` at 15 minutes or later;
- open: not yet searchable and younger than 15 minutes at evaluation time.

Rejects and duplicates have no Photo and are absent. A later state for a
different revision, whether current serving or not, is absent from this
projection, not a second population row. The projection MUST NOT use current
serving selection,
state/revision ordering, transition timestamps, terminal status or attempt
count to choose an admission state. It reports population, success, breach and
open counts plus `success / population`; it reports the 95% verdict only when
`open = 0`.
For an empty interval population all four counts are zero and both
`success_ratio` and `meets_95_percent` are `null`: an empty population is
neither a zero-percent result nor evidence that the target passed.
Developer-triggered Calibration may delay the queue, but its population and
effect stay in these same counts; no exclusion or scheduling exception is
created.

### Shared-worker Calibration delay

A controlled Calibration operation may occupy the same sequential worker and
must remain visible through `current_operation=calibration`. Photo work waits
without preemption, its pending/SLO effect remains ordinary, and processing
resumes when the operation releases the worker. FT-002 implements only this
narrow serialization/projection boundary, not Calibration calculation, run
storage or a generic scheduler.

## Processing Health Projections

### Queue and recovery health projection

For the selected СПА and serving revision, `processing` publishes current
`pending|processing|ready|no_faces|failed` counts, nullable oldest-pending
acceptance time, current operation/start time and the singleton worker/recovery
facts. The projection is a direct PostgreSQL read over owned state; it adds no
history, materialized counter or monitoring store.

### PostgreSQL capacity observation

The PostgreSQL primary-volume probe independently reports `ok`, `low` or
`unavailable`, nullable non-negative available bytes, its configured positive
low threshold and observation time. The simplest deployment mechanism is one
configured read-only filesystem view and a `statvfs`-equivalent read; no data
file content or path is returned. Its infrastructure adapter is
`src/face_moment/infrastructure/capacity.py`; Compose mounts the configured
view only for `backend`.

### MinIO capacity observation

The MinIO primary-volume probe independently reports `ok`, `low` or
`unavailable`, nullable non-negative available bytes, its configured positive
low threshold and observation time. It uses its own configured read-only
filesystem view and the same minimal observation mechanism without coupling
its result to PostgreSQL.

## Errors And Invariants

- A missing original, incompatible/unvalidated revision, engine failure,
  invalid face value or derivative failure follows the bounded retry path and
  can become terminal `failed`; it MUST NOT publish partial `ready` state.
- Tests bind explicit capacity thresholds; this contract invents no product
  capacity target. Neither probe exposes data files, credentials, object keys
  or adds a monitoring service.
- Only the single background-worker entrypoint performs claims. Backend/API
  code may read projections but MUST NOT run inference or publish transitions.
- Photo deletion never cascades across ownership; `inventory` later commands
  idempotent processing cleanup before deleting its own rows/media.

## Migration And Verification Targets

- One revision extends the current linear head; isolated verification covers
  direct `down_revision`, empty-table upgrade, downgrade, re-upgrade,
  constraints and preservation of unrelated prerequisite rows without
  requiring a mutable future exact head. A separate non-empty fixture proves
  the upgrade aborts before schema or data changes.
- Engine-adapter proof shows SFace and Buffalo M take their own configured
  native preprocessing/alignment paths and reject revision/dimension mismatch.
- Lifecycle proof drives `ready`, `no_faces`, transient retry and exhausted
  `failed`, and proves only complete compatible `ready` is searchable.
- Serving-switch proof asks the owner-backed A guard before B commits, covers
  the two blocking and three terminal A states, preserves A on rejection and
  serializes an overlapping admission without direct `serving_control` access
  to processing rows.
- Per-Photo API proof selects the immutable admission state explicitly and
  covers an A-admitted Photo after serving changes to B with an additional B
  state; the response remains scalar A with current compatibility false.
- An injected crash after derivative publication and before terminal commit,
  repeated processing, and worker restart prove one face set, deterministic
  derivatives, preserved population and restart-from-beginning convergence.
- Controlled-clock SLO proof reconciles every accepted Photo into exactly one
  success, breach or open classification, covers both half-open interval
  boundaries and the all-zero/null empty result, and includes delayed
  Calibration backlog without special exclusion. It proves an A-admitted Photo
  remains represented by its persisted A state after serving switches to B,
  and that adding a B state leaves the A Photo classified exactly once.
- Capacity probes independently demonstrate normal, configured-low and
  unavailable PostgreSQL/MinIO observations in disposable state without
  disclosing storage contents.
