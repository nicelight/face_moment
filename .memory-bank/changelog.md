---
description: Compact current Memory Bank state; historical task evidence stays in task records.
status: active
---
# Changelog

## [2026-09-09] Wave 8 — Preserved local Photo reprocessing

- Editorial cleanup: сокращены повторяющиеся протоколы, handoff и инструкции; решения, команды, evidence и verdicts сохранены.

- Completed [TASK-118](tasks/TASK-118-T3-FT-002-W8.task.json): local `opencv-photo-640-v2` deployment, six ready Photos, compatible search, unchanged originals/admission/history and exact repeat-run snapshot.
- Fixed the extra admission-revision search filter and added create-only pending plus disposable retry/recovery coverage. Independent verification passed 34 focused tests, mypy, lint, build and fresh local read-only proof; task and current FT-002 semantic reviews passed.
- Reconciled [FT-002](features/FT-002.md), its implementation plan, RTM links and [local development guide](guides/local-development.md). All 26 feature tasks are done; other feature/epic lifecycles and Planning Revision 4 are unchanged. Actual camera identity evaluation still needs camera attempts and labels.

## [2026-09-09] Wave 7 — Measured SFace Photo preprocessing

- Completed [TASK-117](tasks/TASK-117-T2-FT-002-W7.task.json): bounded detection with original-pixel alignment, shared EXIF decode and preserved legacy/query behavior.
- Eight native samples support `opencv-photo-640-v2`: all six main portrait faces recovered; 1280 adds no faces on the supplied groups. This does not establish camera identity accuracy.
- Independent verification passed 62 focused tests, mypy, lint and repeated native measurements. [FT-002](features/FT-002.md) records AC-010/011 completion; local application and fresh feature semantic verification remain in TASK-118.

## [2026-09-07] Adaptive Promo photo cards

- Implemented the operator-approved paper-card presentation and exact download/domain copy in the existing Chromium client. Landscape, square and portrait layouts replace the fixed display assumption; QR remains stationary.
- [Presentation guide](guides/promo-presentation.md) records visual behavior and supersedes the earlier IDEA_APP six-cell/cursor animation. PRD, FT-005 and display-contract navigation are aligned. No task lifecycle or session/API behavior changed.
- Validation: 52 client unit tests and all 17 browser tests passed; browser layout coverage at six viewport sizes with synthetic landscape/portrait fixtures, reduced motion and stationary QR checks.

## [2026-09-07] Extended quality Calibration removed from pilot plans

- Operator explicitly deferred FR-DEV-08 / FT-011-AC-002, including extra measurement collection and shared redesign, outside the pilot. [PRD](prd.md) and [FT-011](features/FT-011.md#ft-011-ac-002--one-dimensional-quality-recommendations) retain the decision and historical criterion identity.
- Requirements, Calibration scope/testing and planning checkpoints now exclude that work from current obligations; the shared-measurement blocker is withdrawn. Existing search, threshold Calibration, comparison and manual apply remain in scope.
- No runtime, task lifecycle, historical verification or Global Backbone Planning Revision changed. Revised-scope semantic acceptance is not claimed.


## [2026-09-07] Operator defers measurements; remaining code confirmed

- Operator postponed FT-011 quality measurements/shared redesign and requested implementation-only continuation for TASK-115 → TASK-116. [Decision and code evidence](../.protocols/AUTONOMOUS-RUN/decision-log.md) supersede the earlier immediate design question for this scope.
- Both implementations already exist in the committed baseline: canonical Caddy forwarding and the working staff login form. Fresh Caddy validation, mypy (94 files), five routing/shell tests and six local login-script cases passed; no duplicate runtime edit was needed.
- Full acceptance remains deferred; task statuses and accepted criteria are unchanged. The [scheduler checkpoint](../.protocols/AUTONOMOUS-RUN/status.md) distinguishes this completed code handoff from full queue success.

## [2026-09-07] Wave 4 / Promoted Calibration case actions and design blocker

- Closed: [TASK-106](tasks/TASK-106-T3-FT-011-W4.task.json), AC-008, after independent functional PASS and task semantic-pass. Existing Calibration detail actions now promote only the selected curated case and delete its whole subset with separate confirmation; 11 tests, mypy and lint passed.
- Blocked: the [FT-011 feature review](../.tasks/FT-011/FT-011-S-RED-VERIFY-final-report-docs-01.md) proved missing production quality analyses for AC-002. Fresh local tasking traced this to absent shared per-occurrence measurements, not TASK-106 behavior; no follow-up task or implementation contract was invented.
- Next owner: operator decision and `/spec-redesign` for the bounded [shared measurement proposal](../.protocols/FT-011/clarification.md#shared-measurement-boundary--2026-09-07). Query-image retention and serving changes are not proposed. [Scheduler checkpoint](../.protocols/AUTONOMOUS-RUN/status.md) records `HALT_BLOCKING_QUESTIONS`; TASK-114/106 remain done and TASK-115/116 unselected.
- Cleanup: owned TASK-106 PostgreSQL and temporary connection file removed; default/operator data untouched. This records the completion/blocker handoff, not a completed wave sync or strict-readiness claim.

## [2026-09-07] Wave 6 / Buffalo native readiness closure

- Closed: [TASK-114](tasks/TASK-114-T3-FT-002-W6.task.json), AC-009, after fresh functional PASS and independent task/feature semantic-pass. Existing committed correction needed no further source change during resume.
- Verified: 26 tests, actual non-skipped native ONNX warmup, 16 serving/Calibration failure cases, mypy and lint. Dynamic detector preparation and both native inference calls precede readiness; failures remain closed.
- Reconciled: [FT-002](features/FT-002.md) maintenance completion and [testing evidence](testing/photo-processing.md). All 24 FT-002 tasks are closed; baseline ownership and current Planning Revision 4 approval are preserved. Cross-feature requirement/epic lifecycle is unchanged.
- Cleanup: task-owned tmpfs PostgreSQL removed after independent reviews; no deployment or default/operator data change. Scheduler owns post-sync lint and strict doctor before TASK-106.

## [2026-09-07] Multipilot prerequisite evidence reconciliation

- Normalized existing RED/GREEN field labels and full acceptance IDs in [TASK-110 progress](../.protocols/TASK-110-T3-FT-012-W3/progress.md), [TASK-110 verification](../.protocols/TASK-110-T3-FT-012-W3/verification.md) and [TASK-113 progress](../.protocols/TASK-113-T3-FT-003-W5/progress.md) so strict readiness can recognize retained closure evidence. Observations, attempts, verdicts, task lifecycle and runtime are unchanged.
- Explicit GENERAL owner requested this bounded early `/mb-sync` prerequisite for queue 114 → 106 → 115 → 116; scheduler owns subsequent lint and strict-doctor gates.

## [2026-09-07] ASTRA finding 10 — packaged runtime proof

- Updated smoke-runtime.sh and local-development guide for isolated project/network/volumes, migrated product schema, real SFace serving seed and current role readiness.
- Live packaged smoke passed HTTPS route/auth checks, dependency/application restart, storage persistence and owned cleanup; all 13 ASTRA findings are now accepted. No indexed lifecycle or deployment change.
- [Retained handoff and evidence](../.tasks/ASTRA-findings/10-packaged-smoke/implementation-report.md): logs, redacted topology and source links for the next deployment agent. User asked to retain useful artifacts and remove the obsolete test image after checks. The image was removed and its cleanup added to the script. The first preflight null-IPAM failure is also retained. Other project tasks remain untouched.

## [2026-09-07] ASTRA findings — operator pause

- Findings 3–9 and 11–13 are accepted; finding 9 source review and independent client gates confirm 52 unit and 11 browser passes, including 400/400 Blob URL cleanup.
- Finding 10 remains open: accepted plan and read-only preparation only; no script changes or packaged runtime run. Work stopped at operator request.
- The out-of-scope default-Compose pytest incident remains recorded; disposable-data clarification removes the preservation blocker without establishing retrospective isolation.
- [Session handoff](../.tasks/ASTRA-findings/session-handoff.md): accepted work, incident evidence and exact continuation boundary. [Consolidated review](../PAPERCUTS/TECHDEBTS/ASTRA-consolidated-review-2026-09-06.md): one remaining finding.

## [2026-09-06] Wave 5 / Responsive realtime admission

- Closed: [TASK-113-T3-FT-003-W5](tasks/TASK-113-T3-FT-003-W5.task.json), audit finding 2, after root functional PASS and independent semantic-pass.
- Fixed: blocking request work owns Sessions inside framework worker threads; only the unique insert winner starts processing. Concurrent health, same-key in_progress and distinct-key busy responses arrive before inference release.
- Evidence: 47 tests, real PostgreSQL insert/row-lock arbitration, Session cleanup, terminal replay and unchanged rate budgets; mypy/lint passed. JPEG hardening from TASK-112 is preserved. No deployment occurred.

## [2026-09-06] Wave 4 / Realtime JPEG admission hardening

- Closed: [TASK-112-T3-FT-003-W4](tasks/TASK-112-T3-FT-003-W4.task.json), audit finding 1, after root functional PASS and independent semantic-pass.
- Fixed: auth/rate checks precede multipart/crop work; JPEG header dimensions reject oversized crops before allocation. Existing full decode still validates bounded input before Attempt creation.
- Evidence: 15 current-source ASGI tests, independent 513x1/1x513/512x512 probes, mypy and lint. TASK-113 owns the remaining concurrent realtime fix; no runtime deployment occurred.

## [2026-09-06] TASK-104 KISS repair closed

- Repaired: production Calibration completion now composes one stored
  `Balance` threshold recommendation only from homogeneous selected Attempts
  for the exact current serving revision and their one common finite historical
  threshold; mixed or undefined input truthfully produces no recommendation.
- Preserved: the proposal changes only the threshold. Current server-owned
  query-quality and quality-gate settings remain unchanged; no grid search,
  weighting, inferred outcome, quality candidate or automatic apply was added.
- Repaired: the post-apply success notice now requires the current owner state
  to match both the returned settings revision and Calibration run ID, so a
  forged query value cannot report success.
- Hardened within the same KISS boundary: the stored recommendation now retains
  the exact calibrated `pipeline_revision_id`. A supported switch to another
  revision with the same pipeline code makes the old recommendation stale;
  owner apply and the success notice both reject that mismatch.
- Closed: `TASK-104-T3-FT-011-W3` is `done` after fresh focused and adjacent
  tests, mypy, Memory Bank lint, `git diff --check`, the required real-browser
  flow, independent functional `PASS` and task-scoped `semantic-pass`.
- Adversarial proof covers both switch-before-apply rejection and
  switch-after-apply stale-success suppression. No dependent was promoted and
  no unrelated workflow stage was run.

## [2026-09-05] Wave 2 / Calibration missing-original recovery

- Closed: `TASK-111-T3-FT-011-W2` is `done` after independent functional
  `PASS`, task-scoped `semantic-pass` and scheduler-owned closure.
- Reconciled: the supported S3 `NoSuchKey` path now terminalizes the claimed
  Calibration run as `failed/dataset_unavailable`, releases the singleton
  worker and permits queued Photo progress without replacement execution or a
  serving change; `REQ-CAL-003` is `verified` through `FT-011-AC-005`.
- Dependency state: TASK-104 is authoritatively `ready`; TASK-106 remains
  blocked on TASK-104. TASK-110 retains `blocked` status even though its former
  TASK-111 dependency condition is satisfied, pending the scheduler-owned
  post-sync gate and promotion pass. No task status was changed by this sync.
- Evidence: `.memory-bank/tasks/TASK-111-T3-FT-011-W2.task.json`,
  `.tasks/TASK-111-T3-FT-011-W2/TASK-111-T3-FT-011-W2-S-VERIFY-final-report-docs-01.md`
  and `.tasks/TASK-111-T3-FT-011-W2/TASK-111-T3-FT-011-W2-S-RED-VERIFY-final-report-docs-01.md`.

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

## 2026-09-08 — Local application deployment for operator testing

Rebuilt current source and started the persistent local Compose stack using
existing storage. Migrated to 0022, provisioned local SFace/SPA/display settings
and separate operator, photographer and developer accounts. Application roles
are healthy; HTTPS login and role-scoped page checks passed. Access paths,
restart command, test settings and verification limits are recorded in
[local-development.md](guides/local-development.md#persistent-local-testing-stand--2026-09-08).

## 2026-09-08 — Motion Atlas visual integration

Added distinct public and role-aware staff homepages, common staff styling,
selected motion effects and a phase-driven kiosk loading scene. Existing paper
Promo and QR continuation retain their behavior. Public camera capture UI is
presented explicitly as prelaunch: visitor search and payment are not connected;
gallery upload and Google OAuth remain deferred. See the
[presentation guide](guides/motion-presentation.md) for ownership, local review
routes and verification limits.

### Motion Atlas operator visual correction

Restored the original Fluid gradient tiling, color/background and rotation;
removed the added dark overlay. The operator confirmed that the reference's
visible rectangular boundaries are intentional. Earlier QA advice to smooth
those boundaries is superseded. The public portrait frame is now the
«Найти меня» link; the old hero CTA and registration tagline are removed.

### Fluid browser controls

Added the requested collapsible live-preview sliders on `/site`: spot size,
drift, speed (including pause), rotation and blur. Values apply immediately
to the public hero; reset restores the original preset. Settings are local to
the current page and do not change server configuration.

### Fluid hover zoom

The public «Найти меня» hit area now smoothly enlarges the existing Fluid layers
to an effective 100% spot size, returning to the slider-selected size on leave.
The effect uses CSS scale, with no gradient-size animation or JS frame loop.
Speed tuning now targets only drift animations so pause does not stop hover.

### Fluid hover timing refinement

Per operator feedback, increased the hover target from effective 100% to 200%
and changed scale easing to a slow 4-second ease-in-out transition. Pointer
leave reverses smoothly from the current scale; clicking never waits for zoom.

The operator subsequently adjusted the final Fluid hover target to 150%;
the 4-second transition and smooth return remain unchanged.
