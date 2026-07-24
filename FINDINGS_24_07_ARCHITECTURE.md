# Face Moment — актуальные архитектурные findings

Дата: 2026-07-24
Статус: historical review input; не является source of truth.
Вердикт на момент ревью: `CHANGES REQUESTED`

Этот verdict superseded последующими operator decisions и синхронизацией
Planning Revision 3. Текущее состояние и authority order определяет
`.memory-bank/spec-backbone.md`; findings ниже нельзя переносить в работу без
повторной проверки по актуальным canonical docs.

## Основание и границы ревью

- `arch_vision.md` принят оператором как текущий источник истины по архитектуре.
- Проверены только существующие findings и непосредственно связанные с ними
  актуальные документы проекта.
- Mermaid-файлы и ссылки на них исключены из проверки и evidence.
- Ниже оставлены только подтверждённые проблемы. Дубли и findings, уже
  исправленные в исходных документах, удалены.

## 1. Проблемы и незамкнутые контракты в `arch_vision.md`

### AV-01 [P1] Не замкнуты runtime routing и dependency direction

`arch_vision.md` одновременно задаёт:

- один публичный HTTPS edge, под которым в topology показан только `backend`;
- отдельный процесс `RealtimeFaceService`;
- синхронный HTTPS realtime request от `SpaPromoClient`;
- direct typed Python calls между capability slices.

При этом не определено, куда edge направляет realtime request, какой entrypoint
исполняет `promo` orchestration и какие slices композируются в каждом процессе.
Граф runtime calls также содержит взаимную зависимость `promo -> diagnostics`
и `diagnostics -> promo`, а способ получения `processing` immutable
Photo/original projection от `inventory` не указан.

**Влияние:** реализация может случайно превратить process boundary в сетевой
service contract, провести realtime через лишний backend hop либо получить
circular Python imports и размытый ownership.

**Минимальная коррекция:**

- явно закрепить routing `/realtime` через HTTPS edge непосредственно в
  `RealtimeFaceService`, а acknowledgement, QR continuation и staff UI/API — в
  `backend`;
- перечислить capability slices, композируемые каждым entrypoint;
- оставить один узкий diagnostics sink port из `promo` и отдельную published
  promo read projection для `diagnostics`, без event bus;
- определить immutable inventory projection, читаемую `processing`.

Это документационный/component-contract change с низкой стоимостью; новых
runtime services, broker или generic mediator не требуется.

**Evidence:**

- `arch_vision.md:24-29`
- `arch_vision.md:39-59`
- `arch_vision.md:80-103`
- `arch_vision.md:119-121`

### AV-02 [P1] Core Attempt не гарантирован для offline-принятой попытки

Client создаёт `attempt_id` при принятии idle sensor trigger, а server-side
Attempt появляется только после получения запроса. Локальный IndexedDB outbox
описан как необязательный и может хранить diagnostic metadata, поэтому
offline-событие вместе с Chromium restart может исчезнуть до server upsert.

Это расходится с принятым требованием сохранять core Attempt для каждой
принятой capture/search attempt, включая неуспешную, и с наличием
`processing_status=client_offline`.

**Влияние:** часть реально принятых client-side попыток не попадёт в Attempts,
acceptance denominator и diagnostics.

**Минимальная коррекция:** сделать обязательным bounded local outbox только для
минимального attempt envelope: `attempt_id`, неперсональные event/elapsed
timestamps и `client_offline|failure` outcome. Server upsert по
`(spa_id, attempt_id)` должен создавать отсутствующий offline Attempt. Frames,
tokens и personalized result data остаются memory-only.

Стоимость ограничена небольшим metadata lifecycle и idempotent upsert; durable
realtime replay и хранение кадров не нужны.

**Evidence:**

- `arch_vision.md:233-246`
- `arch_vision.md:248-258`
- `.memory-bank/prd.md:336-342`
- `.memory-bank/prd.md:699-701`

### AV-03 [P1] Не определён terminal transition display acknowledgement

Архитектура разделяет `processing_status` и `display_status` и говорит, что
expired acknowledgement становится `unconfirmed`, но не задаёт:

- источник или значение acknowledgement deadline;
- момент перехода `pending -> unconfirmed`;
- поведение позднего acknowledgement;
- idempotency rule после terminal display outcome.

**Влияние:** `display_status=pending` может остаться навсегда, а
`result_issued` может быть ошибочно засчитан как успешный Promo.

**Минимальная коррекция:**

- сохранить `ack_deadline_at` либо однозначно вычислять его из persisted
  issuance time и фиксированной настройки;
- поздний acknowledgement не переводит Attempt в `confirmed`;
- `unconfirmed` вычисляется при чтении или выставляется существующим cleanup
  command;
- отдельный scheduler для этого не создавать.

Это один timestamp/derived transition поверх уже принятого acknowledgement
contract, без нового сервиса или lifecycle subsystem.

**Evidence:**

- `arch_vision.md:250-267`
- `IDEA_APP.md:1170-1185`
- `IDEA_APP.md:1212-1220`

### AV-04 [P2] Штатный rejected upload оставляет candidate object без cleanup

Candidate сначала записывается в MinIO, а затем декодируется и валидируется.
Удаление нового object явно задано только для checksum duplicate. Для обычного
`invalid|undecodable -> rejected` исхода delete не определён.

**Влияние:** повторяющиеся invalid uploads создают неограниченные private
orphans даже без crash.

**Минимальная коррекция:** выполнять idempotent delete уникального candidate
object при любом штатном rejected outcome. Редкий crash между PUT и cleanup
остаётся уже принятым orphan risk; reconciliation service не требуется.

**Evidence:**

- `arch_vision.md:164-176`
- `IDEA_INGEST.md:24-37`
- `IDEA_INGEST.md:60-72`
- `IDEA_INGEST.md:85-110`

### AV-05 [P2] Bounded retry limit worker не замкнут переходами состояний

Worker algorithm публикует `ready|no_faces|failed`, возвращает старые
`processing` в `pending` и ограничивает число попыток тремя, но переход на
processing error и startup behavior при уже исчерпанном limit не определены.

**Влияние:** разные реализации могут оставить poison file вечным `pending`,
превысить retry limit или навсегда сохранить `processing`.

**Минимальная коррекция:**

```text
processing error + attempts < 3  -> pending
processing error + attempts >= 3 -> failed
startup processing + attempts < 3  -> pending
startup processing + attempts >= 3 -> failed
```

Это уточнение существующей state machine; leases, fencing, отдельная jobs table
и второй worker не нужны.

**Evidence:**

- `arch_vision.md:214-225`
- `IDEA_INGEST.md:114-132`

## 2. Расхождения проектной документации с `arch_vision.md`

### DOC-01 [P1] Архитектурный source of truth не канонизирован в Memory Bank

Оператор уже считает `arch_vision.md` источником истины, но durable
documentation продолжает описывать архитектуру как непринятый proposal:

- Global Backbone имеет `Acceptance: not_accepted`, `Status: blocked` и
  `Planning Revision: 0`;
- `system-architecture.md` остаётся шаблоном с `TBD`;
- `NEED_UPDATE.md` требует не принимать proposal целиком;
- `.memory-bank/foundation.md` отсутствует, хотя архитектура фиксирует
  `Foundation Required: true`.

**Влияние:** следующий workflow может повторно открыть принятые решения,
сформировать несовместимые tasks или не пройти Foundation/Backbone gates.

**Минимальная коррекция:** провести принятую архитектуру через `/spec-design`,
перенеся только её обязательные решения в существующий минимальный canonical
набор. Точные API/data contracts, которых нет в `arch_vision.md`, могут
оставаться pending. Нельзя просто вручную объявить весь Backbone готовым или
повысить Planning Revision без workflow reconciliation.

Стоимость — ограниченная docs-синхронизация; новые ADR/spec-файлы создаются
только при реальной contract pressure.

**Evidence:**

- `arch_vision.md:1-18`
- `arch_vision.md:368-382`
- `.memory-bank/spec-backbone.md:7-19`
- `.memory-bank/spec-backbone.md:84-103`
- `.memory-bank/spec-backbone.md:115-133`
- `.memory-bank/spec-index.md:20-25`
- `.memory-bank/architecture/system-architecture.md:7-42`
- `NEED_UPDATE.md:6-11`
- `NEED_UPDATE.md:58-80`

### DOC-02 [P1] Boundary Map назначает ownership процессам и хранилищам

`boundary-map.md` назначает владельцами бизнес-состояния `backend`,
`RealtimeFaceService`, worker, PostgreSQL и object storage. В
`arch_vision.md` write ownership принадлежит capability slices, а процессы и
stores являются runtime/infrastructure boundaries.

Особенно расходятся:

- selected СПА/date/settings — `serving_control`, не backend;
- Photo admission и original — `inventory`;
- pipeline state и search — `processing`;
- Attempt/result/session — `promo`;
- detailed evidence/annotations/Calibration — `diagnostics`;
- staff principals/credentials/server sessions — узкий `platform/auth`.

**Влияние:** implementation plan может смешать доменные инварианты в
технических entrypoints и разрешить foreign writes.

**Минимальная коррекция:** в Boundary Map сохранить существующие runtime edges,
но заменить responsibility owner на capability owner; process/store указывать
как execution или persistence mechanism. Новые slices или services не нужны.

**Evidence:**

- `arch_vision.md:78-88`
- `arch_vision.md:119-128`
- `.memory-bank/contracts/boundary-map.md:27-35`

### DOC-03 [P1] Normative и supporting docs продолжают требовать realtime queue

`arch_vision.md` и актуальный `IDEA_APP.md` фиксируют один inference slot,
немедленный `busy`, server deadline и отсутствие waiter queue. При этом PRD
по-прежнему требует queue wait в timeline/metrics и bounded short-lived
in-memory queue. Те же semantics остаются в FT-007, `IDEA_DEBUG.md` и
`IDEA_OS.md`.

**Влияние:** task decomposition может добавить лишнее waiting state, queue
capacity/rejection contract и telemetry для concurrency, которой нет в
one-display pilot.

**Минимальная коррекция:**

- через owning product workflow убрать waiter queue из PRD reliability и
  обязательной diagnostic timeline;
- синхронизировать FT-007 и supporting docs;
- сохранять `busy` count, deadline outcomes и реальные inference/search
  durations; фиктивный queue-wait stage не создавать.

Это удаляет, а не добавляет runtime complexity.

**Evidence:**

- `arch_vision.md:229-235`
- `IDEA_APP.md:1042-1058`
- `IDEA_APP.md:1060-1070`
- `.memory-bank/prd.md:343-346`
- `.memory-bank/prd.md:427-430`
- `.memory-bank/prd.md:443-445`
- `.memory-bank/features/FT-007.md:22-28`
- `IDEA_DEBUG.md:38-40`
- `IDEA_OS.md:384-400`
- `IDEA_OS.md:501-538`
- `IDEA_OS.md:630-639`

### DOC-04 [P2] `IDEA_OS.md` сохраняет несколько устаревших архитектурных решений

Помимо realtime queue, которая учтена отдельно в DOC-03, документ расходится с
источником истины в следующих местах:

- QR/browser TTL заданы как `900/1800`, тогда как принятые значения —
  `1800/3600`;
- paid originals заранее привязаны к signed URLs, хотя стартовая participant
  delivery boundary — backend proxy, а presigned URLs отложены до измеренного
  bandwidth bottleneck;
- raw reference series, normalized images, crops и Promo screenshot описаны как
  обычный сохраняемый bundle, а ручное promotion не ограничено curated subset;
- Kubuntu/KDE, ровно два OS users и запрет headless-топологии представлены как
  обязательные принятые MVP-решения, хотя `arch_vision.md` оставляет конкретный
  display/hardware deployment зависимым от выбора площадки.

**Влияние:** infrastructure tasks могут получить неверные TTL/privacy/storage
contracts и преждевременно зафиксировать delivery и deployment mechanisms.

**Минимальная коррекция:** синхронизировать TTL, backend-proxy и curated
retention semantics. Конкретную OS/user/headless схему либо явно принять в
архитектурный source of truth, либо пометить как deployment recommendation, а
не обязательный architecture gate.

Стоимость в текущей greenfield-фазе только документационная; миграции runtime
ещё не требуются.

**Evidence:**

- `arch_vision.md:286-304`
- `arch_vision.md:306-327`
- `arch_vision.md:339-347`
- `arch_vision.md:395-408`
- `IDEA_OS.md:76-96`
- `IDEA_OS.md:149-159`
- `IDEA_OS.md:191-230`
- `IDEA_OS.md:278-301`
- `IDEA_OS.md:432-451`
- `IDEA_OS.md:556-580`
- `IDEA_OS.md:596-622`

### DOC-05 [P2] Навигация и synchronization handoff описывают уже устаревшее состояние

`NEED_UPDATE.md` всё ещё требует обновить Product Brief и пометить
`IDEA_INGEST.md` как historical/superseded. Фактически Product Brief уже
содержит per-photo/best-effort semantics, а `IDEA_INGEST.md` прямо объявляет
себя актуальным ingest-контуром и ссылается на `arch_vision.md` как на принятые
решения. Одновременно `.memory-bank/index.md` продолжает называть
`IDEA_INGEST.md` исторической Batch-first концепцией.

**Влияние:** следующий агент может откатить выполненную синхронизацию или
проигнорировать актуальный supporting document.

**Минимальная коррекция:** refresh/archive `NEED_UPDATE.md` после
канонизации архитектуры и исправить routing entry в `.memory-bank/index.md`.
Новый handoff-документ не нужен.

**Evidence:**

- `NEED_UPDATE.md:14-24`
- `NEED_UPDATE.md:87-101`
- `.memory-bank/analysis/product-brief.md:94-110`
- `IDEA_INGEST.md:3-22`
- `.memory-bank/index.md:7-14`

## Итог

Архитектурная основа остаётся жизнеспособной и KISS-соразмерной: modular
monolith, три server runtime role, PostgreSQL/MinIO и singleton workers не
требуют пересмотра. Перед tasking нужно закрыть три P1 contract gap внутри
архитектуры и синхронизировать canonical/product documents. P2 findings можно
исправить в том же documentation pass без добавления новых services,
schedulers, brokers или coordination machinery.
