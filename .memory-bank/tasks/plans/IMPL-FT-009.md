---
description: Implementation plan for non-blocking structured server events, bounded developer search and expiry.
status: active
last_updated: 2026-09-02
---
# IMPL-FT-009 — Minimal Structured Server Events

## Goal

Let an authorized developer inspect recent important redacted server events and
navigate correlated events into FT-008, while event enqueue, writer and
persistence latency/failure never changes the participant outcome and every
retained row expires through the existing cleanup command after 30 days.

## Normative Basis And Canonical Coverage

- [FT-009](../../features/FT-009.md): `FT-009-AC-001..004` and governing
  `REQ-LOG-001`, `REQ-DATA-001` and `REQ-ARCH-001`.
- [System Architecture](../../architecture/system-architecture.md): AD-007,
  AD-010, AD-013, capability ownership and runtime composition.
- [Boundary Map](../../contracts/boundary-map.md): module inventory,
  Participant Promo, Diagnostic evidence and access, Retention cleanup, shared
  PostgreSQL, authentication/delivery and HTTP failure contracts.
- [Structured Server Events](../../domains/structured-server-events.md): new
  subject data spec for the exact owner table, fixed catalog, non-blocking
  emitter, redaction and owner expiry. No prior canonical data spec defined
  this shape.
- [Server Event API](../../contracts/server-event-api.md): new subject contract
  for the exact developer route, bounded filters, FT-008 navigation, role
  isolation and failures. No prior canonical staff surface defined it.
- [Diagnostic Retention API](../../contracts/diagnostic-retention-api.md):
  reused command/result and extended diagnostics owner deletion without a new
  field, command or timer.
- [Attempt Investigation API](../../contracts/attempt-investigation-api.md):
  reused unchanged FT-008 target routes.
- [Staff Access](../../domains/staff-access.md), [Lifecycle
  Map](../../states/lifecycle-map.md), [Client Realtime
  Verification](../../testing/client-realtime.md) and [Testing
  Index](../../testing/index.md): reused authentication, retention and evidence
  contracts.

| Concern | Action | Canonical path | Reason |
|---|---|---|---|
| Event data, catalog, emission and owner expiry | create | `.memory-bank/domains/structured-server-events.md` | No existing subject spec defined the fixed row or non-blocking diagnostics writer. |
| Staff event search/navigation | create | `.memory-bank/contracts/server-event-api.md` | Existing FT-008 and retention APIs do not define the FT-009 route/filter/failure surface. |
| Cleanup orchestration and latest result | extend | `.memory-bank/contracts/diagnostic-retention-api.md` | The accepted command already carries the technical cutoff and count; only owner deletion was missing. |
| Module ownership and edges | extend | `.memory-bank/contracts/boundary-map.md` | Add direct subject links and deletion detail under existing owners/edges without topology change. |
| FT-008 target, staff sessions, lifecycle and verification | reuse | existing registered specs | Their current shapes are sufficient and are not changed by FT-009. |

The Boundary Map is extended only with direct subject links and the event
deletion detail under existing headings. Module identities, ownership, the
`promo -> diagnostics` and `diagnostics -> staff_access` edges and Global
Backbone Planning Revision `4` remain unchanged. Foundation final gate
`TASK-002-T2-FT-000-W0` is `done` and every task retains it transitively.

## Scope And Non-Goals

In scope are one fixed event envelope/catalog, one diagnostics-owned PostgreSQL
table/repository, one bounded non-waiting process-local writer per emitting
role, producer wiring at accepted runtime/realtime/Promo/display/QR outcomes,
the minimum next-linear correction that makes the accepted correlation-only
row valid in PostgreSQL and matching ORM/envelope validation, one developer-only
server-rendered search page, exact bounded filters and navigation, and owner
deletion through the current retention result.

There is no browser-log ingestion, arbitrary message/payload, Python root-log
capture, full-text query, JSON API, detail route, pagination, live tail,
dashboard, export, read model, second datastore, broker, reliable outbox,
internal scheduler, new runtime role or production-only configuration. No
behavior JSON is needed because correlation/no-correlation, invalid filters,
blocked sink and expiry are exact in the feature and canonical specs.

## Architecture And Ownership

All three outcomes are primarily owned by `diagnostics`, rooted at
`src/face_moment/diagnostics/`. Promo producers call the existing diagnostics
application boundary and remain owners of Attempt/result/session/QR state.
Diagnostics owns event validation, background persistence, search authorization
and row deletion. Entrypoints bind lifecycle/HTTP adapters only.

The correlation-shape correction is provider-local to diagnostics. It adds one
revision after the actual direct Alembic predecessor, updates matching
SQLAlchemy/envelope validation and preserves migration 0018 as history. It adds
no new module edge, payload, event code, owner lookup or product behavior.

Promo remains the owner of QR/Attempt correlation. It may execute the one
accepted explicit bounded owner lookup after the owner outcome is known, then
pass only immutable UUID primitives to diagnostics. That ordinary owner access
is not event persistence; diagnostics still never reads promo tables. Realtime
entrypoint sequencing snapshots the same primitives before commit so its
post-commit event handoff needs no ORM refresh.

The server-event page obtains the current principal through the accepted
`diagnostics -> staff_access` edge. It links to the FT-008 routes but does not
read promo tables, validate target existence or embed Attempt detail. The
retention command remains orchestrated by `promo`; it supplies both fixed
cutoffs, diagnostics deletes only its own event/evidence rows, and promo records
the confirmed count without a cross-owner write. Provider propagation stops at
the existing typed diagnostics call, current-principal projection, unchanged
FT-008 URL contract and unchanged cleanup result shape.

## Execution-Cohesive Slicing And Claims

| Task | Tier | Wave | Direct prerequisites | Exact owned claim | Outcome |
|---|---|---|---|---|---|
| `TASK-090-T3-FT-009-W1` | T3 | W1 | completed QR, realtime evidence and retention/migration seams | historical failed ownership of `FT-009-AC-002` | Preserve the exhausted-retry collection implementation and verifier evidence; this identity is not executable. |
| `TASK-094-T3-FT-009-W1` | T3 | W1 | completed QR, realtime evidence and retention/migration seams; current TASK-090 implementation/evidence as bounded repair input | replacement ownership of `FT-009-AC-002` | Finish only producer integration: primitive realtime handoffs, explicit bounded QR owner correlation and removal of diagnostics-only transient Promo state. |
| `TASK-095-T3-FT-009-W1` | T3 | W1 | closed `TASK-094` persistence/producer baseline | accepted correlation-only persistence obligation in `.protocols/FT-009/clarification.md#finding--correlation-only-persistence-shape`; no feature AC reassignment | Add one next-linear Alembic correction plus matching ORM/envelope validation and focused persistence regression evidence. |
| `TASK-091-T3-FT-009-W2` | T3 | W2 | `TASK-089`, `TASK-094` and completed `TASK-095` | `FT-009-AC-001`, `FT-009-AC-004`; exact invalid-filter and sanitized-failure obligations | Resume the preserved Attempt 1 only after TASK-095 closes, then expose the complete developer-only bounded HTML search/navigation flow, including truthful uncorrelated rows. |
| `TASK-093-T3-FT-009-W3` | T3 | W3 | `TASK-091` staff search plus completed owner-ordered cleanup | `FT-009-AC-003` | Delete correlated and uncorrelated server events at the fixed 30-day cutoff, report the confirmed count and prove current/bookmarked browser non-recovery. |

The original collection boundary was execution-cohesive, but its normal retry
budget is exhausted. The replacement does not reslice the finished migration,
repository, queue/writer, catalog or redaction work: it isolates only the
evidence-backed producer correction needed to make that same material outcome
acceptable. Realtime snapshots UUID/state primitives before commit and emits
after commit without ORM access. QR uses an explicit bounded promo-owner query
instead of diagnostics-only transient attributes on `PromoSession` or payload
on `PromoBrowserAccessExpiredError`. Query and HTML remain one W2 surface;
destructive expiry remains the unchanged W3 outcome. Tests, RED/GREEN probes and
browser evidence stay with their implementing tasks. No production-only work is
introduced, so there is no `Production acceptance:` task.

TASK-095 stays in W1 because it repairs the collection provider consumed by the
W2 search result; moving TASK-091 or TASK-093 would rewrite their established
identities without adding ordering value. TASK-095 is T3 because its
next-linear constraint migration changes deployed runtime persistence even
though the correction is bounded, reversible in disposable proof and has no
data-loss intent. Adding TASK-095 to the already `in_progress` TASK-091
dependency set is the required explicit `rebuild_required` action; TASK-091's
lifecycle and evidence are otherwise immutable.

## Advisory Expected Change Surface

- `migrations/versions/0018_structured_server_events.py`;
- `migrations/versions/0019_allow_correlation_only_server_events.py` as the
  expected next-linear correction without rewriting 0018;
- `src/face_moment/diagnostics/server_events.py`, package exports and a bounded
  diagnostics-owned writer lifecycle;
- existing runtime/realtime/Promo/display/QR producer seams and backend/
  realtime entrypoint bindings;
- bounded producer repair in `promo/realtime_orchestration.py`,
  `entrypoints/realtime.py`, `promo/qr_continuation.py`, `promo/session.py`,
  `promo/attempt_queries.py` and their focused tests;
- `src/face_moment/diagnostics/server_event_search.py`, diagnostics HTTP adapter
  and backend route registration;
- existing diagnostics/promo retention services;
- focused `tests/diagnostics/` and `tests/promo/` fixtures.

These paths are advisory and non-exhaustive. Executors may choose clearer
purpose-named files while preserving the owner, public boundaries and proof
paths. No hard write boundary is inferred from this list.

## Tests, Gates And UAT

- Migration/repository fixtures use a disposable PostgreSQL database, resolve
  the actual direct Alembic predecessor and prove exact fields, constraints,
  indexes, catalog projections and restart persistence.
- The correction fixture upgrades only from its direct predecessor, proves the
  correlation-only row through the envelope/repository/database, preserves
  seeded accepted rows, removes the new-shape fixture before downgrade and
  proves downgrade without making its revision the mutable exact-head gate.
- One producer matrix covers every catalog code and verifies fixed severity/
  component/correlation plus complete exclusion of credentials, tokens,
  participant/session data, images, embeddings, request bodies and arbitrary
  payloads.
- A diagnostics-writer latch, full queue and database failure prove the
  participant call and owner transaction finish unchanged before persistence is
  released, without retry, rollback or response mutation. The accepted explicit
  promo-owner QR query is traced separately and is not held as a writer-failure
  fixture.
- A real PostgreSQL all-SQL latch proves realtime admitted and terminal event
  enqueue performs no post-commit ORM refresh or other event-assembly SQL.
  Source/runtime checks prove producer helpers consume primitives and no
  diagnostics-only correlation/event-decision state remains on `PromoSession`
  or `PromoBrowserAccessExpiredError`.
- Search fixtures cover default/custom intervals, every filter, conjunctive
  behavior, deterministic ties, the 100-row cap, invalid filters and sanitized
  failures.
- Authorization/browser fixtures use disposable current developer/operator/
  photographer sessions, revocation/downgrade, copied URLs and current/stale
  pages. `playwright cli` proves filter/table/FT-008 navigation and no-link
  behavior using only synthetic redacted rows.
- Retention fixtures cover strict before/equal/after boundaries, correlated and
  uncorrelated rows, owner failure, overlap, partial convergence, safe rerun,
  exact `technical_logs_deleted` and stale-search absence. `playwright cli`
  drives one current search and the same bookmarked filter URL before/after
  cleanup, retaining redacted transcript/screenshots under the W3 task without
  re-owning the W2 search claims.
- Every task runs focused pytest, full Python mypy and Memory Bank lint. The
  repository has no separate project-native architecture command; ownership
  and import checks remain explicit verification targets.

## Constitution Constraints And Invariants

- Keep one modular monolith, one PostgreSQL schema/Base/Alembic stream and one
  writer per mutable invariant; no direct producer table write or cross-owner
  cascade is allowed.
- Event persistence is best-effort. Queue/sink latency, capacity exhaustion,
  failure and shutdown never delay, retry or change capture/search/Promo/QR.
- Only the fixed typed catalog reaches storage. Browser events, arbitrary
  messages/payloads and every forbidden protected value remain absent.
- Current developer authorization is evaluated on every search. Browser cache,
  copied URLs, revoked/downgraded sessions and expired rows grant no retained
  access or recovery.
- Retention uses the fixed UTC cutoff, deletes owner rows only, preserves the
  existing latest-result shape and adds no scheduler/history/tombstone.

## Definition Of Done

The executable replacement, correlation-shape prerequisite and unchanged W2/W3
cards satisfy their exact claims and tier obligations; failed TASK-090 remains
historical evidence rather than an executable owner; every
`FT-009-AC-001..004` has one current executable owner without assigning a
second AC to TASK-095; task-relevant modules, edges and contract headings
resolve; the migration stream remains linear; dependencies are acyclic and
retain Foundation; feature design remains `complete`; Planning Revision remains
`4`; and fresh `/review-tasks-plan FT-009` can return `APPROVE` without
implementation guesses.

## Current Delivery State

The producer/persistence slice `FT-009-AC-002` is complete through TASK-094.
TASK-090 remains failed historical evidence. TASK-095 is planned as the minimum
provider correction. TASK-091 remains `in_progress` with Attempt 1 stopped
before production implementation and cannot resume until TASK-095 is done;
TASK-093 remains planned behind TASK-091. The feature itself remains
incomplete.
