---
description: Advisory technical-debt review for the closed FT-002 W2 change surface.
status: advisory
---
# Technical-debt review — FT-002 W2

## Result

No material technical debt was confirmed in the checked closed W2 change
surface. This report is advisory only and does not alter implementation or
workflow state.

## Checked scope

Only the actual FT-002 W2 surfaces named by the review request:

- `TASK-019-T2-FT-002-W2`: native SFace adapter at
  `src/face_moment/processing/sface_adapter.py:52-181` and its direct proof
  `tests/processing/test_sface_adapter.py`.
- `TASK-020-T2-FT-002-W2`: native Buffalo M adapter at
  `src/face_moment/processing/buffalo_adapter.py:50-187` and its direct proof
  `tests/processing/test_buffalo_adapter.py`.
- `TASK-021-T3-FT-002-W2`: deterministic private derivatives at
  `src/face_moment/processing/derivatives.py:37-145` and
  `tests/processing/test_derivatives.py`.
- `TASK-022-T2-FT-002-W2`: worker claim/failure boundary at
  `src/face_moment/processing/worker_claims.py:23-95`, its package export,
  and `tests/processing/test_worker_claims.py`.
- `TASK-034-T3-FT-002-W2`: independent MinIO capacity configuration in
  `src/face_moment/infrastructure/settings.py:7-65` and `compose.yaml:8-72`,
  plus the reused minimal observation adapter
  `src/face_moment/infrastructure/capacity.py:11-48` and
  `tests/infrastructure/test_minio_capacity.py`.

Direct task records, their functional verification reports and the required
T3 semantic reports were also checked. Unrelated W2 work, later FT-002
consumer/orchestration work, and repository-wide legacy code are outside this
review.

## Evidence checked

- All five indexed task records are `done`; TASK-019, TASK-020 and TASK-022
  record functional `PASS`, while TASK-021 and TASK-034 record functional
  `PASS` plus `red-verify` `semantic-pass`.
- The independent functional evidence is in
  `.tasks/TASK-019-T2-FT-002-W2/TASK-019-T2-FT-002-W2-S-VERIFY-final-report-docs-01.md`,
  `.tasks/TASK-020-T2-FT-002-W2/TASK-020-T2-FT-002-W2-S-VERIFY-final-report-docs-01.md`,
  `.tasks/TASK-021-T3-FT-002-W2/TASK-021-T3-FT-002-W2-S-VERIFY-final-report-docs-01.md`,
  `.tasks/TASK-022-T2-FT-002-W2/TASK-022-T2-FT-002-W2-S-VERIFY-final-report-docs-01.md`,
  and
  `.tasks/TASK-034-T3-FT-002-W2/TASK-034-T3-FT-002-W2-S-VERIFY-final-report-docs-01.md`.
- T3 adversarial evidence is
  `.tasks/TASK-021-T3-FT-002-W2/TASK-021-T3-FT-002-W2-S-RED-VERIFY-final-report-docs-01.md`
  and
  `.tasks/TASK-034-T3-FT-002-W2/TASK-034-T3-FT-002-W2-S-RED-VERIFY-final-report-docs-01.md`.
- Current tracked-diff whitespace validation completed cleanly with
  `git diff --check`; the untracked TASK-022 source/test and TASK-034 test
  were inspected directly as part of the actual surface.
- The earlier `TD-W2-01` in
  `PAPERCUTS/TECHDEBTS/wave-W2-tech-debt-2026-08-10.md` concerns the FT-001
  login limiter under `platform/auth/`. None of these FT-002 W2 tasks changes
  or depends on that path, so it is not a carried finding for this scope.

## Confirmed findings

None.

## Smallest remediation direction

None.

## Uncertainty

This review uses the closed task evidence and current implementation only. It
does not assess later worker orchestration, API consumers, model deployment
assets, or repository-wide technical debt.
