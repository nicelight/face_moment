---
description: Implementation plan for the FT-000 executable Foundation queue.
status: active
last_updated: 2026-07-24
---
# IMPL-FT-000 — Executable Foundation

## Goal

Establish the minimum reproducible Face Moment walking skeleton and prove it
from a fresh isolated state before any product task is designed.

## Normative basis

- [.memory-bank/foundation.md](../../foundation.md): accepted scope, Feature
  Pressure Map, commands and exit criteria.
- [System architecture](../../architecture/system-architecture.md): AD-001,
  AD-010 and AD-011 plus runtime/deployment and capability-root rules.
- [Boundary map](../../contracts/boundary-map.md): one schema/Base/Alembic
  stream, private stores and PostgreSQL/MinIO convergence.
- [Testing specification](../../testing/index.md), section
  `Executable Baseline Contract`: required shape, isolation, failure behavior
  and proof targets.
- [.memory-bank/requirements.md](../../requirements.md): `REQ-000`.

## Scope

### In scope

- One installable Python release and one application image.
- Separately invocable backend, background-worker and realtime roles.
- Minimum composition/infrastructure roots and only the capability root needed
  by the fake `FaceEngine` seam.
- PostgreSQL/pgvector, private MinIO, one Base/Alembic stream and an
  empty-database baseline migration.
- Non-production HTTPS readiness.
- Configured mypy/pytest gates and a deterministic isolated host-side smoke
  command covering imports, topology, storage, restart and cleanup.

### Out of scope

- FT-001..FT-012 behavior, product schemas, endpoints, auth or seed data.
- Empty future capability packages or generic shared abstractions.
- Real face model download/inference, camera/display integration, production
  certificates/deployment, backup, broker, extra workers or distributed
  coordination.

## Architecture and ownership

- The composition root owns only settings, adapters, wiring, lifecycle, start
  and shutdown.
- `entrypoints` and `infrastructure` are technical roots, not business owners.
- A `processing` root is created only if needed to own the accepted
  `FaceEngine` seam. `serving_control`, `inventory`, `promo` and `diagnostics`
  are not scaffolded empty.
- One physical PostgreSQL schema does not create shared business ownership.
  Foundation creates no business tables or cross-slice commands.

## Cohesive strategy

1. Build the package/release, role entrypoints and fake-engine readiness seam.
2. Add the one-image Compose topology, private stores, HTTPS edge and
   migrate/init path.
3. Configure the single Base/Alembic stream and an empty product schema.
4. Add unit/static coverage and `scripts/smoke-runtime.sh` with isolated
   Compose identity, disposable resources, deterministic restart/cleanup and
   non-zero failure behavior.
5. Run the implementation task's applicable gates.
6. Run the separate final gate from a fresh isolated state without repairing
   failures.

## Tasks

| Task | Tier | Initial status | Depends on | Outcome |
|---|---|---|---|---|
| [TASK-001-T3-FT-000-W0](../TASK-001-T3-FT-000-W0.task.json) | T3 | ready | none | Implement the complete minimal walking skeleton and deterministic smoke harness. |
| [TASK-002-T2-FT-000-W0](../TASK-002-T2-FT-000-W0.task.json) | T2 | planned | TASK-001 | Independently prove every Foundation exit target; this is the only final gate. |

## Advisory expected change surface

- `pyproject.toml`
- `Dockerfile`
- `compose.yaml`
- `.dockerignore`
- `alembic.ini`
- `migrations/`
- `src/face_moment/entrypoints/`
- `src/face_moment/infrastructure/`
- `src/face_moment/processing/` only for the actual `FaceEngine` seam
- `tests/`
- `scripts/smoke-runtime.sh`
- a narrowly located HTTPS-edge configuration selected by the executor

These paths are advisory and non-exhaustive. Exact module/config filenames
remain implementation discretion where the framework or chosen edge supplies
the convention. No hard write boundary is inferred from this list.

## Quality gates and UAT

- `docker compose config --quiet`
- `docker compose build`
- `docker compose run --rm --no-deps backend python -m mypy src/face_moment`
- `docker compose run --rm backend python -m pytest`
- `bash scripts/smoke-runtime.sh`
- Tier-routed `/verify`; TASK-001 additionally requires T3 `/red-verify` and
  the human checkpoint before closure.

The smoke run is the Foundation UAT: one image/three roles, empty migration,
pgvector, private MinIO, OpenCV/InsightFace imports, fake-engine readiness,
HTTPS, read/write/delete, persistence after restart and owned cleanup.

## Stop conditions

- Meeting the outcome would require changing the accepted architecture,
  Foundation decision, public/private service boundary or single migration
  stream.
- A product schema, endpoint, state machine, auth flow or feature behavior is
  required to make the proof pass.
- The smoke run cannot be isolated from existing operator/default volumes or
  would need the Docker socket mounted into a container.
- A real model download/inference, production certificate or production action
  becomes necessary.

## Definition of done

- Both indexed tasks satisfy their tier lifecycle and evidence requirements.
- `TASK-002-T2-FT-000-W0` is `done` with independent `VERDICT: PASS`.
- `REQ-000` and FT-000 lifecycle/RTM state are reconciled at the owning
  wave-boundary sync.
- The final gate enables product `/feature-to-tasks`; it does not generate
  product tasks itself.
