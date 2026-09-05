---
description: Advisory technical-debt assessment for the completed current W1 task set.
status: active
---
# Current W1 Technical-Debt Assessment — 2026-09-05

## Checked Scope

The completed current W1 task set resolved through the indexed task records:

- `TASK-100-T2-FT-011-W1` — durable Calibration-run core;
- `TASK-108-T3-FT-012-W1` — recent Photo statistics; and
- `TASK-109-T3-FT-012-W1` — processing-owned purge cleanup.

This is not a repository-wide assessment. `TASK-100` was inspected from its
committed change `23474db`; `TASK-108` and `TASK-109` were inspected from the
current task-owned working-tree change surface and their durable task evidence.

## Evidence Checked

- Task status and scopes: `.memory-bank/tasks/TASK-100-T2-FT-011-W1.task.json`,
  `.memory-bank/tasks/TASK-108-T3-FT-012-W1.task.json`, and
  `.memory-bank/tasks/TASK-109-T3-FT-012-W1.task.json`.
- Calibration ownership, immutable snapshot and verified-byte boundary:
  `src/face_moment/diagnostics/calibration_runs.py:108-271` and
  `src/face_moment/processing/offline_calibration.py:46-115`; focused
  regression coverage: `tests/diagnostics/test_calibration_runs.py:130-242`.
- Statistics direct aggregate, immutable admission-revision join and thin
  transport: `src/face_moment/inventory/recent_statistics.py:49-125` and
  `src/face_moment/inventory/http.py:175-226`; controlled-clock and role/API
  coverage: `tests/inventory/test_recent_statistics.py:130-195`.
- Purge cleanup's owner-local object/row deletion and repeat behaviour:
  `src/face_moment/processing/purge_cleanup.py:30-84` and
  `tests/processing/test_purge_cleanup.py:277-337`.
- Applicable durable boundaries: `.memory-bank/domains/photo-inventory.md`
  (`Recent Statistics Projection`, `Purge Orchestration`),
  `.memory-bank/contracts/photo-inventory-api.md` (`Recent Statistics`), and
  `.memory-bank/domains/calibration.md`.
- Current task verification/semantic evidence:
  `.protocols/TASK-100-T2-FT-011-W1/verification.md`,
  `.protocols/TASK-108-T3-FT-012-W1/verification.md`,
  `.protocols/TASK-108-T3-FT-012-W1/red-verification.md`,
  `.protocols/TASK-109-T3-FT-012-W1/verification.md`, and
  `.protocols/TASK-109-T3-FT-012-W1/red-verification.md`.
- `git diff --check` on the current change surface: passed.

## Confirmed Findings

None. No inspected mechanism demonstrated material repeated-change cost,
undesired cross-owner coupling, regression exposure, reliability loss, or
maintenance burden beyond the accepted current boundaries.

The statistics implementation remains a direct active-Photo aggregate rather
than stored/realtime metric machinery. Purge cleanup is a narrow public
processing edge that retains caller-owned transaction and inventory authority.
The Calibration run persists a bounded immutable snapshot and uses the
processing edge to verify and share a single decoded original with both native
adapters.

## Uncertainty

- This review does not treat Calibration worker restart, manual rerun, retention
  or staff UI work as debt: they are separately accepted FT-011 criteria
  (`FT-011-AC-005..008`) and outside `TASK-100`'s explicit scope.
- No production-volume or long-duration database load measurement was present
  in the W1 evidence. The direct aggregate is the accepted mechanism, so the
  absence of such a benchmark alone is not a technical-debt finding.
- Full inventory hard-purge orchestration is a later FT-012 outcome. This
  assessment covers only its completed processing-owned cleanup boundary.

## Advisory Result

No material technical debt confirmed for the checked current W1 scope.
