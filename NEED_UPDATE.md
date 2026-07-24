# Face Moment synchronization handoff

Status: historical synchronization handoff for Planning Revision 2; superseded
by `.memory-bank/spec-backbone.md` Planning Revision 3.
Scope: documentation only; no code, TASK records or implementation plans.

This file is not a current source of truth. It preserves the prior handoff
snapshot only.

## Current authority

- `arch_vision.md` is the accepted target-architecture source.
- `arch_impr1.md` is the accepted refinement source for HTTP failure semantics
  and the PostgreSQL schema/migration boundary; `arch_vision.md` includes those
  decisions.
- `.memory-bank/prd.md` and the requirements/epic/feature decomposition contain
  the current accepted product behavior.
- The repository still has no working application, backend, worker, database
  schema or deployed runtime.
- Historical `BR-*` records remain unchanged.

## Completed synchronization

- Product Brief and supporting discovery/navigation documents were reconciled
  with the accepted greenfield, per-photo and best-effort diagnostics position.
- Product decomposition and RTM were refreshed. FT-012 adds Photo Inventory
  Operations, bringing the current decomposition to twelve features.
- Global `/spec-design` is complete at Planning Revision 2. The canonical
  architecture, boundary, lifecycle, glossary, invariants, registry and
  Foundation documents are synchronized.
- Technical failures use standard HTTP statuses without a custom error
  framework; admitted capture/search non-successes remain typed `2xx` domain
  outcomes.
- The modular monolith uses one PostgreSQL application schema, one shared
  SQLAlchemy `Base/MetaData`, one Alembic configuration/stream and
  ownership-safe foreign-key/`ON DELETE` rules.
- Foundation is required; its gate remains
  `pending_foundation_to_tasks`. No Foundation or product task records exist.
- Supporting `IDEA_*` and Mermaid documents were reconciled without rewriting
  historical `BR-*` records.

## Feature-plan review result

The fresh
[review report](.tasks/TASK-MB-REVIEW-FEAT-PLAN/TASK-MB-REVIEW-FEAT-PLAN-S-FEAT-final-report-docs-01.md)
records `VERDICT: APPROVE`.

The review confirms 32 stable `REQ-*` IDs with complete RTM/feature coverage,
three epics and twelve product features. FT-012 durably records the explicit
operator decision to keep Photo mutation/purge and independently testable
1/5/60-minute counters in one planning and completion boundary for the current
pilot; splitting or renumbering requires a new operator decision.

The review reports no blockers, unresolved operator questions or repair route.
The authoritative next handoff from `.memory-bank/spec-backbone.md` is
`/foundation-to-tasks`.

## Caller-owned validation

- `node scripts/mb-lint.mjs` passes.
- Strict doctor is expected to report `TASK_INDEX_EMPTY` until the Foundation
  queue is created through the authorized workflow.
- Preserve `Planning Revision: 2` and `pending_foundation_to_tasks`; do not
  create Foundation tasks outside the `/foundation-to-tasks` workflow.
