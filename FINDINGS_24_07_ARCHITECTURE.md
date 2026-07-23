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
