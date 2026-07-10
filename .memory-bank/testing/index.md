---
description: Стратегия тестирования и верификации (quality gates, anti-cheat, UI/e2e).
status: active
---
# Testing & Verification

## Quality gates
- lint / typecheck
- unit tests
- integration tests (if applicable)
- e2e tests for critical user flows

## UI verification
- Prefer Playwright / agent-browser / CDP for UI flows when available
- Store screenshots/videos/traces in .tasks/TASK-NNN-TN-FT-NNN-WN/
- In Memory Bank keep only links + short conclusions

## Artifacts
- screenshots/logs/videos → .tasks/TASK-NNN-TN-FT-NNN-WN/
- in Memory Bank store only links + conclusions
