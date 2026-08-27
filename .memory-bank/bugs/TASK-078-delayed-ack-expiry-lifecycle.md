---
description: Task-local defect found after the final TASK-078 verification attempt.
status: active
---
# TASK-078 delayed-ACK expiry lifecycle defect

## Evidence

Fresh independent verification of `TASK-078-T3-FT-005-W2` Attempt 3/3 passed
the independent display timer, delayed-ACK suppression, configuration,
session-continuity and cooldown-owner checks. The app-level expiry probe then
observed:

- `client/app.js:426-433` releases the result outcome and renders advertising;
- the only `triggerController.finishAttempt(...)` listener is
  `client/app.js:780-785`;
- the capture controller remains `searching` after pending-ACK expiry and the
  next trigger is rejected as `busy` by `client/trigger-series.js:198-205`.

Verifier artifacts:

- `.tasks/TASK-078-T3-FT-005-W2/attempt-3-verifier-app-expiry-probe-output.json`
- `.tasks/TASK-078-T3-FT-005-W2/TASK-078-T3-FT-005-W2-S-VERIFY-final-report-docs-03.md`

## Disposition

The defect is task-local and was found on the final overall Attempt 3/3.
`TASK-078` is authoritatively `failed` and the autopilot run halts with
`HALT_FAILURE_BUDGET`. No fourth executor attempt, semantic verifier,
promotion or later-task selection is authorized in this run.

## Owner / next action

The normal implementation owner must route a reviewed task-local correction
that completes the active capture lifecycle exactly once when pending-ACK
display expiry returns to advertising, while preserving the late-ACK stale
guard and independent success cooldown. This run does not execute that repair.
