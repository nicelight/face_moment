---
description: Canonical Photo admission data, storage, transaction and recovery specification.
status: active
last_updated: 2026-08-14
source_of_truth:
  - .memory-bank/domains/photo-admission.md
---
# Photo Admission

## Scope And Ownership

This specification owns the internal data and persistence contract for one
independently admitted commercial JPEG. `inventory` owns the Photo identity,
original-object reference and admission outcome. `serving_control` supplies an
immutable `IngestTarget`; `processing` owns creation of the initial serving-
revision `pending` state. HTTP handlers, shared helpers and the composition root
MUST NOT own or directly reproduce this orchestration.

The [Photo Admission API](../contracts/photo-admission-api.md) owns the external
staff-browser contract. Later processing, search and inventory-management
features may extend their own states and reads without changing the admission
transaction defined here.

## Runtime Persistence Shape

All rows use the existing `face_moment` PostgreSQL schema, shared SQLAlchemy
`Base/MetaData` and single linear Alembic stream. Models and repositories remain
under their capability owners.

### Required target records

The serving target used by admission resolves:

| Value | Owner and rule |
|---|---|
| `spa_id` | `serving_control`; UUID of one active configured СПА. |
| `timezone` | `serving_control`; valid IANA timezone used for EXIF interpretation. |
| `visit_date` | Selected by the photographer for this upload and validated by `serving_control`; it is not silently replaced by EXIF, filename, browser time or upload time. |
| `pipeline_revision_id` | `serving_control` points to one immutable revision owned by `processing`; admission does not validate, switch or implement that revision. |

The implementation MUST provide an owner-backed configuration/test path for one
active СПА and one serving revision. It MUST NOT seed production identities in
the migration, add a generic settings framework or implement the later manual
revision-switch lifecycle.

The minimum persisted target uses:

### `face_moment.pipeline_revisions`

The `processing` repository owns immutable `id` (UUID), `pipeline_code`
(`opencv_sface` or `insightface_buffalo_m`), `created_at` and non-null
`validated_at` for a revision eligible to be selected as serving. FT-001 stores
identity and the already-established eligibility fact only; model artifact,
dimension, inference and revalidation behavior belong to FT-002 and later
serving-control work.

### `face_moment.spas`

The `serving_control` repository owns UUID `id`, required display `name`, valid
IANA `timezone`, required `active` and required
`serving_pipeline_revision_id`. The revision reference uses deliberate
`RESTRICT`/no-cascade behavior. Only an active СПА pointing to an eligible
revision can produce an `IngestTarget`; invalid, inactive or unknown targets
are rejected before object/database admission.

The initial owner-backed configuration path may create these two records for
the pilot and isolated tests. It is not an operator UI, automatic pipeline
switch or production seed.

### `face_moment.photos`

The `inventory` repository owns:

| Field | Contract |
|---|---|
| `id` | Server-generated UUID primary key. |
| `spa_id` | Required UUID from the immutable `IngestTarget`. |
| `visit_date` | Required authoritative calendar date selected for the upload. |
| `captured_at` | Required timezone-aware effective capture time. |
| `captured_at_source` | `exif` or `upload_started_at`; `visit_date_fallback` is allowed only when neither earlier source is available. |
| `accepted_at` | Required server timestamp assigned inside the successful admission transaction. |
| `admission_pipeline_revision_id` | Required immutable UUID copied from the same `IngestTarget.pipeline_revision_id` that creates the initial pending row. It is the admission-time pipeline-state identity; a later serving switch or additional state row MUST NOT rewrite it. |
| `uploader_id` | Required active staff-user UUID supplied by the authenticated principal. |
| `checksum_sha256` | Required 32-byte SHA-256 digest of the exact uploaded JPEG bytes. |
| `original_object_key` | Required unique opaque key in the configured private MinIO bucket. |
| `original_byte_size` | Required positive compressed-byte count. |
| `width`, `height` | Required positive decoded dimensions after JPEG validation. |
| `is_active` | Required `true` at admission; later visibility transitions belong to FT-012. |

PostgreSQL MUST enforce uniqueness on
`(spa_id, visit_date, checksum_sha256)`. The table MUST NOT contain Batch,
manifest, confirmation or per-photo purge fields.

`uploader_id` is an immutable audit/ownership reference across the
`platform/auth -> inventory` boundary. The application validates the active
principal before admission; a cross-capability database foreign key is not
required, and staff reset/deactivation MUST NOT delete or rewrite Photos.

### `face_moment.photo_pipeline_states`

The `processing` repository owns the row keyed by
`(photo_id, pipeline_revision_id)`. Admission creates exactly one row for the
serving revision with `status = pending`, `attempt_count = 0` and a server-side
state timestamp. Its key MUST equal the accepted Photo's immutable
`admission_pipeline_revision_id`; this is the only state eligible for that
Photo's admission-time SLO classification. FT-001 MUST NOT implement claiming,
inference, terminal-state publication or retry behavior beyond making the
durable initial row available to FT-002.

The Photo relation may cascade only into inventory-owned data. A Photo delete
MUST NOT use database cascade across the `inventory -> processing` ownership
boundary; later physical cleanup calls the processing boundary explicitly.

## JPEG And Time Contract

- Each request supplies exactly one candidate JPEG. SHA-256 is calculated over
  the exact accepted byte stream before any decode normalization.
- The deployment supplies positive limits for compressed bytes, decoded side
  length and decoded pixels. Tests bind explicit deterministic values. A limit
  breach or an unsupported/undecodable JPEG creates no Photo or pipeline state.
- A reliable EXIF capture timestamp is a parseable `DateTimeOriginal` (or
  `DateTimeDigitized` when the former is absent) with a valid explicit offset,
  or a value interpreted in the configured СПА IANA timezone. Invalid,
  impossible or missing values are unreliable.
- Effective `captured_at` uses reliable EXIF, otherwise the server-recorded
  upload-start instant, otherwise 01:00 in the СПА timezone on authoritative
  `visit_date`. A reliable EXIF calendar date different from `visit_date`
  yields the API warning but never rewrites or rejects the selected scope.
- EXIF orientation is validated for safe decoding; original stored bytes are
  not rewritten by admission.

## Admission And Convergence

### Private Candidate Staging And Request-Owned Cleanup

`inventory` obtains the immutable `IngestTarget` and authenticated
`uploader_id`, then writes the candidate once under a unique opaque key in the
configured private MinIO bucket. The browser never receives that key or direct
MinIO access. Handled rejection before commit SHOULD delete only its
request-owned candidate; repeated cleanup is safe.

### Atomic Photo And Pending Transaction

After configured byte/decode, JPEG and EXIF validation produces the digest and
effective capture time, one short PostgreSQL transaction attempts the unique
Photo insert and calls the typed `processing` application boundary to add its
initial `pending` row using the same transaction and the same immutable
`IngestTarget.pipeline_revision_id`. Commit publishes the Photo's
`accepted_at`/`admission_pipeline_revision_id` pair and its matching pending
row; rollback publishes neither. A later serving-revision change may create a
different state for other work, but it cannot alter the recorded admission
identity or select a substitute state for this Photo.

### Admission-time Serving-Revision Lineage

`Photo.admission_pipeline_revision_id` is the one non-null immutable admission
snapshot and `photo_pipeline_states(photo_id, pipeline_revision_id)` with that
same revision is its one required initial state. The application writes both
from one `IngestTarget` in the atomic admission transaction; no later command
may change the Photo field. The SLO projection consumes this persisted pair,
not current serving selection or an inferred state order. An additive lineage
migration may begin only with an empty `photos` table because existing rows
lack an authoritative backfill source; it aborts unchanged otherwise.

### Duplicate Arbitration And Candidate Cleanup

A committed unique Photo returns `accepted`. PostgreSQL uniqueness arbitrates
concurrent same-scope candidates. A conflict returns `duplicate`, creates no
new Photo or pipeline state and deletes only the losing request's candidate
object.

### Pre-Commit Crash Recovery

A process crash after object upload but before commit may leave one
inaccessible orphan and no database admission; ordinary re-upload is the
accepted recovery. No outbox, distributed transaction, object move/copy or
orphan lifecycle is introduced. An accepted Photo keeps its original opaque
key.

## Errors And Invariants

- A rejected or duplicate candidate MUST NOT create a Photo, processing state,
  searchable result, teaser candidate or contribution to `N`.
- Success is atomic at the PostgreSQL boundary: observers see both Photo and
  serving `pending` with the same admission revision, or neither.
- Concurrent same-scope uploads are arbitrated only by the database uniqueness
  constraint; exactly one may be accepted.
- Retrying candidate deletion and handled rollback cleanup is safe and affects
  only the request-owned opaque key.
- Admission MUST NOT write `serving_control` configuration or later
  `processing` transitions directly.
- The admission-time pipeline revision is a persisted Photo fact, not an
  inference from current serving selection, state order, transition time,
  terminal status, attempt count or revision creation time.
- Before the public auth task exists, isolated core tests may supply a synthetic
  non-secret uploader UUID directly to the inventory application boundary; no
  unauthenticated HTTP path is created by that test seam.

## Migration And Verification Targets

- The feature revision uses the current linear Alembic head as its direct
  `down_revision`; verification checks ancestry, upgrade, downgrade and
  re-upgrade without making a mutable future head an FT-001 requirement.
- Repository/integration proof covers exact uniqueness, concurrent duplicate
  arbitration, candidate deletion, authoritative date, EXIF mismatch warning
  data, and one accepted Photo plus one `pending` row.
- An injected exception immediately before commit proves complete rollback;
  a separate crash-window fixture leaves at most a private orphan, no database
  rows, and permits successful re-upload.
- PostgreSQL and MinIO probes run in isolated disposable state, are safe to
  rerun and record owned cleanup.
- The lineage migration is a pre-production greenfield cutover. Because an
  existing Photo and one or more state rows do not truthfully reveal which
  state was admitted, it MUST abort before any schema or data mutation unless
  `face_moment.photos` is empty. It MUST NOT backfill, delete or repoint an
  existing Photo/state relation; an explicit pre-pilot reset is outside the
  migration. Empty-table upgrade/downgrade/re-upgrade proves the non-null
  `admission_pipeline_revision_id` shape, its `RESTRICT` reference and one
  atomic admission pair.
