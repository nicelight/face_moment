---
description: Implementation plan for core Attempt timing, best-effort evidence and owner-ordered retention in FT-007.
status: active
last_updated: 2026-08-25
---
# IMPL-FT-007 — Correlated Attempt Evidence

## Goal

Complete the server-admitted Attempt diagnostic foundation: retain the missing
browser response marker, persist a reproducible best-effort evidence bundle,
attach it without affecting Promo and expire ordinary Attempt/evidence data
through one observable owner-ordered cleanup result and activate its external
daily pilot-host timer.

## Normative Basis

- [FT-007](../../features/FT-007.md): `FT-007-AC-001..007` and governing
  `REQ-DIAG-001`, `REQ-DIAG-002`, `REQ-PERF-001`, `REQ-REL-001`,
  `REQ-DATA-001`, `REQ-DIAG-003`, `REQ-SEC-001` and `REQ-ARCH-001`.
- [System Architecture](../../architecture/system-architecture.md): AD-007,
  AD-010, AD-011 and AD-013.
- [Boundary Map](../../contracts/boundary-map.md): capability boundaries,
  Participant Promo, Diagnostic evidence and access, Retention cleanup,
  authentication/delivery and shared PostgreSQL rules.
- [Client Diagnostic API](../../contracts/client-diagnostic-api.md): exact
  authenticated timing report, idempotency, gaps and failures.
- [Diagnostic Evidence](../../domains/diagnostic-evidence.md): owner table,
  versioned bundle, completeness, promoted subset and owner cleanup boundary.
- [Diagnostic Retention API](../../contracts/diagnostic-retention-api.md): exact
  command, latest-result state and staff read contract.
- [Diagnostic Retention Runbook](../../runbooks/diagnostic-retention.md):
  pilot-host timer installation, activation, observation and recovery.
- [Promo Attempt](../../domains/promo-attempt.md),
  [Lifecycle Map](../../states/lifecycle-map.md) and
  [Client Realtime Verification](../../testing/client-realtime.md).

Global Backbone Planning Revision remains `4`. Foundation final gate
`TASK-002-T2-FT-000-W0` is `done`; every FT-007 task retains it directly or
transitively.

## Scope And Non-Goals

In scope are one nullable core response marker, its authenticated best-effort
client report, deterministic core issue tags/gaps, one diagnostics evidence
table and repository, realtime/search/result/display evidence attachment,
complete/incomplete projection, a promoted-subset persistence seam, strict
ordinary 90-day Attempt/evidence cleanup, one latest result, authorized status
page/API and one external daily pilot-host timer.

FT-008 owns Attempts list/detail UI and role-scoped investigation. FT-009 owns
structured-log collection/search and its 30-day implementation. FT-010 owns
annotation behavior. FT-011 owns Calibration selection, promotion UI and
recommendations. FT-012 owns Photo purge. This plan adds no mandatory capture
media, selfie, per-crop logging, replay runner, reliable client outbox, generic
jobs/history table, internal scheduler, second datastore or distributed
tracing.

No behavior JSON is needed: complete/partial/absent evidence, offline delivery,
media absence and retention fixtures are already exact in the feature and
canonical contracts.

## Architecture And Ownership

`promo` remains the only writer of core Attempt timing and the project-wide
latest cleanup result. `diagnostics`, rooted at
`src/face_moment/diagnostics/`, owns detailed evidence and its expiry.
`SpaPromoClient` reports only its browser marker; HTTP and entrypoint code bind
adapters and do not own business state.

The crossed boundaries are the existing `promo -> diagnostics` Participant
Promo and Retention cleanup calls plus the read-only `diagnostics -> promo`
Attempt projection. Diagnostics never writes `promo_attempts`; promo never
writes `diagnostic_evidence`; database cascade never crosses either owner.
Promo supplies its expired core-Attempt candidates to diagnostics; a missing
evidence row is a confirmed owner-local no-op, not a reason to retain the core
Attempt. A project-scoped PostgreSQL advisory lock rejects overlapping cleanup
invocations without replacing the active latest result.

Three sequential migrations follow the already planned FT-006 browser-access
migration: promo response timing, diagnostics evidence and promo latest cleanup
result. Dependencies serialize the shared Alembic stream; executors resolve
the actual direct predecessor at runtime and never require a mutable future
exact head.

## Execution-Cohesive Slicing And Claims

| Task | Tier | Wave | Direct prerequisites | Exact owned claim | Outcome |
|---|---|---|---|---|---|
| `TASK-083-T3-FT-007-W1` | T3 | W1 | completed client timing plus planned FT-005 display and FT-006 migration seams | `FT-007-AC-001`, `FT-007-AC-005` | Authenticated first-write client response timing completes the core timeline while offline delivery remains best-effort. |
| `TASK-084-T2-FT-007-W2` | T2 | W2 | `TASK-083` | `FT-007-AC-007`; Diagnostic Evidence `PostgreSQL Shape And Owner Boundary` | One versioned diagnostics-owned evidence provider with explicit completeness, ordinary privacy enforcement and promoted-subset persistence. |
| `TASK-085-T2-FT-007-W3` | T2 | W3 | `TASK-084` plus completed busy/deadline/restart outcomes | `FT-007-AC-002`, `FT-007-AC-003` | Realtime/search/result/display evidence attaches best-effort without required media or participant-flow impact. |
| `TASK-086-T3-FT-007-W3` | T3 | W3 | `TASK-084` plus completed staff sessions | `FT-007-AC-004` | Owner-ordered ordinary retention covers absent evidence, overlap and authorized latest-result access. |
| `TASK-087-T3-FT-007-W4` | T3 | W4 | `TASK-083`, `TASK-084`, `TASK-085`, `TASK-086` | `FT-007-AC-006` | Production acceptance joins every implementation outcome, then installs and activates the source-managed external daily timer on the authorized pilot host. |

The provider task is independent of its consumer integration and therefore
remains separate. The two W3 outcomes may follow the provider independently:
realtime evidence attachment does not need destructive cleanup, while cleanup
can prove its contract against task-owned evidence fixtures. Production-only
timer activation stays in the final W4 task, depends on the verified command
and has no dependents. Tests and UAT stay with their implementing tasks.

## Advisory Expected Change Surface

- next-linear `migrations/versions/*_promo_attempt_client_timing.py`,
  `*_diagnostic_evidence.py` and `*_retention_cleanup_latest.py` revisions;
- `client/app.js`, `client/attempt-timing.js` and a minimal client diagnostic
  timing sender;
- `src/face_moment/promo/attempt.py`, promo timing/retention application code,
  `src/face_moment/promo/http.py` where available, and realtime/backend wiring;
- `src/face_moment/diagnostics/evidence.py`,
  `src/face_moment/diagnostics/retention.py` and package exports;
- `src/face_moment/processing/realtime_search.py` only if the accepted public
  observation needs a bounded field already produced by processing;
- `src/face_moment/entrypoints/retention_cleanup.py` and backend/realtime route
  registration;
- `deploy/systemd/system/face-moment-retention-cleanup.service`, the matching
  `.timer` and a bounded activation check script;
- focused `tests/client/`, `tests/promo/` and `tests/diagnostics/` fixtures.

Paths are advisory and non-exhaustive. Exact filenames remain executor
discretion when the accepted module owner, public boundary, migration order and
proof path remain unchanged.

## Tests, Gates And UAT

- Timing tests use one controlled browser monotonic clock and disposable
  display-client/core Attempt rows. They prove valid terminal outcomes,
  first/equal/conflicting reports, current-token СПА scope, no-store/redaction,
  missing-report gaps and pre/post-admission disconnect behavior.
- Evidence repository tests use a disposable PostgreSQL database and prove the
  next migration, logical no-cascade relation, partial/final transitions,
  version/size validation, ordinary-name/annotation rejection, curated
  promoted-subset admission, expiry irreversibility and restart persistence.
- Realtime integration fixtures cover result, zero proposals, busy, deadline,
  internal failure, complete/partial/failed finalization, selected/repeated
  detections, candidate pools, teaser/union/`N` and display/QR event. The same
  core participant result is compared before and after forced evidence failure.
- Media inventory and source scans prove no mandatory capture object/cache,
  per-crop log or selfie, and no embeddings, credentials, authentication state,
  commercial originals, personalized session data or request bodies in the
  evidence bundle.
- Retention uses unique disposable Attempts/evidence/promoted subsets and a
  private object prefix with known initial state, strict controlled cutoffs,
  an old no-evidence-row Attempt, overlapping invocations,
  failure/interruption injection, safe rerun and cleanup limited to fixtures.
  Staff API/page fixtures cover operator/developer, photographer and
  unauthenticated reads plus sanitized errors and `no-store`.
- Production acceptance verifies source/installed systemd unit identity,
  enabled/active daily persistent scheduling, next-trigger observation and one
  explicitly authorized one-shot/latest-result join on the pilot host.
- Every task runs focused pytest/Node tests, Python mypy and
  `node scripts/mb-lint.mjs`.

## Constitution Constraints And Invariants

- Keep the modular monolith, one schema/Base/Alembic stream and one writer per
  mutable invariant.
- Core Attempt creation and participant result remain independent of detailed
  evidence. No evidence or timing-report failure may roll them back.
- Client latency uses one monotonic clock; server timestamps localize server
  stages and are never subtracted from the client wall clock.
- Missing evidence/markers remain explicit; no empty replacement anchor or
  fabricated complete timeline is allowed.
- Capture-derived media has no developer-only classification solely because it
  is image content, but the implementation creates no storage mechanism without
  an actual need.
- Cleanup makes owner data inaccessible before object deletion, preserves only
  the curated promoted subset, mutates no foreign rows and retains one latest
  result rather than history or scheduler state. Ordinary evidence never
  contains participant names/annotations; the promoted seam is separate.

## Definition Of Done

All five indexed cards satisfy their exact claims and tier obligations; every
`FT-007-AC-001..007` is owned exactly once; task-relevant modules, edges and
canonical headings match the Boundary Map; the single migration stream remains
linear; every task retains the Foundation dependency; feature design remains
`complete`; and fresh `/review-tasks-plan FT-007` has returned `APPROVE` for
Planning Revision `4` without implementation guesses.
