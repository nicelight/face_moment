# Технический долг — волна W5

## Проверенная область

Только authoritative W5-задачи: `TASK-012-T2-FT-001-W5`,
`TASK-026-T3-FT-002-W5`, `TASK-028-T2-FT-002-W5`,
`TASK-030-T3-FT-002-W5` и `TASK-037-T2-FT-002-W5`. Проверены их indexed
records, terminal independent verification/red-verification evidence и
фактически изменённые исходники/тесты этой поверхности. Это не
repository-wide review; W6+ и посторонние незавершённые изменения исключены.

## Проверенные доказательства

- Пять `.memory-bank/tasks/TASK-*-W5.task.json`, включая их границы,
  `touched_files`, финальные verdict и нормативные inputs.
- Финальные independent reports задач 012, 026, 028, 030 и 037; в частности,
  [`TASK-028` verification attempt 4](../../.tasks/TASK-028-T2-FT-002-W5/TASK-028-T2-FT-002-W5-S-VERIFY-final-report-docs-03.md)
  подтверждает допустимое состояние с двумя persisted state-строками одного
  Photo после добавления состояния revision B.
- Фактически затронутые W5-срезы: atomic admission и immutable lineage
  (`inventory/admission.py`, `inventory/photo_persistence.py`,
  `processing/initial_pending.py`, migration `0009`), model-consuming runtime
  и worker, SLO projection, а также status API
  (`inventory/http.py`, `inventory/photo_processing_status.py`,
  `processing/searchable_projection.py`) с их focused tests.
- [`PhotoPipelineState`](../../src/face_moment/processing/initial_pending.py#L30)
  имеет составной primary key `(photo_id, pipeline_revision_id)`, поэтому
  несколько revision-state для одного Photo — представимое состояние.

## Подтверждённые findings

### MEDIUM — status API аварийно завершается при нескольких state одного Photo

`read_photo_processing_status()` вызывает public processing boundary без
revision selector (`inventory/photo_processing_status.py:82`).
`resolve_for_photo()` так же передаёт только `photo_id`
(`processing/searchable_projection.py:57-62`); запрос фильтрует только это
поле (`:101`) и завершает выбор через `one_or_none()` (`:107`). При двух
persisted state-строках допустимого одного Photo этот вызов выбрасывает
`MultipleResultsFound`. HTTP handler преобразует такой owner-read failure в
`500`, поэтому polling принятого Photo перестаёт возвращать контрактный
статус.

Это не гипотетическая кардинальность: W5 evidence для `TASK-028` прямо
подтверждает два state rows после добавления B при сохранении A. При этом
`TASK-030` tests покрывают по одному state на Photo и не проверяют этот
поддерживаемый вариант.

- Практическое влияние: после serving/revision evolution статусный API
  становится ненадёжным для затронутых Photo; повторные изменения обработки
  требуют неявно помнить о его single-row assumption.
- Наименьшее направление исправления: определить в контракте единственный
  state, представляемый одним per-Photo response (admission revision либо
  current serving revision), добавить соответствующий predicate в public
  processing projection и один integration case с A+B rows.

## Неопределённость

Контракт возвращает единственный `pipeline_revision_id`, но не задаёт правило
выбора при нескольких revision-state. Поэтому направление не предписывает,
какой именно из двух допустимых selectors принять; независимо от выбора
нынешний unqualified query и `one_or_none()` подтверждённо не обслуживают
допустимое состояние.

## Итог

Подтверждён один material finding. Отчёт advisory: он не меняет код, задачи,
статусы, gates или lifecycle.
