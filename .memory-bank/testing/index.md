---
description: Стратегия тестирования и верификации (quality gates, anti-cheat, UI/e2e).
status: active
last_updated: 2026-09-02
---
# Testing & Verification

## Subject specifications

- [Client realtime verification](client-realtime.md): chronological
  first-at-most-20 BlazeFace submission, browser/ESP32 transport, crop/JPEG/
  manifest contract, one-clock Promo latency, diagnostic markers,
  QR phone continuation, media/retention checks and explicit exclusions.
- [Calibration verification](calibration.md): deterministic threshold-profile
  oracle, one-dimensional quality analysis, before/after comparison,
  manual-apply isolation, shared-worker recovery and promoted-case retention.
- [Photo processing verification](photo-processing.md): terminal and
  compatibility states, idempotent retry/restart, full-population ingest SLO,
  shared-worker delay and independent PostgreSQL/MinIO capacity evidence.

## Quality gates

- Baseline code DoD: configured build/typecheck and relevant unit tests
- lint / typecheck
- unit tests
- integration tests (if applicable)
- e2e tests for critical user flows
- additional tier-required `/verify`, `/red-verify`, protocol, and human gates

## Executable Baseline Contract

[Foundation Dev Path](../foundation.md#minimal-work-path) owns the required
commands, substrate shape, scope and exclusions.

### Current-source development gate

- Python typecheck, relevant tests, migrations and role startup run with
  `uv run --locked` from the editable working tree. Integration commands load
  `.env.local` explicitly.
- The local Compose overlay starts only PostgreSQL/pgvector and MinIO and
  publishes them on loopback. Python roles and Caddy are not part of the daily
  container loop.
- A successful local gate proves current source, not the packaged release.
  Conversely, bare `docker compose run` without a current build is not accepted
  as current-source evidence.

### Packaged-runtime gate

- `scripts/smoke-runtime.sh` remains the final isolated proof of the built
  image, three Python roles, private topology and HTTPS edge.
- The base `compose.yaml` remains the release composition; the local overlay is
  never used as production-topology evidence.

### Foundation verification targets

A fresh final gate MUST:

- run every Foundation command from unique disposable Compose resources without
  touching operator/default state; a failed prerequisite or assertion is
  unready/non-zero;
- prove `REQ-000`: one image/three roles, one `Base`/Alembic stream over
  PostgreSQL/pgvector without product tables, OpenCV/InsightFace imports,
  fake-engine HTTPS readiness, private topology without a Docker socket,
  storage restart and owned cleanup;
- stop without repair on failure and store redacted command/probe evidence
  under `.tasks/<TASK_ID>/`.

## Current pilot priority

- Promo/QR latency and stable continuation are acceptance priorities.

## UI verification

- The installed Playwright CLI (`playwright cli`) is the project-default driver
  for agent-run real-browser UI/UAT.
- A task that requires real-browser proof MUST name `playwright cli` in its
  `constraints` and specify the concrete browser flow and artifacts in
  `verification_targets`.
- Store the Playwright CLI transcript and screenshots/videos/traces in
  `.tasks/TASK-NNN-TN-FT-NNN-WN/`.
- In Memory Bank keep only links + short conclusions

## Artifacts
- screenshots/logs/videos → .tasks/TASK-NNN-TN-FT-NNN-WN/
- in Memory Bank store only links + conclusions
