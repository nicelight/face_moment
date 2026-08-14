# Технический долг — волна W6

## Проверенная область

Только authoritative W6-задачи из `.memory-bank/tasks/index.json`:
`TASK-013-T2-FT-001-W6`, `TASK-014-T2-FT-001-W6`,
`TASK-029-T2-FT-002-W6`, `TASK-031-T2-FT-002-W6`,
`TASK-035-T3-FT-002-W6` и `TASK-038-T2-FT-002-W6`.

Включены их task records, terminal evidence и фактические исходные/тестовые
поверхности. Planning repair рассмотрен только в необходимой связи W6:
`TASK-038`, его добавление в `IMPL-FT-002`, и ровно тот prerequisite
`TASK-037-T2-FT-002-W5`, который ввёл immutable admission lineage. Другие
W5/W7-задачи и repository-wide поверхность исключены.

## Проверенные доказательства

- Все шесть W6 task records и final independent evidence; для TASK-035 также
  повторные verify/red-verify reports, закрывающие исходную ошибку mixed
  timezone-aware bounds.
- TASK-013/014: `inventory/admission.py:44-92`,
  `tests/inventory/test_duplicate_admission.py:116-215` и
  `tests/inventory/test_crash_recovery.py:84-168`; evidence подтверждает
  database-only arbitration, loser-only cleanup и private pre-commit orphan.
- TASK-029: `processing/worker_claims.py:31-86`,
  `processing/worker_runtime.py:53-70` и
  `tests/processing/test_shared_worker.py:49-145`; calibration hold остаётся
  одним locked runtime operation и освобождается в `finally`.
- TASK-038/031 planning repair и фактический read/UI путь:
  `inventory/photo_persistence.py:78-86`, migration
  `0009_photo_admission_lineage.py:19-58`,
  `inventory/photo_processing_status.py:58-108`,
  `processing/searchable_projection.py:68-153`,
  `inventory/http.py:76-126, 323-363`,
  `tests/inventory/test_admission_lineage.py` и
  `tests/inventory/test_photo_processing_api.py`. Exact composite selector
  устраняет прежнюю допустимую A+B cardinality failure без fallback/ordering
  heuristic; uploader потребляет только API truth.
- TASK-035: `inventory/processing_health.py:58-159`,
  `inventory/http.py:100-126` и
  `tests/inventory/test_processing_health_api.py:155-429`; interval
  нормализуется до UTC только после проверки обеих aware границ, а owner reads
  и capacity observations остаются раздельными и read-only.
- Repair documents: `.memory-bank/tasks/plans/IMPL-FT-002.md:103-112,
  137-150, 185-196` и
  `.memory-bank/contracts/photo-processing-api.md:37-67` фиксируют один
  admission-lineage selector и его A+B matrix. Это соответствует текущему
  коду и terminal TASK-038/TASK-031 evidence.

Итог проверки: подтверждённого material technical debt в этой ограниченной
поверхности не обнаружено; раздел findings намеренно пуст.

## Подтверждённые findings

## Неопределённость

- Это не повторная функциональная верификация и не repository-wide audit:
  вывод опирается на сохранённые независимые доказательства и статический
  осмотр текущих W6/repair файлов.
- Рабочее дерево содержит параллельные незакоммиченные изменения соседних
  волн. Они не интерпретировались как часть W6, кроме явно названного
  admission-lineage prerequisite и файлов, на которые ссылаются W6 evidence.

## Итог

Отчёт advisory. Он не меняет задачи, статусы, gates, lifecycle или код.
