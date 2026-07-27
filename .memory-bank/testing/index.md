---
description: Стратегия тестирования и верификации (quality gates, anti-cheat, UI/e2e).
status: active
last_updated: 2026-07-28
---
# Testing & Verification

## Subject specifications

- [Client realtime verification](client-realtime.md): all-occurrence
  submission, one-clock Promo latency, diagnostic markers, media/retention
  checks and explicit exclusions.

## Quality gates

- Baseline code DoD: configured build/typecheck and relevant unit tests
- lint / typecheck
- unit tests
- integration tests (if applicable)
- e2e tests for critical user flows
- additional tier-required `/verify`, `/red-verify`, protocol, and human gates

## Executable Baseline Contract

This section is the canonical verification contract for the greenfield
walking skeleton defined by
[.memory-bank/foundation.md](../foundation.md). It proves substrate only and
does not authorize product behavior.

### Required shape

- One installable Python release and one application image MUST expose
  separately invocable `backend`, `BackgroundPhotoWorker` and
  `RealtimeFaceService` roles.
- The walking skeleton MUST use one PostgreSQL application schema, one shared
  SQLAlchemy `Base/MetaData`, one Alembic configuration and one linear
  migration stream.
- PostgreSQL/pgvector and MinIO MUST run on the private Compose network.
  Only the non-production HTTPS edge may publish a host-facing application
  port during the proof.
- The realtime role MUST use an explicit fake `FaceEngine` for bootstrap
  warmup/readiness. The common image MUST still import OpenCV and InsightFace.
- Only composition/wiring roots and capability roots used by the proof may be
  created. Empty future slices are not evidence.

### Project-native commands

The implemented baseline MUST make these commands runnable:

- `docker compose config --quiet`
- `docker compose build`
- `docker compose run --rm --no-deps backend python -m mypy src/face_moment`
- `docker compose run --rm backend python -m pytest`
- `docker compose up --build`
- `bash scripts/smoke-runtime.sh`

The smoke command is a deterministic host-side orchestrator for the isolated
proof. Its exact internal steps are implementation detail, but its observable
contract is fixed below.

### Isolated smoke contract

- The smoke run MUST use a unique non-production Compose project identity,
  dedicated disposable volumes, test credentials and a local test certificate.
  It MUST NOT attach to, reset or delete operator/default project volumes.
- It MUST apply the single migration stream to an empty PostgreSQL database,
  prove pgvector availability and confirm that migration output contains no
  Product, Attempt, Promo/session, evidence, auth or purge tables.
- It MUST ensure a private MinIO bucket and prove PostgreSQL and MinIO
  read/write/read-after-restart/delete convergence with test-scoped probe data.
  Any probe-created database relation and object MUST be removed during owned
  cleanup.
- It MUST start all three application roles from the same image, prove fake
  realtime warmup/readiness, and complete one non-production readiness request
  through HTTPS.
- It MUST prove that PostgreSQL, MinIO and internal application ports are not
  host-published, then restart the applicable application and storage services,
  re-check readiness and retained probe data, and clean up only its own
  Compose project resources.
- Containers MUST NOT receive the host Docker socket. Service restart
  orchestration remains in the host-side smoke command.

### Failure and evidence semantics

- Dependency, migration/init, fake-engine warmup or readiness failure MUST
  leave the affected role unready or terminate startup non-zero; readiness MUST
  NOT report success before its prerequisites pass.
- Any build, typecheck, test, import, topology, storage, restart, HTTPS or
  cleanup assertion failure MUST make the owning command exit non-zero.
- A failed final gate MUST stop and report evidence; it MUST NOT repair source,
  runtime configuration or product scope inside the gate task.
- Redacted command output, effective Compose topology, image identity,
  migration state, import checks, readiness responses, storage/restart results
  and owned-cleanup result belong under `.tasks/<TASK_ID>/`.

### Foundation verification targets

The final Foundation gate passes only when a fresh isolated run proves:

1. Compose config, build, configured mypy and pytest commands exit `0`.
2. One image supplies all three healthy role entrypoints.
3. Empty-database migration, pgvector and the single
   `Base/MetaData`/Alembic-stream constraint hold without product tables.
4. OpenCV and InsightFace import in the target image; fake `FaceEngine`
   warmup/readiness succeeds without downloading or running a production model.
5. HTTPS readiness, private-service topology, PostgreSQL/MinIO
   read-write-delete, persistence across restart and owned cleanup all pass.

### Foundation exclusions

- No product endpoint, domain state, seed data, Photo/Attempt/session/evidence
  row, staff authentication or participant flow belongs in this proof.
- No real model download/inference, public PostgreSQL/MinIO port, Docker socket
  mount, backup system, broker, extra worker, production certificate or
  production deployment is permitted.

## Current pilot priority

- Promo/QR latency and stable continuation are acceptance priorities.

## UI verification

- Prefer Playwright / agent-browser / CDP for UI flows when available
- Store screenshots/videos/traces in .tasks/TASK-NNN-TN-FT-NNN-WN/
- In Memory Bank keep only links + short conclusions

## Artifacts
- screenshots/logs/videos → .tasks/TASK-NNN-TN-FT-NNN-WN/
- in Memory Bank store only links + conclusions
