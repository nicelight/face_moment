---
description: Diagnostics-owned structured server-event persistence, non-blocking emission and retention data contract.
status: active
last_updated: 2026-09-01
source_of_truth:
  - .memory-bank/domains/structured-server-events.md
---
# Structured Server Events

## Scope And Owner

`diagnostics` owns the fixed server-event envelope, its PostgreSQL rows, the
non-blocking application boundary and deletion of expired rows. Producers call
that public boundary; they MUST NOT write the table directly or make event
persistence part of a participant transaction. The browser sends no events.

The runtime persistence path is `face_moment.server_events` through the
diagnostics repository. This is a bounded operational event set, not
DiagnosticEvidence, an Attempt read model, a generic logging sink or a second
observability datastore.

## PostgreSQL Shape And Search Projection

One next-linear Alembic revision creates:

| Field | Contract |
|---|---|
| `event_id` | Server-generated UUID primary key. |
| `occurred_at` | UTC server timestamp captured before enqueue. |
| `severity` | `info \| warning \| error`. |
| `component` | `runtime \| realtime \| promo \| qr`. |
| `event_code` | One exact code from the catalog below. |
| `release_id` | Non-empty bounded release identifier, at most 128 characters. |
| `attempt_id` | Nullable server `PromoAttempt.id` UUID supplied by the promo owner when known. |
| `correlation_id` | Nullable client correlation UUID supplied by the promo owner when known. |

There is no message, payload, JSON, traceback, object key, URL, request field or
participant/session field. Attempt identities are logical cross-owner
references without a foreign key or delete cascade. Either identity may be
null; both null means the event is truthfully uncorrelated.

The owner repository publishes immutable projections and applies filters before
returning rows. It indexes `occurred_at`, exact Attempt/correlation identity and
the bounded severity/component/code search paths. Results order by
`occurred_at DESC, event_id DESC`; the exact external bound and filter behavior
are owned by the [Server Event API](../contracts/server-event-api.md).

## Event Catalog And Producer Boundary

The initial catalog is deliberately small:

| Event code | Severity | Component | Correlation rule |
|---|---|---|---|
| `runtime.readiness_closed` | `warning` | `runtime` | Uncorrelated because no core Attempt is admitted. |
| `attempt.admitted` | `info` | `realtime` | Both identities when the core Attempt exists. |
| `attempt.failed` | `error` | `realtime` | Both identities from the terminal core Attempt. |
| `promo.result_issued` | `info` | `promo` | Both identities after result/session commit. |
| `promo.display_confirmed` | `info` | `promo` | Both identities after the accepted display outcome. |
| `qr.session_opened` | `info` | `qr` | Existing Attempt identities only; no ticket, cookie or session identity. |
| `qr.session_expired` | `warning` | `qr` | Existing Attempt identities when available; otherwise uncorrelated. |

Producers emit only after the corresponding owner state/outcome is known. They
cannot supply severity/component independently of the event code, add a new
field or attach free-form context. A new code changes this catalog and its
redaction test inventory before producer wiring.

## Non-Blocking Emission

Each emitting server process binds one diagnostics-owned emitter to one fixed
capacity `256` process-local FIFO. Emission validates the typed envelope and
uses a non-waiting enqueue. A separate diagnostics writer owns its database
session and commits event rows independently of the caller transaction.

- A full/unavailable queue, rejected envelope, sink latency, database failure or
  shutdown may lose an event and returns a local unsuccessful result.
- The producer MUST ignore that result for capture, search, Promo, display and
  QR behavior and MUST NOT retry, wait, roll back or change its response.
- The writer rolls back its own failed transaction and may continue with later
  events. There is no outbox, delivery guarantee, broker, internal scheduler,
  second runtime role or shutdown-drain guarantee.
- Backend and realtime entrypoints bind lifecycle wiring only. Entrypoints and
  generic infrastructure own no event selection, redaction or persistence
  rule.

Controlled proof holds the sink behind a latch while the producer completes,
then exercises queue-full and database-failure branches. Wall-clock subtraction
or an arbitrary performance threshold is not the proof method.

## Redaction And Validation

The fixed typed envelope is the redaction boundary. Every catalog entry is
tested, and an invalid field/code is rejected before enqueue. Rows MUST NOT
contain credentials, authorization headers, cookies, tokens, infrastructure
access, participant names, annotations, commercial Photo media, personalized
session data, images/crops, embeddings, request bodies, arbitrary payloads,
tracebacks or replay content. Capture-derived media is also absent even though
its separate classification does not make it developer-only.

Browser logs, Python root-logger capture, arbitrary application messages and
automatic exception serialization are outside this boundary. Task artifacts
use synthetic UUIDs/releases and retain no production event rows or protected
values.

## Retention Boundary

The existing owner-ordered cleanup passes the fixed UTC technical-event cutoff
to `diagnostics`. The diagnostics owner deletes `server_events` strictly before
that 30-day cutoff independently of Attempt/evidence candidates, including
uncorrelated rows, and returns `technical_logs_deleted` to the existing promo-
owned latest result. Equal-cutoff rows remain.

Deletion is idempotent and safe to rerun. A partial owner failure remains a
sanitized failed cleanup result; a later run converges without restoring rows or
inventing counts. Current or stale server-event search URLs cannot reconstruct
deleted rows from Attempts, DiagnosticEvidence, task artifacts or browser
cache.

## Verification Targets

- Migration/repository fixtures prove the exact table, constraints, catalog,
  indexes, restart persistence, bounded immutable query projection and absence
  of ownership-crossing foreign-key cascades.
- A per-code inventory proves fixed severity/component, allowed correlation and
  complete forbidden-field absence for every emitted event type.
- Blocked-sink, full-queue and failed-database fixtures prove unchanged caller
  transaction, participant response/outcome and completion while the writer
  remains isolated.
- Controlled-time cleanup proves before/equal/after cutoff behavior,
  uncorrelated deletion, exact latest-result count, failure/rerun convergence
  and no stale-search recovery.
