---
description: Advisory technical-debt report for the explicit W6 change surface.
status: active
---
# Технический долг — wave W6

## Проверенная область

Только explicit `/tech-debt wave W6`: authoritative entries из
`.memory-bank/tasks/index.json:117-158` и их task records:

- `TASK-013-T2-FT-001-W6`, `TASK-014-T2-FT-001-W6`;
- `TASK-029-T2-FT-002-W6`, `TASK-031-T2-FT-002-W6`,
  `TASK-035-T3-FT-002-W6`, `TASK-038-T2-FT-002-W6`,
  `TASK-039-T2-FT-002-W6`.

Проверены `.memory-bank/tasks/TASK-*-W6.task.json`, task-owned execution и
independent verification evidence в `.tasks/`, а также соответствующие
`.protocols/TASK-*-W6/{verification,red-verification,handoff}.md`.
Repository-wide аудит, соседние волны и lifecycle/gate/status decisions
исключены.

## Фактическая change surface

По task receipts и текущему рабочему дереву просмотрены следующие production и
test surfaces:

- admission/crash recovery: `src/face_moment/inventory/admission.py:26-112`,
  `src/face_moment/inventory/__init__.py`,
  `tests/inventory/test_duplicate_admission.py`,
  `tests/inventory/test_crash_recovery.py`;
- shared worker: `src/face_moment/processing/worker_claims.py:24-87`,
  `src/face_moment/processing/worker_runtime.py:14-71`,
  `tests/processing/test_shared_worker.py:49-154`;
- uploader/status boundary: `src/face_moment/inventory/http.py:48-117,360-402`,
  `src/face_moment/inventory/photo_processing_status.py:58-99`,
  `src/face_moment/processing/searchable_projection.py:44-75,159-174`,
  `tests/inventory/test_photo_processing_ui.py`,
  `tests/inventory/test_photo_processing_api.py:154-369`;
- processing health: `src/face_moment/inventory/processing_health.py:70-159`,
  `tests/inventory/test_processing_health_api.py:155-430`;
- exact-A ordinary serving guard: `src/face_moment/processing/serving_revision_guard.py:12-67`,
  `src/face_moment/processing/__init__.py:13-31`,
  `tests/processing/test_serving_revision_guard.py:203-295`.

The worktree contains unrelated pre-existing changes in neighboring task
records/waves; they were not treated as W6 debt. The current W6 task-record
reconciliation and TASK-039 source/test additions were included in the static
review, without changing them.

## Evidence и precise locations

- `TASK-013` and `TASK-014`: independent PASS reports at
  `.tasks/TASK-013-T2-FT-001-W6/TASK-013-T2-FT-001-W6-S-VERIFY-final-report-docs-01.md:7-24`
  and `.tasks/TASK-014-T2-FT-001-W6/TASK-014-T2-FT-001-W6-S-VERIFY-final-report-docs-01.md:7-26`;
  duplicate arbitration, private orphan and re-upload evidence in the linked
  task protocols.
- `TASK-029` and `TASK-031`: PASS reports at
  `.tasks/TASK-029-T2-FT-002-W6/TASK-029-T2-FT-002-W6-S-VERIFY-final-report-docs-01.md:7-30`
  and `.tasks/TASK-031-T2-FT-002-W6/TASK-031-T2-FT-002-W6-S-VERIFY-final-report-docs-01.md:3-29`;
  the first covers singleton-worker mutual exclusion/release and the second
  covers accepted-only browser polling, API truth, auth/error matrix and zero
  residue.
- `TASK-035`: Attempt 2 functional PASS and semantic-pass at
  `.tasks/TASK-035-T3-FT-002-W6/TASK-035-T3-FT-002-W6-S-VERIFY-final-report-docs-02.md:7-25`
  and `.tasks/TASK-035-T3-FT-002-W6/TASK-035-T3-FT-002-W6-S-RED-VERIFY-final-report-docs-02.md:7-37`;
  the earlier mixed-timezone failure is explicitly corrected and is not an
  open mechanism.
- `TASK-038` and `TASK-039`: PASS reports at
  `.tasks/TASK-038-T2-FT-002-W6/TASK-038-T2-FT-002-W6-S-VERIFY-final-report-docs-01.md:7-29`
  and `.tasks/TASK-039-T2-FT-002-W6/TASK-039-T2-FT-002-W6-S-VERIFY-final-report-docs-01.md:7-27`;
  exact admission-lineage selection and the exact-A read-only guard each have
  fresh packaged probes, SELECT-only assertions, unchanged snapshots and
  cleanup evidence.
- Normative boundaries checked: `.memory-bank/contracts/boundary-map.md`
  (processing-status/manual-serving edges),
  `.memory-bank/contracts/photo-processing-api.md`,
  `.memory-bank/domains/photo-admission.md`,
  `.memory-bank/domains/photo-processing.md`,
  `.memory-bank/states/lifecycle-map.md`, and
  `.memory-bank/testing/photo-processing.md`.

## Итог проверки

Material technical debt не подтверждён; `findings` отсутствуют. W6 changes
retain the accepted KISS boundaries: PostgreSQL-only duplicate arbitration,
ordinary re-upload recovery, one singleton worker hold, inventory-to-processing
read contracts qualified by immutable admission lineage, and a processing-owned
read-only exact-A guard. No evidence shows material repeated-change cost,
coupling, regression risk, reliability burden or maintenance burden requiring
an advisory finding.

## Подтверждённые findings

## Неопределённость

- Это bounded advisory review, а не повторный запуск всех W6 integration or
  browser probes и не repository-wide audit; вывод опирается на сохранённые
  independent receipts, their evidence locations and static inspection of the
  current change surface.
- Existing worktree edits from other waves were observed but excluded from the
  W6 verdict. This report does not infer debt from style, coverage, dependency
  age, warnings alone, or the historical TASK-035 Attempt 1 defect after its
  verified correction.

## Ограничения отчёта

Отчёт advisory и не изменяет tasks, code, specs, statuses, lifecycle, gates,
blockers, `.protocols/AUTONOMOUS-RUN/status.md` или debt lifecycle.
