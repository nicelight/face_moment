---
description: Advisory technical-debt review for the completed TASK-111 FT-011 Wave 2 slice.
status: final
---
# TASK-111 Wave 2 technical-debt review — 2026-09-05

## Checked scope

- Only the newly completed `TASK-111-T3-FT-011-W2` replacement slice for
  `FT-011-AC-005`; the earlier Wave 2 report covering `TASK-102`, `TASK-103`
  and `TASK-105` was treated as prior scope, not as TASK-111 coverage.
- The authoritative task record, linked Calibration immutable-input,
  run-state, shared-worker and serving-isolation contracts, and the retained
  execution, functional-verification and semantic-verification evidence.
- The task-scoped code change in
  `src/face_moment/processing/offline_calibration.py:13,102-107,222-227` and
  regression fixture in
  `tests/processing/test_calibration_worker.py:47-57,173-266`. The declared
  `tests/diagnostics/test_calibration_runs.py` surface was inspected but has no
  TASK-111 change.

The containing commit `025ea17` includes other feature work. Those unrelated
hunks are outside this review; the TASK-111 execution report and actual
task-specific diff delimit the checked change surface.

## Outcome

No material technical debt was confirmed in the checked TASK-111 slice. The
change maps only the supported S3 `NoSuchKey` response at the two existing
offline Calibration reads, preserves propagation of other `ClientError`
values, and reuses the existing `CalibrationDatasetUnavailableError`, terminal
run transition and singleton-worker release path. The focused retained test and
independent verification evidence cover the prior durable-running failure,
terminal `failed/dataset_unavailable` state with `finished_at`, worker release,
queued Photo progress, unchanged serving revision and absence of a replacement
run.

## Confirmed findings

## Evidence locations

- `.memory-bank/tasks/TASK-111-T3-FT-011-W2.task.json`
- `.memory-bank/domains/calibration.md#immutable-input-and-evaluation`
- `.memory-bank/domains/calibration.md#persistence-and-run-state`
- `.memory-bank/testing/calibration.md#worker-recovery-and-retention-proof`
- `.tasks/TASK-111-T3-FT-011-W2/TASK-111-T3-FT-011-W2-S-EXECUTE-final-report-code-01.md`
- `.protocols/TASK-111-T3-FT-011-W2/verification.md`
- `.protocols/TASK-111-T3-FT-011-W2/red-verification.md`
- `.tasks/TASK-111-T3-FT-011-W2/red.txt`
- `.tasks/TASK-111-T3-FT-011-W2/green.txt`
- `src/face_moment/processing/offline_calibration.py:13,95-112,209-234`
- `tests/processing/test_calibration_worker.py:47-57,173-266`

## Uncertainty

- The retained NoSuchKey regression test exercises the production
  `execute_claimed`/sequential worker path. Independent verification reports a
  fresh direct classification probe for both offline input paths, but that
  probe is not retained as a separate test. Absence of that additional test
  alone is not an admitted debt finding, and the identical narrow mapping is
  present at both inspected reads.
- This bounded review does not assess unrelated code bundled in commit
  `025ea17` or reopen the earlier Wave 2 slices.
