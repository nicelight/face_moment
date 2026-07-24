---
description: Canonical greenfield system shape, capability ownership and Architecture Spine for the Face Moment pilot.
status: active
last_updated: 2026-07-24
source_of_truth:
  - .memory-bank/architecture/system-architecture.md
---
# System Architecture

## Status And Source Boundary

- Face Moment is in documentation/design: no working application, backend,
  worker, database schema or deployed runtime exists yet.
- [arch_vision.md](../../arch_vision.md) is the accepted target-architecture
  source. [.memory-bank/prd.md](../prd.md) owns product behavior and acceptance.
- This document, the [boundary map](../contracts/boundary-map.md) and
  [lifecycle map](../states/lifecycle-map.md) are the canonical compact SDD
  projection of that accepted target.

## System Goal

Deliver the one-СПА pilot as one greenfield modular-monolith release with
predictable process-restart recovery, searchable per-photo inventory,
low-latency Promo/QR continuation and protected diagnostics, without
speculative distributed infrastructure.

## Main Constraints

- One central CPU-only server, one display client and one configured replica of
  each long-running server role.
- Five capability packages for the current pilot:
  `serving_control`, `inventory`, `processing`, `promo`, `diagnostics`.
- PostgreSQL/pgvector owns durable state and exact vector search; private MinIO
  owns binary bytes. No shared cross-store transaction is assumed.
- All capability tables use one PostgreSQL schema, one SQLAlchemy
  `Base/MetaData`, one Alembic configuration and one sequential migration
  stream; slice write ownership remains semantic, not schema-based.
- Public browser traffic crosses the HTTPS application boundary. PostgreSQL,
  MinIO and internal process ports stay private.
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
- Rule: one Python/FastAPI modular monolith supplies five capability packages;
  `backend`, one `BackgroundPhotoWorker` and one `RealtimeFaceService` are
  process entrypoints over the same release. The composition root owns only
  settings, adapters, wiring, lifecycle, start and shutdown.
- Verification: Required Foundation proof, not currently runnable: all three
  entrypoints start against fake adapters from one release.
- Source: [arch_vision.md](../../arch_vision.md) sections 2–4.

#### AD-002 — One write owner per mutable invariant
- Binds: shared PostgreSQL access and every cross-slice use case.
- Prevents: foreign direct writes, duplicated business rules, generic
  Unit-of-Work/event-bus/outbox machinery and orchestration in HTTP/UI handlers.
- Rule: a slice may read a published projection, but commands and transitions
  pass through the owning slice's application boundary. Cross-slice
  orchestration lives in the capability that owns the user-visible outcome.
- Verification: Required feature-level integration proof, not currently
  runnable: each cross-slice flow changes state only through the named owner.
- Source: [arch_vision.md](../../arch_vision.md) sections 4–5 and
  [boundary map](../contracts/boundary-map.md).

#### AD-003 — Independent per-photo durable admission
- Binds: ingest, duplicate arbitration and searchable readiness.
- Prevents: Batch/manifest/confirmation, aggregate upload commits and
  distributed PostgreSQL/MinIO transactions.
- Rule: one unique JPEG produces one short PostgreSQL transaction containing
  `Photo + accepted_at + serving pending`; uniqueness is
  `(spa_id, visit_date, checksum_sha256)`. MinIO remains outside the transaction.
- Verification: Required FT-001/FT-002 proof, not currently runnable:
  concurrent duplicates yield one Photo and accepted work survives restart.
- Source: [arch_vision.md](../../arch_vision.md) sections 5 and 7.

#### AD-004 — Singleton background execution with restart from the beginning
- Binds: Photo processing, Calibration and global hard purge.
- Prevents: broker, leases, fencing, preemption, priority scheduling and
  additional worker replicas.
- Rule: `photo_pipeline_states` is the durable Photo-processing queue for one
  sequential worker; stale `processing` returns to `pending` on startup.
  Calibration may block processing. A confirmed hard purge waits for the
  current operation and then reuses the same worker.
- Verification: Required FT-002/FT-011/FT-012 restart proofs, not currently
  runnable.
- Source: [arch_vision.md](../../arch_vision.md) sections 8 and 11.

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
- Verification: Required FT-012 proof, not currently runnable: authorization,
  hide/restore, exact counters and restartable fixed-snapshot purge.
- Source: [.memory-bank/prd.md](../prd.md) FR-INV-01..11 and
  [arch_vision.md](../../arch_vision.md) section 7.

#### AD-006 — Bounded realtime request and explicit display success
- Binds: automatic capture, search, Promo and performance acceptance.
- Prevents: a realtime waiter queue, durable replay and treating a server
  response as visible Promo success.
- Rule: one client-generated `attempt_id`, one inference slot and one server
  deadline govern the synchronous request; concurrency returns `busy`. Only an
  idempotent client acknowledgement after four teasers and QR are visible sets
  display success. Missing acknowledgement becomes derived `unconfirmed` after
  the result-display window; no scheduler or acknowledgement outbox exists.
- Verification: Required FT-003..FT-005 controlled 20-attempt proof, not
  currently runnable.
- Source: [arch_vision.md](../../arch_vision.md) sections 8–9.

#### AD-007 — Core Attempt survives best-effort evidence
- Binds: Promo, diagnostics, retention and hard purge.
- Prevents: diagnostic evidence blocking participant flow, an empty anchor,
  server-side reliable-delivery outbox or hard-purge cascade into
  sessions/Attempts/evidence.
- Rule: `promo` persists a core Attempt before inference for every
  server-admitted request; `diagnostics` attaches detailed evidence
  best-effort and exposes missing finalization as `incomplete`. Client-only
  offline triggers are best-effort and may have no durable Attempt. Photo hard
  purge retains existing Promo result/session data, the core Attempt and
  diagnostic evidence; clients skip unavailable media.
- Verification: Required FT-007/FT-012 integration proof, not currently
  runnable.
- Source: [arch_vision.md](../../arch_vision.md) sections 5, 9 and 11.

#### AD-008 — Session-wide QR continuation
- Binds: Promo session authorization and participant media delivery.
- Prevents: per-device grant rows and public MinIO/presigned participant URLs in
  the pilot.
- Rule: one Promo session has a 30-minute first-open window and one shared
  60-minute idle access state; protected media is served through authorized
  no-store backend reads.
- Verification: Required FT-006 multi-phone expiry proof, not currently
  runnable.
- Source: [arch_vision.md](../../arch_vision.md) section 10.

#### AD-009 — Standard HTTP failures and typed domain outcomes
- Binds: every public/staff HTTPS endpoint and the SpaPromoClient realtime
  contract.
- Prevents: a project-specific error envelope/framework, business outcomes
  disguised as transport errors and client decisions based on response prose.
- Rule: authentication, permission, payload, validation, rate-limit and
  internal/upstream failures use the standard `401`, `403`, `413`, `422`,
  `429` and `5xx` classes. An admitted capture/search request returns `2xx`
  with a compact typed outcome such as `busy`, `deadline`,
  `unacceptable_query` or `insufficient_results`; clients branch on
  status/outcome, never `5xx` text.
- Verification: Required boundary contract proof, not currently runnable:
  representative transport failures map to the standard status and admitted
  non-success search results remain typed domain outcomes.
- Source: [arch_impr1.md](../../arch_impr1.md) section 1 and
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
- Verification: Required Foundation/feature proof, not currently runnable:
  the single migration stream builds an empty database and deletion tests
  preserve foreign-owned Attempt/evidence state.
- Source: [arch_impr1.md](../../arch_impr1.md) section 2 and
  [boundary map](../contracts/boundary-map.md).

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
└── local advertising, capture ring buffer, Promo render and display ack
```

All server roles use the same release and capability packages. Process
separation protects realtime latency and long-running background work; it is
not a microservice boundary.

## Capability Ownership

| Slice | Project-relative discovery root | Write ownership | Must not own | Minimum proof |
|---|---|---|---|---|
| `serving_control` | `src/face_moment/serving_control/` | СПА/timezone, active date/pipeline/settings, display token lifecycle and manual-change audit. | Photo, pipeline results, attempts, Promo sessions or recommendations. | Client cannot override СПА/date; attempt gets one immutable serving snapshot. |
| `inventory` | `src/face_moment/inventory/` | Photo admission/identity/uploader/effective time/visibility, inventory authorization, direct recent counters and global hard-purge orchestration. | ML transitions, result/session rules, Attempts or evidence. | Independent admission; owner-scoped hide/restore; fixed-snapshot purge and 1/5/60 counters. |
| `processing` | `src/face_moment/processing/` | Pipeline revisions, Photo processing states, derivatives/faces/embeddings, quality gates, exact search and offline evaluation. | Photo visibility, settings mutation or Promo assembly. | Restart from `processing`; one final face set; exact compatible search. |
| `promo` | `src/face_moment/promo/` | Core Attempt, result/session, four teasers, `N`, QR ticket/access and participant continuation. | Inventory/processing/settings writes or detailed evidence. | Four unique teasers; truthful `N`; display acknowledgement; QR expiry. |
| `diagnostics` | `src/face_moment/diagnostics/` | Detailed evidence/logs, views, annotations, curated cases and recommendations. | Core Attempt/result/session or direct settings mutation. | Role split, complete/incomplete evidence and promotion whitelist. |

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

HTTP/UI handlers and the composition root only authenticate, validate and
dispatch these use cases; they do not contain business orchestration.

## Data And Storage Flow

- PostgreSQL is authoritative for identities, relationships, mutable state,
  serving settings, counters' source timestamps, Attempts, sessions and
  structured evidence.
- PostgreSQL uses one application schema, one SQLAlchemy `Base/MetaData` and
  one sequential Alembic migration stream. Capability packages still own their
  table models, repositories, invariants and commands.
- MinIO is authoritative for binary bytes only. A PostgreSQL visibility/state
  decision determines whether a private object may be read.
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

- A future Compose-based single-server deployment uses persistent primary
  PostgreSQL and MinIO volumes and restart policies for server roles.
- Process crashes restart automatically. Photo work restarts from the
  beginning; realtime work is closed as interrupted and not replayed.
- An in-progress upload is not interrupted by hard purge. Ordinary upload may
  continue and add normal `pending` work while the shared worker is occupied.
- Backup, replication, zero-downtime deployment and automated recovery from
  native hangs are outside the accepted pilot.

## Deferred Decisions

| Decision | Deferred because | Revisit when |
|---|---|---|
| Exact camera/sensor transport | Pilot hardware is not selected. | Site hardware is selected before FT-003 implementation. |
| Multiple worker/realtime replicas and coordination | Singleton topology is accepted. | Measured throughput/availability failure. |
| ANN or external vector store | Exact scoped search has no measured failure. | Representative benchmark misses the latency target. |
| Presigned media delivery | Authorized backend proxy is simpler. | Backend bandwidth is a measured bottleneck. |
| Backup/replication/snapshots | Loss of the sole primary is accepted. | Paid/public scope or a new durability decision. |
| Purge jobs/per-photo state or materialized counters | The accepted global-run and direct-query design satisfies the pilot. | Measured purge/polling failure. |

## Verification Route

The repository currently has no runnable code. Foundation establishes the
build/start/test commands, one linear migration-from-empty proof and one
storage/runtime smoke; feature work later owns the HTTP contract and
ownership-safe deletion proofs named in the Architecture Spine. The bootstrap
[testing policy](../testing/index.md) remains the quality-gate router.
