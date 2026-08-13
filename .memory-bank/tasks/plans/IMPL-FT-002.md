---
description: Implementation plan for compatible Photo processing and searchable readiness in FT-002.
status: active
last_updated: 2026-08-13
---
# IMPL-FT-002 — Processing And Searchable Readiness

## Goal

Deliver compatible native Photo processing through one model-admitted,
idempotent sequential worker, bind both model-consuming processes to the same
committed validated revision before readiness/work, expose truthful per-Photo/
searchable and operational health views, and prove the complete accepted-JPEG
SLO without adding another queue, scheduler, monitoring service or cross-store
transaction mechanism.

## Normative Basis

- [FT-002](../../features/FT-002.md): `FT-002-AC-001..008` and governing
  `REQ-ING-003..004`, `REQ-SRCH-001`, `REQ-REL-002`, `REQ-SEC-001` and
  `REQ-ARCH-001`.
- [System Architecture](../../architecture/system-architecture.md): AD-002,
  AD-004, AD-010, AD-011, AD-012 and `Deployment And Recovery`.
- [Boundary Map](../../contracts/boundary-map.md): capability application
  boundaries, processing input/status projections, manual serving-revision
  switch, shared PostgreSQL and PostgreSQL/MinIO convergence.
- [Photo Processing](../../domains/photo-processing.md): compatibility,
  model-asset admission, persistence, native adapters, worker state machine,
  publication, recovery, searchable/SLO and health projections.
- [Realtime Search](../../domains/realtime-search.md#reference-query-boundary):
  affected-consumer readiness boundary; FT-002 changes no query/search behavior.
- [Photo Processing API](../../contracts/photo-processing-api.md): exact
  authenticated per-Photo and processing-health surfaces.
- [Lifecycle Map](../../states/lifecycle-map.md#photo-pipeline-state): durable
  processing lifecycle and restart-from-the-beginning rule.
- [Photo Processing Verification](../../testing/photo-processing.md): terminal,
  adapter, runtime-admission, retry/restart, SLO, shared-worker and capacity
  matrices.
- [Client Realtime Verification](../../testing/client-realtime.md#reference-search-and-joint-correctness-proof):
  affected-consumer startup/readiness proof only; FT-002 owns no request flow.

## Scope And Non-Goals

In scope are the one processing migration, two direct native engine adapters,
operator-managed read-only model mounts for both model-consuming processes,
composition-root admission of only the committed validated revision before
readiness/recovery/work, deterministic derivatives, bounded worker transitions
and recovery, compatible searchable/SLO projections, independently observable
PostgreSQL/MinIO capacity, the exact staff APIs and their existing-page UI
integration.

Out of scope are realtime query execution, participant result assembly,
Calibration calculation/storage, Photo inventory delete/purge, model download,
fallback, registry/factory/cache machinery, hot switching, automatic rollback,
dual preload, extra workers, broker/queue frameworks, priority/preemption
scheduling, monitoring services and production deployment.

## Architecture And Ownership

Canonical module identity, discovery roots, responsibilities, forbidden
ownership and dependency direction live only in the Boundary Map
[module inventory](../../contracts/boundary-map.md#modules) and
[dependency graph](../../contracts/boundary-map.md#dependency-graph). FT-002
creates or changes no module or graph edge.

The FT-002-specific implementation order and affected-consumer boundary are
resolved through these canonical contract blocks:

- [Processing input projections](../../contracts/boundary-map.md#processing-input-projections)
  and [Processing status projections](../../contracts/boundary-map.md#processing-status-projections)
  bound the Photo/serving inputs and the staff-visible processing projections;
  propagation stops at the compatible projection/API boundary.
- [Independent Photo admission](../../contracts/boundary-map.md#independent-photo-admission)
  remains the prerequisite path for the atomic initial serving `pending` state;
  FT-002 does not reopen admission ownership.
- [Calibration and serving change](../../contracts/boundary-map.md#calibration-and-serving-change)
  limits FT-002 to the shared-worker delay/resume seam; Calibration calculation,
  recommendation and persistence remain outside this plan.
- [Manual serving-revision switch](../../contracts/boundary-map.md#manual-serving-revision-switch)
  and [Model-asset admission](../../domains/photo-processing.md#model-asset-admission)
  bind the worker/realtime startup integration. Realtime request and query
  behavior remain outside FT-002 and with FT-004.

These links justify task prerequisites and affected-consumer traversal without
republishing the canonical subgraph. Expected code paths remain advisory in
`Advisory Expected Change Surface` below.

## KISS Implementation Strategy

- Extend the current schema once through the linear migration stream.
- Because legacy revision rows cannot supply truthful compatibility metadata,
  fail the pre-production migration before any mutation unless
  `pipeline_revisions` is empty; never fabricate, delete or repoint identity.
- Implement exactly two direct engine adapters behind the existing
  `FaceEngine` boundary; add no plugin registry, adapter factory or second
  engine abstraction.
- Mount one operator-managed host model directory read-only into worker and
  realtime. At each process start, resolve the committed selected validated
  revision, instantiate only its direct adapter, verify full identity plus
  computed `weights_sha256`, and stay unavailable before work on mismatch.
- Apply a serving-revision change only through the accepted operator update and
  restart downtime; add no download, fallback, cache, hot switch or dual preload.
- Use the existing `photo_pipeline_states` rows plus one narrow runtime-status
  singleton for the one sequential worker; add no jobs table, lease, fencing,
  `SKIP LOCKED`, broker or scheduler.
- Use deterministic private derivative keys and idempotent owner transactions;
  add no PostgreSQL/MinIO transaction emulator.
- Compute queue/SLO state with direct PostgreSQL reads and capacity with two
  read-only `statvfs`-equivalent observations; add no materialized metrics or
  monitoring service.
- Extend the existing FastAPI backend and plain staff pages rather than adding
  another UI/runtime framework.

## Accepted Tasks And Dependency Strategy

Every root retains the verified Foundation final gate directly or transitively.
Dependencies express owner-valid implementation prerequisites; execution stays
sequential even where tasks share a wave.

| Task | Tier | Wave | Direct prerequisites | Exact claim | Outcome |
|---|---|---|---|---|---|
| [TASK-018-T2-FT-002-W1](../TASK-018-T2-FT-002-W1.task.json) | T2 | W1 | TASK-009 | `photo-processing.md#compatibility-identity` plus the three persisted-shape headings | Processing persistence and compatibility migration. |
| [TASK-019-T2-FT-002-W2](../TASK-019-T2-FT-002-W2.task.json) | T2 | W2 | TASK-018 | `FT-002-AC-007` | Native SFace Photo adapter. |
| [TASK-020-T2-FT-002-W2](../TASK-020-T2-FT-002-W2.task.json) | T2 | W2 | TASK-018 | `FT-002-AC-008` | Native Buffalo M Photo adapter. |
| [TASK-021-T3-FT-002-W2](../TASK-021-T3-FT-002-W2.task.json) | T3 | W2 | TASK-018, TASK-011 | `photo-processing.md#deterministic-private-derivatives` | Deterministic private derivatives. |
| [TASK-022-T2-FT-002-W2](../TASK-022-T2-FT-002-W2.task.json) | T2 | W2 | TASK-018 | `photo-processing.md#atomic-claim-and-bounded-failure` | Atomic claim and bounded failure state machine. |
| [TASK-023-T3-FT-002-W3](../TASK-023-T3-FT-002-W3.task.json) | T3 | W3 | TASK-021, TASK-022 | `FT-002-AC-002` | Idempotent terminal face/derivative publication. |
| [TASK-024-T2-FT-002-W4](../TASK-024-T2-FT-002-W4.task.json) | T2 | W4 | TASK-019, TASK-020, TASK-023 | `photo-processing.md#single-photo-orchestration` | Single-Photo processing orchestration. |
| [TASK-025-T2-FT-002-W3](../TASK-025-T2-FT-002-W3.task.json) | T2 | W3 | TASK-022 | `photo-processing.md#startup-recovery` | Startup recovery transaction. |
| [TASK-026-T3-FT-002-W5](../TASK-026-T3-FT-002-W5.task.json) | T3 | W5 | TASK-024, TASK-025 | `FT-002-AC-003` plus `photo-processing.md#model-asset-admission` | Model-admitted worker/realtime startup plus sequential worker runtime and restart integration. |
| [TASK-027-T2-FT-002-W4](../TASK-027-T2-FT-002-W4.task.json) | T2 | W4 | TASK-023, TASK-007, TASK-008 | `photo-processing.md#compatible-searchable-truth` | Compatible searchable-truth projection. |
| [TASK-028-T2-FT-002-W5](../TASK-028-T2-FT-002-W5.task.json) | T2 | W5 | TASK-027 | `FT-002-AC-004` | Full-population ingest-to-searchable SLO projection. |
| [TASK-029-T2-FT-002-W6](../TASK-029-T2-FT-002-W6.task.json) | T2 | W6 | TASK-026, TASK-028 | `FT-002-AC-005` | Shared-worker Calibration delay/resume boundary. |
| [TASK-030-T3-FT-002-W5](../TASK-030-T3-FT-002-W5.task.json) | T3 | W5 | TASK-027, TASK-017 | `photo-processing-api.md#per-photo-processing-status` | Authenticated per-Photo processing-status API. |
| [TASK-031-T2-FT-002-W6](../TASK-031-T2-FT-002-W6.task.json) | T2 | W6 | TASK-026, TASK-030 | `FT-002-AC-001` | Photographer uploader status-polling UI. |
| [TASK-032-T2-FT-002-W4](../TASK-032-T2-FT-002-W4.task.json) | T2 | W4 | TASK-025 | `photo-processing.md#queue-and-recovery-health-projection` | Queue and recovery health projection. |
| [TASK-033-T3-FT-002-W1](../TASK-033-T3-FT-002-W1.task.json) | T3 | W1 | TASK-002 | `photo-processing.md#postgresql-capacity-observation` | PostgreSQL capacity probe. |
| [TASK-034-T3-FT-002-W2](../TASK-034-T3-FT-002-W2.task.json) | T3 | W2 | TASK-033 | `photo-processing.md#minio-capacity-observation` | MinIO capacity probe. |
| [TASK-035-T3-FT-002-W6](../TASK-035-T3-FT-002-W6.task.json) | T3 | W6 | TASK-028, TASK-032, TASK-034, TASK-005 | `photo-processing-api.md#processing-health-and-slo` | Authenticated processing-health API. |
| [TASK-036-T3-FT-002-W7](../TASK-036-T3-FT-002-W7.task.json) | T3 | W7 | TASK-029, TASK-035 | `FT-002-AC-006` | Processing-health UI and real-browser UAT. |

## Advisory Expected Change Surface

- `src/face_moment/processing/`
- `src/face_moment/serving_control/`
- `src/face_moment/inventory/`
- `src/face_moment/infrastructure/`
- `src/face_moment/entrypoints/background_worker.py`
- `src/face_moment/entrypoints/realtime.py`
- `src/face_moment/infrastructure/settings.py`
- `src/face_moment/entrypoints/backend.py`
- `migrations/versions/`
- `compose.yaml`
- `tests/processing/` and `tests/inventory/`

These paths are advisory and non-exhaustive. The migration uses the linear head
current at execution as its direct `down_revision`; no mutable future exact
head or hard task write boundary is inferred.

## Tests, Gates And UAT

- Every task runs configured mypy and its focused project-native pytest target.
- Migration proof covers direct ancestry, upgrade, downgrade, re-upgrade,
  constraints, preservation of unrelated prerequisite rows on the empty-table
  path and an unchanged-schema/data abort for any legacy revision row.
- Adapter proof records the two native call paths independently and uses
  deterministic fixtures without downloading or auto-selecting models.
- Runtime-admission proof mounts deterministic assets read-only and covers both
  model-consuming roles: matching committed identity opens readiness/work;
  missing, absent/ineligible, identity/hash-mismatched or other-pipeline assets
  fail closed before readiness, recovery, claim, inference or processing-state
  mutation. A selected-revision change has no effect until an explicit restart.
- Storage/worker probes use task-owned PostgreSQL rows and MinIO prefixes, known
  initial state, safe rerun and owner-bounded cleanup.
- Retry/restart proof injects post-derivative/pre-commit interruption and a real
  worker process restart without touching production data.
- SLO proof uses a controlled clock, the half-open
  `[accepted_from, accepted_before)` interval and reconciles every accepted or
  excluded fixture exactly once; an empty population yields zero counts and
  null ratio/verdict.
- `REQ-SEC-001` material proof remains owned exactly by `FT-002-AC-006` in
  TASK-036. Earlier private-media, authenticated-API and read-only capacity
  tasks retain their canonical privacy/auth/topology constraints and hostile
  T3 verification, but do not duplicate that feature-level NFR claim.
- The two UI tasks use `playwright cli` and store transcripts, screenshots and
  traces under their task artifact directories.
- Tier-routed `/verify` applies to every task; each T3 additionally requires
  per-task `/red-verify`. Feature completion later requires
  `/red-verify --feature FT-002`.

## Constitution Constraints And Invariants

- Preserve the one-release modular monolith, one schema/Base/Alembic stream,
  one sequential worker and private PostgreSQL/MinIO topology.
- Only processing writes processing state; inventory owns authorization and
  staff-visible read outcomes.
- Only complete active `ready` for the current compatible revision is
  searchable.
- Worker and realtime bind only the committed selected validated revision from
  read-only operator assets; every model identity or `weights_sha256` mismatch
  fails closed before work and never triggers fallback.
- Retry and restart converge without duplicate faces or a second queue.
- The full accepted-JPEG SLO population remains truthful, including late and
  Calibration-delayed work.
- Capacity results stay independent and reveal no credential, path, key,
  embedding, model or commercial-media content.

## Definition Of Done

All nineteen indexed tasks independently satisfy their task-owned exact claims
and tier obligations, every `FT-002-AC-001..008` has one owner, both
model-consuming roles pass the selected-revision admission/fail-closed matrix,
the two staff UAT flows pass, and fresh review can approve the queue without
adding a runtime mechanism or changing Global Backbone Planning Revision `4`.
