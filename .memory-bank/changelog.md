---
description: Compact current Memory Bank state; historical task evidence stays in task records.
status: active
---
# Changelog

## [2026-09-05] Wave 2 / FT-012 role-scoped Photo visibility

- Closed: `TASK-107-T3-FT-012-W2` is `done` after independent functional
  `PASS`, task-scoped `semantic-pass` and scheduler-owned closure.
- Implemented: inventory-owned role-safe half-open Photo selection and
  idempotent `Photo.is_active` visibility change; inactive Photos leave new
  search and counters while issued media remains readable.
- Preserved: FT-012 and `REQ-INV-001..003` remain `planned`; TASK-110 remains
  blocked through failed TASK-101 and no blocked path was promoted.
- Evidence: `.memory-bank/tasks/TASK-107-T3-FT-012-W2.task.json` and
  `.tasks/TASK-107-T3-FT-012-W2/TASK-107-T3-FT-012-W2-S-RED-VERIFY-final-report-docs-01.md`.

## [2026-09-05] Wave 2 / FT-011 independent completed slices

- Closed: `TASK-102-T2-FT-011-W2`, `TASK-103-T2-FT-011-W2` and
  `TASK-105-T3-FT-011-W2` are `done` after their required task-scoped evidence;
  TASK-105 additionally has independent `semantic-pass` and scheduler closure.
- Implemented: threshold-profile locator validation, five independent quality
  recommendations including lower-is-better `blur_score <= cutoff`, and
  existing-owner expiry of old terminal ordinary Calibration runs under the
  shared strict 90-day cutoff.
- Preserved: FT-011 and its requirements remain `planned`; TASK-101 is failed,
  TASK-104 and TASK-106 remain blocked, and no dependent is promoted through
  that failed path.
- Evidence: task records `TASK-102`, `TASK-103`, `TASK-105`; TASK-105 reports
  `.tasks/TASK-105-T3-FT-011-W2/TASK-105-T3-FT-011-W2-S-VERIFY-final-report-docs-01.md`
  and `.tasks/TASK-105-T3-FT-011-W2/TASK-105-T3-FT-011-W2-S-RED-VERIFY-final-report-docs-01.md`.

## [2026-09-05] Wave 1 / FT-012 statistics and processing-cleanup providers

- Closed: `TASK-108-T3-FT-012-W1` and `TASK-109-T3-FT-012-W1` are `done`
  after their independent T3 functional `PASS`, task-scoped `semantic-pass`
  and scheduler-owned closure decisions.
- Implemented: the closed W1 providers cover exact direct recent per-СПА
  counters (`FT-012-AC-006`) and the processing-owned Photo derivative/row
  cleanup boundary needed by the later fixed-snapshot purge.
- Reconciled: `REQ-INV-004` is `verified` through the closed
  `FT-012-AC-006` slice. FT-012 and `REQ-INV-001..003` remain `planned`
  because TASK-107 and TASK-110 still own the remaining feature acceptance
  outcomes; no feature lifecycle transition or dependent promotion is made by
  this sync.
- Evidence: `.memory-bank/tasks/TASK-108-T3-FT-012-W1.task.json`,
  `.memory-bank/tasks/TASK-109-T3-FT-012-W1.task.json` and
  `.tasks/TASK-AUTONOMOUS/TASK-AUTONOMOUS-S-MB-SYNC-W1-final-report-docs-02.md`.

## [2026-09-04] FT-012 task decomposition closure

- Closed: fresh `/review-tasks-plan FT-012` approved the four-card task plan
  for Global Backbone Planning Revision `4`; no architecture review was
  required.
- Reconciled: `TASK-107..110` retain their reviewed scopes and statuses;
  `FT-012-AC-001..007` and `REQ-INV-001..004` keep complete, unambiguous
  task ownership and traceability.
- Evidence: `.tasks/TASK-MB-REVIEW-TASKS-PLAN/TASK-MB-REVIEW-TASKS-PLAN-S-TASKS-FT-012-final-report-docs-01.md`.
- Preserved: FT-012 and its requirements remain `planned` until implementation
  and verification; the applicable `/mb-doctor` gate precedes execution.

## [2026-09-04] Wave 2 / FT-010 feature closure

- Closed: `TASK-097-T3-FT-010-W2`, `TASK-098-T3-FT-010-W2` and
  `TASK-099-T3-FT-010-W2` are `done` after their required T3 functional
  `PASS`, task-scoped `semantic-pass` and scheduler-owned closure decisions.
- Verified: FT-010 is `verified` after all `FT-010-AC-001..005` outcomes and
  feature-level `semantic-pass`; `REQ-ANN-001` is reconciled to `verified`.
- Evidence: `.tasks/FT-010/FT-010-S-RED-VERIFY-final-report-docs-01.md` and the
  durable marker in `.memory-bank/features/FT-010.md#semantic-verification`.
- Preserved: EP-003 remains `planned` while FT-007 production acceptance and
  FT-011 are unfinished. Their tasks, all FT-012 work and all production-
  acceptance task statuses remain unchanged.

## [2026-09-04] Wave 1 / FT-010 normalized annotation provider closure

- Closed: `TASK-096-T3-FT-010-W1` is `done` after Attempt 2 functional `PASS`,
  required task-scoped `semantic-pass` and scheduler-owned closure.
- Implemented: the diagnostics-owned normalized provider persists valid
  detection `correct|false` and person-level `missed` semantics, exposes an
  immutable ordered calculation projection and rejects mutation after
  committed evidence expiry or removal.
- Evidence: `.tasks/TASK-096-T3-FT-010-W1/TASK-096-T3-FT-010-W1-S-VERIFY-final-report-docs-02.md`
  and `.tasks/TASK-096-T3-FT-010-W1/TASK-096-T3-FT-010-W1-S-RED-VERIFY-final-report-docs-02.md`.
- Preserved: `TASK-097..099`, FT-010 and `REQ-ANN-001` remain `planned` because
  the Wave 2 developer flow, promoted subset and ordinary-retention outcomes
  are unfinished. The current Planning Revision `4` task-plan `APPROVE` remains
  valid because this closure changes status and evidence only.

## [2026-09-04] FT-010 task decomposition closure

- Closed: fresh `/review-tasks-plan FT-010` approved the four-card task plan for
  Global Backbone Planning Revision `4`; no architecture review is required.
- Reconciled: `TASK-096..099` remain `planned`, every `FT-010-AC-001..005` has
  one owner, and the implementation-plan router now links IMPL-FT-010.
- Evidence: `.tasks/TASK-MB-REVIEW-TASKS-PLAN/TASK-MB-REVIEW-TASKS-PLAN-S-TASKS-FT-010-final-report-docs-01.md`.
- Preserved: FT-010 and `REQ-ANN-001` remain `planned` until implementation and
  verification; the applicable `/mb-doctor` gate precedes execution.

## [2026-09-04] Wave 3 / FT-009 feature closure

- Closed: FT-009 is `verified` after all `FT-009-AC-001..004` task outcomes,
  required T3 gates and feature-level `semantic-pass` completed.
- Reconciled: `REQ-LOG-001` is `verified`, and the feature router now reflects
  the closed persistence, developer-search and retention outcome.
- Evidence: `.tasks/FT-009/FT-009-S-RED-VERIFY-final-report-docs-01.md` and the
  durable marker in `.memory-bank/features/FT-009.md#semantic-verification`.
- Preserved: EP-003 remains `planned` while FT-010 and FT-011 are unfinished.

## [2026-09-03] Wave 3 / FT-009 server-event retention closure

- Closed: `TASK-093-T3-FT-009-W3` is `done` after functional PASS and required
  per-task `semantic-pass`.
- Implemented: the existing owner-ordered cleanup now expires diagnostics-owned
  structured server events strictly before the 30-day cutoff, reports the
  confirmed count and preserves truthful failure, overlap and rerun behavior.
- Verified: current and bookmarked search, FT-008 navigation and browser history
  cannot recover deleted event content; equal/newer events and 90-day
  Attempt/evidence state remain intact.
- Reconciled: all `FT-009-AC-001..004` implementation slices are closed, FT-009
  and `REQ-LOG-001` are `implemented`, and feature-level semantic verification
  remains the final gate before `verified`.

## [2026-09-03] Wave 2 / FT-009 server-event search closure

- Closed: `TASK-091-T3-FT-009-W2` is `done` after fresh Attempt 4 functional
  PASS and required per-task `semantic-pass`.
- Implemented: the effective release HTTPS route exposes the exact
  developer-only bounded server-event search with usable optional filters,
  fixed-field escaped HTML, paired FT-008 navigation and truthful uncorrelated
  rows; internal `event_id` values are not rendered.
- Preserved: FT-008 retains target authorization/projection ownership, denied
  and stale sessions disclose no rows, and diagnostics performs no Promo-table
  read for navigation.
- Reconciled: FT-009 now has closed producer/persistence and search/navigation
  slices. `TASK-093-T3-FT-009-W3` remains `planned` for retention expiry; its
  dependencies are satisfied, but this sync does not promote or select it.
- Lifecycle: FT-009 and `REQ-LOG-001` remain `planned` until the W3 retention
  outcome is implemented and receives its required verification.

## [2026-09-02] FT-008 closure and FT-009 producer slice

- Verified: FT-008 is complete. TASK-088 and TASK-089 are `done`, the
  feature-level adversarial review is `semantic-pass`, and `REQ-DIAG-003` is
  verified.
- Implemented: FT-009's isolated redacted persistence slice
  (`FT-009-AC-002`) is closed by TASK-094 with functional PASS and
  task-scoped semantic-pass.
- Reconciled: TASK-090 remains failed historical evidence and its resolved bug
  note is archived. TASK-091 and TASK-093 no longer carry the obsolete failed-
  dependency block; TASK-091 is `in_progress`, while TASK-093 remains `planned`.
- Clarified: one explicit bounded Promo-owned QR correlation query after commit
  is accepted ordinary owner access, not diagnostics writer latency. No global
  zero-SQL requirement was introduced.
- Local development now runs current editable Python source through locked
  `uv`; only PostgreSQL/pgvector and MinIO stay in the daily Compose overlay.
  The unchanged base Compose topology remains the packaged-runtime smoke.
- Backend HTTP adapters now reuse one composition-owned SQLAlchemy Engine and
  open a short Session per request. The Engine is disposed at backend shutdown;
  the diagnostics writer keeps its contract-required independent Session path.
  API, transaction ownership, schema and capability ownership are unchanged.
- Promo now derives effective `pending -> unconfirmed` display state through
  one pure `PromoAttempt` helper reused by display outcome and diagnostics
  timeline reads. The persisted state, expiry boundary and API remain unchanged.

## [2026-08-29] Development baseline after FT-001…FT-007

- All development work for `FT-001` through `FT-007` is terminal. Their
  completed task records are historical evidence, not active work or blockers.
- `TASK-075-T3-FT-004-W5` is `done_for_prod`. Its development evidence is
  accepted; `FT-004-AC-004` remains production-only and does not block
  development scheduling.
- `TASK-078-T3-FT-005-W2`, `TASK-081-T3-FT-006-W2` and
  `TASK-086-T3-FT-007-W3` are `done`. Their earlier failures, retry limits and
  halted-run records are superseded historical checkpoints.
- The remaining non-terminal `FT-001`…`FT-007` records are title-prefixed
  `Production acceptance:` tasks. They remain deferred until production and
  are excluded from development autopilot.
- No active bug or development blocker remains for `FT-001`…`FT-007`.

Current lifecycle authority is `.memory-bank/tasks/*.task.json`. Historical
verification entries inside terminal task records preserve provenance but do
not override the record's top-level status.
