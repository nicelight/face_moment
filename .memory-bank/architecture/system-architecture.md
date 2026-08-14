---
description: Canonical greenfield system shape, capability ownership and Architecture Spine for the Face Moment pilot.
status: active
last_updated: 2026-08-14
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
- Rule: `inventory` is the sole owner of Photo visibility, recent-statistics
  reads and permanent removal. It uses one visibility marker, direct PostgreSQL
  aggregates and one restartable global purge run through the shared worker;
  foreign Promo/diagnostic state remains with its owner.
- Verification: FT-012 ownership, aggregation and restart proof.
- Source: [.memory-bank/prd.md](../prd.md) `FR-INV-01..11` and the
  [Photo inventory lifecycle](../states/lifecycle-map.md#photo-inventory-visibility).

#### AD-006 — Bounded realtime request with owner-separated orchestration
- Binds: automatic capture, search, Promo and performance acceptance.
- Prevents: client takeover of server-side selection/search, unbounded
  proposal submission, a realtime waiter queue and durable replay.
- Rule: one bounded synchronous request uses one inference slot and one server
  deadline. `promo` owns admission/orchestration; `processing` owns inference,
  selection and search. Exact transport and display transitions belong to the
  boundary and lifecycle contracts.
- Verification: FT-003..FT-005 boundedness and owner-boundary proof.
- Source: [.memory-bank/prd.md](../prd.md) `FR-CAP-01..17`,
  `FR-UX-01..09`, the [boundary map](../contracts/boundary-map.md) and the
  [Attempt/display lifecycle](../states/lifecycle-map.md#automatic-attempt-and-display).

#### AD-007 — Core Attempt survives best-effort evidence
- Binds: Promo, diagnostics, retention and hard purge.
- Prevents: diagnostic evidence blocking participant flow, a reliable-delivery
  outbox and cross-owner purge/retention cascades.
- Rule: `promo` persists the core Attempt before processing an admitted
  request; `diagnostics` owns optional detailed evidence. Evidence failure does
  not change the participant outcome, and each owner controls its own cleanup.
- Verification: FT-007/FT-012 independence and ownership proof.
- Source: [.memory-bank/prd.md](../prd.md) `FR-DIAG-01..05`,
  `NFR-DATA-01..04` and the
  [Attempt/evidence lifecycle](../states/lifecycle-map.md#core-attempt-and-diagnostic-evidence).

#### AD-008 — Session-wide access with private media delivery
- Binds: Promo session authorization and participant media delivery.
- Prevents: per-device grant rows and public MinIO/presigned participant URLs in
  the pilot.
- Rule: `promo` owns one session-wide access state; commercial Photo media and
  personalized session data cross authorized no-store backend reads. Exact
  first-open, idle and expiry behavior belongs to the lifecycle contract.
- Verification: FT-006 shared-access and private-delivery proof.
- Source: [.memory-bank/prd.md](../prd.md) `FR-UX-03..10` and the
  [Promo/QR lifecycle](../states/lifecycle-map.md#promo-qr-and-browser-session).

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
- Binds: changes to the active face pipeline or model revision, including the
  pre-commit processing guard for the current serving revision.
- Prevents: hot switching, automatic rollback, model download/fallback,
  simultaneous dual-pipeline preload and an ordinary switch that strands
  current-revision Photo work.
- Rule: `serving_control` owns an operator-initiated change with accepted
  downtime. Only a validated revision may serve. Before it commits B in place
  of current A for one СПА, it calls the read-only processing-owned guard for
  A. Serving selection and Photo admission serialize: an admission either
  commits against A before the guard and blocks the switch, or observes B only
  after a successful switch. Any A-admitted Photo whose A state is `pending` or
  `processing` rejects the switch, keeps A committed and leaves Photo state,
  mounted assets and model-consuming processes unchanged. `ready`, `no_faces`
  and `failed` A states do not block. Calibration/model comparison is test-only
  and is never an exemption or automatic caller of this command. After B
  commits, a deployment/admission failure leaves participant service unavailable
  until the operator retries or explicitly selects the prior revision; recovery
  never changes the revision automatically. The operator-managed model
  directory is mounted read-only; worker and realtime restart, load only the
  committed revision and verify its full configured identity plus computed asset
  hash before accepting work. Restart stays unavailable if the committed
  revision cannot serve.
- Verification: Serving-control/processing integration proof serializes a
  concurrent admission with the A-to-B decision, rejects both `pending` and
  `processing` A states without changing A, permits each terminal A state, and
  proves invalid or missing/mismatched B assets never serve or mutate work.
- Source: accepted operator KISS decisions, [.memory-bank/prd.md](../prd.md)
  `NFR-REL-01`, [FT-002](../features/FT-002.md#clarifications), the
  [boundary map](../contracts/boundary-map.md) and
  [Photo Processing](../domains/photo-processing.md#model-asset-admission).

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

The server application is the parent architecture unit for the accepted
`serving_control`, `inventory`, `processing`, `promo` and `diagnostics`
capability slices plus the narrow supporting `staff_access` component. The
detailed module identities, discovery roots, responsibilities, forbidden
ownership and proof paths are owned by the
[Boundary Map module inventory](../contracts/boundary-map.md#modules).

All server roles compose these modules from the same release.
`src/face_moment/entrypoints/` and `src/face_moment/infrastructure/` remain
wiring/adapters rather than business change units. Discovery roots do not
become task write boundaries.

## Cross-Slice Orchestration

Cross-slice use cases are owned by the capability responsible for the
user/operator-visible outcome. HTTP/UI handlers, generic helpers and the
composition root never own business orchestration or write foreign state.

The accepted `Consumer -> Provider` topology and exact interaction contracts
are canonical only in the
[Boundary Map dependency graph](../contracts/boundary-map.md#dependency-graph).
Shared PostgreSQL access does not add an edge or write authority.

## Serving Snapshot And Revision Change

Each Attempt copies one immutable serving snapshot:

- `settings_revision`, `spa_id`, `visit_date`;
- `pipeline_revision_id`, `pipeline_code`, `query_source=reference`;
- threshold, quality settings and optional `calibration_id`;
- `release_id`.

The copied values are the reproducibility contract; the pilot does not add a
versioned configuration platform. Serving-revision changes follow AD-012: the
pre-commit guard keeps A when its admitted work is non-terminal, and a permitted
change accepts maintenance downtime.

## Data And Storage Flow

AD-010 and AD-011 define PostgreSQL/MinIO authority, the single migration
stream and cross-store convergence. The
[boundary map](../contracts/boundary-map.md) owns capability write authority
and cascade limits; the [lifecycle map](../states/lifecycle-map.md) owns Photo,
media, Attempt, session, deletion and retention behavior.

## Deployment And Recovery

- The verified Foundation supplies the Compose-based single-server substrate.
  The target pilot deployment uses persistent primary PostgreSQL and MinIO
  volumes. One migrate/init command applies the single Alembic stream and
  ensures private buckets before backend, worker and realtime start or fail
  fast; realtime is ready only after exact active-model warmup.
- Model files remain outside the shared application image in one
  operator-managed host directory mounted read-only into
  `BackgroundPhotoWorker` and `RealtimeFaceService`. Each process resolves the
  committed selected validated revision, loads only that direct pipeline and
  verifies the mounted assets against its immutable identity before becoming
  available or accepting work. Missing or mismatched assets fail closed; no
  download, fallback, registry or simultaneous dual-pipeline preload is added.
- Restart policies cover the Compose services and a systemd user service covers
  SpaPromoClient/Chromium; the HTTPS edge returns `502/503` while an upstream is
  unavailable. The user service restarts Chromium, but successful client reload
  requires the central HTTPS origin; an already loaded client may continue
  advertising through a server/network failure, while restart during that
  failure has no offline-start guarantee. Photo work restarts from the
  beginning, while realtime work is not replayed; serving-revision recovery
  follows AD-012.
- An operator serving-revision change first passes the AD-012 pre-commit guard.
  Only then may it update mounted assets/settings when necessary and restart
  both model-consuming processes during the maintenance window; restart binds
  them to the committed revision. A guard rejection leaves the A deployment
  untouched.
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
