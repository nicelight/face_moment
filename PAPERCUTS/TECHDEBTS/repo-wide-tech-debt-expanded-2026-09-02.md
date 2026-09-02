---
description: Expanded repository-wide technical-debt review with feature and task attribution.
status: active
---
# Расширенный repository-wide technical-debt review — 2026-09-02

## Назначение и проверенная область

Это уточнённое продолжение отчёта
`PAPERCUTS/TECHDEBTS/repo-wide-tech-debt-2026-09-01.md`. Старый отчёт не
перезаписывался: здесь каждому finding добавлен контекст выполнения, явная
связь с product features и indexed tasks, а также повторно проверен его статус
в текущем рабочем tree.

Проверены все ранее принятые девять findings на текущем source, включая
незакоммиченные результаты FT-008/FT-009. Для повторной проверки использованы:

- 82 Python source files, 19 first-party client files и 18 Alembic migrations;
- HTTP/composition boundaries, capability package exports, Docker/Compose и
  Caddy;
- конкретные regression tests и task-local verification evidence;
- актуальные feature documents, implementation plans и indexed task cards.

Task attribution ниже означает не одно и то же во всех случаях:

- **owner/source task** — task, в чьей implementation surface находится
  механизм долга;
- **trigger task** — корректная последующая работа, которая лишь обнаружила
  старый долг;
- **affected/downstream task** — task, чьи gates, projections или integration
  зависят от этого seam. Такой task не объявляется причиной finding.

Отчёт advisory-only. Он не меняет implementation, specs, task status,
dependencies, gates или workflow lifecycle.

## Актуализированный итог

Полная архитектурная переработка не нужна. Нужен ограниченный рефакторинг
восьми активных механизмов. Бывший единственный HIGH/P0 finding уже закрыт
`TASK-094-T3-FT-009-W1`; оставлять его в очереди работ было бы ошибкой.

| № | Текущий статус | Приоритет | Кратко | Основная feature/task связь |
|---|---|---|---|---|
| 1 | Закрыт | бывший P0 | post-commit ORM read в event emission | FT-009: failed TASK-090, repair TASK-094 |
| 2 | Активен | P1 | Engine создаётся на каждый HTTP request | FT-001, FT-004, FT-005/006, FT-008 |
| 3 | Активен | P1 | eager package exports раздувают import graph | FT-004—FT-009 |
| 4 | Активен | P1 | regression tests привязаны к исторической форме | FT-000, FT-001, FT-002; trigger FT-009 |
| 5 | Активен | P1 | container gate может запускать stale wheel | Foundation/workflow; проявлялся в FT-004, FT-008, FT-009 |
| 6 | Активен | P2 | effective display status вычисляется дважды | FT-005/TASK-077, FT-007/TASK-083 |
| 7 | Активен | P2 | realtime route registry дублируется в Caddy | FT-003/TASK-045, FT-007/TASK-083 |
| 8 | Активен | P3 | browser-recovery proof непереносим и допускает false positive | FT-003/TASK-054 |
| 9 | Активен | P3 | serving switch требует неявно чистую Session | FT-002/TASK-040 |

## Findings

### 1. ЗАКРЫТ — best-effort event emission больше не читает commit-expired ORM row

**Контекст.** FT-009 добавляет best-effort structured server events. Основной
participant flow сначала должен надёжно сохранить Promo Attempt, а уже затем
попытаться поставить diagnostics event в bounded queue. Логирование разрешено
потерять, но оно не должно задерживать или менять owner outcome.

В failed реализации `TASK-090` realtime handler делал commit, а затем передавал
в emitter ORM object. При стандартном SQLAlchemy `expire_on_commit` чтение его
полей запускало implicit refresh. Real PostgreSQL latch доказал, что
logging-only SELECT способен остановить participant request ещё до enqueue.

**Связь с features и tasks.** Это был finding только FT-009:

- `TASK-090-T3-FT-009-W1` — source task и исторический failed outcome;
- `TASK-094-T3-FT-009-W1` — единственный executable replacement, сейчас
  `done`; он владеет исправлением `FT-009-AC-002`;
- `TASK-091-T3-FT-009-W2` и `TASK-093-T3-FT-009-W3` — downstream search и
  retention tasks. Они зависят от завершённого producer boundary, но не были
  причиной дефекта;
- prerequisites `TASK-081-T3-FT-006-W2`, `TASK-085-T2-FT-007-W3` и
  `TASK-086-T3-FT-007-W3` задавали Promo/diagnostics context и также не
  являются владельцами finding.

**Текущее evidence.** В
`src/face_moment/entrypoints/realtime.py:211-227` UUID `attempt_id` и
`correlation_id` снимаются до commit, а после commit в
`emit_attempt_admitted()` передаются только эти primitives. В
`src/face_moment/promo/realtime_orchestration.py:248-292` admitted и terminal
emitters больше не принимают `PromoAttempt`. QR path после owner commit делает
не скрытый ORM refresh, а ровно один явный bounded Promo-owned lookup при
необходимости. Fresh verification и red verification `TASK-094` подтвердили
отсутствие post-commit event-assembly SQL в realtime path и неизменность owner
outcome при отказах diagnostics.

**Вердикт.** Дополнительный рефакторинг по этому finding не нужен. Историческое
evidence `TASK-090` следует сохранять, но активную очередь начинать со finding
№4/№5, а не повторно открывать producer repair.

### 2. MEDIUM / P1 — пять HTTP adapters создают и уничтожают Engine на каждый request

**Контекст.** Backend composition уже является долгоживущим process, но каждый
capability HTTP adapter локально реализует собственный `_database_session()`.
При DB-backed request helper создаёт SQLAlchemy `Engine`, открывает одну
`Session`, после ответа делает `engine.dispose()`. Pool существует только в
пределах одного request и практически не переиспользуется.

Точные копии находятся в:

- `src/face_moment/platform/auth/http.py:131-137`;
- `src/face_moment/inventory/http.py:214-220`;
- `src/face_moment/serving_control/http.py:160-166`;
- `src/face_moment/diagnostics/http.py:259-265`;
- `src/face_moment/promo/http.py:470-476`.

**Связь с features и tasks.** Это cross-feature composition debt, а не дефект
одной бизнес-фичи:

- FT-001: `TASK-004-T3-FT-001-W2` использует auth HTTP/session surface, а
  `TASK-015-T3-FT-001-W3` — inventory ingest-target API;
- FT-004: `TASK-068-T3-FT-004-W1` добавил serving-control staff HTTP surface;
- FT-005/FT-006: `TASK-076-T3-FT-005-W1`, `TASK-077-T3-FT-005-W2` и
  `TASK-081-T3-FT-006-W2` последовательно расширяли Promo HTTP adapter,
  сохраняя тот же request-local Engine lifecycle;
- FT-008: `TASK-089-T3-FT-008-W2` добавил пятый экземпляр helper в diagnostics
  HTTP adapter;
- FT-009: `TASK-094-T3-FT-009-W1` затрагивает Promo route wiring, но не создаёт
  сам lifecycle debt. Плановый `TASK-091-T3-FT-009-W2` будет его downstream
  consumer, если diagnostics routes продолжат использовать тот же helper.

**Почему это debt.** Это одновременно operational и change-cost mechanism.
Каждый DB request повторяет создание/настройку pool и connection checkout, а
политика `pool_pre_ping`, credentials и disposal размножена по пяти местам.
Новый adapter естественным образом копирует шестую версию вместо повторного
использования process-owned resource. Tests также вынуждены monkeypatch-ить
каждый локальный seam отдельно.

**Impact.** Подтверждён сам lifecycle/connection churn и пять точек изменения;
production latency percentile не измерялся. Поэтому severity остаётся MEDIUM,
но устранение стоит делать до дальнейшего роста staff API.

**Минимальная remediation.** `backend` composition root владеет одним
process-local Engine и narrow session factory и передаёт factory registrars
маршрутов. Capability repositories продолжают получать обычную `Session` и не
требуют нового service layer. Diagnostics background event writer должен
сохранить отдельный Engine/Session: его isolation от participant transaction —
принятый FT-009 contract, а не дублирование этого HTTP lifecycle.

### 3. MEDIUM / P1 — eager package re-exports превращают leaf import в system-wide import

**Контекст.** В Python перед загрузкой `package.module` всегда выполняется
`package/__init__.py`. Сейчас capability packages используют `__init__.py` как
широкий facade и немедленно импортируют почти все repositories, models и
services. Поэтому даже лёгкий diagnostics event catalog сначала поднимает
investigation, Promo, Processing, image/object-store dependencies и ORM models.

Основные seams: `diagnostics/__init__.py:3-39`, `promo/__init__.py:3-69`,
`processing/__init__.py:3-29`, `inventory/__init__.py:1-14` и
`serving_control/__init__.py:3-40`.

**Связь с features и tasks.** Механизм накапливался с ростом capability graph:

- FT-004: `TASK-070-T2-FT-004-W2`, `TASK-071-T2-FT-004-W3` и
  `TASK-072-T3-FT-004-W4` добавили Processing/Promo realtime search и
  result-session exports;
- FT-005: `TASK-076-T3-FT-005-W1` и `TASK-077-T3-FT-005-W2` расширили Promo
  facade display symbols;
- FT-007: `TASK-084-T2-FT-007-W2` и `TASK-085-T2-FT-007-W3` добавили
  Diagnostics evidence и его связи с Promo projection;
- FT-008: `TASK-088-T2-FT-008-W1` и `TASK-089-T3-FT-008-W2` добавили Attempt
  query/investigation exports;
- FT-009: failed `TASK-090-T3-FT-009-W1` добавил server-event exports, а
  `TASK-094-T3-FT-009-W1` расширил Promo producer surface. Он исправил
  post-commit SQL, но не import topology;
- ранние FT-001/FT-002 capability packages также участвуют в каскаде, хотя
  текущий резкий рост лучше всего виден на FT-004—FT-009.

Эти tasks перечислены как точки расширения graph, не как individually failed
tasks: их feature acceptance может быть полностью корректным.

**Текущее evidence.** Fresh current-source probe импортировал только
`face_moment.diagnostics.server_events`, но в результате загрузились 46
`face_moment.*` modules плюс `cv2`, NumPy и boto3; cold import занял около
1.75 s в project image. Тот же cascade регистрирует 15 SQLAlchemy tables и
делает Foundation metadata test order/shape-sensitive.

**Impact.** Лёгкие CLI, migration/tooling imports и isolated tests зависят от
ML/object-store stack; import failure или side effect в далёком capability
ломает несвязанный leaf. Ранее проект уже сталкивался с circular-import
вариантом этого класса проблемы. Текущий cycle закрыт, но wide cascade остаётся.

**Минимальная remediation.** Сделать перечисленные `__init__.py` тонкими и
перевести production consumers на imports из concrete modules. Оставить в
facade только небольшой, действительно стабильный и dependency-neutral API.
Lazy-import framework, plugin registry или новый DI layer для этого не нужны.

### 4. MEDIUM / P1 — regression suite проверяет историческую форму вместо долговечного поведения

**Контекст.** Пять tests сейчас красные не из-за product regression, а потому
что зафиксировали временный снимок repository layout. На fresh current-source
run все пять упали отдельно и предсказуемо, тогда как Caddy сам принимает
конфигурацию как валидную.

Подтверждены три независимых подмеханизма.

1. `tests/inventory/test_admission_lineage.py:204-209` требует, чтобы global
   Alembic head навсегда оставался `0009`. `tests/processing/test_processing_persistence.py:138-143`
   требует, чтобы global head непосредственно наследовал `0007`. При текущем
   корректном единственном head `0018_structured_server_events` оба assertions
   закономерно ложны.
2. `tests/staff_access/test_sessions.py:156-162` и
   `tests/inventory/test_ingest_targets_api.py:151-158` ищут Caddy blocks как
   literal strings с прежней indentation. Текущий `route` nesting меняет
   пробелы, не routing semantics. Fresh `caddy validate` вернул
   `Valid configuration`, а оба tests всё равно упали.
3. `tests/test_foundation.py:10-12` после import composition roots требует
   пустой `Base.metadata`. Реальные model imports корректно регистрируют 15
   tables, поэтому test падает даже изолированно.

**Связь с features и tasks.** Здесь важно отделить owner старого test от
последующего trigger:

- FT-002 `TASK-018-T2-FT-002-W1` владеет processing migration round-trip test;
- FT-002 `TASK-037-T2-FT-002-W5` владеет admission-lineage migration test;
- FT-001 `TASK-004-T3-FT-001-W2` и `TASK-015-T3-FT-001-W3` владеют двумя
  text-shape Caddy assertions;
- FT-000 `TASK-001-T3-FT-000-W0` / `TASK-002-T2-FT-000-W0` — Foundation
  skeleton/gate, к которому относится metadata invariant;
- FT-007 `TASK-083-T3-FT-007-W1` изменил legitimate Caddy nesting и обнаружил
  хрупкость старых FT-001 assertions;
- FT-009 `TASK-090-T3-FT-009-W1` добавил migration `0018`;
  `TASK-094-T3-FT-009-W1` сохранил её как завершённую часть predecessor.
  FT-009 здесь trigger, а не владелец stale assertions.

**Impact.** Repo-wide gate смешивает настоящие regressions с гарантированными
ложными отказами. Следующая допустимая migration, Caddy grouping или model
import снова потребует ручного разбора уже известных failures; доверие к
красному full-suite signal падает.

**Минимальная remediation.** Historical migration tests должны проверять
конкретную named revision и её собственного predecessor; отдельный общий test
— ровно один Alembic head. Caddy shape проверяется через `caddy validate/adapt`
и один executable routing smoke. Foundation test проверяет единственность
shared `Base`/metadata owner, а не отсутствие таблиц после imports. Product
contracts и migrations менять не нужно.

### 5. MEDIUM / P1 — container gate не доказывает соответствие image текущему source

**Контекст.** Indexed Python gates обычно имеют форму
`docker compose run --rm backend python -m ...`. Compose запускает установленный
wheel из `face-moment:dev`; host source не смонтирован. Команда сама по себе не
доказывает, что image собран после последней source/test правки.

Это не теоретический риск. В текущем tree `emit_attempt_admitted` уже имеет
исправленную primitive-only сигнатуру `(event_sink, *, attempt_id,
correlation_id)`. Bare Compose image сейчас импортирует файл из
`/usr/local/lib/python3.11/site-packages` со старой rejected сигнатурой
`(event_sink, attempt: PromoAttempt)`. Иначе говоря, обычная gate command прямо
сейчас способна тестировать код до закрытия finding №1.

Вторая часть того же build/gate seam — стоимость обновления image.
`Dockerfile:11-13` копирует весь `src/` до `pip wheel .`, причём wheel command
разрешает также dependency set. Любое source-only изменение инвалидирует слой
и может повторно скачивать тяжёлые ML dependencies. Task evidence уже
фиксировало external rebuild failure на pinned `insightface`, после чего
проверки приходилось выполнять через current-source read-only mounts.

**Связь с features и tasks.** Это workflow/Foundation debt, а не product
acceptance одного feature:

- FT-000 `TASK-001-T3-FT-000-W0` / `TASK-002-T2-FT-000-W0` — executable image
  и Foundation gate являются ближайшим durable ownership surface;
- FT-004 `TASK-068-T3-FT-004-W1`, `TASK-069-T2-FT-004-W1` и
  `TASK-074-T3-FT-004-W1` — ранний подтверждённый repeated trigger: bare image
  давал misleading failures, current-source mount проходил;
- FT-008 `TASK-088-T2-FT-008-W1` / `TASK-089-T3-FT-008-W2` — execution
  evidence снова использовало rebuild либо explicit `PYTHONPATH=/workspace/src`;
- FT-009 `TASK-090-T3-FT-009-W1` / `TASK-094-T3-FT-009-W1` — самый сильный
  текущий пример: image всё ещё содержит failed ORM-handoff API, хотя current
  source и verification уже закрыли repair.

Приоритет повышен с прежнего P2 до P1 именно из-за этого текущего
source-versus-image расхождения. Это не означает, что названные feature tasks
неверно завершены: их independent verification использовало current-source
evidence. Ненадёжен default gate path.

**Impact.** Исполнитель может получить зелёный или красный результат для
другой версии программы, чем та, которую сдаёт. Это увеличивает число retries
и делает provenance test evidence неочевидным. Медленный network-sensitive
rebuild стимулирует повторное использование stale image и усиливает первый
механизм.

**Минимальная remediation.** Shared executor/receipt принимает только один из
двух доказанных режимов: read-only mount текущего workspace с явным
`PYTHONPATH`, либо successful rebuild после последней правки с записанным image
digest/source marker. В Dockerfile dependency wheels следует кэшировать
отдельно от application wheel, а application wheel строить `--no-deps`.
Новый build system и переписывание task cards по одной не нужны.

### 6. MEDIUM / P2 — effective display status имеет два владельца вычисления

**Контекст.** В БД хранится raw display state. Пока raw state равен `pending`,
после `display_expires_at` read model должен показывать derived
`unconfirmed`, не мутируя историческую row. Это одно domain rule, но оно
реализовано независимо в двух projections:

- `src/face_moment/promo/display_outcome.py:213-221`;
- `src/face_moment/promo/client_timing.py:144-153`.

**Связь с features и tasks.** Ownership здесь точечный:

- FT-005 `TASK-077-T3-FT-005-W2` ввёл display outcome и исходное temporal rule;
- FT-007 `TASK-083-T3-FT-007-W1` повторил rule в core timing projection. На
  первой попытке именно этот task уже получил реальное semantic divergence:
  tag был `display_unconfirmed`, а projection возвращала raw `pending`;
- FT-007 `TASK-085-T2-FT-007-W3` и FT-008 `TASK-088-T2-FT-008-W1` /
  `TASK-089-T3-FT-008-W2` являются downstream consumers diagnostic/core
  timeline projection. Они не создали правило, но получат противоречивое
  состояние при следующем drift.

**Impact.** Любая правка срока или набора display states требует синхронного
изменения двух функций и их tests. Уже существовавший divergence доказывает
repeated-change risk, а не только формальное нарушение DRY.

**Минимальная remediation.** Вынести одну pure Promo-owned функцию
`effective_display_status(raw_status, display_expires_at, now)` в существующий
подходящий Promo module и вызвать её из обеих projections. Stored schema,
repository lifecycle и новый service/class не нужны. Tests должны сохранить
no-mutation invariant и одинаковый результат до, ровно на и после expiry.

### 7. MEDIUM / P2 — public realtime routes перечислены и в FastAPI, и в Caddy

**Контекст.** FastAPI realtime application владеет endpoint shapes, но
центральный origin направляет запросы по отдельному Caddy matcher:
`deploy/Caddyfile:16,38-45`. Сейчас там вручную перечислены root
`/api/realtime/attempts` и child `/api/realtime/attempts/*/client-timing`.
Таким образом path registry существует дважды.

**Связь с features и tasks.** Механизм пересекает две feature boundaries:

- FT-003 `TASK-044-T2-FT-003-W1` установил central-origin client shell и edge;
- FT-003 `TASK-045-T3-FT-003-W3` установил точный realtime admission path и
  двойной 20 MiB boundary;
- FT-007 `TASK-083-T3-FT-007-W1` добавил child timing route и обнаружил
  operational failure дублированного registry: endpoint работал в ASGI app,
  но отсутствовал в Caddy matcher и уходил в backend fallback;
- будущие tasks, добавляющие public children к `/api/realtime/*`, будут
  affected, пока обязаны вручную синхронизировать оба списка.

**Impact.** Рассинхронизация уже сделала валидный endpoint недоступным по
реальному client path и вернула misleading fallback response. Нынешние
text-shape assertions не исполняют Caddy-to-realtime handoff и частично
пересекаются с finding №4.

**Минимальная remediation.** Если отдельного security requirement на exact
allow-list нет, Caddy должен владеть одним bounded capability prefix
`/api/realtime/*` с текущим request-body limit, а FastAPI — child routing. Если
exact allow-list обязателен, registry остаётся, но один disposable executable
Caddy routing smoke должен заменить доказательство через literal text. Перед
выбором prefix нужно подтвердить только это security решение; новый proxy
layer не требуется.

### 8. MEDIUM / P3 — permanent browser-recovery test непереносим и проверяет невалидный sensor payload

**Контекст.** FT-003 требует, чтобы managed Chromium profile переживал reload
и process restart, сохраняя только kiosk configuration и отбрасывая
participant state. Постоянный test моделирует три состояния (`advertising`,
`active`, `result`) и повторно открывает persistent profile. Сам recovery
ранее доказан отдельными verifier probes; debt находится в permanent
regression harness.

Здесь два связанных механизма:

1. `tests/client/test_browser_recovery.spec.mjs:7-8` делает bare
   `require("playwright/test")`, но repository не содержит project-owned Node
   manifest/lock/config или resolver. Fresh `node --test` сейчас завершается
   `MODULE_NOT_FOUND` до выполнения сценариев.
2. Fixture в строках `17-25` сохраняет `sensor_id`, тогда как production
   `client/sensor-config.js:14-40` принимает `sensorId` и вернёт `null` для
   такого payload. После relaunch test сравнивает raw `localStorage`, поэтому
   неработоспособная для приложения конфигурация считается успешно
   восстановленной.

**Связь с features и tasks.** Primary owner — FT-003
`TASK-054-T3-FT-003-W5` (`done_for_prod`), который добавил kiosk user-service
restart и permanent browser recovery scenario. `TASK-053-T2-FT-003-W5`
предоставляет часть Attempt state behavior, используемую сценарием, но не
владеет Playwright resolution или sensor fixture. Другие features этим
finding не затронуты.

**Impact.** Clean checkout не имеет очевидного воспроизводимого запуска
главного recovery regression. Даже на машине с глобально доступным Playwright
test может дать false green по sensor configuration. Поэтому future change в
profile persistence требует снова искать task-local probes и не получает
надёжного permanent signal.

**Минимальная remediation.** Дать test один repository-owned entrypoint на
уже принятом Playwright runtime и включить его в recovery gate. Sensor config
сохранять через production `saveSensorConfig()` и после relaunch читать через
`readSensorConfig()`. Полный frontend framework/toolchain не нужен; достаточно
переносимого runner seam и application-level assertion.

### 9. MEDIUM / P3 — serving revision switch имеет скрытое clean-Session требование

**Контекст.** `IngestTargetRepository.switch_serving_revision()` выполняет
guarded A-to-B command и сам открывает transaction через
`with self._session.begin()` в
`src/face_moment/serving_control/ingest_target.py:124-132`. SQLAlchemy Session
использует autobegin: любой предыдущий authentication/read уже открывает
transaction. Повторный `begin()` тогда детерминированно бросает
`InvalidRequestError` до audited commit/reject result.

Текущие focused tests всегда передают свежую Session, а transport handler для
manual switch ещё не существует. Поэтому accepted FT-002 behavior сейчас не
сломано: это latent integration precondition, которое проявится при первом
обычном authenticated caller, если auth/read и command используют одну
request-scoped Session.

**Связь с features и tasks.** Finding принадлежит FT-002
`TASK-040-T2-FT-002-W7`, реализовавшему manual serving-revision switch.
`TASK-039-T2-FT-002-W6` поставляет exact-A read-only backlog guard, вызываемый
командой, но сам не является источником transaction precondition. Пока нет
отдельного transport task, которому можно честно приписать reachable defect.

**Impact.** Будущая интеграция может падать только из-за порядка чтения и
начала transaction, хотя все target/guard semantics корректны. Это повышает
стоимость подключения handler и создаёт неявное правило, уже знакомое соседнему
photo-admission flow, где read transaction приходится явно заканчивать.

**Минимальная remediation.** Composition boundary вызывает command в отдельной
короткой write Session после read-only authentication либо явно завершает read
transaction перед передачей управления owner command. Добавить один
integration case «authenticated read, затем switch». Не делать безусловный
`rollback()` внутри repository: он может молча уничтожить caller-owned pending
work.

## Рекомендуемый порядок работ

1. Восстановить доверие к evidence: вместе закрыть finding №4 (durable tests)
   и №5 (source/image congruence). Сейчас это самые частые и самые дорогие
   источники ложного сигнала.
2. Уменьшить process-wide coupling: finding №3 (thin package exports), затем
   №2 (один backend-owned Engine/session factory). Порядок снижает import и
   wiring noise перед lifecycle refactor.
3. Выполнить два малых semantic/integration refactors: №6 (единый effective
   display helper) и №7 (единое ownership realtime route registry либо
   executable edge smoke).
4. Починить permanent recovery harness №8. Finding №9 закрыть до появления
   authenticated switch transport, но не расширять сейчас в новый API.
5. Finding №1 не переоткрывать: `TASK-094` уже дал нужный bounded repair и
   independent proof.

## Что не принято как debt

- Размер `client/app.js`, HTTP adapters или diagnostics repositories сам по
  себе — без отдельного failure/change-cost mechanism.
- Отсутствие Ruff, coverage percentage или дополнительных abstraction layers.
- Уже закрытый post-commit ORM defect после `TASK-094`.
- Плановые `TASK-091`/`TASK-093`: их незавершённость — workflow state, а не
  technical debt уже сделанного кода.

## Неопределённость и границы выводов

- Production load test не выполнялся; finding №2 основан на точном resource
  lifecycle и duplicated policy, а не на измеренном p95 latency.
- Full browser UAT и pilot-host restart не повторялись; finding №8 ограничен
  permanent test и fresh module-resolution failure. Прежнее task-local
  functional proof не оспаривается.
- Prefix remediation в finding №7 зависит от наличия или отсутствия
  обязательного exact route allow-list. Это единственное решение, которое
  нельзя принимать без security contract/owner confirmation.
- Пять targeted Python failures и import/Caddy/Node probes запускались на
  current-source read-only mount. Full 280-test suite повторно не запускался,
  потому что для расширения контекста достаточно было перепроверить каждый
  конкретный механизм и не смешивать его с незавершённой FT-009 queue.
- Task attribution не меняет уже принятые task verdicts. Большинство findings
  — debt вокруг завершённых функциональных результатов, а не доказательство,
  что соответствующая feature acceptance неверна.
