# Face Moment — Architecture Review Findings

Date: 2026-07-24  
Verdict: `CHANGES REQUESTED`

## Review basis

- `arch_vision.md` принят как источник истины для архитектурного ревью.
- Проверен текущий worktree относительно `HEAD`, включая untracked-файлы.
- `arch_vision.md` исключён из объектов ревью.

## Findings

### F-01 [P1] Новый источник истины не отражён в source precedence

`.memory-bank/spec-backbone.md` по-прежнему отдаёт приоритет PRD и считает
архитектуру, ownership, transaction boundaries и Foundation открытыми.
`.memory-bank/spec-index.md` объявляет глобальную архитектуру pending, а
`NEED_UPDATE.md` прямо называет `arch_vision.md` непринятым proposal.

**Влияние:** следующий агент может повторно обсуждать уже принятые решения или
спроектировать несовместимый backbone.

**Требуемая коррекция:** признать `arch_vision.md` принятым архитектурным входом.
Сохранить pending только для точных контрактов и деталей, отсутствующих в
`arch_vision.md`; не объявлять весь Global Backbone завершённым до выполнения
его workflow-синхронизации.

**Evidence:**

- `.memory-bank/spec-backbone.md:38`
- `.memory-bank/spec-backbone.md:64`
- `.memory-bank/spec-backbone.md:110`
- `.memory-bank/spec-index.md:22`
- `NEED_UPDATE.md:8`
- `NEED_UPDATE.md:78`

### F-02 [P1] Потерян отдельный display acknowledgement

PRD, Promo feature и lifecycle map не разделяют выдачу результата сервером и
подтверждённый client-side показ четырёх teasers с полностью видимым QR.

**Влияние:** server response может быть ошибочно засчитан как успешный Promo,
хотя browser не декодировал teasers или не показал QR.

**Требуемая коррекция:** закрепить idempotent client acknowledgement после
декодирования четырёх teasers и полной видимости QR. Разделить
`processing_status` и `display_status`; acceptance latency измерять по
client-side monotonic timestamps.

**Evidence:**

- `.memory-bank/prd.md:294`
- `.memory-bank/prd.md:685`
- `.memory-bank/features/FT-005.md:29`
- `.memory-bank/states/lifecycle-map.md:47`
- `arch_vision.md:248`

### F-03 [P1] Boundary Map назначает ownership процессам вместо пяти slices

`.memory-bank/contracts/boundary-map.md` отдаёт backend одновременно
authentication, выбранную дату, checksum arbitration и commit `Photo + pending`.
`RealtimeFaceService` получает search, result construction и session issue, а
backend/PostgreSQL — core Attempt и diagnostic evidence.

**Влияние:** write ownership пяти slices размывается; implementation может
смешать `serving_control`, `inventory`, `processing`, `promo` и `diagnostics` в
техническом backend layer.

**Требуемая коррекция:** назначить ответственность capability slices:

- `platform/auth` — staff principals, credentials и server sessions;
- `serving_control` — СПА/date/settings context;
- `inventory` — Photo admission и original ownership;
- `processing` — `pending` state, pipeline processing и search;
- `promo` — core Attempt, result и session;
- `diagnostics` — detailed evidence, annotations и Calibration.

Process boundaries должны оставаться deployment/runtime boundaries, а не
владельцами доменных инвариантов.

**Evidence:**

- `.memory-bank/contracts/boundary-map.md:29`
- `.memory-bank/contracts/boundary-map.md:30`
- `.memory-bank/contracts/boundary-map.md:31`
- `.memory-bank/contracts/boundary-map.md:33`
- `.memory-bank/contracts/boundary-map.md:34`
- `arch_vision.md:81`

### F-04 [P1] PRD продолжает требовать отвергнутую realtime-очередь

PRD требует bounded short-lived in-memory queue. `IDEA_APP.md`, `IDEA_OS.md` и
runtime diagram закрепляют FIFO queue, queue length, rejection и queue-wait
metrics.

**Влияние:** появляется лишнее состояние ожидания, дополнительные failure paths
и telemetry для concurrency, отсутствующей в one-СПА pilot.

**Требуемая коррекция:** оставить один realtime process, один inference slot и
server deadline. Concurrent request получает `busy`; waiter и realtime queue не
создаются. Queue-wait metric не является обязательной pilot-метрикой.

**Evidence:**

- `.memory-bank/prd.md:343`
- `.memory-bank/prd.md:427`
- `.memory-bank/prd.md:443`
- `IDEA_APP.md:1054`
- `IDEA_APP.md:1261`
- `IDEA_OS.md:630`
- `mermaids/03-runtime-architecture.md:27`
- `arch_vision.md:229`

### F-05 [P1] IDEA_APP остаётся действующим Batch-first документом

`IDEA_APP.md` заявляет, что фиксирует принятые архитектурные решения, но
сохраняет batch confirmation, `batch.confirmed_at`, `batch_id`, Batch-scoped
search и Batch upload в MVP.

**Влияние:** документ продолжает предлагать запрещённую доменную сущность,
неверный ingest UX, неправильный SLO anchor и лишний aggregate lifecycle.

**Требуемая коррекция:** синхронизировать active pilot sections с independent
per-photo admission:

- без Batch, manifest и confirmation;
- `UNIQUE(spa_id, visit_date, checksum_sha256)`;
- server-side `photo.accepted_at`;
- atomic per-photo `Photo + pending`;
- search по всем совместимым `ready` Photo активных СПА/date.

**Evidence:**

- `IDEA_APP.md:6`
- `IDEA_APP.md:53`
- `IDEA_APP.md:115`
- `IDEA_APP.md:141`
- `IDEA_APP.md:351`
- `IDEA_APP.md:486`
- `IDEA_APP.md:1218`
- `IDEA_APP.md:1312`

### F-06 [P1] IDEA_APP сохраняет обязательный diagnostic bundle

`IDEA_APP.md` описывает полный diagnostic bundle и требует его для каждой
попытки. `IDEA_OS.md` предполагает сохранение raw reference series, normalized
images, crops и Promo screenshot и не ограничивает promoted case curated
subset.

**Влияние:** diagnostic completeness становится скрытым success dependency,
увеличивает storage/privacy burden и противоречит принятому best-effort
evidence contract.

**Требуемая коррекция:** core Attempt остаётся единственной обязательной
correlation record. Detailed evidence присоединяется best-effort; terminal gap
виден как `incomplete`. До явного удаления хранится только вручную promoted
curated subset, а не весь ordinary evidence set.

**Evidence:**

- `IDEA_APP.md:1174`
- `IDEA_APP.md:1205`
- `IDEA_APP.md:1312`
- `IDEA_OS.md:439`
- `arch_vision.md:263`

### F-07 [P2] IDEA_APP предлагает лишнюю job/lease-модель для singleton worker

`IDEA_APP.md` вводит отдельную `photo_processing_jobs`, `locked_at`,
`locked_by`, `SKIP LOCKED`, timeout reclaim, job types и `claim_uuid`.

**Влияние:** добавляются вторая очередь состояний, lease lifecycle,
reconciliation и тестирование concurrency, отсутствующей в deployment
contract.

**Требуемая коррекция:** использовать `photo_pipeline_states` как durable queue:
один atomic claim, startup `processing -> pending`, restart-from-beginning,
полная замена final face set и небольшой retry limit. Multi-consumer claim
machinery отложить до появления второго worker.

**Evidence:**

- `IDEA_APP.md:814`
- `IDEA_APP.md:821`
- `IDEA_APP.md:843`
- `IDEA_APP.md:898`
- `arch_vision.md:214`

### F-08 [P2] Post-pilot delivery seam расходится с принятой full-version границей

`IDEA_APP.md` и `IDEA_OS.md` заранее закрепляют signed URLs как механизм выдачи
originals после pilot.

**Влияние:** supporting documents направляют будущую реализацию в обход
принятого ownership: payment/entitlement принадлежит внутреннему модулю
`promo`, original — `inventory`, а backend proxy остаётся стартовым способом
выдачи.

**Требуемая коррекция:** сохранить только stable IDs и ownership seam. Не
закреплять presigned participant delivery до измеренного bottleneck backend
proxy или отдельного решения при активации full-version scope.

**Evidence:**

- `IDEA_APP.md:65`
- `IDEA_APP.md:1293`
- `IDEA_OS.md:80`
- `IDEA_OS.md:280`
- `arch_vision.md:353`
- `arch_vision.md:395`

## Validation evidence

- `git diff --check` — passed.
- `node scripts/mb-lint.mjs` — passed with non-blocking warnings about missing
  epic/feature `lifecycle` fields and glossary `source_of_truth`.

  

  --- 
  
 ----------------------------------------
  ВТорой проход и сбор файндингов 
 ---------------------------------------- 

## 1. Проблемы в arch_vision.md

  ### P1 — Не замкнуты process boundaries и dependency direction

  Одновременно заявлены direct in-process calls и три отдельных
  процесса, но не зафиксировано, куда HTTPS edge направляет realtime
  request и какой процесс исполняет promo orchestration:
  arch_vision.md:24, arch_vision.md:39.

  Дополнительно граф содержит явный цикл:

  promo -> diagnostics -> promo

  Он виден в arch_vision.md:94. При буквальной реализации через Python
  imports это даст circular dependency либо скрытую orchestration-
  логику.

  Минимальная коррекция:

  - явно выбрать routing: /realtime сразу в RealtimeFaceService, а
    acknowledgement/QR/staff UI — в backend;

  - назвать, какие slices композируются каждым entrypoint;
  - разорвать цикл одним узким typed port для diagnostic sink и
    published read projection — без event bus;

  - явно определить, как processing получает immutable Photo/original
    projection от inventory.

  ### P1 — Core Attempt может потеряться в offline-сценарии

  Client создаёт attempt_id при принятии sensor trigger, но сервер
  создаёт Attempt только при получении запроса. Local IndexedDB outbox
  описан как необязательный: arch_vision.md:244. Это не гарантирует core
  Attempt после offline + Chromium restart и расходится с требованием
  сохранять каждую принятую попытку в .memory-bank/prd.md:338.

  Самая дешёвая коррекция — обязательный bounded local outbox только для
  минимального attempt envelope: attempt_id, monotonic timestamps,
  client_offline/failure outcome. Без frames, tokens и персонального
  результата. Server upsert должен уметь создать отсутствующий offline
  Attempt.

  ### P1 — Не определён terminal transition display acknowledgement

  Указано, что просроченный acknowledgement превращает pending в
  unconfirmed, но не определены deadline, событие перехода и поведение
  позднего ack: arch_vision.md:252.

  Без этого display_status=pending может остаться навсегда, а Promo
  success и acceptance-метрики будут недостоверны.

  Достаточно зафиксировать:

  - ack_deadline_at;
  - поздний ack не подтверждает Promo;
  - unconfirmed может вычисляться при чтении или выставляться
    существующим cleanup — отдельный scheduler не нужен.

  ### P2 — Rejected upload оставляет неописанный MinIO object

  Сначала candidate записывается в MinIO, затем декодируется и
  валидируется; удаление явно предусмотрено только для duplicate:
  arch_vision.md:166. Для invalid/undecodable файла cleanup отсутствует
  и в IDEA_INGEST.md:57.

  Нужен idempotent delete candidate object при любом штатном rejected
  outcome. Редкий crash-orphan при этом может остаться принятым риском.

  ### P2 — Retry limit worker не замкнут в state machine

  Алгоритм одновременно говорит о публикации failed и о трёх retry, но
  не определяет переход при ошибке и поведение restart, когда attempts
  >= 3: arch_vision.md:214.

  Следует явно зафиксировать:

  processing error + attempts < 3 -> pending
  processing error + attempts >= 3 -> failed
  startup processing + attempts >= 3 -> failed

  Иначе poison-file может остаться вечным pending или продолжить crash-
  loop.

  ### P2 — Переключение pipeline не проверяет готовность inventory

  Pointer меняется до warmup/smoke, но validate target revision не
  включает наличие compatible ready states для текущих СПА/date:
  arch_vision.md:147.

  Если pilot действительно живёт на одной заранее выбранной revision,
  это не blocker. Если ручное переключение входит в эксплуатацию,
  достаточно добавить precondition: target revision, calibration и
  нужное inventory coverage готовы до изменения pointer. Автоматический
  backfill/orchestration для этого не нужен.

  ## 2. Расхождения остальных документов с arch_vision.md

  ### P1 — Архитектурный source of truth не канонизирован

  Сейчас одновременно существуют несовместимые утверждения:

  - arch_vision.md сам называет себя advisory recommendation;
  - Constitution требует хранить durable knowledge в .memory-
    bank/: .memory-bank/constitution.md:40;

  - Global Backbone остаётся blocked, ownership и architecture style
    обозначены открытыми: .memory-bank/spec-backbone.md:70;

  - canonical .memory-bank/architecture/system-architecture.md:7
    практически полностью TBD;

  - NEED_UPDATE.md:6 всё ещё говорит, что proposal не принят;
  - отсутствует .memory-bank/foundation.md, хотя архитектура определяет
    Foundation Required: true: arch_vision.md:368.

  Это главный documentation blocker. Global Backbone не следует просто
  помечать готовым вручную, но /spec-design уже должен потреблять
  arch_vision.md как принятый архитектурный вход, а не повторно
  открывать все решения.

  ### P1 — Boundary Map назначает ownership процессам

  .memory-bank/contracts/boundary-map.md:26 назначает владельцами
  backend, worker, service, PostgreSQL и MinIO. В arch_vision.md
  владельцами состояния являются пять capability slices, а процессы —
  только runtime boundaries.

  Особенно расходятся:

  - Photo admission: должен владеть inventory, не backend;
  - active date/settings: serving_control;
  - pipeline/search: processing;
  - Attempt/result/session: promo;
  - detailed evidence: diagnostics.

  ### P1 — Normative docs продолжают требовать realtime queue

  arch_vision.md требует один slot, busy и отсутствие waiter queue:
  arch_vision.md:229.

  Но очередь всё ещё присутствует в:

  - .memory-bank/prd.md:343 — queue wait;
  - .memory-bank/prd.md:443 — bounded in-memory queue;
  - .memory-bank/features/FT-007.md:22;
  - IDEA_DEBUG.md:35;
  - IDEA_OS.md:380 и его обязательных метриках.

  queue wait нужно убрать из обязательной timeline/acceptance модели и
  заменить на busy count и, при необходимости, локальное время захвата
  inference slot, которое для singleton обычно равно нулю.

  ### P2 — IDEA_OS.md заметно устарел

  Подтверждённые противоречия:
  - raw diagnostic series/bundles описаны как обычное обязательное
    хранение, без чёткой best-effort границы и curated promotion:
    IDEA_OS.md:439.

  Кроме того, Kubuntu/KDE, «ровно два OS users» и запрет headless-
  топологии являются дополнительными архитектурными решениями, которых
  нет в arch_vision.md. Их следует либо оформить как deployment
  recommendations, либо явно принять в архитектурный источник.

  ### P2 — Служебные handoff/review документы уже не соответствуют
  текущим файлам

  - NEED_UPDATE.md:16 требует обновить Product Brief, хотя это уже
    сделано.

  - FINDINGS_24_07_ARCHITECTURE.md:115 всё ещё утверждает, что
    IDEA_APP.md Batch-first и использует lease/jobs, хотя текущий
    IDEA_APP.md уже прямо отвергает это.

  - .memory-bank/index.md:7 называет текущий IDEA_INGEST.md историческим
    Batch-first документом, хотя тот уже описывает актуальный per-photo
    flow.

  Их нужно refresh/archive, иначе следующий агент повторит уже
  выполненную синхронизацию.

  В целом хорошо согласованы IDEA_APP.md, IDEA_INGEST.md, Product Brief,
  product/requirements и большая часть feature decomposition.
  arch_impr1.md корректно помечен advisory и прямых конфликтов не
  создаёт. CAMERA_OPTIONS.md совместим с отложенным hardware selection.

  Проверки: mb-lint и mb-doctor проходят; doctor ожидаемо сообщает
  SPEC_BACKBONE_NOT_READY. Файлы я не изменял.
