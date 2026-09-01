---
description: Implementation plan for role-scoped Attempt investigation in FT-008.
status: active
last_updated: 2026-09-01
---
# IMPL-FT-008 — Role-Scoped Attempt Investigation

## Goal

Let an operator or authorized developer find one existing Attempt and inspect
the role-allowed state, stages, durations, client markers and existing
DiagnosticEvidence, while every missing, expired or removed detail remains
truthful and current authorization is enforced on each read.

## Normative Basis And Canonical Coverage

- [FT-008](../../features/FT-008.md): `FT-008-AC-001..005` and governing
  `REQ-DIAG-001`, `REQ-DIAG-003`, `REQ-DATA-001` and `REQ-ARCH-001`.
- [System Architecture](../../architecture/system-architecture.md): AD-002,
  AD-007, AD-009 and capability/cross-slice ownership.
- [Boundary Map](../../contracts/boundary-map.md): module inventory,
  capability application boundaries, Diagnostic evidence and access, shared
  PostgreSQL, staff HTTPS and HTTP failure contracts.
- [Attempt Investigation API](../../contracts/attempt-investigation-api.md):
  exact filters, promo query boundary, staff routes, role projections,
  evidence states, failures and browser proof. This subject contract is
  created for FT-008 because no prior canonical staff investigation surface
  defined the necessary HTTP shape.
- [Promo Attempt](../../domains/promo-attempt.md): reused core identity/state
  and timeline projection.
- [Diagnostic Evidence](../../domains/diagnostic-evidence.md): reused owner
  storage and extended the investigation read plus irreversible ordinary-
  removal transition without schema change.
- [Staff Access](../../domains/staff-access.md): reused current principal and
  server-session behavior.
- [Lifecycle Map](../../states/lifecycle-map.md), [Client Realtime
  Verification](../../testing/client-realtime.md) and [Testing
  Index](../../testing/index.md): reused lifecycle, marker and UI evidence
  contracts.

The Boundary Map is extended with the canonical contract link and the feature-
level `diagnostics -> staff_access` edge. Its module inventory, global
ownership, existing `diagnostics -> promo` edge and Planning Revision remain
unchanged. No competing canonical path exists.

Global Backbone Planning Revision remains `4`. Foundation final gate
`TASK-002-T2-FT-000-W0` is `done`; both tasks retain that gate transitively
through their completed FT-007 prerequisites.

## Scope And Non-Goals

In scope are one bounded promo query projection, exact server/correlation/time/
state filters, deterministic ordering/cap, diagnostics composition, current-
role projection, server-rendered staff list/detail, no-store responses, truthful
evidence availability, one internal diagnostics-owned irreversible ordinary-
removal transition and focused automated plus browser proof.

There is no new table, migration, materialized read model, JSON API, public
removal endpoint, arbitrary
query builder, pagination, export, log/artifact navigation, annotations,
Calibration, promoted-subset display, FT-009 server-event UI, media-delivery
mechanism, generic RBAC service or production deployment/configuration work.
No behavior JSON is needed because the feature ACs and canonical contract
already state the exact role/evidence examples.

## Architecture And Ownership

The primary owner of the first outcome is `promo`, rooted at
`src/face_moment/promo/`. It publishes immutable bounded projections and stays
the only writer of core Attempts. The primary owner of the second outcome is
`diagnostics`, rooted at `src/face_moment/diagnostics/`; it composes promo truth
with its own evidence and owns business authorization/projection. The backend
entrypoint only registers the HTTP adapter.

The crossed capability boundaries are the accepted `diagnostics -> promo` and
`diagnostics -> staff_access` edges under
[Diagnostic evidence and access](../../contracts/boundary-map.md#diagnostic-evidence-and-access).
Diagnostics MUST NOT query or write `promo_attempts` directly; promo MUST NOT
read/write `diagnostic_evidence`. The diagnostics HTTP adapter obtains the
current principal through `staff_access`; diagnostics owns business
authorization/projection, while `platform/auth` and the backend composition
root own neither. Changed provider propagation stops at the immutable Attempt
and principal projections consumed by diagnostics.

## Execution-Cohesive Slicing And Claims

| Task | Tier | Wave | Direct prerequisites | Exact owned claim | Outcome |
|---|---|---|---|---|---|
| `TASK-088-T2-FT-008-W1` | T2 | W1 | completed core Attempt/client-timeline provider | Attempt Investigation API `Promo Query Boundary` | Promo publishes the bounded immutable exact-ID/time/state Attempt projection without exposing ORM state or adding persistence. |
| `TASK-089-T3-FT-008-W2` | T3 | W2 | `TASK-088` plus completed evidence attachment and retention behavior | `FT-008-AC-001..005`; exact `404`, `422`, `500` failure obligations | Diagnostics exposes the complete role-scoped staff investigation flow, reachable removed state, current-role isolation and exact sanitized failures. |

The query provider is independently completable and provable, so it remains
separate from its consumer. Diagnostics composition, server-rendered routes and
UI/security proof are one user-visible outcome in the existing backend and do
not justify a separate frontend/read-model task. Tests and RED/GREEN probes stay
with their implementing task. There is no production-only configuration or
external acceptance result, so no final Production acceptance task is created.

## Advisory Expected Change Surface

- `src/face_moment/promo/attempt_queries.py` and promo package exports;
- `src/face_moment/diagnostics/attempt_investigation.py` and a diagnostics HTTP
  adapter;
- `src/face_moment/diagnostics/evidence.py` for the existing-shape owner
  removal transition;
- `src/face_moment/entrypoints/backend.py` route registration;
- `tests/promo/test_attempt_investigation_queries.py`;
- `tests/diagnostics/test_attempt_investigation.py`.

These paths are advisory and non-exhaustive. Exact filenames remain executor
discretion when the accepted owner, public boundary and proof path remain
unchanged. No hard write boundary is inferred from this list.

## Tests, Gates And UAT

- Promo query fixtures seed more than 100 Attempts across identities, times and
  every processing state, then prove conjunctive typed filters, deterministic
  cap/order and complete core timeline projection.
- Diagnostics fixtures compare complete, partial/absent, expired and removed
  evidence, create removed only through the idempotent owner transition, reject
  stale ordinary writes and prove no stale-route recovery.
- Authorization fixtures use disposable operator, developer and photographer
  sessions with known initial roles, a downgrade transition, direct links,
  safe rerun and cleanup limited to those rows.
- Response/HTML checks prove the exact operator/developer field asymmetry,
  `no-store`, sanitized failures and exclusion of promoted subsets, names,
  annotations, Calibration, server events, personalized session data and
  commercial Photo media.
- Route failure injection proves missing-detail `404`, every malformed/
  unsupported/repeated-filter `422` without a provider call, and redacted
  provider/evidence/render `500`, all with `no-store`.
- `playwright cli` drives the real staff filter/table/detail and stale-role
  journey, retaining transcript and screenshots under the T3 task evidence
  directory.
- Focused pytest, full Python mypy and Memory Bank lint are required for each
  task. The repository has no separate project-native architecture command;
  ownership/import checks remain focused verification targets rather than a
  fabricated gate.

## Constitution Constraints And Invariants

- Keep the modular monolith, one shared database schema and one owner per
  mutable invariant; the removal transition stays in diagnostics and adds no
  persistence schema, public mutation route or scheduler.
- The provider returns immutable projections; diagnostics never receives an
  ORM entity or direct foreign-table authority.
- The current principal is evaluated on every request. Browser history, copied
  URLs and role downgrade never preserve prior diagnostic access.
- Client monotonic markers and server timestamps stay separate; nullable stages
  and evidence gaps are never fabricated as complete.
- Expired and removed ordinary content remains inaccessible, while a promoted
  subset never recreates it; only the diagnostics owner transition can create
  removed and stale ordinary writes cannot reverse it.
- Capture-derived content is not developer-only solely because it is image-
  derived, but this feature creates no new storage or delivery path.

## Definition Of Done

Both indexed cards satisfy their exact claims and tier obligations; every
`FT-008-AC-001..005` is owned exactly once; task-relevant modules, edge and
contract headings resolve; dependencies are acyclic and retain Foundation;
feature design remains `complete`; Planning Revision remains `4`; and fresh
`/review-tasks-plan FT-008` returns `APPROVE` without implementation guesses.
