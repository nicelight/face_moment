---
description: Advisory technical-debt review of recovered FT-009 Wave 3.
status: active
---
# FT-009 Wave 3 — technical-debt review

## Проверенная область

Запрос `/tech-debt wave 3` разрешён через индексированную запись
`.memory-bank/tasks/TASK-093-T3-FT-009-W3.task.json`: единственный текущий
Wave 3 boundary для FT-009 — закрытый `TASK-093-T3-FT-009-W3`, владеющий
`FT-009-AC-003`.

Проверены:

- task card, feature и принятый implementation plan:
  `.memory-bank/tasks/TASK-093-T3-FT-009-W3.task.json`,
  `.memory-bank/features/FT-009.md`,
  `.memory-bank/tasks/plans/IMPL-FT-009.md`;
- execution/closure evidence в
  `.protocols/TASK-093-T3-FT-009-W3/` и
  `.tasks/TASK-093-T3-FT-009-W3/`, включая functional `PASS` и per-task
  semantic-pass;
- фактический production/test delta commit
  `bdaa67917125a833376071ab30f0839051eaafa5`: изменения в
  `src/face_moment/diagnostics/retention.py`,
  `src/face_moment/diagnostics/server_events.py`,
  `src/face_moment/promo/retention.py`,
  `tests/diagnostics/test_retention_cleanup.py` и новый
  `tests/diagnostics/test_server_event_retention.py`;
- непосредственно соседние diagnostics fixtures только для проверки
  повторяемости найденного test-infrastructure механизма.

Durable closure-документы из того же commit проверены как evidence границы,
но review не расширялся на другие FT-009 waves или repository-wide surface.
Это advisory review: оно не меняет implementation, Memory Bank, task/protocol
state, gates, verdicts или routes.

## Итог

Подтверждён один материальный технический долг. Он не опровергает закрытие
TASK-093: strict 30-day deletion, owner ordering, partial-failure convergence и
stale-search non-recovery имеют независимые положительные доказательства.

## Подтверждённые findings

### LOW / P2 — Wave 3 добавил ещё одну полную копию disposable PostgreSQL lifecycle

Новый fixture самостоятельно повторяет создание случайной базы, подмену
`DATABASE_URL`, Alembic upgrade, создание Engine и forced teardown
(`tests/diagnostics/test_server_event_retention.py:31-56`). Тот же lifecycle
уже локально продублирован как минимум в соседних diagnostics tests:
`tests/diagnostics/test_retention_cleanup.py:32-55`,
`tests/diagnostics/test_server_event_search.py:59-74,202-208` и
`tests/diagnostics/test_server_events.py:40-78`.

Это не предположение об отсутствующей документации: Wave 3 фактически добавил
новую копию уже повторяющегося setup/teardown механизма. Его общие изменения
(admin connection options, URL switching, migration bootstrap, teardown or
parallel-run safety) теперь требуют нескольких согласованных правок. Соседние
копии уже различаются по fixture scope и способу восстановления environment,
что затрудняет отличить намеренную test-specific настройку от drift.

Практический impact ограничен test infrastructure, поэтому приоритет низкий,
но repeated maintenance cost подтверждён внутри diagnostics surface.

Минимальное направление: вынести только общий primitive provision/drop
случайной PostgreSQL database и возврат её URL/Engine в diagnostics test
support. Task-specific migration stage, seed data и fixture scope оставить в
исходных тестах; generic test framework не нужен.

## Неопределённость и исключённые кандидаты

- Commit-before-later-owner-work в `expire_server_events()` не записан как
  долг: task-linked contracts явно принимают partial convergence, нулевой
  confirmed count после failed run и безопасный rerun, а tests и semantic
  verification доказывают это поведение.
- Concrete `DiagnosticRetentionProvider` в injection seam и test-only
  `# type: ignore` отмечают возможную типизационную шероховатость, но текущая
  evidence не показывает самостоятельного материального impact сверх обычной
  стоимости изменения интерфейса; finding не принят.
- Production performance не измерялась. Bulk `DELETE ... WHERE occurred_at <
  cutoff` имеет индексированную границу согласно task evidence, и данных для
  вывода о performance debt нет.
