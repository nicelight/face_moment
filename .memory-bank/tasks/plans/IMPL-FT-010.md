---
description: Implementation plan for normalized ground-truth annotations, developer entry and retention.
status: active
last_updated: 2026-09-04
---
# IMPL-FT-010 — Ground-Truth Annotation

## Goal

Let an authorized developer record small person/detection ground truth for an
existing Attempt, expose exactly the persisted rows through a calculation-ready
projection with a stable Attempt locator, and apply the accepted
ordinary/promoted retention boundary without placing names in ordinary evidence
or technical logs. FT-011 owns consumption by Calibration and drill-down.

## Scope And Non-Goals

In scope are one diagnostics-owned normalized table and repository, a bounded
calculation projection, one developer-only same-origin HTML child flow and
integration with existing ordinary retention and promoted-subset seams.

The plan adds no product behavior: AC-005 only gives the promoted half of the
former combined AC-004 its own atomic ID. It adds no participant registry,
identity clustering, dataset catalog, annotation history, JSON API, frame
upload, detector-miss proof, artifact store, Calibration recommendation/run,
new worker, scheduler, module or production configuration. FT-011 owns
Calibration selection, promotion UI, calculation and recommendation behavior.

No behavior JSON is needed: `FT-010-AC-003` and the canonical annotation data
spec already define the only material example, absent versus explicit
person-level `missed`.

## Normative Basis And Canonical Coverage

- [FT-010](../../features/FT-010.md): `FT-010-AC-001..005` and
  governing `REQ-ANN-001`, `REQ-DATA-001` and `REQ-ARCH-001`.
- [Ground-Truth Annotations](../../domains/ground-truth-annotations.md): new
  canonical data owner, exact normalized shape, calculation input and
  ordinary/promoted lifecycle.
- [Ground-Truth Annotation API](../../contracts/ground-truth-annotation-api.md):
  new canonical developer HTML route, authorization, mutation and failure
  contract.
- [Boundary Map](../../contracts/boundary-map.md): reused module inventory and
  exact `Diagnostic evidence and access`, `Calibration and serving change`,
  `Retention cleanup`, shared PostgreSQL and authentication boundaries.
- [Diagnostic Evidence](../../domains/diagnostic-evidence.md): extended in
  place only for the selected annotation snapshot and explicit promoted-subset
  deletion seam.
- [Attempt Investigation API](../../contracts/attempt-investigation-api.md):
  extended compatibly with a developer-only child-page link while its FT-008
  projection remains annotation-free.
- [Diagnostic Retention API](../../contracts/diagnostic-retention-api.md):
  extended in place so diagnostics owner convergence also deletes ordinary
  annotation rows without changing the command or latest-result shape.
- [Lifecycle Map](../../states/lifecycle-map.md), [Staff
  Access](../../domains/staff-access.md), [Calibration
  Verification](../../testing/calibration.md), [Client Realtime
  Verification](../../testing/client-realtime.md) and [Testing
  Index](../../testing/index.md): reused lifecycle, security, downstream input
  and project-gate contracts.

| Concern | Action | Canonical path | Reason |
|---|---|---|---|
| Normalized ordinary annotations and calculation input | create | `.memory-bank/domains/ground-truth-annotations.md` | Existing ordinary evidence deliberately rejects names/annotations and cannot represent a missed person without an evidence row. |
| Developer annotation route/mutation | create | `.memory-bank/contracts/ground-truth-annotation-api.md` | No existing contract owns this child flow or its CSRF/failure surface. |
| Promoted annotation snapshot | extend | `.memory-bank/domains/diagnostic-evidence.md` | The existing cohesive promoted-subset owner remains correct and needs only the selected annotation fragment/deletion seam. |
| Ordinary annotation retention | extend | `.memory-bank/states/lifecycle-map.md` | Annotations share the accepted Attempt-selected cutoff without a new lifecycle. |
| Cleanup command/result | extend | `.memory-bank/contracts/diagnostic-retention-api.md` | Existing owner order includes annotation deletion without another field, command or timer. |
| Downstream Calibration input | extend | `.memory-bank/testing/calibration.md` | The existing oracle now names the immutable annotation projection and keeps absence out of its sample. |
| Module topology and crossed edges | reuse | `.memory-bank/contracts/boundary-map.md` | `diagnostics -> promo` and `diagnostics -> staff_access` already cover the flow; no edge changes. |
| FT-008 base Attempt detail | reuse | `.memory-bank/contracts/attempt-investigation-api.md` | Only a developer link is composed; the existing projection and claims remain unchanged. |

Global Backbone Planning Revision remains `4`; this is a leaf capability
extension with no ownership or topology change. Foundation final gate
`TASK-002-T2-FT-000-W0` is `done` and remains a transitive dependency through
the closed FT-009 baseline.

## Architecture And Strategy

The primary owner for all four outcomes is `diagnostics` at
`src/face_moment/diagnostics/`. It reads immutable promo Attempt truth through
the existing application query, uses the existing staff principal for business
authorization and writes only diagnostics-owned rows. Backend and HTTP code
remain adapters; they do not own validation, authorization or persistence.

One next-linear migration adds `face_moment.ground_truth_annotations`. The
executor resolves the actual direct Alembic predecessor at execution time and
proves upgrade/downgrade on a disposable task database; the plan does not pin a
mutable future head. No cross-owner foreign key or cascade is added.

Detection annotations refer to current evidence occurrence indexes and accept
only `correct|false`. A person-level `missed` row has no occurrence index and
needs no detector-miss artifact. Only stored rows enter the immutable
calculation projection. Promotion copies only selected rows into the existing
curated subset and supplies one idempotent whole-subset deletion operation.
Scheduled expiry and explicit ordinary removal share one annotation-deletion
boundary and leave the promoted subset unchanged.

## Execution-Cohesive Slicing And Claims

| Task | Tier | Wave | Direct prerequisite | Exact owned claim | Outcome |
|---|---|---|---|---|---|
| `TASK-096-T3-FT-010-W1` | T3 | W1 | done `TASK-093-T3-FT-009-W3` | Ground-Truth Annotations `Calculation-Ready Owner Boundary` | A protected normalized provider stores only valid annotation semantics and returns only explicit rows as immutable calculation input. |
| `TASK-097-T3-FT-010-W2` | T3 | W2 | `TASK-096` | `FT-010-AC-001`, `FT-010-AC-002`, `FT-010-AC-003` | An active developer can use the exact HTML flow while names remain isolated and the calculation projection carries its Attempt locator. |
| `TASK-098-T3-FT-010-W2` | T3 | W2 | `TASK-096` | `FT-010-AC-005` | Only selected current annotations enter the promoted subset; one idempotent owner operation deletes the whole subset. |
| `TASK-099-T3-FT-010-W2` | T3 | W2 | `TASK-096` | `FT-010-AC-004` plus Ground-Truth Annotations `Ordinary Annotation Removal` | Scheduled expiry and explicit ordinary removal delete annotation rows while leaving the promoted subset unchanged. |

TASK-096 is a reusable implementation result for both the user flow and later
FT-011 input. TASK-097, TASK-098 and TASK-099 are independent after it.
TASK-099 keeps the two existing ordinary-removal entry paths together because
they apply the same diagnostics-owned annotation deletion boundary. Tests,
probes and real-browser evidence stay with their implementing task. No
production-only acceptance work exists for this feature.

## Advisory Expected Change Surface

- next-linear `migrations/versions/*_ground_truth_annotations.py`;
- `src/face_moment/diagnostics/ground_truth_annotations.py` and package export;
- a focused diagnostics annotation HTTP adapter plus minimal Attempt-detail and
  backend registration changes;
- `src/face_moment/diagnostics/evidence.py` for selected annotation promotion,
  whole-subset deletion and explicit ordinary-removal integration;
- `src/face_moment/diagnostics/retention.py` for scheduled ordinary cleanup;
- focused `tests/diagnostics/test_ground_truth_annotations.py`,
  `test_ground_truth_annotation_http.py` and
  `test_ground_truth_annotation_retention.py`.

Paths are advisory and non-exhaustive. Exact implementation filenames may
change when the owner, public boundary and proof remain unchanged. No hard
`write_boundary` is justified.

## Tests, Gates And UAT

- Provider fixtures use disposable PostgreSQL Attempts/evidence and prove the
  linear migration, exact checks, partial detection-target uniqueness, valid
  create/correct/remove/list, immutable calculation snapshots and owner-only
  writes without cascade.
- Missing-versus-missed fixtures prove that no row contributes nothing while a
  person-level `missed` row contributes without a detection or uploaded frame.
- HTML tests cover exact routes, successful redirect, escaping, no-store,
  validation/rollback, current developer authorization, CSRF and denial after
  revocation/downgrade. Logs, URLs, server events and retained artifacts are
  scanned for synthetic names.
- One `playwright cli` smoke covers Attempt-detail navigation and one successful
  annotation submission with disposable data; focused application tests own
  the wider mutation and authorization matrix.
- Promotion fixtures prove selected snapshot fields, whole-subset deletion and
  one safe repeated delete.
- Ordinary-removal fixtures prove annotation deletion for scheduled expiry and
  explicit removal, promoted snapshot preservation and one safe repeat per path
  without touching operator/default state.
- Each task runs focused pytest, Python mypy and Memory Bank lint. Ownership and
  import inspection confirms the existing boundary graph because the project
  has no separate architecture-check command.

## Constitution Constraints And Invariants

- Keep one modular monolith, one schema/Base/Alembic stream and one writer for
  annotations; HTTP/auth/wiring code cannot write owner rows directly.
- Participant names are protected: only the developer flow and selected
  promoted snapshot may expose them. Ordinary evidence and structured server
  events continue rejecting them.
- Missing ground truth is absence, not a result class. Explicit `missed` needs
  no local-detector proof or diagnostic frame upload.
- Promotion does not extend ordinary annotation/evidence lifetime and cannot
  retain the whole bundle, Promo screenshot, technical logs or session data.
- The two destructive tasks use disposable state, one safe repeat per deletion
  path, redacted evidence and complete cleanup.

## Definition Of Done

The four indexed cards satisfy their exact claims and T3 obligations;
`FT-010-AC-001..005` are each owned exactly once; AC-005 is only the promoted
half split from the former combined AC-004, with no added behavior. All
task-relevant modules, edges and canonical headings resolve; the migration
stream stays linear; Foundation remains transitive; feature design remains
`complete`; and fresh `/review-tasks-plan FT-010` returns `APPROVE` for Planning
Revision `4` before execution.
