---
description: Implementation plan for role-scoped Photo visibility, recent statistics and resumable global hard purge.
status: active
last_updated: 2026-09-04
---
# IMPL-FT-012 — Photo Inventory Operations

## Goal

Let staff find Photos by the accepted scope, soft-delete or restore them within
their role, see exact recent per-СПА processing counts, and let an authorized
operator/developer run one resumable project-wide purge without harming issued
Promo sessions, Attempts or diagnostics.

## Scope And Non-Goals

In scope are the existing Photo visibility marker, one small inventory page and
API, direct rolling aggregates, a processing-owned cleanup call, one singleton
fixed-snapshot purge row and integration with the existing background worker.

The plan adds no Batch state, deletion service, per-photo purge lifecycle,
purge jobs/targets/history tables, retry framework, second worker, priority or
preemption, counter storage, metrics service, WebSocket/SSE, ownership-crossing
cascade or production configuration. No behavior JSON is needed because the
canonical matrices are concise and reproducible.

## Normative Basis And Canonical Coverage

- [FT-012](../../features/FT-012.md): `FT-012-AC-001..007` and governing
  `REQ-INV-001..004`, `REQ-ARCH-001`.
- [Photo Inventory API](../../contracts/photo-inventory-api.md): created as the
  exact staff selection, visibility, statistics and purge transport owner.
- [Photo Inventory](../../domains/photo-inventory.md): created as the exact
  visibility, aggregate and singleton purge persistence/orchestration owner.
- [Photo Processing](../../domains/photo-processing.md): extended with one
  exact processing-owned purge cleanup boundary.
- [Photo Inventory Verification](../../testing/photo-inventory.md): created for
  role, rolling-window, crash/restart and retained-state proof.
- [Boundary Map](../../contracts/boundary-map.md): extended only with direct
  links from its existing `inventory -> processing` edge.
- [System Architecture](../../architecture/system-architecture.md), [Lifecycle
  Map](../../states/lifecycle-map.md), [Photo Admission](../../domains/photo-admission.md),
  [Staff Access](../../domains/staff-access.md), [QR Continuation
  API](../../contracts/qr-continuation-api.md) and [Testing Index](../../testing/index.md):
  reused without a new module, edge or lifecycle.

| Concern | Action | Canonical path | KISS reason |
|---|---|---|---|
| Staff API and UI | create | `.memory-bank/contracts/photo-inventory-api.md` | No existing contract defines these exact routes, roles, payloads and failures. |
| Visibility, counters and purge persistence | create | `.memory-bank/domains/photo-inventory.md` | One cohesive inventory-owned domain concern; one singleton row is sufficient. |
| Processing-owned derived cleanup | extend | `.memory-bank/domains/photo-processing.md` | Reuse the existing processing owner instead of duplicating its schema/rules. |
| Cross-module call | extend | `.memory-bank/contracts/boundary-map.md` | Existing modules and `inventory -> processing` edge remain unchanged. |
| Verification | create | `.memory-bank/testing/photo-inventory.md` | Destructive/restart behavior needs a reproducible isolated matrix. |
| Architecture, lifecycle, auth and issued-media behavior | reuse | Existing linked canonical specs | Accepted owners and behavior already suffice. |

Global Backbone Planning Revision remains `4`. Foundation final gate
`TASK-002-T2-FT-000-W0` is done and remains transitive through all selected
prerequisites.

## Architecture And Strategy

`inventory` at `src/face_moment/inventory/` owns all user-visible FT-012
orchestration. It uses persisted `captured_at`, `uploader_id`, `accepted_at`,
`admission_pipeline_revision_id` and `is_active`; no alternate Photo model is
needed. The backend handler remains a thin adapter.

Statistics join each active Photo to its one immutable admission state and run
three direct window aggregates from one observation time. Processing exposes
one owner-local cleanup call covering all revision rows, faces and derivatives
for a Photo. The final purge task composes that call with inventory original/
Photo deletion through the accepted edge.

One next-linear migration adds the singleton `inventory_hard_purge_run` row.
The target UUID array is frozen and sorted at confirmation; `completed_count`
is its persisted prefix. Object deletion is idempotent, while processing-row,
Photo-row and prefix changes commit together. Worker restart resets stale
runtime state, then the durable inventory run resumes before ordinary Photo
claims. Exact migration ancestry is resolved at execution time.

## Execution-Cohesive Slicing And Claims

| Task | Tier | Wave | Direct prerequisite | Exact owned claim | Outcome |
|---|---|---|---|---|---|
| `TASK-107-T3-FT-012-W2` | T3 | W2 | completed staff/uploader/search/phone seams and TASK-108 statistics | `FT-012-AC-001`, `FT-012-AC-002` | Enforce role-scoped Photo selection and idempotent soft-delete/restore with preserved state, counter exclusion and issued-session continuity. |
| `TASK-108-T3-FT-012-W1` | T3 | W1 | completed admission-state and staff polling seams | `FT-012-AC-006` | Return exact direct 1/5/60-minute per-СПА counters and poll them every five seconds without stored or realtime statistics machinery. |
| `TASK-109-T3-FT-012-W1` | T3 | W1 | completed derivative/publication seams | `.memory-bank/domains/photo-processing.md#inventory-purge-cleanup-boundary` | Delete processing-owned Photo derivatives/rows idempotently through one public boundary without changing worker arbitration. |
| `TASK-110-T3-FT-012-W3` | T3 | W3 | tasks 107/109, shared-worker Calibration integration and retained foreign-state seams | `FT-012-AC-003..005`, `FT-012-AC-007` | Deliver restore-all and one fixed-snapshot resumable global purge with truthful wait/progress and owner-safe cleanup. |

Statistics and processing cleanup are independent W1 providers. Visibility is
W2 because its accepted continuity claim includes the statistics exclusion;
the dependency lets that proof be honest without merging the two outcomes.
The final W3 task keeps snapshot, restore exclusion, worker arbitration,
progress, restart and inventory deletion together because splitting that state
machine would leave no independently complete purge outcome. No production-
only task exists.

## Expected Change Surface

- `src/face_moment/inventory/photo_inventory.py`,
  `src/face_moment/inventory/recent_statistics.py`,
  `src/face_moment/inventory/hard_purge.py` and the existing inventory HTTP
  registration;
- `src/face_moment/processing/purge_cleanup.py`, worker operation boundary and
  existing background-worker integration;
- one next-linear `migrations/versions/*_inventory_hard_purge_run.py`;
- focused tests under `tests/inventory/`, `tests/processing/` and existing Promo
  phone-continuation regression coverage.

These paths are advisory and non-exhaustive. No hard `write_boundary` is
justified.

## Tests, Gates And UAT

- Role/API tests cover exact filters, photographer ownership, operator/
  developer scope, CSRF and standard failures.
- Controlled-clock database tests compare every recent counter with an
  independent oracle, including boundaries, visibility and extra revision rows.
- Processing cleanup tests use disposable PostgreSQL/MinIO state, injected
  failure, safe rerun and proof that inventory/foreign state is unchanged.
- Global purge tests cover operator/developer access, CSRF, state-preserving
  `401/403`, fixed snapshot, late soft delete, restore exclusion, idle/busy
  worker, progress, two crash points, restart, concurrent upload, complete
  owned deletion and retained Promo/Attempt/evidence state.
- API and rendered-page tests verify `/staff/photo-inventory` selection,
  visibility, polling and waiting/progress behavior without adding a separate
  browser-only acceptance task.
- Every task runs configured mypy, its focused tests and Memory Bank lint.

## Constitution Constraints And Invariants

- Preserve the KISS modular monolith, current modules/edge, one worker, one
  schema/Base/Alembic stream and private storage.
- Only inventory changes Photo visibility/run/progress; only processing deletes
  its faces, states and derivatives.
- The fixed target set never grows, restore never revives a non-terminal member
  and restart never resets progress.
- Purge never deletes/rebuilds Promo sessions/results, core Attempts,
  diagnostics or issued `N`.
- Destructive proof is isolated, reversible at fixture scope, safe to rerun and
  fully cleaned up.

## Definition Of Done

All four indexed cards satisfy their owned claims and tier obligations;
`FT-012-AC-001..007` are each owned exactly once; the processing cleanup
obligation is independently owned; every direct module/contract heading
resolves; Foundation remains transitive; Planning Revision remains `4`; and
fresh `/review-tasks-plan FT-012` returns `APPROVE` before execution.
