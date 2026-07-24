---
description: Canonical capability ownership, public application boundaries and cross-slice write rules for the greenfield pilot.
status: active
last_updated: 2026-07-24
source_of_truth:
  - .memory-bank/contracts/boundary-map.md
---
# Boundary Map

## Status And Scope

The repository has no working backend or runtime. This map constrains the
target implementation described by [arch_vision.md](../../arch_vision.md) and
the [system architecture](../architecture/system-architecture.md); it does not
describe existing code.

## Capability Boundaries

| Owner | Public application boundary | Owned mutable state and transitions | Forbidden ownership | Allowed dependencies | Minimum credible proof |
|---|---|---|---|---|---|
| `serving_control` | Read immutable `ServingContext`/`IngestTarget`; validate and apply an audited manual change. | СПА/timezone, active `visit_date`, pipeline/settings revision, display token lifecycle and manual-change audit. | Photos, processing results, Attempts, sessions, evidence or Calibration recommendations. | Platform auth/infrastructure adapters only. | Client input cannot override СПА/date; one attempt sees one immutable snapshot. |
| `inventory` | Admit one JPEG; query authorized Photos; soft-delete/restore; restore-all; start/read one global hard purge; read recent per-СПА counters. | Photo identity, uploader, authoritative date, effective capture time, accepted time, checksum/original reference, active marker, authorization and global purge orchestration/progress. | Pipeline transition rules, embeddings, Promo integrity, core Attempt or evidence retention. | Read `serving_control`; command `processing` and `promo`; platform auth/storage adapters. | Duplicate arbitration; owner-scoped visibility; fixed-snapshot purge recovery; exact counter definitions. |
| `processing` | Create initial `pending`; report readiness; process Photo; exact compatible search; offline evaluate; clean Photo-derived state on inventory purge. | Pipeline catalog, processing state, derivatives/faces/embeddings, quality gates, exact-search and evaluation rules. | Photo admission/visibility, live setting mutation, Promo assembly or evidence retention. | Read Photo/serving projections; storage/model adapters. | Restart from `processing`, one final face set, compatible exact search and idempotent cleanup. |
| `promo` | Execute fresh attempt; accept display outcome; exchange/read QR continuation; clean affected result/session on inventory purge. | Core Attempt, result/session, candidate union, teasers, `N`, QR ticket and session-wide browser access. | Photo/processing/settings mutation or detailed diagnostic evidence. | Read `serving_control`/`inventory`; command `processing`; best-effort command `diagnostics`. | Four unique teasers, correct `N`, explicit display acknowledgement and session expiry. |
| `diagnostics` | Record/search authorized evidence/logs; annotate; run evaluation; request audited manual apply. | Detailed evidence/logs, access views, annotations, curated Calibration cases and recommendations. | Core Attempt/result/session or direct serving-setting change. | Read `promo`; command `processing` evaluation and `serving_control` apply. | Sanitized/developer split, visible incomplete evidence and promotion whitelist. |

Shared PostgreSQL access does not grant shared write authority. A slice may read
a published projection; only the owner may validate and perform its command or
transition.

## Shared PostgreSQL Contract

- The modular monolith uses one PostgreSQL application schema, one SQLAlchemy
  `Base/MetaData`, one Alembic configuration and one sequential migration
  stream.
- Table models and repositories remain in their owning capability packages.
  One physical schema does not permit a slice to issue foreign commands,
  mutate foreign-owned state or duplicate another slice's business rules.
- Cross-slice transactions are allowed only through public application
  boundaries under the named orchestration owner; they do not create shared
  business ownership.
- Foreign keys and `ON DELETE` behavior are deliberate per relation. Database
  cascade MUST NOT cross a capability ownership boundary. In particular,
  deleting a Photo MUST NOT cascade into core Attempts or diagnostic evidence;
  the inventory-owned hard-purge flow calls owner cleanup boundaries and
  preserves those records.
- Per-slice PostgreSQL schemas, database users/ACLs and independent migration
  pipelines are outside the accepted pilot.

## External And Runtime Boundaries

| Boundary | Contract | Owner | Required constraints |
|---|---|---|---|
| Staff browser -> application | HTTPS staff authentication, independent JPEG upload and authorized Admin UI commands. | `platform/auth` authenticates; the target capability authorizes and handles the command. | MinIO/PostgreSQL stay private; no Batch/manifest/confirmation. |
| `SpaPromoClient` -> realtime | One bounded synchronous request with client-generated `attempt_id`, server-derived СПА, one slot and deadline. | `promo` orchestrates; `processing` performs compatible inference/search. | Concurrent request returns `busy`; stale work is not replayed. |
| Display -> application | Idempotent acknowledgement after four teasers decode and QR is fully visible. | `promo`. | Server result issue alone is not Promo success. |
| QR browser -> application | Ticket exchange and authorized no-store session reads. | `promo`. | 30-minute first-open, shared 60-minute idle state, no per-device grants. |
| Application/worker -> PostgreSQL | Owner-scoped state writes and published projections. | Each capability owns its rows/invariants. | Direct foreign writes are forbidden even in one database. |
| Application/worker -> MinIO | Opaque-key private binary read/write/delete behind owner authorization/state. | `inventory` owns originals; `processing` owns derivatives; `diagnostics` owns protected evidence. | PostgreSQL state determines usability; MinIO is never a browser endpoint. |

## HTTP Failure Contract

The application and realtime boundaries use standard HTTP transport semantics
without a project-specific error framework:

| Status | Contract |
|---|---|
| `401` | Authentication is missing or invalid. |
| `403` | The authenticated principal lacks permission. |
| `413` | The request exceeds an accepted payload bound. |
| `422` | Request validation fails. |
| `429` | The applicable rate limit is exceeded. |
| `5xx` | An internal or upstream technical failure occurred. |

An admitted capture/search request returns `2xx` with a compact typed domain
result even when its outcome is `busy`, `deadline`, `unacceptable_query` or
`insufficient_results`. These outcomes are not transport errors. `429` is a
rate-limit rejection, while `busy` describes the valid request's singleton-slot
condition; `422` is request validation failure, while `unacceptable_query`
describes evaluated query quality. Clients make decisions from the HTTP status
and typed outcome; response prose, especially `5xx` text, is never a control
contract. A technical failure may also be persisted on the core Attempt for
diagnostics, but its transport signal remains `5xx`.

Feature-level endpoint design may define the smallest required success payload,
but MUST NOT add a shared custom error envelope, error-code registry or mapping
framework. Contract verification must cover representative standard-status
mappings and prove that admitted non-success capture/search outcomes remain
domain outcomes.

## Cross-Slice Orchestration

### Independent Photo admission

`inventory` is the orchestration owner:

1. read immutable `IngestTarget` from `serving_control`;
2. persist the unique Photo and ask `processing` to create its serving
   `pending` state in one short PostgreSQL transaction;
3. return the per-file accepted/rejected/duplicate outcome.

No HTTP handler, shared helper or composition root owns this flow.

### Participant Promo

`promo` is the orchestration owner:

1. read immutable serving and active-Photo projections;
2. call `processing` for one exact compatible reference search;
3. persist core Attempt/result/session;
4. write detailed diagnostics best-effort through `diagnostics`.

`promo` cannot make a Photo active or mutate pipeline/search rules.

### Calibration and serving change

`diagnostics` owns evidence selection and recommendation. It calls
`processing` for offline evaluation. Only `serving_control` may apply a
developer-confirmed setting through its audited command.

### Photo Inventory Operations

`inventory` owns the operator-visible outcome:

- effective `captured_at` is reliable EXIF in the СПА timezone, otherwise the
  file's server-side upload-start time, otherwise 01:00 on `visit_date`;
- photographer soft-delete/restore is restricted to `uploader_id`; an
  operator/developer may act on any Photo in an accessible СПА;
- soft delete/restore changes only the inventory-owned active marker;
  participant-facing search, participant media access and recent-statistics
  reads must filter the marker;
- restore-all clears the marker for every soft-deleted Photo in the project;
- hard purge starts one confirmed fixed-snapshot global run, waits for the
  shared worker, then calls `processing` to remove derived state and `promo` to
  remove every result/session containing the Photo before final Photo/media
  removal;
- no command is sent to `diagnostics`: core Attempts and diagnostic evidence
  remain under their ordinary retention rules.

The global run is the only purge recovery state. It stores enough durable
snapshot/progress identity to resume after restart but creates no per-photo
`purge_pending` transition or purge jobs table. New soft deletes are outside a
running snapshot.

## Recent Statistics Read Contract

The `inventory` read boundary returns separate 1-, 5- and 60-minute values for
one СПА. Every counter excludes soft-deleted Photos:

| Counter | PostgreSQL source meaning |
|---|---|
| `new` | Unique Photo with `accepted_at` inside the window. |
| `unprocessed` | Photo accepted inside the window and currently `pending \| processing`. |
| `processed` | Photo whose current processing state transitioned to `ready \| no_faces` inside the window. |
| `failed` | Photo whose current processing state transitioned to `failed` inside the window. |

The Admin UI polls this read boundary every five seconds. Direct PostgreSQL
aggregation is the initial contract; WebSocket, SSE, a metrics store and
materialized counters are outside the pilot.

## Hard-Purge Runtime Contract

- Confirmation fixes all currently soft-deleted Photos across every СПА.
- If the shared worker is busy, purge waits without preemption and the UI shows
  `Начну удаление, как только закончится процесс {human-readable process name}`.
- During execution, destructive settings are replaced by completed/total
  progress for the fixed snapshot.
- Restart resumes the same run and may repeat idempotent cleanup.
- An upload already in progress is not interrupted. Ordinary uploads may
  continue and accumulate normal `pending` work while purge occupies the
  worker.
- Hard purge removes Photo, original/preview/thumbnail, faces, pipeline states
  and affected Promo results/sessions. It preserves core Attempts and
  diagnostic evidence; historical references may remain but deleted media is
  unavailable.

## Runtime Context Rules

- Future code discovery roots are documented in the
  [system architecture](../architecture/system-architecture.md); they are not
  task hard write boundaries.
- Post-pilot payment/original delivery, standalone selfie search, external
  ingest, tracking/clustering and speculative infrastructure cannot enter pilot
  work implicitly.
- Stop when implementation would change accepted ownership, public/session
  behavior, searchable truth, authorization, retention or irreversible
  deletion behavior without an operator decision.
