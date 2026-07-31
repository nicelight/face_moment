---
description: Canonical greenfield system shape, capability ownership and Architecture Spine for the Face Moment pilot.
status: active
last_updated: 2026-07-31
source_of_truth:
  - .memory-bank/architecture/system-architecture.md
---
# System Architecture

## Status And Source Boundary

- The verified Foundation supplies the executable substrate only; product
  behavior remains target design rather than implemented behavior.
- This document, the [boundary map](../contracts/boundary-map.md),
  [lifecycle map](../states/lifecycle-map.md) and
  [Foundation decision](../foundation.md) are the canonical accepted
  architecture bundle. [.memory-bank/prd.md](../prd.md) owns product behavior
  and acceptance.

## System Goal

Deliver the one-СПА pilot as one greenfield modular-monolith release with
predictable process-restart recovery, searchable per-photo inventory,
low-latency Promo/QR continuation and data-class-aware diagnostics, without
speculative distributed infrastructure.

## Main Constraints

- One central CPU-only server, one display client and one configured replica of
  each long-running server role.
- Ordinary process crashes recover automatically. Chromium/display restarts
  automatically and reloads once the central HTTPS origin is reachable; no
  cold-start advertising guarantee applies while that origin is unavailable.
  Background work restarts safely from durable state. Maintenance downtime and
  manual restart for a rare native hang are accepted.
- Five capability packages for the current pilot:
  `serving_control`, `inventory`, `processing`, `promo`, `diagnostics`.
- PostgreSQL/pgvector owns durable state and exact vector search; private MinIO
  owns binary bytes. No shared cross-store transaction is assumed.
- All capability tables use one PostgreSQL schema, one SQLAlchemy
  `Base/MetaData`, one Alembic configuration and one sequential migration
  stream; slice write ownership remains semantic, not schema-based.
- Public browser traffic crosses the HTTPS application boundary. PostgreSQL,
  MinIO and internal process ports stay private.
- `SpaPromoClient` is browser-native Chromium loaded from the central HTTPS
  origin. It owns local capture/proposal preparation and crosses the ESP32 and
  realtime boundaries defined in the
  [boundary map](../contracts/boundary-map.md); server-side selection and search
  ownership remain unchanged.
- Technical HTTP failures use standard statuses; admitted capture/search
  requests use typed domain outcomes rather than a custom error framework.
- No Batch, broker, ANN, multi-worker coordination, backup guarantee,
  per-photo purge state, purge jobs table or realtime statistics transport.

## Architecture Spine

### Architecture Decisions

#### AD-001 — One release with five capability slices
- Binds: all pilot features and runtime entrypoints.
- Prevents: microservices, technical-layer slices and a speculative sixth
  commerce slice.
- Rule: one repository and Python/FastAPI modular monolith supply five
  capability packages; `backend`, one `BackgroundPhotoWorker` and one
  `RealtimeFaceService` are process entrypoints over the same release. The
  composition root owns only settings, adapters, wiring, lifecycle, start and
  shutdown.
- Verification: Verified Foundation proof: all three entrypoints start against
  fake adapters from one release.
- Source: accepted operator architecture decision, recorded in this
  Architecture Spine.

#### AD-002 — One write owner per mutable invariant
- Binds: shared PostgreSQL access and every cross-slice use case.
- Prevents: foreign direct writes, duplicated business rules, generic
  Unit-of-Work/event-bus/outbox machinery and orchestration in HTTP/UI handlers.
- Rule: a slice may read a published projection, but commands and transitions
  use direct typed Python calls through the owning slice's application
  boundary. Cross-slice orchestration lives in the capability that owns the
  user-visible outcome.
- Verification: Feature-level integration proof: each cross-slice flow changes
  state only through the named owner.
- Source: accepted operator architecture decision and the
  [boundary map](../contracts/boundary-map.md).

#### AD-003 — Independent per-photo durable admission
- Binds: ingest, duplicate arbitration and searchable readiness.
- Prevents: Batch/manifest/confirmation, aggregate upload commits and
  distributed PostgreSQL/MinIO transactions.
- Rule: one unique JPEG produces one short PostgreSQL transaction containing
  `Photo + accepted_at + serving pending`; uniqueness is
  `(spa_id, visit_date, checksum_sha256)`. MinIO remains outside the transaction.
- Verification: FT-001/FT-002 proof: concurrent duplicates yield one Photo and
  accepted work survives restart.
- Source: [.memory-bank/prd.md](../prd.md) `FR-ING-01..08` and the
  [lifecycle map](../states/lifecycle-map.md).

#### AD-004 — Singleton background execution with restart from the beginning
- Binds: Photo processing, Calibration and global hard purge.
- Prevents: broker, leases, fencing, preemption, priority scheduling and
  additional worker replicas.
- Rule: `photo_pipeline_states` is the durable Photo-processing queue for one
  sequential worker; stale `processing` returns to `pending` on startup.
  Calibration may block processing. A confirmed hard purge waits for the
  current operation and then reuses the same worker.
- Verification: FT-002/FT-011/FT-012 restart proof.
- Source: [.memory-bank/prd.md](../prd.md) `NFR-REL-04`, `FR-DEV-11`,
  `FR-INV-07..09` and the [lifecycle map](../states/lifecycle-map.md).

#### AD-005 — Inventory owns visibility, statistics and permanent removal
- Binds: FT-012 and every consumer of Photo/media.
- Prevents: a deletion service, per-photo `purge_pending`, purge jobs, counter
  materialization and WebSocket/SSE statistics.
- Rule: one Photo visibility marker controls search/media/statistics. One
  durable global run fixes the project-wide hard-purge snapshot and progress,
  rejects restore of snapshot members until completion, resumes after restart
  and removes Photo-owned data while preserving already issued Promo sessions,
  core Attempts and diagnostic evidence. Soft delete blocks new result
  formation but not an already issued session; hard-purged media is skipped by
  clients without rebuilding the session or `N`. Per-СПА 1/5/60-minute counters
  are direct PostgreSQL queries polled every five seconds.
- Verification: FT-012 proof: authorization, hide/restore, exact counters and
  restartable fixed-snapshot purge.
- Source: [.memory-bank/prd.md](../prd.md) `FR-INV-01..11` and the
  [boundary map](../contracts/boundary-map.md).

#### AD-006 — Bounded realtime request and explicit display success
- Binds: automatic capture, search, Promo and performance acceptance.
- Prevents: client takeover of server-side selection/search, unbounded
  proposal submission, a realtime waiter queue, durable replay and treating a
  server response as visible Promo success.
- Rule: one client-generated `attempt_id`, one bounded proposal request, one
  inference slot and one server deadline govern the synchronous attempt.
  `promo` owns admission and orchestration; `processing` owns inference,
  selection and search. Request structure and transport rejection semantics
  are owned by the [boundary map](../contracts/boundary-map.md). Only an
  idempotent client acknowledgement after four teasers and QR are visible sets
  display success; the [lifecycle map](../states/lifecycle-map.md) owns its
  terminal states.
- Verification: FT-003..FT-005 boundary, orchestration and post-render
  acknowledgement proof plus the controlled 20-attempt outcome.
- Source: [.memory-bank/prd.md](../prd.md) `FR-CAP-01..17`,
  `FR-UX-01..09`, the [boundary map](../contracts/boundary-map.md) and the
  [lifecycle map](../states/lifecycle-map.md).

#### AD-007 — Core Attempt survives best-effort evidence
- Binds: Promo, diagnostics, retention and hard purge.
- Prevents: diagnostic evidence blocking participant flow, an empty anchor,
  mandatory reference-frame upload or local-detector miss proof, a server-side
  reliable-delivery outbox or hard-purge cascade into sessions/Attempts/
  evidence.
- Rule: `promo` persists a core Attempt before inference for every
  server-admitted request; `diagnostics` attaches detailed evidence
  best-effort and exposes missing finalization as `incomplete`. Client-only
  offline triggers are best-effort and may have no durable Attempt.
  Capture-derived media is not developer-only merely because it is an image,
  and no logging, cache, storage or public-delivery mechanism is required.
  Photo hard purge retains existing Promo result/session data, the core Attempt
  and diagnostic evidence; clients skip unavailable media.
- Verification: FT-007/FT-012 integration proof.
- Source: [.memory-bank/prd.md](../prd.md) `FR-DIAG-01..05`,
  `NFR-DATA-01..04` and the [lifecycle map](../states/lifecycle-map.md).

#### AD-008 — Session-wide QR continuation
- Binds: Promo session authorization and participant media delivery.
- Prevents: per-device grant rows and public MinIO/presigned participant URLs in
  the pilot.
- Rule: one Promo session has a 30-minute first-open window and one shared
  60-minute idle access state; commercial Photo media and personalized session
  data are served through authorized no-store backend reads.
- Verification: FT-006 multi-phone expiry proof.
- Source: [.memory-bank/prd.md](../prd.md) `FR-UX-03..10` and the
  [boundary map](../contracts/boundary-map.md).

#### AD-009 — Standard HTTP failures and typed domain outcomes
- Binds: every public/staff HTTPS endpoint and the SpaPromoClient realtime
  contract.
- Prevents: a project-specific error envelope/framework, business outcomes
  disguised as transport errors and client decisions based on response prose.
- Rule: authentication, permission, payload, validation, rate-limit and
  internal/upstream failures use the standard `401`, `403`, `413`, `422`,
  `429` and `5xx` classes. Closed serving maintenance/readiness returns `503`
  before capture/search admission and creates no core Attempt. An admitted
  request returns `2xx` with a compact typed outcome such as `busy`, `deadline`,
  `unacceptable_query` or `insufficient_results`; clients branch on
  status/outcome, never `5xx` text.
- Verification: Boundary contract proof: representative transport failures map
  to the standard status and admitted non-success search results remain typed
  domain outcomes.
- Source: accepted contract recorded in the
  [boundary map](../contracts/boundary-map.md).

#### AD-010 — One PostgreSQL schema and migration stream
- Binds: every capability table, repository, shared transaction and Foundation
  storage baseline.
- Prevents: per-slice PostgreSQL schemas/users/ACLs, independent migration
  pipelines, foreign direct writes and ownership-crossing delete cascades.
- Rule: one application schema uses one SQLAlchemy `Base/MetaData`, one Alembic
  configuration and one sequential migration stream. Models/repositories stay
  in owning slices; foreign keys and `ON DELETE` rules are explicit, and
  database cascade never crosses ownership boundaries or deletes core Attempts
  or diagnostic evidence with a Photo.
- Verification: Foundation/feature proof: the single migration stream builds
  an empty database and deletion tests preserve foreign-owned Attempt/evidence
  state.
- Source: accepted contract recorded in the
  [boundary map](../contracts/boundary-map.md).

#### AD-011 — Idempotent PostgreSQL/MinIO convergence
- Binds: Photo admission, derived media publication, hard purge and retention
  cleanup.
- Prevents: a distributed transaction emulator, public object-store access,
  hidden retained versions and per-object recovery lifecycles.
- Rule: committed PostgreSQL state decides whether a private MinIO object is
  usable. MinIO remains private for every stored object, including ordinary
  capture-derived media; data classification changes application authorization,
  not the storage boundary. Admission uses a unique opaque object key and
  database uniqueness; a pre-commit crash may leave a private orphan. Derived
  keys are deterministic by Photo, pipeline revision and artifact kind. Cleanup
  first makes data inaccessible, then performs idempotent object deletion, then
  finalizes the owning database cleanup. MinIO versioning and external volume
  snapshots stay disabled while the no-backup pilot decision is active.
- Verification: FT-001/FT-002/FT-012 proof: duplicate/orphan handling and
  repeated cleanup converge without exposing foreign or deleted media.
- Source: [.memory-bank/prd.md](../prd.md) `FR-ING-03..06`,
  `NFR-SEC-01`, the [boundary map](../contracts/boundary-map.md) and
  [lifecycle map](../states/lifecycle-map.md).

#### AD-012 — Manual serving-revision switch with accepted downtime
- Binds: changes to the active face pipeline or model revision.
- Prevents: hot switching and automatic rollback.
- Rule: `serving_control` owns an operator-initiated change with accepted
  downtime. Only a validated revision may serve. Any failed change leaves
  participant service unavailable until the operator retries or explicitly
  selects the prior revision; recovery never changes the revision
  automatically. Restart uses the committed revision and stays unavailable if
  it cannot serve.
- Verification: Serving-control/processing integration proof: an invalid
  revision never serves and every failed change requires explicit operator
  recovery.
- Source: accepted operator KISS decision, [.memory-bank/prd.md](../prd.md)
  `NFR-REL-01` and the [boundary map](../contracts/boundary-map.md).

#### AD-013 — Owner-ordered retention cleanup
- Binds: core Attempts, technical logs, ordinary diagnostic evidence and
  promoted Calibration subsets.
- Prevents: cross-owner delete cascades, foreign direct writes, a generic jobs
  subsystem and retention cleanup that destroys promoted evidence.
- Rule: `promo` owns the cleanup outcome; each capability deletes only its own
  data. Cleanup exposes the latest result defined by the boundary contract and
  is safe to rerun after failure or interruption.
- Verification: FT-007..FT-011 integration proof: cleanup enforces both
  cutoffs, preserves the promoted subset, avoids cross-owner writes and exposes
  the latest result.
- Source: [.memory-bank/prd.md](../prd.md) `NFR-REL-05`,
  `NFR-DATA-01..04` and the [boundary map](../contracts/boundary-map.md).

## Runtime Shape

```text
HTTPS edge
├── backend: staff UI/API, ingest, inventory operations, QR and diagnostics
└── RealtimeFaceService: one warmed model and one inference slot

private network
├── PostgreSQL + pgvector
├── MinIO
└── BackgroundPhotoWorker: one sequential operation

SpaPromoClient
├── central HTTPS browser runtime and local camera/proposal pipeline
├── ESP32 passage-event boundary
└── realtime attempt and Promo/display boundary
```

All server roles use the same release image and capability packages. Process
separation protects realtime latency and long-running background work; it is
not a microservice boundary. Realtime loads only the active model; worker and
realtime reuse the same revisioned FaceEngine implementations. One realtime
slot, one sequential background operation and conservative native thread caps
are the initial CPU policy.

## Capability Ownership

| Slice | Project-relative discovery root | Write ownership | Must not own | Minimum proof |
|---|---|---|---|---|
| `serving_control` | `src/face_moment/serving_control/` | СПА/timezone, active date/pipeline/settings, display token lifecycle and audited manual revision changes. | Photo, pipeline results, attempts, Promo sessions or recommendations. | Client cannot override СПА/date; one Attempt gets one immutable serving snapshot; revision recovery is operator-owned. |
| `inventory` | `src/face_moment/inventory/` | Photo admission/identity/uploader/effective time/visibility, inventory authorization, direct recent counters and global hard-purge orchestration. | ML transitions, result/session rules, Attempts or evidence. | Independent admission; owner-scoped hide/restore; processing-projection counters; configured primary-storage free capacity; fixed-snapshot purge and 1/5/60 counters. |
| `processing` | `src/face_moment/processing/` | Pipeline revisions, Photo processing states, derivatives/faces/embeddings, quality gates, revision validation, exact search and offline evaluation. | Photo visibility, settings mutation or Promo Attempt/session assembly. | Restart from `processing`; one final face set; exact compatible search; invalid revisions do not serve. |
| `promo` | `src/face_moment/promo/` | Core Attempt, result/session, four teasers, `N`, QR ticket/access, participant continuation and retention-cleanup outcome. | Inventory/processing/settings writes or detailed evidence. | Four unique teasers; truthful `N`; display acknowledgement; QR expiry; observable retention result. |
| `diagnostics` | `src/face_moment/diagnostics/` | Detailed evidence/logs, views, annotations, curated cases, recommendations and diagnostic-data expiry. | Core Attempt/result/session or direct settings mutation. | Role split, complete/incomplete evidence, promotion whitelist and 30/90-day cleanup. |

`src/face_moment/platform/auth/` is a narrow technical component for staff
principals, credentials and sessions. Business authorization stays in the five
capability slices. `src/face_moment/entrypoints/` and
`src/face_moment/infrastructure/` are wiring/adapters, not capability owners.
These roots are discovery locations, not task write boundaries.

## Cross-Slice Orchestration

- `inventory` owns per-photo admission and calls `serving_control` for the
  immutable ingest target and `processing` to create `pending` in the same
  per-photo PostgreSQL transaction.
- `promo` owns the participant attempt and calls `serving_control` for a
  snapshot, `processing` for exact search and `diagnostics` best-effort.
- `diagnostics` owns Calibration analysis and calls `processing` for offline
  evaluation; an accepted setting is applied only through `serving_control`.
- `inventory` owns hard purge and calls the `processing` cleanup boundary.
  `promo` and `diagnostics` receive no purge command because existing sessions,
  Attempts and diagnostic evidence are retained; UI/device reads skip missing
  hard-purged media.
- `serving_control` owns manual serving-revision changes and asks `processing`
  to validate a target.
- `promo` owns retention cleanup and calls `diagnostics` for diagnostic-data
  expiry. Each capability deletes only its own data; promoted Calibration
  subsets remain under `diagnostics` ownership.

## Serving Snapshot And Revision Change

Each Attempt copies one immutable serving snapshot:

- `settings_revision`, `spa_id`, `visit_date`;
- `pipeline_revision_id`, `pipeline_code`, `query_source=reference`;
- threshold, quality settings and optional `calibration_id`;
- `release_id`.

The copied values are the reproducibility contract; the pilot does not add a
versioned configuration platform. Serving-revision changes follow AD-012 and
accept maintenance downtime.

## Data And Storage Flow

- PostgreSQL is authoritative for identities, relationships, mutable state,
  serving settings, counters' source timestamps, Attempts, sessions and
  structured evidence.
- PostgreSQL uses one application schema, one SQLAlchemy `Base/MetaData` and
  one sequential Alembic migration stream. Capability packages still own their
  table models, repositories, invariants and commands.
- MinIO is authoritative for binary bytes only. A PostgreSQL visibility/state
  decision determines whether a private object may be read.
- Persisted capture-derived diagnostic media follows the ordinary 90-day
  evidence cutoff. Its image content alone does not require developer-only
  authorization, and persistence is optional rather than a new storage path.
- Effective `captured_at` is reliable EXIF interpreted in the СПА timezone,
  otherwise the file's server-side upload-start time, otherwise 01:00 on its
  authoritative `visit_date`.
- Soft deletion preserves all data and excludes the Photo from new
  search/result formation and counters. An already issued session continues to
  use the media while it exists. Restore reuses the preserved state.
- Hard purge rejects restore of fixed-snapshot members until completion and
  deletes Photo/media/face/pipeline data. Existing Promo sessions, Attempts and
  diagnostic evidence retain historical identifiers; clients skip removed
  media without invalidating or rebuilding the session or recalculating `N`.

Detailed lifecycle rules are in the
[lifecycle map](../states/lifecycle-map.md); write directions are in the
[boundary map](../contracts/boundary-map.md), including HTTP failure semantics,
shared-schema ownership and cascade limits.

## Deployment And Recovery

- The verified Foundation supplies the Compose-based single-server substrate.
  The target pilot deployment uses persistent primary PostgreSQL and MinIO
  volumes. One migrate/init command applies the single Alembic stream and
  ensures private buckets before backend, worker and realtime start or fail
  fast; realtime is ready only after exact active-model warmup.
- Restart policies cover the Compose services and a systemd user service covers
  SpaPromoClient/Chromium; the HTTPS edge returns `502/503` while an upstream is
  unavailable. The user service restarts Chromium, but successful client reload
  requires the central HTTPS origin; an already loaded client may continue
  advertising through a server/network failure, while restart during that
  failure has no offline-start guarantee. Photo work restarts from the
  beginning, while realtime work is not replayed; serving-revision recovery
  follows AD-012.
- Native-operation timing/health remains observable. A rare native hang may
  require manual `docker compose restart`; no watchdog/subprocess isolation is
  required without reproduced hangs.
- One idempotent daily cleanup command enters through the `promo` application
  boundary and follows AD-013; it may run through the shared worker or a simple
  host timer.
- Backup, replication, zero-downtime deployment and automated recovery from
  native hangs are outside the accepted pilot.

## Low-Cost Extension Seams

- Preserve immutable `photo_id`, result/session identity and the exact result
  `photo_id` set.
- Keep `query_source` extensible while the pilot serves only `reference`; the
  processing query boundary must not assume one camera transport.

## Deferred Decisions

| Decision | Deferred because | Revisit when |
|---|---|---|
| Camera/site geometry | Exact camera model, lens, lighting and maximum input dimensions depend on the selected site; frames above the configured maximum are already required to downscale before the ring buffer/detector. | Configure and verify the pilot site. |
| Client-side embeddings/search | Current accepted boundary keeps embeddings and search off the client. | A future benchmark and explicit operator decision justify reconsideration. |
| Multiple worker/realtime replicas and coordination | Singleton topology is accepted. | Measured throughput/availability failure. |
| Leases, fencing and claim-scoped derived keys | One configured worker prevents stale concurrent publication. | More than one worker or overlapping deployments are accepted. |
| Killable inference subprocess/watchdog | Ordinary crashes already restart; hang isolation adds failure surface. | A native hang is reproduced and requires intervention. |
| Broker, generic scheduler or reliable-delivery outbox | Owner-specific PostgreSQL rows and direct calls cover current durable flows. | A required durable workflow no longer fits those mechanisms. |
| ANN or external vector store | Exact scoped search has no measured failure. | Representative benchmark misses the latency target. |
| Automated pipeline switching/rollback | Maintenance downtime and manual rollback are accepted. | Revision switching becomes frequent enough to create measured operational cost. |
| Presigned media delivery | Authorized backend proxy is simpler. | Backend bandwidth is a measured bottleneck. |
| Backup/replication/snapshots | Loss of the sole primary is accepted. | Paid/public scope or a new durability decision. |
| Purge jobs/per-photo state or materialized counters | The accepted global-run and direct-query design satisfies the pilot. | Measured purge/polling failure. |
| GPU, Kubernetes, external observability, cpuset, dynamic priority or pause/resume scheduling | One CPU server with conservative thread caps has no measured failure. | Site measurements prove a compute, deployment or diagnostic limit. |
| Payment, selfie and original delivery | Only low-cost identity/ownership seams have current value. | The corresponding post-pilot product scope is accepted. |
| Per-slice database administration | One deployable shares transactions, joins and operations. | A slice becomes independently deployed and receives an accepted migration plan. |

## Accepted Pilot Risks

These risks do not authorize extra lifecycle or recovery machinery:

- Loss of the sole primary disk/server may destroy all persisted data.
- A crash between MinIO upload and PostgreSQL commit may leave one private
  orphan and require one Photo re-upload.
- During an unfinished multi-file upload, readers and metrics may see only the
  compatible `ready` subset; there is no Batch-level SLO.
- Calibration may occupy the shared worker and delay Photo processing; after
  interruption the developer reruns it manually.
- A Photo admitted under the wrong selected СПА/date has no dedicated correction
  workflow in the pilot.
- Effective `captured_at` may be approximate when EXIF is unreliable and the
  upload-start or 01:00 fallback is used.
- Global hard purge may delay processing while uploads continue to accumulate
  normal `pending` work.
- Client-only offline attempt metadata may expire or be lost on Chromium
  restart without creating a server Attempt.
- Hard purge may leave an issued session with fewer loadable media items and an
  historical `N`; clients skip missing media without session reconstruction.

## Verification Route

The verified Foundation supplies build/typecheck/start/test commands, one
linear migration-from-empty proof and one storage/runtime smoke; it does not
verify product behavior. Feature work owns the HTTP, client-proposal,
cross-slice, owner-ordered retention and ownership-safe deletion proofs named
in the Architecture Spine. The bootstrap
[testing policy](../testing/index.md) remains the quality-gate router.
