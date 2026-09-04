---
description: Advisory technical-debt review of FT-010 Wave 1 closed by TASK-096.
status: active
---
# FT-010 Wave 1 — technical-debt review

## Проверенная область

Запрос `/tech-debt wave 1` разрешён в текущей FT-010 границе как закрытый
`TASK-096-T3-FT-010-W1`. Review не расширялся на одноимённые waves других
features, на ещё не выполненные `TASK-097..099` или на repository-wide surface.

Проверены:

- индексированная task card, feature и принятый implementation plan:
  `.memory-bank/tasks/TASK-096-T3-FT-010-W1.task.json`,
  `.memory-bank/features/FT-010.md` и
  `.memory-bank/tasks/plans/IMPL-FT-010.md`;
- прямые нормативные границы provider/schema/calculation input:
  `.memory-bank/domains/ground-truth-annotations.md`,
  `.memory-bank/domains/diagnostic-evidence.md`,
  `.memory-bank/contracts/boundary-map.md` и
  `.memory-bank/testing/calibration.md`;
- фактический Attempt 1 implementation surface:
  `migrations/versions/0019_ground_truth_annotations.py`,
  `src/face_moment/diagnostics/ground_truth_annotations.py`,
  `src/face_moment/diagnostics/__init__.py` и
  `tests/diagnostics/test_ground_truth_annotations.py`;
- точечная Attempt 2 correction в provider и test: evidence-row `FOR UPDATE`,
  regression для stale create и независимая матрица
  `create|correct|remove × expired|removed`;
- execution, functional verification, adversarial verification и closure
  evidence в `.tasks/TASK-096-T3-FT-010-W1/`,
  `.protocols/TASK-096-T3-FT-010-W1/verification.md`,
  `.protocols/TASK-096-T3-FT-010-W1/red-verification.md` и
  `.protocols/FT-010/clarification.md#2026-09-04-task-096-attempt-1-semantic-failure`.

`touched_files` использовался только как ориентир и был сопоставлен с
execution reports и текущим фактическим change surface. Соседние diagnostics
tests прочитаны только для проверки повторяемости одного найденного
test-infrastructure механизма.

## Итог

Подтверждены два материальных технических долга. Они не опровергают закрывающие
functional `PASS` и `semantic-pass`: Attempt 1 stale-write race исправлен, а
Attempt 2 независимо доказал сериализацию всех шести поддержанных interleavings.
Отчёт advisory-only и не меняет implementation, Memory Bank, tasks, protocols,
scheduler/lifecycle state, gates, verdicts или routes.

## Подтверждённые findings

### MEDIUM / P1 — application и PostgreSQL по-разному определяют пустое имя

Provider нормализует `participant_name` через Python `str.strip()` и после
этого требует длину `1..200`
(`src/face_moment/diagnostics/ground_truth_annotations.py:319-325`). ORM и
migration независимо кодируют database check как
`char_length(btrim(participant_name)) BETWEEN 1 AND 200`
(`src/face_moment/diagnostics/ground_truth_annotations.py:54-56`,
`migrations/versions/0019_ground_truth_annotations.py:36-39`). Без второго
аргумента PostgreSQL `btrim` удаляет обычный пробел, тогда как `str.strip()`
удаляет более широкий набор whitespace. Поэтому, например, строка только из
табуляции отклоняется public provider, но удовлетворяет текущему database
check.

Это наблюдаемое расхождение двух защит одного нового protected field, а не
стилистическое замечание. Repository/model экспортированы из diagnostics
package (`src/face_moment/diagnostics/__init__.py:30-39,80-91`), а task test
явно проверяет database-level rejection прямой вставки, но покрывает только
невалидную target shape
(`tests/diagnostics/test_ground_truth_annotations.py:527-542`). Будущий
owner-local путь, bulk operation или data repair, полагающийся на schema
invariant, способен сохранить визуально пустое имя и дать provider/database
разные результаты для одной семантики.

Практический impact: увеличивается data-integrity и regression risk при
расширении annotation flow в следующих tasks; изменение правил имени требует
синхронно поддерживать две уже расходящиеся реализации.

Минимальное направление: зафиксировать один набор принимаемого whitespace,
выровнять database constraint с provider normalization и добавить один прямой
database regression на whitespace-only значение. Поля, public response shape и
новый validation layer для этого не нужны.

### LOW / P2 — Wave 1 добавил ещё одну полную копию disposable PostgreSQL lifecycle

Новый module-scoped fixture самостоятельно выполняет получение base URL,
создание случайной базы, глобальную подмену `DATABASE_URL`, staged Alembic
upgrade, Engine lifecycle, восстановление environment и forced drop
(`tests/diagnostics/test_ground_truth_annotations.py:39-77`). Практически тот
же lifecycle уже присутствует в соседнем predecessor test
`tests/diagnostics/test_server_events.py:40-78`; другие diagnostics fixtures
повторяют тот же create/migrate/drop primitive, например
`tests/diagnostics/test_evidence_persistence.py:23-46` и
`tests/diagnostics/test_retention_cleanup.py:32-55`.

Повторяемость подтверждена точными соседними реализациями: изменение admin
connection options, безопасного URL switching, migration bootstrap, teardown
или parallel-run поведения потребует нескольких согласованных правок. Уже
виден drift между ручным восстановлением `os.environ` и `monkeypatch`, а также
между staged revision и `head`; часть различий task-specific, часть относится
к одному и тому же infrastructure primitive.

Практический impact ограничен test infrastructure, поэтому приоритет низкий,
но новая Wave 1 копия увеличивает повторную стоимость поддержки и риск
неодинакового cleanup.

Минимальное направление: вынести только общий primitive создания и
гарантированного удаления случайной PostgreSQL database с контролируемой
подменой URL. Task-specific predecessor/head migration, seed и fixture scope
оставить локально; generic test framework не нужен.

## Неопределённость и исключённые кандидаты

- Не найден остаточный debt в Attempt 2 lock ordering: current provider берёт
  evidence-row `FOR UPDATE` перед каждой mutation
  (`src/face_moment/diagnostics/ground_truth_annotations.py:234-276,299-307`),
  а свежий adversarial probe подтвердил rejection и неизменность annotation
  state для всех шести поддержанных transition-first сценариев.
- Отсутствующая в Wave 1 физическая очистка annotations при retention/removal
  не записана как debt: это явно отложенный и отдельно запланированный outcome
  `TASK-099-T3-FT-010-W2`, а не скрытый долг TASK-096.
- Экспорт repository и дублирование ORM/migration schema сами по себе не
  записаны как findings. Материальным является только доказанное расхождение
  whitespace semantics; прочих самостоятельных последствий текущая evidence
  не показывает.
- Performance provider queries не измерялась, и данных для уверенного
  performance finding в этой Wave 1 границе нет.
