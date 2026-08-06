---
description: Стратегия тестирования и верификации (quality gates, anti-cheat, UI/e2e).
status: active
last_updated: 2026-08-06
---
# Testing & Verification

## Subject specifications

- [Client realtime verification](client-realtime.md): chronological
  first-at-most-20 BlazeFace submission, browser/ESP32 transport, crop/JPEG/
  manifest contract, one-clock Promo latency, diagnostic markers,
  media/retention checks and explicit exclusions.
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

- Prefer Playwright / agent-browser / CDP for UI flows when available
- Store screenshots/videos/traces in .tasks/TASK-NNN-TN-FT-NNN-WN/
- In Memory Bank keep only links + short conclusions

## Artifacts
- screenshots/logs/videos → .tasks/TASK-NNN-TN-FT-NNN-WN/
- in Memory Bank store only links + conclusions
