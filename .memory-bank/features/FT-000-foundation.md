---
description: Foundation pseudo-feature for the minimum executable Face Moment baseline.
status: active
lifecycle: verified
last_updated: 2026-07-24
source_of_truth:
  - .memory-bank/features/FT-000-foundation.md
spec_design_status: complete
spec_design_links:
  - .memory-bank/architecture/system-architecture.md
  - .memory-bank/contracts/boundary-map.md
  - .memory-bank/testing/index.md
---
# FT-000 — Executable Foundation

## Pseudo-feature note

`FT-000` is the reserved Foundation Dev Path pseudo-feature. It supplies a
verified executable substrate for later product work; it is not a product epic,
user-visible feature or authorization to implement FT-001..FT-012 behavior.

## Outcome

A fresh checkout can build, typecheck, test and start one Face Moment release
with backend, background-worker and realtime roles, one PostgreSQL/pgvector and
Alembic baseline, private MinIO, a non-production HTTPS edge and deterministic
fake-engine/storage/restart probes.

## Requirement

- `REQ-000`.
- Registry: [.memory-bank/requirements.md](../requirements.md).

## Canonical inputs

- [.memory-bank/foundation.md](../foundation.md): accepted Foundation decision,
  scope guard, Feature Pressure Map and final gate.
- [System architecture](../architecture/system-architecture.md): AD-001,
  AD-010 and AD-011 plus the accepted runtime, capability-root and deployment
  shape.
- [Boundary map](../contracts/boundary-map.md): one schema/Base/Alembic stream,
  private-service topology and PostgreSQL/MinIO convergence.
- [Testing specification](../testing/index.md), section
  `Executable Baseline Contract`: required commands, isolation, failures,
  evidence and verification targets.

## Scope

- One installable Python release and one image.
- Three separately invocable server roles with the minimum composition,
  infrastructure and actually used capability roots.
- One empty-database migration baseline, PostgreSQL/pgvector and private MinIO.
- Non-production HTTPS readiness and fake `FaceEngine` warmup.
- Deterministic isolated build/typecheck/test/storage/restart proof.

## Non-goals

- Product Photo, processing, Attempt, Promo/session, diagnostics, inventory,
  authentication or participant behavior.
- Empty future capability slices, product tables/endpoints or seed data.
- Real model download/inference, production certificates/deployment, browser or
  camera integration, backup, broker, extra worker or distributed machinery.

## Acceptance and failure behavior

- Every command and verification target in the executable baseline contract
  passes from a fresh isolated state.
- The same image supplies the three role entrypoints and imports OpenCV and
  InsightFace while the realtime proof uses only a fake engine.
- PostgreSQL/MinIO/internal application ports remain private and only the test
  HTTPS edge is host-facing.
- Any build, migration, warmup, readiness, topology, storage, restart or
  cleanup failure is visible and non-zero.
- The final gate does not repair failures. It records evidence and stops for
  the owning task or planning route.

## Tasking

- [Implementation plan](../tasks/plans/IMPL-FT-000.md).
- Implementation: [TASK-001-T3-FT-000-W0](../tasks/TASK-001-T3-FT-000-W0.task.json).
- Final gate: [TASK-002-T2-FT-000-W0](../tasks/TASK-002-T2-FT-000-W0.task.json).

## Verified outcome

- [TASK-001-T3-FT-000-W0](../tasks/TASK-001-T3-FT-000-W0.task.json) is `done`
  with functional `PASS`, `semantic-pass` and `HUMAN_CHECKPOINT: done`;
  see its
  [functional report](../../.tasks/TASK-001-T3-FT-000-W0/TASK-001-T3-FT-000-W0-S-VERIFY-final-report-docs-01.md)
  and
  [semantic report](../../.tasks/TASK-001-T3-FT-000-W0/TASK-001-T3-FT-000-W0-S-RED-VERIFY-final-report-docs-01.md).
- [TASK-002-T2-FT-000-W0](../tasks/TASK-002-T2-FT-000-W0.task.json) is `done`
  with independent `VERDICT: PASS`; see its
  [verification report](../../.tasks/TASK-002-T2-FT-000-W0/TASK-002-T2-FT-000-W0-S-VERIFY-final-report-docs-01.md)
  and
  [REQ-000/Foundation evidence map](../../.tasks/TASK-002-T2-FT-000-W0/req-foundation-evidence-map.md).
- The accepted executable substrate is therefore verified. No product behavior
  was added and no finding, fix or follow-up task remains.
