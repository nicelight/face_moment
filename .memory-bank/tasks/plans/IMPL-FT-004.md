---
description: Implementation plan for scoped realtime search and result assembly in FT-004.
status: active
last_updated: 2026-08-29
---
# IMPL-FT-004 — Scoped Realtime Search And Result Assembly

## Goal

Complete the admitted realtime path after FT-003: let an operator control the
active server date, select and prepare at most five proposals through the
committed native pipeline, search only compatible active ready inventory,
assemble four unique teasers and truthful `N`, publish one durable result
session, and return explicit bounded outcomes under one slot and deadline.

## Normative Basis

- [FT-004](../../features/FT-004.md): `FT-004-AC-001..008` and governing
  `REQ-SRCH-001..003`, `REQ-CAP-003`, `REQ-PERF-001`, `REQ-REL-001`,
  `REQ-DIAG-001`, `REQ-SEC-001` and `REQ-ARCH-001`.
- [System Architecture](../../architecture/system-architecture.md): AD-001,
  AD-002, AD-006..011 and capability ownership.
- [Boundary Map](../../contracts/boundary-map.md): modules, dependency graph,
  capability application boundaries, active search date, Participant Promo,
  shared PostgreSQL, runtime/authentication and HTTP failure contracts.
- [Realtime Attempt API](../../contracts/realtime-attempt-api.md): exact public
  request, idempotency, typed outcome and result response.
- [Realtime Reference Search](../../domains/realtime-search.md): immutable
  context, native query preparation, selection and exact search.
- [Promo Attempt](../../domains/promo-attempt.md): Attempt lifecycle, singleton,
  result assembly, session persistence and restart rules.
- [Display Client Access](../../domains/display-client-access.md),
  [Photo Processing](../../domains/photo-processing.md),
  [Lifecycle Map](../../states/lifecycle-map.md),
  [Testing Router](../../testing/index.md) and
  [Client Realtime Verification](../../testing/client-realtime.md).

Global Backbone Planning Revision remains `4`. Foundation final gate
`TASK-002-T2-FT-000-W0` and the required FT-001..FT-003 substrate dependencies
are already `done`.

## Scope And Non-Goals

In scope are the accepted staff active-date surface, native reference-query
operations, exact scoped pgvector search, pHash ranking observations, result
assembly, Promo session persistence, singleton/deadline/restart behavior and
the complete authenticated realtime response path.

FT-005 owns display rendering, acknowledgement, cooldown and the joint QR
latency verdict. FT-006 owns QR browser access and phone continuation. FT-007
owns detailed diagnostic evidence. This plan adds no client-side selection,
tracking, clustering, ANN, cache, waiter queue, replay, model fallback, generic
configuration platform, custom error framework or production deployment work.

No behavior JSON is needed: the canonical mixed-scope, selection, candidate,
concurrency, restart and controlled-corpus fixtures already remove the material
ambiguity.

## Architecture And Ownership

The accepted graph is unchanged. `serving_control` owns active-date mutation;
`processing` owns native query preparation, selection and exact compatible
search; `promo` owns slot/deadline orchestration, Attempt transitions, result
assembly and sessions. The final route is technical wiring over the
`promo -> serving_control|processing|inventory|diagnostics` Participant Promo
boundary and MUST NOT move business orchestration into the FastAPI handler,
composition root or a generic helper.

Expected owner roots are `src/face_moment/serving_control/`,
`src/face_moment/processing/` and `src/face_moment/promo/`. The existing
`src/face_moment/entrypoints/realtime.py` only binds adapters/lifecycle and
exposes the public route. `inventory` and `serving_control` projections are
read-only to processing; foreign mutable state is never written directly.

## Execution-Cohesive Slicing And Unique Claims

| Task | Tier | Wave | Direct prerequisites | Exact owned claim | Outcome |
|---|---|---|---|---|---|
| `TASK-068-T3-FT-004-W1` | T3 | W1 | `TASK-004-T3-FT-001-W2`, `TASK-042-T2-FT-003-W1` | Boundary Map `Staff active-date surface` | Authorized GET/PUT/UI control of the server-owned active date. |
| `TASK-069-T2-FT-004-W1` | T2 | W1 | `TASK-019-T2-FT-002-W2`, `TASK-020-T2-FT-002-W2`, `TASK-026-T3-FT-002-W5`, `TASK-060-T2-FT-003-W2` | Realtime Search `Native reference-query operations` and `Server-authoritative occurrence selection` | Native crop inspection/preparation and deterministic at-most-five selection. |
| `TASK-070-T2-FT-004-W2` | T2 | W2 | `TASK-069-T2-FT-004-W1`, `TASK-027-T2-FT-002-W4` | `FT-004-AC-001`, `FT-004-AC-002` | Exact compatible search and complete typed match observations with pHash. |
| `TASK-071-T2-FT-004-W3` | T2 | W3 | `TASK-070-T2-FT-004-W2` | `FT-004-AC-003` | Four unique teasers and complete truthful union/`N`. |
| `TASK-072-T3-FT-004-W4` | T3 | W4 | `TASK-071-T2-FT-004-W3`, `TASK-043-T2-FT-003-W1` | Promo Attempt `Atomic result-session publication` | One durable session and atomic/idempotent result publication. |
| `TASK-073-T3-FT-004-W3` | T3 | W3 | `TASK-070-T2-FT-004-W2`, `TASK-043-T2-FT-003-W1` | `FT-004-AC-007` | One non-blocking slot, typed busy, one deadline and fresh acquisition. |
| `TASK-074-T3-FT-004-W1` | T3 | W1 | `TASK-043-T2-FT-003-W1` | `FT-004-AC-008` | Startup interruption of stale Attempts without inference replay or late result. |
| `TASK-075-T3-FT-004-W5` | T3 | W5 | `TASK-045-T3-FT-003-W3`, `TASK-057-T3-FT-003-W2`, `TASK-060-T2-FT-003-W2`, `TASK-068-T3-FT-004-W1`, `TASK-072-T3-FT-004-W4`, `TASK-073-T3-FT-004-W3`, `TASK-074-T3-FT-004-W1` | `FT-004-AC-005..006` | Full authenticated route, typed outcomes and security are development outcomes; TASK-075 becomes `done_for_prod` once those dev claims pass their T3 gates. |
| `TASK-088-T3-FT-004-W6` | T3 | W6 | `TASK-075-T3-FT-004-W5` | `FT-004-AC-004` | Final production-only acceptance of the authorized same-twenty server-correctness corpus and 19/20 result. |

`TASK-069` owns the native selection seam; `TASK-070` owns the feature-level
processing integration delta and may exercise the completed seam without
adopting its proof. `TASK-075` similarly composes completed dependencies without
re-owning their exact claims.

## Advisory Expected Change Surface

- `src/face_moment/serving_control/active_search_date.py`,
  `src/face_moment/serving_control/http.py`, `tests/serving_control/`
- `src/face_moment/processing/reference_query.py`,
  `src/face_moment/processing/realtime_search.py`, direct native adapters,
  `tests/processing/`
- `src/face_moment/promo/result_assembly.py`,
  `src/face_moment/promo/session.py`,
  `src/face_moment/promo/realtime_orchestration.py`,
  `src/face_moment/promo/startup_recovery.py`, `tests/promo/`
- the next linear `migrations/versions/*_promo_sessions.py` revision and
  `src/face_moment/entrypoints/realtime.py`

These paths are advisory and non-exhaustive. The session migration extends the
single linear stream with its direct predecessor as resolved at execution; the
current observed predecessor is `0012_promo_attempts`. Verification checks its
own upgrade/downgrade/re-upgrade and data preservation, never a mutable future
exact-head requirement.

## Tests, Gates And UAT

- Every task runs configured Python mypy, its focused pytest target and
  `node .memory-bank/scripts/mb-lint.mjs`.
- `TASK-068` uses task-owned staff/СПА state and `playwright cli` for the real
  same-origin operator flow, preserving screenshots/transcript under its task
  artifact directory.
- Processing fixtures cover both native adapters, ordering/ties/repeated-person
  selection, mixed revision/СПА/date/visibility/state scope, threshold inclusion
  and deterministic pHash output.
- Promo fixtures cover repeated Photo matches, diversity ties, insufficient
  pools, atomic result publication, idempotent repeats, busy/no-waiter, deadline
  discard and startup interruption.
- `TASK-075` sends direct requests through the available development/test edge,
  proves token-derived scope/rate/redaction and typed non-success behavior, and
  does not run the production-only correctness corpus before deployment. After
  deployment, the authorized acceptance run retains one stable twenty-row
  corpus; each row names all four teasers and every union member, the manual
  reviewer role and pass/fail comparison. Missing group-member coverage
  remains allowed.
- FT-004 closure does not claim the later FT-005 join of these Attempt IDs to
  fully-visible/scannable QR latency evidence.
- All stateful probes use unique disposable PostgreSQL/application records,
  are safe to rerun, expose the decisive stored/result state and remove only
  their own fixtures. No shared operator/default database is downgraded.

## Constitution Constraints And Invariants

- Keep the modular monolith, one schema/Base/Alembic stream, exact search and
  one owner per mutable invariant.
- Use only the committed validated pre-warmed pipeline and its native path;
  never mix revisions or add fallback/ensemble behavior.
- Derive `spa_id` only from the authenticated display token and never log token
  material or accept a body override.
- pHash ranks only threshold-valid Photos; four teaser IDs remain a subset of
  the complete unique union and `N` equals its cardinality.
- One slot has no waiter queue; deadline/restart never publishes a late session
  and only a fresh request may run later.
- Detailed diagnostics remain best-effort; their absence cannot roll back a
  valid participant outcome.

## Definition Of Done

All eight implementation cards satisfy their development claims and tier
obligations; `TASK-075` is `done_for_prod` after AC-005/AC-006 development
verification and semantic review, while `TASK-088` remains the explicit planned
production acceptance card for AC-004. Every `FT-004-AC-001..008` remains owned
exactly once; every task retains the completed Foundation gate directly or
transitively; task-relevant modules and edges match the accepted Boundary Map;
the feature remains `spec_design_status: complete`; and fresh
`/review-tasks-plan FT-004` can evaluate the queue at Planning Revision `4`
without implementation guesses. FT-004 feature completion is not claimed until
TASK-088 provides the production AC-004 evidence.
