---
description: Foundation Dev Path evidence and feature pressure map for the greenfield Face Moment pilot.
status: active
last_updated: 2026-07-24
---
# Foundation Dev Path

## Gate Anchors
- Foundation Required: true
- Foundation Requirement: REQ-000
- Foundation Pseudo-Feature: FT-000
- Foundation Gate Task: pending_foundation_to_tasks

## Decision Evidence

The repository has no working application, backend, worker, database schema,
deployed runtime or project-native build/start/test command. A minimal
executable walking skeleton is required before product feature work can prove
the accepted shared runtime and storage boundaries.

Foundation establishes substrate only. Photo admission, processing, Promo,
diagnostics and Photo Inventory Operations remain product-feature behavior.

## Minimal Work Path
- Build command: not_available - Foundation must establish one reproducible build/typecheck command.
- Start command: not_available - Foundation must establish one single-server local start command.
- Primary entrypoint: not_available - Foundation must create backend, worker and realtime entrypoint seams from one release.
- Smoke path: future fake-FaceEngine substrate path through HTTPS application,
  one PostgreSQL schema built by the single Alembic stream, and private MinIO.
- Test command: not_available - Foundation must establish one project-native test command.
- Evidence: successful commands plus migration from an empty database through
  one SQLAlchemy `Base/MetaData`/Alembic path, PostgreSQL and MinIO
  read/write/delete, realtime warmup seam, SpaPromoClient build and one
  substrate end-to-end smoke.

## Feature Pressure Map

| Feature | Pressure | Foundation Response | Probe | Status |
|---|---|---|---|---|
| FT-001, FT-002, FT-012 | Shared PostgreSQL/MinIO baseline, migration/init and backend/worker entrypoints. | Compose storage, one application schema, one shared `Base/MetaData`, one Alembic configuration/stream and fake processing seam. | Apply the linear stream to an empty database; storage roundtrip and durable row visibility across restart. | planned |
| FT-003, FT-004, FT-005, FT-006 | Realtime entrypoint, client build and warmup/readiness seam. | One fake realtime request path and SpaPromoClient build. | Start roles and complete one non-production substrate flow. | planned |
| FT-007..FT-011 | Shared auth, Attempt/evidence persistence and background entrypoint. | Minimal role/auth and persistence wiring only. | Authenticated write/read through owning boundary. | planned |

## Deferred Decisions

| Decision | Why deferred | Trigger to revisit |
|---|---|---|
| Photo/Attempt/purge table shape, foreign keys/`ON DELETE` rules and endpoint payloads | Product behavior does not belong in Foundation; cross-ownership cascade is already forbidden. | Owning feature task design and contract proof. |
| Crash/restart matrices | Owner-specific recovery is cheaper to prove with each feature. | FT-002, FT-007, FT-011 or FT-012 execution. |
| Camera/sensor transport and offline browser proof | Pilot hardware is not selected. | Before FT-003 implementation. |
| Backup, replicas and distributed coordination | Explicitly outside the accepted pilot. | New operator durability/scale decision. |

## Foundation Exit Criteria
- minimal path passes
- single Alembic migration stream builds the empty application schema
- compatibility probes pass
- no P0/P1 design pressure unresolved
- feature dev path allowed
