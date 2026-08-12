# Technical-debt review — wave W1

## Result

No material technical debt was confirmed in the checked closed W1 change
surface. This is an advisory report only; it does not block or change workflow
state.

## Checked scope

Only the actual closed-task change surface for `TASK-018-T2-FT-002-W1` and
`TASK-033-T3-FT-002-W1`:

- processing persistence: `migrations/versions/0008_processing_persistence.py`,
  `migrations/env.py`, `src/face_moment/processing/{revisions,initial_pending,persistence}.py`,
  and their direct processing/inventory/serving-control fixtures including
  `tests/processing/test_processing_persistence.py` and
  `tests/pipeline_compatibility.py`;
- PostgreSQL capacity observation:
  `src/face_moment/infrastructure/capacity.py`,
  `src/face_moment/infrastructure/settings.py`, `compose.yaml`, and
  `tests/infrastructure/test_postgresql_capacity.py`;
- direct task records, closure reports and the task-owned documentation updates.

Later FT-002 waves, unconnected working-tree changes and future API/UI consumer
integration are outside this review.

## Evidence checked

- Indexed done records:
  `.memory-bank/tasks/TASK-018-T2-FT-002-W1.task.json` and
  `.memory-bank/tasks/TASK-033-T3-FT-002-W1.task.json`.
- TASK-018 direct implementation: legacy-cutover guard and compatibility
  immutability trigger in
  `migrations/versions/0008_processing_persistence.py:26-91`; face ownership
  and embedding-dimension enforcement at `:120-155,283-380`; runtime singleton
  at `:382-423`; mapped processing persistence at
  `src/face_moment/processing/persistence.py:34-164`; and focused migration
  proof at `tests/processing/test_processing_persistence.py:39-390`.
- TASK-018 decisive closure evidence:
  `.tasks/TASK-018-T2-FT-002-W1/TASK-018-T2-FT-002-W1-S-VERIFY-final-report-docs-01.md`
  records fresh packaged-image mypy, focused PostgreSQL migration proof,
  one-head inspection and Memory Bank lint as passing.
- TASK-033 direct implementation: redacted `statvfs` observation at
  `src/face_moment/infrastructure/capacity.py:20-48`, required positive
  configuration at `src/face_moment/infrastructure/settings.py:26-61`, and the
  backend-only read-only volume view at `compose.yaml:8-16,63-70`.
- TASK-033 focused projection/redaction tests at
  `tests/infrastructure/test_postgresql_capacity.py:32-96`, plus functional
  and adversarial evidence in
  `.tasks/TASK-033-T3-FT-002-W1/TASK-033-T3-FT-002-W1-S-VERIFY-final-report-docs-01.md`
  and
  `.tasks/TASK-033-T3-FT-002-W1/TASK-033-T3-FT-002-W1-S-RED-VERIFY-final-report-docs-01.md`.
- Current actual diff was inspected, including untracked task-owned source and
  tests; `git diff --check` completed with exit `0` and no output.

## Confirmed findings

## Smallest remediation direction

None; no material finding was admitted.

## Uncertainty

This review did not execute a repository-wide audit or assess later FT-002
consumer integration. It relies on the fresh task-owned verification evidence
for the closed runtime probes and considers only the explicit W1 surface.
