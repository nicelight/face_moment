---
description: Implementation plan for immutable Calibration runs, recommendations, developer control and retention.
status: active
last_updated: 2026-09-04
---
# IMPL-FT-011 — Explainable Calibration

## Goal

Let an authorized developer run reproducible SFace and Buffalo M Calibration
over one selected immutable set of existing Photo originals and annotated
Attempts, inspect deterministic threshold and one-dimensional quality
recommendations, and separately apply or retain only an explicitly selected
result. Calibration never changes serving state automatically.

## Scope And Non-Goals

In scope are one diagnostics-owned run table, the existing processing adapters'
offline evaluation, the existing singleton worker's Calibration operation,
deterministic recommendations, one bounded same-origin developer flow, the
existing serving-control apply command, and the existing retention/promoted
subset seams.

The plan adds no model registry, experiment platform, dataset catalog, generic
job system, second worker, priority scheduler, automatic rerun/apply, settings
history, audit table, cleanup command, timer or production configuration. It
defines no minimum sample threshold beyond the accepted undefined-metric case.
No behavior JSON is needed because the canonical oracle is deterministic.

## Normative Basis And Canonical Coverage

- [FT-011](../../features/FT-011.md): `FT-011-AC-001..008` and governing
  `REQ-CAL-001..003`, `REQ-DATA-001` and `REQ-ARCH-001`.
- [Calibration](../../domains/calibration.md): created as the single canonical
  owner of immutable input, run state, developer flow, manual apply and
  retention.
- [Calibration Verification](../../testing/calibration.md): extended with the
  accepted same-JPEG dataset oracle and exact claim evidence.
- [Boundary Map](../../contracts/boundary-map.md): extended in place only to
  point its accepted diagnostics-to-processing/serving and retention edges to
  the Calibration owner; module identity and topology are unchanged.
- [Diagnostic Retention API](../../contracts/diagnostic-retention-api.md):
  extended so the existing cleanup also expires terminal ordinary Calibration
  runs without changing its public result.
- [Diagnostic Evidence](../../domains/diagnostic-evidence.md), [Ground-Truth
  Annotations](../../domains/ground-truth-annotations.md), [Lifecycle
  Map](../../states/lifecycle-map.md), [Staff Access](../../domains/staff-access.md)
  and [Realtime Search](../../domains/realtime-search.md): reused.

| Concern | Action | Canonical path | KISS reason |
|---|---|---|---|
| Immutable dataset, run, evaluation, staff flow, apply and lifecycle | create | `.memory-bank/domains/calibration.md` | No prior subject spec owned the feature; one document covers the cohesive Calibration boundary. |
| Deterministic calculation and evidence oracle | extend | `.memory-bank/testing/calibration.md` | Reuse the existing Calibration verification owner and add only accepted dataset-reuse detail. |
| Cross-module ownership and calls | extend | `.memory-bank/contracts/boundary-map.md` | Existing modules and edges are sufficient; only the exact Calibration contract link changed. |
| Terminal-run cleanup | extend | `.memory-bank/contracts/diagnostic-retention-api.md` | Reuse the existing command, cutoff and public result. |
| Calibration retention state | extend | `.memory-bank/states/lifecycle-map.md` | Add terminal ordinary runs to the existing 90-day lifecycle without a new state machine. |
| Annotations, promoted subset, staff sessions, settings and native adapters | reuse | Existing linked subject specs | Existing owners and operations already supply these prerequisites. |

Global Backbone Planning Revision remains `4`. This is a leaf feature extension
inside accepted modules and edges. Foundation final gate
`TASK-002-T2-FT-000-W0` is done and remains transitive through every selected
completed prerequisite.

## Architecture And Strategy

`diagnostics` at `src/face_moment/diagnostics/` owns selection, run state,
recommendations, drill-down and the developer-visible outcome. It reads the
existing immutable annotation/Attempt projections, calls `processing` through
the accepted offline-evaluation edge, and asks `serving_control` to apply only
one confirmed stored recommendation. HTTP and entrypoint code remain adapters.

One next-linear migration adds `face_moment.calibration_runs`. The executor
resolves its direct predecessor at execution time and proves only that
revision's upgrade/downgrade and data transition. Processing reads each selected
Photo original once, verifies its stored SHA-256 and feeds the same bytes and
Attempt selection to the two existing native adapters. Missing input fails the
run rather than changing its snapshot.

The recommendation code consists only of the three accepted threshold rankings
and five one-gate-at-a-time analyses. Candidate lists are retained with the run;
there is no general optimizer. Before/after accepts complete results with the
same dataset hash. The existing settings row supplies apply provenance, and the
existing cleanup/promoted-subset operations supply lifecycle behavior.

## Execution-Cohesive Slicing And Claims

| Task | Tier | Wave | Direct prerequisite | Exact owned claim | Outcome |
|---|---|---|---|---|---|
| `TASK-100-T2-FT-011-W1` | T2 | W1 | done SFace/Buffalo adapters and annotation provider | `FT-011-AC-003` | Persist and execute one immutable cross-revision Calibration run with reproducible same-dataset results and comparison. |
| `TASK-101-T3-FT-011-W2` | T3 | W2 | `TASK-100` and existing shared-worker seam | `FT-011-AC-005` | Run Calibration on the singleton worker and recover interruption without blocking later Photo work or creating a replacement run. |
| `TASK-102-T2-FT-011-W2` | T2 | W2 | `TASK-100` | `FT-011-AC-001`, `FT-011-AC-006` | Produce all three deterministic threshold profiles, drill-down and honest unavailable output. |
| `TASK-103-T2-FT-011-W2` | T2 | W2 | `TASK-100` | `FT-011-AC-002` | Produce the five one-dimensional quality recommendations without joint optimization. |
| `TASK-104-T3-FT-011-W3` | T3 | W3 | `TASK-101..103`, existing staff/settings providers | `FT-011-AC-004` | Deliver the developer list/create/detail flow and allow only a separate confirmed stored recommendation to change serving settings. |
| `TASK-105-T3-FT-011-W2` | T3 | W2 | `TASK-100`, existing retention seam | `FT-011-AC-007` | Expire terminal ordinary runs without widening retention or the cleanup result. |
| `TASK-106-T3-FT-011-W4` | T3 | W4 | `TASK-104`, `TASK-105`, existing promotion seam | `FT-011-AC-008` | Expose confirmed curated promotion/deletion and preserve the subset through ordinary cleanup. |

The four W2 outcomes are independent after the durable run core. The worker
claim remains separate because restart recovery is an independently observable
runtime result. Threshold and quality calculations remain separate because they
implement different accepted algorithms. The developer flow composes their
completed results without adopting dependency proof. Ordinary-run retention is
independent of the staff flow; the final promoted-case task composes that flow,
the existing promotion seam and completed cleanup only to prove its own curated
lifecycle. Tests, RED/GREEN probes and UAT stay with their owning task.

## Advisory Expected Change Surface

- next-linear `migrations/versions/*_calibration_runs.py`;
- focused Calibration run, threshold, quality and HTTP modules under
  `src/face_moment/diagnostics/`;
- a narrow offline-evaluation adapter under `src/face_moment/processing/` plus
  existing worker runtime/recovery integration;
- the existing serving-control settings command and diagnostics retention/
  promoted-subset boundaries;
- backend route registration and focused tests under `tests/diagnostics/`,
  `tests/processing/` and `tests/serving_control/`.

Paths are advisory and non-exhaustive. No hard `write_boundary` is justified.

## Tests, Gates And UAT

- Disposable migration/repository fixtures prove run shape, immutable bounded
  snapshots, transitions, same-byte adapter input, missing-input failure and
  same-hash comparison.
- Worker restart fixtures prove visible interruption, no automatic replacement
  and resumed queued Photo processing.
- Independent calculation fixtures prove every threshold ranking/tie-break,
  undefined metrics, Attempt reconciliation and every one-gate-at-a-time
  quality result.
- Application/HTML tests cover exact routes, role/CSRF, validation, rollback,
  no-store and stored-value-only actions. One focused `playwright cli` smoke
  covers run creation, result inspection and confirmed apply, retaining the
  exact transcript and screenshot named by TASK-104.
- Fixed-time disposable retention fixtures independently prove strict-before
  terminal run deletion and safe rerun. Separate promoted-action fixtures prove
  curated-only preservation, explicit whole-subset deletion and one safe repeat
  without touching operator/default state.
- Each task runs focused pytest, Python mypy and Memory Bank lint. Import/source
  inspection is the project-native ownership check; no separate architecture
  command exists.

## Constitution Constraints And Invariants

- Keep the modular monolith, one PostgreSQL schema/Base/Alembic stream and the
  accepted capability ownership graph.
- Reuse existing Photo originals, annotation projections, native adapters,
  worker, settings row, cleanup command and promoted subset.
- Calibration is test-only and cannot change serving state without the separate
  authorized confirmed action.
- Never retain embeddings, credentials, tokens, arbitrary bodies, object keys,
  whole evidence bundles, screenshots or logs in a run/promoted subset.
- Destructive/runtime probes use known disposable state, safe rerun, redacted
  artifacts and complete cleanup.

## Definition Of Done

All seven indexed cards satisfy their task-owned claims and tier obligations;
`FT-011-AC-001..008` are each owned exactly once; all affected module edges and
canonical headings resolve; Foundation remains transitive; Planning Revision
remains `4`; and fresh `/review-tasks-plan FT-011` returns `APPROVE` before
execution.
