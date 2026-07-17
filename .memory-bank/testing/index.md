---
description: Стратегия тестирования и верификации (quality gates, anti-cheat, UI/e2e).
status: active
---
# Testing & Verification

## Quality gates

- Baseline code DoD: configured build/typecheck and relevant unit tests
- lint / typecheck
- unit tests
- integration tests (if applicable)
- e2e tests for critical user flows
- additional tier-required `/verify`, `/red-verify`, protocol, and human gates

## Current pilot priority

- Promo/QR latency and stable continuation are acceptance priorities.

## UI verification

- Prefer Playwright / agent-browser / CDP for UI flows when available
- Store screenshots/videos/traces in .tasks/TASK-NNN-TN-FT-NNN-WN/
- In Memory Bank keep only links + short conclusions

## Artifacts
- screenshots/logs/videos → .tasks/TASK-NNN-TN-FT-NNN-WN/
- in Memory Bank store only links + conclusions
