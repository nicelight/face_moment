---
description: Advisory technical-debt review for W2 product change surfaces TASK-004 and TASK-007.
status: advisory
---
# Технический долг W2 — TASK-004 и TASK-007

## Проверенная поверхность

Только индексированные W2 product task surfaces:

- `TASK-004-T3-FT-001-W2` — HTTPS staff browser sessions: `deploy/Caddyfile`,
  `migrations/versions/0004_staff_sessions.py`,
  `src/face_moment/platform/auth/http.py`,
  `src/face_moment/platform/auth/sessions.py` и
  `tests/staff_access/test_sessions.py`.
- `TASK-007-T2-FT-001-W2` — serving-owned ingest target:
  `migrations/versions/0005_serving_ingest_targets.py`,
  `src/face_moment/serving_control/__init__.py`,
  `src/face_moment/serving_control/ingest_target.py` и
  `tests/serving_control/test_ingest_target.py`.

Provenance surface подтверждён task records
`.memory-bank/tasks/TASK-004-T3-FT-001-W2.task.json` и
`.memory-bank/tasks/TASK-007-T2-FT-001-W2.task.json`, а также историей
`git show --stat ffb0980`. Проверялись итоговые receipts:
`.tasks/TASK-004-T3-FT-001-W2/TASK-004-T3-FT-001-W2-S-VERIFY-final-report-docs-03.md`,
`.tasks/TASK-004-T3-FT-001-W2/TASK-004-T3-FT-001-W2-S-RED-VERIFY-final-report-docs-03.md`
и `.tasks/TASK-007-T2-FT-001-W2/TASK-007-T2-FT-001-W2-S-VERIFY-final-report-docs-01.md`.

## Подтверждённые находки

### TD-W2-01 — login limiter сохраняет ключи навсегда

- Приоритет: средний.
- Механизм и точные места: `LoginRateLimiter._attempts` — обычный
  неограниченный `dict` в
  `src/face_moment/platform/auth/sessions.py:78-85`. Каждый новый нормализованный
  `(username, IP)` создаётся через `setdefault` в строке 91. В строках 92-93
  истёкшие попытки удаляются только из deque текущего ключа; пустой deque не
  удаляется, а ключи, к которым больше нет обращений, никогда не обходятся.
  `POST /api/staff/sessions` передаёт в limiter произвольный введённый username и
  IP в `src/face_moment/platform/auth/http.py:39-51`; positive configured limit
  and window подтверждены в
  `.memory-bank/domains/staff-access.md:62-65`.
- Практический эффект: поток уникальных логинов и/или source IP за время жизни
  backend-процесса монотонно увеличивает in-memory state, даже после истечения
  всех окон. Это создаёт неограниченный рост памяти на публичной login boundary
  и со временем повышает риск деградации или перезапуска процесса; перезапуск
  лишь временно очищает state.
- Наименьшее направление исправления: сохранить single-backend limiter, но
  ограничить cardinality и удалять неактивные ключи по истёкшему окну (без
  введения distributed limiter или очереди).

## Неопределённость и неадмитированные области

- Новые runtime/load-пробы не запускались: вывод основан на текущем коде и
  уже успешных task verification receipts. В проекте нет production telemetry,
  поэтому конкретный момент исчерпания памяти не оценён; сам неограниченный
  рост ключевого словаря детерминирован кодом.
- На проверенной evidence-поверхности не подтверждён иной материальный долг.
  В частности, Caddy trust boundary и маршрутизация TASK-004 имеют итоговый
  semantic-pass, а TASK-007 подтверждённо сохраняет owner boundary, immutable
  projection и RESTRICT migration behavior. Наблюдения только о стиле, размере
  функций, процентах покрытия или отсутствии будущих возможностей не считались
  находками.
