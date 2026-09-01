---
description: Implementation plan for non-blocking structured server events, bounded developer search and expiry.
status: active
last_updated: 2026-09-01
---
# IMPL-FT-009 — Minimal Structured Server Events

## Goal

Let an authorized developer inspect recent important redacted server events and
navigate correlated events into FT-008, while event collection never delays the
participant flow and every retained row expires through the existing cleanup
command after 30 days.

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
one developer-only server-rendered search page, exact bounded filters and
navigation, and owner deletion through the current retention result.

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
| `TASK-090-T3-FT-009-W1` | T3 | W1 | completed QR, realtime evidence and retention/migration seams | `FT-009-AC-002` | Persist the fixed event catalog through an isolated non-blocking diagnostics writer and wire accepted producers without changing participant outcomes. |
| `TASK-091-T3-FT-009-W2` | T3 | W2 | `TASK-090` and the planned FT-008 staff surface | `FT-009-AC-001`, `FT-009-AC-004`; exact invalid-filter and sanitized-failure obligations | Expose the complete developer-only bounded HTML search/navigation flow, including truthful uncorrelated rows. |
| `TASK-093-T3-FT-009-W3` | T3 | W3 | `TASK-091` staff search plus completed owner-ordered cleanup | `FT-009-AC-003` | Delete correlated and uncorrelated server events at the fixed 30-day cutoff, report the confirmed count and prove current/bookmarked browser non-recovery. |

The row/repository, emitter and producer wiring remain one collection result:
splitting them would leave a storage-only intermediate with no accepted feature
outcome under the same owner. Query and HTML remain one surface because there is
no JSON API, read model or separate frontend. Destructive expiry is independently
completable and provable, so it remains separate. Its W3 dependency on the W2
search surface is proof-required: AC-003 owns current/bookmarked route
non-recovery and cannot execute that browser proof before the route exists.
Tests, RED/GREEN probes and browser evidence stay with their implementing tasks.
No production-only work is introduced, so there is no `Production acceptance:`
task.

## Advisory Expected Change Surface

- `migrations/versions/0018_structured_server_events.py`;
- `src/face_moment/diagnostics/server_events.py`, package exports and a bounded
  diagnostics-owned writer lifecycle;
- existing runtime/realtime/Promo/display/QR producer seams and backend/
  realtime entrypoint bindings;
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
- One producer matrix covers every catalog code and verifies fixed severity/
  component/correlation plus complete exclusion of credentials, tokens,
  participant/session data, images, embeddings, request bodies and arbitrary
  payloads.
- A sink latch, full queue and database failure prove the participant call and
  owner transaction finish unchanged before persistence is released, without
  retry, rollback or response mutation.
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

All three indexed cards satisfy their exact claims and tier obligations; every
`FT-009-AC-001..004` is owned exactly once; task-relevant modules, edges and
contract headings resolve; the migration stream remains linear; dependencies
are acyclic and retain Foundation; feature design remains `complete`; Planning
Revision remains `4`; and fresh `/review-tasks-plan FT-009` can return
`APPROVE` without implementation guesses.
