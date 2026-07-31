---
description: Foundation Dev Path evidence and feature pressure map for the greenfield Face Moment pilot.
status: active
last_updated: 2026-07-31
---
# Foundation Dev Path

## Gate Anchors
- Foundation Required: true
- Foundation Requirement: REQ-000
- Foundation Pseudo-Feature: FT-000
- Foundation Gate Task: TASK-002-T2-FT-000-W0

## Decision Evidence

The accepted target requires one release with backend, worker and realtime
roles, one PostgreSQL/Alembic stream, private MinIO and an HTTPS edge. At the
Foundation decision boundary, the repository had no application code,
package/build manifest, Compose definition, database schema, migration,
entrypoint or project-native build/typecheck/start/test command. Product
features therefore could not start with a reproducible executable baseline,
which required a separate minimum Foundation queue.

Foundation establishes substrate only. Photo admission, processing, Promo,
diagnostics and Photo Inventory Operations remain product-feature behavior.
That initial absence was evidence for the walking skeleton; the verified
Foundation does not define or override the accepted target architecture.

## Minimal Work Path
- Build command: `docker compose build`.
- Typecheck command:
  `docker compose run --rm --no-deps backend python -m mypy src/face_moment`;
  `mypy` is a dev/test dependency configured in the project `pyproject.toml`.
- Start command: `docker compose up --build` (single-server composition).
- Primary entrypoint: one release image with separately invocable `backend`,
  `BackgroundPhotoWorker` and `RealtimeFaceService` roles; concrete Python
  module names remain implementation discretion.
- Smoke path: apply the one Alembic stream to an empty PostgreSQL database,
  ensure private MinIO buckets, start all three roles with a fake `FaceEngine`,
  verify HTTPS readiness, PostgreSQL/MinIO read-write-delete and restart.
- Test command: `docker compose run --rm backend python -m pytest`.
- Deterministic smoke command: `bash scripts/smoke-runtime.sh`; its isolation,
  failure and evidence rules are canonical in the
  [testing specification](testing/index.md), section
  `Executable Baseline Contract`.
- Evidence: build, typecheck, start, test and smoke commands exit with code
  `0`; the empty-database migration uses one SQLAlchemy `Base/MetaData`; the
  target image imports OpenCV and InsightFace; fake realtime warmup/readiness
  and storage/restart probes pass. No product Photo, Attempt, session, evidence
  or Promo behavior is part of this proof.

## Feature Pressure Map

| Feature | Pressure | Foundation Response | Probe | Status |
|---|---|---|---|---|
| FT-001, FT-002, FT-012 | Shared PostgreSQL/MinIO baseline, migration/init and backend/worker entrypoints. | Compose storage, one application schema, one shared `Base/MetaData`, one Alembic configuration/stream and fake worker seam. | Apply the linear stream to an empty database; storage roundtrip and restart visibility. | required |
| FT-003, FT-004, FT-005, FT-006 | Realtime role and HTTPS readiness must exist before capture/search behavior. | One fake realtime warmup/readiness seam in the common release. The accepted central-origin browser/mDNS ESP32 transport and client proposal behavior remain product-feature scope, not Foundation work. | Start all server roles and complete one non-production readiness request. | required |
| FT-007..FT-011 | Diagnostics need only the same runnable application, database and worker substrate. | Reuse the common server/storage seams; do not create auth, Attempt, evidence or Calibration product rows in Foundation. | Common build/typecheck/start/test and database probes pass without empty capability scaffolds. | covered |

## Deferred Decisions

| Decision | Why deferred | Trigger to revisit |
|---|---|---|
| Photo/Attempt/purge table shape, foreign keys/`ON DELETE` rules and endpoint payloads | Product behavior does not belong in Foundation; cross-ownership cascade is already forbidden. | Owning feature task design and contract proof. |
| Crash/restart matrices | Owner-specific recovery is cheaper to prove with each feature. | FT-002, FT-007, FT-011 or FT-012 execution. |
| Exact camera/site geometry | Camera model, lens, lighting and maximum input dimensions are deployment configuration; the browser/mDNS ESP32 route is already accepted and adds no Foundation work. | Configure and verify the pilot site. |
| Backup, replicas and distributed coordination | Explicitly outside the accepted pilot. | New operator durability/scale decision. |

## Foundation Exit Criteria
- minimal path passes
- configured project-native build, Python typecheck and relevant unit tests pass
- single Alembic migration stream builds the empty application schema
- compatibility probes pass
- no P0/P1 design pressure unresolved
- feature dev path allowed
