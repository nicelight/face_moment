---
description: Implementation plan for independent authenticated Photo admission in FT-001.
status: active
last_updated: 2026-08-08
---
# IMPL-FT-001 — Independent Photo Admission

## Goal

Deliver the authenticated per-file photographer flow from staff provisioning
through private candidate staging, atomic Photo admission and visible uploader
outcomes, while preserving capability ownership and the accepted crash/
duplicate semantics.

## Normative Basis

- [FT-001](../../features/FT-001.md): `FT-001-AC-001..012` and governing
  `REQ-ING-001..003`, `REQ-SEC-001` and `REQ-ARCH-001`.
- [System Architecture](../../architecture/system-architecture.md): AD-002,
  AD-003, AD-009, AD-010 and AD-011.
- [Boundary Map](../../contracts/boundary-map.md): modules, Independent Photo
  admission, shared PostgreSQL, PostgreSQL/MinIO convergence and HTTP failures.
- [Photo Admission API](../../contracts/photo-admission-api.md): staff session,
  ingest-target, upload, failure and independent uploader-page contracts.
- [Photo Admission](../../domains/photo-admission.md): target records, Photo/
  pending persistence, validation, staging, transaction, duplicate and crash
  recovery contracts.
- [Staff Access](../../domains/staff-access.md): principals, browser sessions,
  initial provisioning and credential lifecycle.
- [Lifecycle Map](../../states/lifecycle-map.md#independent-photo-admission):
  independent admission and accepted recovery.

## Scope And Non-Goals

In scope are staff principals/sessions needed by the photographer, one owner-
backed pilot ingest target, the minimum immutable processing revision and
initial `pending` provider, Photo/JPEG persistence, private MinIO staging, the
exact staff API and the per-file uploader page.

Out of scope are background claiming/inference/terminal processing, processing-
status UI, operator revision switching, inventory delete/restore/purge,
external/resumable ingest, Batch state, production identities and production
deployment.

## Architecture And Ownership

| Outcome owner | Code root | Public/crossed boundary | Forbidden bypass |
|---|---|---|---|
| `staff_access` | `src/face_moment/platform/auth/` | Authenticate staff and publish the current principal. | Auth code does not authorize or orchestrate Photo admission. |
| `processing` | `src/face_moment/processing/` | Publish immutable revision eligibility and typed initial-`pending` creation. | Inventory never writes processing-owned rows directly. |
| `serving_control` | `src/face_moment/serving_control/` | Publish immutable `IngestTarget`. | Transport/inventory never writes СПА or revision selection directly. |
| `inventory` | `src/face_moment/inventory/` | Own JPEG validation, candidate staging, Photo admission, API and uploader outcome. | Handlers, shared helpers and composition roots do not own the flow or write foreign state. |

Thin route registration, dependency wiring, shared `Base`/Alembic integration
and S3 adapters may touch the existing entrypoint/infrastructure roots without
moving business ownership there.

## Accepted Tasks And Dependency Strategy

Every W1 root depends directly on the verified Foundation final gate. Later
tasks retain it transitively. Waves express prerequisites; execution remains
sequential.

| Task | Tier | Wave | Direct prerequisites | Exact claim | Outcome |
|---|---|---|---|---|---|
| [TASK-003-T3-FT-001-W1](../TASK-003-T3-FT-001-W1.task.json) | T3 | W1 | Foundation final gate | `FT-001-AC-006` | Staff principals and initial provisioning. |
| [TASK-004-T3-FT-001-W2](../TASK-004-T3-FT-001-W2.task.json) | T3 | W2 | TASK-003 | `FT-001-AC-007` | Secure browser sessions. |
| [TASK-005-T3-FT-001-W3](../TASK-005-T3-FT-001-W3.task.json) | T3 | W3 | TASK-004 | `FT-001-AC-008` | Reset/deactivation with session revocation. |
| [TASK-006-T2-FT-001-W1](../TASK-006-T2-FT-001-W1.task.json) | T2 | W1 | Foundation final gate | `FT-001-AC-009` | Immutable processing-revision eligibility. |
| [TASK-007-T2-FT-001-W2](../TASK-007-T2-FT-001-W2.task.json) | T2 | W2 | TASK-006 | `FT-001-AC-010` | Serving-owned ingest target. |
| [TASK-008-T2-FT-001-W3](../TASK-008-T2-FT-001-W3.task.json) | T2 | W3 | TASK-007 | `photo-admission.md#face_momentphotos` | Photo identity persistence. |
| [TASK-009-T2-FT-001-W4](../TASK-009-T2-FT-001-W4.task.json) | T2 | W4 | TASK-006, TASK-008 | `photo-admission.md#face_momentphoto_pipeline_states` | Initial processing `pending` boundary. |
| [TASK-010-T2-FT-001-W1](../TASK-010-T2-FT-001-W1.task.json) | T2 | W1 | Foundation final gate | `photo-admission.md#jpeg-and-time-contract` | JPEG/time validation. |
| [TASK-011-T3-FT-001-W1](../TASK-011-T3-FT-001-W1.task.json) | T3 | W1 | Foundation final gate | `FT-001-AC-011` | Private candidate staging and cleanup. |
| [TASK-012-T2-FT-001-W5](../TASK-012-T2-FT-001-W5.task.json) | T2 | W5 | TASK-007, TASK-008, TASK-009, TASK-010, TASK-011 | `FT-001-AC-003` | Atomic Photo plus pending transaction. |
| [TASK-013-T2-FT-001-W6](../TASK-013-T2-FT-001-W6.task.json) | T2 | W6 | TASK-012 | `FT-001-AC-002` | Duplicate arbitration and cleanup. |
| [TASK-014-T2-FT-001-W6](../TASK-014-T2-FT-001-W6.task.json) | T2 | W6 | TASK-012 | `FT-001-AC-005` | Pre-commit crash and re-upload recovery. |
| [TASK-015-T3-FT-001-W3](../TASK-015-T3-FT-001-W3.task.json) | T3 | W3 | TASK-004, TASK-007 | `FT-001-AC-012` | Authenticated ingest-target endpoint. |
| [TASK-016-T3-FT-001-W7](../TASK-016-T3-FT-001-W7.task.json) | T3 | W7 | TASK-005, TASK-013, TASK-014 | `FT-001-AC-004` | Secured Photo upload endpoint. |
| [TASK-017-T2-FT-001-W8](../TASK-017-T2-FT-001-W8.task.json) | T2 | W8 | TASK-015, TASK-016 | `FT-001-AC-001` | Independent per-file uploader UI. |

The accepted boundary intentionally keeps all fifteen outcomes separate.
Common ownership, command, migration stream or transaction is not merge
evidence.

## Advisory Expected Change Surface

- `src/face_moment/platform/auth/`
- `src/face_moment/processing/`
- `src/face_moment/serving_control/`
- `src/face_moment/inventory/`
- `src/face_moment/entrypoints/backend.py`
- `src/face_moment/infrastructure/`
- `migrations/versions/`
- `tests/staff_access/`, `tests/processing/`, `tests/serving_control/` and
  `tests/inventory/`

These paths are advisory and non-exhaustive. Each Alembic revision uses the
linear head current at execution as its direct `down_revision`; exact revision
filenames remain executor discretion. No hard write boundary is inferred.

## Tests, Gates And UAT

- Configured mypy over `src/face_moment` and task-relevant pytest files run for
  every task.
- Migration tasks prove ancestry, upgrade, downgrade and re-upgrade in isolated
  PostgreSQL state without asserting a mutable future exact head.
- Storage/integration probes use disposable PostgreSQL/MinIO data, are safe to
  rerun and clean only task-owned objects/rows.
- Contract tests cover exact cookies, roles, CSRF, response shapes and standard
  HTTP mappings; T3 probes also retain redacted security evidence.
- Staff-session, credential-lifecycle and ingest-target T3 probes name their
  task-unique disposable fixtures, isolated application/database state, safe
  rerun behavior and owner-bounded cleanup directly in each task card.
- Final UAT runs through the installed Playwright CLI (`playwright cli`), logs
  in as a photographer, selects one СПА/date and independently uploads valid,
  invalid, undecodable, mixed-EXIF and duplicate files while preserving every
  completed row; retain the CLI transcript, screenshots and trace in the
  TASK-017 artifact directory.
- Tier-routed `/verify` applies to every task; each T3 task additionally needs
  per-task `/red-verify`. Feature completion is determined by the accepted task
  records and feature completion boundary; no separate feature-level verdict is
  used.

## Constitution Constraints And Invariants

- Keep the one-release modular monolith, one schema/Base/Alembic stream and
  private PostgreSQL/MinIO topology.
- Create no Batch, distributed limiter, object transaction emulator, generic
  IAM/RBAC service or processing lifecycle beyond initial `pending`.
- The photographer-selected `visit_date` remains authoritative; accepted Photo
  and serving `pending` publish together; duplicate/rejected candidates publish
  neither.
- Cross-slice writes use the accepted typed application boundaries, and no
  database cascade crosses ownership.

## Definition Of Done

All fifteen indexed tasks independently satisfy their task-owned claims and
tier obligations, every FT-001 AC has one owner, the complete photographer UAT
passes, and later feature-completion review/semantic verification can proceed
without guessing or changing Planning Revision `4`.
