---
description: Advisory technical-debt review of the TASK-090 structured server-event fixes.
status: active
---
# TASK-090 structured server events — technical-debt review

## Проверенная область

Проверены только изменения и evidence `TASK-090-T3-FT-009-W1`:

- task card и три последовательных verification attempts в
  `.memory-bank/tasks/TASK-090-T3-FT-009-W1.task.json` и
  `.tasks/TASK-090-T3-FT-009-W1/`;
- durable failure evidence
  `.memory-bank/bugs/task-090-realtime-event-post-commit-sql.md`;
- действующий контракт FT-009 в
  `.memory-bank/features/FT-009.md:55-64` и
  `.memory-bank/domains/structured-server-events.md:48-87`;
- реализация emitter/lifecycle в
  `src/face_moment/diagnostics/server_events.py:138-250` и
  `src/face_moment/entrypoints/common.py:21-55`;
- producer wiring в
  `src/face_moment/entrypoints/realtime.py:211-224,268-282`,
  `src/face_moment/promo/realtime_orchestration.py:237-284`,
  `src/face_moment/promo/session.py:113-130,271-301,364-383,419-428`,
  `src/face_moment/promo/qr_continuation.py:140-179` и соответствующие tests.

Учтено актуальное решение оператора: отладка используется редко, поэтому
ограниченный correlation lookup к PostgreSQL во время основного flow допустим;
усложнять producer paths ради абсолютного отсутствия такого SQL не требуется.

Это advisory review. Оно не меняет implementation, specs, tasks, statuses,
verification verdicts или workflow state.

## Итог

Костыли подтверждены, но не в базовом typed event envelope и не в самой идее
best-effort persistence. Они появились на стыке Promo/QR и diagnostics из-за
абсолютного требования «producer path не выполняет и не ждёт никакой SQL».
Три попытки исправления последовательно находили один и тот же ORM-lifecycle
эффект в разных местах. Продолжать закрывать его новыми snapshots, скрытыми
полями и latch probes нецелесообразно.

При этом разрешение одного bounded correlation lookup не означает, что нужно
синхронно выполнять event `INSERT/COMMIT`. Частота открытия отладочного UI не
уменьшает частоту producer events. Текущая очередь и отдельная writer Session
по-прежнему дают простую полезную гарантию: медленная или упавшая запись
диагностики не меняет результат участника.

## Подтверждённые findings

### HIGH / P0 — принятый zero-wait контракт разошёлся с актуальным operator intent

Действующий SDD требует capacity-256 FIFO, non-waiting enqueue и запрещает
producer ждать (`structured-server-events.md:67-87`). Task card превратил это в
проверку через held all-SQL latch (`TASK-090...task.json:74,113-129`). При этом
последовательные verdicts показывают один механизм в трёх местах:

1. Attempt 1 — logging-only correlation lookup в QR;
2. Attempt 2 — implicit refresh commit-expired `PromoSession`;
3. Attempt 3 — implicit refresh commit-expired `PromoAttempt` в realtime.

Третий случай воспроизводится в
`.tasks/TASK-090-T3-FT-009-W1/TASK-090-T3-FT-009-W1-S-VERIFY-final-report-docs-03.md:7-18`:
owner commit уже состоялся, но чтение ORM attributes при enqueue ждёт
PostgreSQL refresh. Исправление QR прошло ту же проверку только после ввода
pre-commit snapshot.

Практический impact: одна диагностическая гарантия стала сквозным инвариантом
для каждого producer seam. Любой новый event после commit требует помнить о
SQLAlchemy expiration, добавлять snapshot и специальный latch test. Три
исчерпанные попытки — наблюдаемая повторная стоимость этого механизма, а не
гипотетический edge case.

Минимальное направление: до следующего implementation attempt согласовать SDD
с решением оператора. Сохранить обязательными только две продуктовые гарантии:

- ошибка или задержка именно event persistence не меняет owner transaction,
  response и participant outcome;
- producer не делает retry и не откатывает owner outcome из-за diagnostics.

Допустить один bounded, явный correlation lookup после известного owner
outcome. Удалить требование all-SQL latch для producer path; проверять held
writer/database failure и неизменность owner outcome. Это изменение контракта,
поэтому его нельзя маскировать очередным code-only retry TASK-090.

### HIGH / P1 — diagnostics state спрятан внутри Promo domain ORM object и exception

`PromoSession` получил немаппированные свойства `event_correlation_id` и
`event_first_open`, которые записываются напрямую в `self.__dict__`
(`promo/session.py:113-130`). `_get_by_ticket()` теперь при каждом ticket lookup
делает join с `PromoAttempt`, валидирует типы и внедряет correlation ID в
возвращаемый ORM object (`:364-383`). `_expired_error()` затем извлекает это
скрытое значение и переносит logging identities через
`PromoBrowserAccessExpiredError` (`:419-428`; constructor `:156-168`).

В `PromoQrContinuationService.snapshot_opened_event()` те же скрытые значения
сворачиваются в positional tuple
`tuple[bool, UUID, UUID]`, который позже читается по индексам
(`promo/qr_continuation.py:148-179`). Эти поля и exception payload существуют
не ради Promo behavior, а исключительно ради прохождения diagnostics latch.

Практический impact: diagnostics изменил семантику domain entity, общий ticket
query и domain exception. Даже когда event не нужен, QR lookup платит за join;
tests теперь должны создавать ORM-like объекты с несуществующими persisted
полями. Данные зависят от того, каким repository path объект был загружен, но
ни mapping, ни тип `PromoSession` эту зависимость не выражают.

Минимальное направление после reconciliation:

- удалить `event_*` свойства и private setters из `PromoSession`;
- вернуть `_get_by_ticket()` к загрузке владельца QR без diagnostics-only join;
- вернуть `PromoBrowserAccessExpiredError` к domain error без logging payload;
- для успешного первого открытия передать наружу обычный `first_open` вместе с
  `PromoSession` (достаточен явный двухэлементный return, новый framework не
  нужен), выполнить owner commit, затем при наличии sink явно получить
  `PromoAttempt.client_attempt_id` по уже известному `attempt_id` и enqueue;
- expired event оставлять uncorrelated, если identities недоступны: это уже
  разрешено каталогом в `structured-server-events.md:59-60`.

Так correlation query становится видимым и локальным, а Promo entity и
исключения снова описывают только Promo behavior.

### MEDIUM / P1 — realtime helpers принимают commit-sensitive ORM object

`emit_attempt_admitted()` и `emit_attempt_terminal()` принимают целый
`PromoAttempt` и читают mapped attributes внутри best-effort `try`
(`promo/realtime_orchestration.py:247-284`). Call sites вызывают их после
`database_session.commit()` (`entrypoints/realtime.py:220-221,277-278`). При
стандартном expire-on-commit обычное чтение становится скрытым SQL; финальный
real PostgreSQL probe это подтвердил.

Разрешение SQL снижает критичность задержки, но не делает скрытый запрос хорошей
границей: поведение helper зависит от Session lifecycle, а broad `except
Exception` молча превращает ошибку refresh в потерянное событие.

Минимальное направление: перед commit снять уже загруженные UUID и terminal
status в локальные переменные, после commit передать helper только эти
primitives. Это несколько локальных аргументов, а не новая snapshot hierarchy,
event-intent abstraction или generic bus. Отдельный DB query здесь не нужен,
поскольку значения уже есть в памяти.

## Что не следует усложнять

- Не вводить outbox, broker, retry, scheduler, delivery guarantee или новый
  runtime role: TASK-090 не требует надёжной доставки diagnostics.
- Не строить generic snapshot/event-intent layer ради семи фиксированных event
  codes. В realtime достаточно локальных primitives; в QR — явного результата
  первого открытия и одного lookup.
- Не удалять очередь и отдельную writer Session только на основании редкого
  использования отладочного UI. Их удаление сделает каждый event INSERT/COMMIT
  частью participant latency. Это отдельное решение, на которое текущая фраза
  о допустимом correlation query не даёт достаточного основания.
- Не продолжать чинить TASK-090 в обход specs: пока normative текст сохраняет
  абсолютный zero-wait contract, verifier обязан отвергать разрешённый
  оператором SQL.

## Неопределённость

Не доказано, что process-local queue/thread создаёт материальную operational
проблему: current evidence показывает сложность lifecycle, но также прямую
изоляцию event persistence. Удалять её стоит только если оператор отдельно
разрешит синхронный event INSERT/COMMIT и его отказ/latency в participant flow.

Также не проверялась архитектура FT-009 за пределами TASK-090 producer/emitter
surface; выводы не распространяются на search API, retention или staff UI.
