---
description: Product Brief input contract for PRD.
status: draft
type: product-brief
---
# Product Brief

## Metadata

- Status: draft
- Decision: proceed
- Source artifacts:
  - `.memory-bank/analysis/brainstorming/BR-001.md`
  - `.memory-bank/analysis/brainstorming/BR-002.md`
  - `.memory-bank/analysis/brainstorming/BR-003.md`
  - `IDEA_APP.md`
  - `IDEA_DEBUG.md`
  - `IDEA_INGEST.md`
  - `IDEA_OS.md`
  - `.memory-bank/architecture/system-architecture.md`

## 1. One-liner

Face Moment автоматически находит профессиональные фотографии участников
one-СПА pilot, показывает четыре персональных teaser на Promo display и
переносит найденную session на телефон по QR без повторного selfie.

## 2. Target Users

- Участник pilot — тестировщик пользовательского сценария.
- Фотограф — загружает свежие готовые JPEG и получает новый канал контакта с
  потенциальным покупателем; управляет видимостью только собственных uploads.
- Оператор Face Moment/СПА — контролирует readiness фотографий, Promo и
  диагностику, управляет доступными Photo и запускает глобальные inventory
  actions.
- Разработчик приложения — расследует attempts и browser/server logs, размечает
  результаты, подбирает thresholds/quality gates и имеет staff-доступ к Photo
  Inventory Operations.
- После pilot: посетитель СПА как покупатель полного пакета фотографий.

Экономический заказчик будущего продукта пока является гипотезой: СПА, фотограф
или их коммерческое партнёрство.

## 3. Problem

Посетитель может не узнать о сделанных фотографиях или не найти их вовремя, а
фотограф теряет продажу. Персональный Promo полезен только когда свежие снимки
уже загружены и searchable к моменту выхода посетителя. Главная pilot-гипотеза —
можно ли автоматически найти правильные фотографии движущегося человека или
группы с дистанции 3–5 метров и бесшовно продолжить результат на телефоне.

## 4. Current Alternatives

- личный контакт фотографа и ручная продажа;
- общая web-галерея с ручным просмотром множества снимков;
- самостоятельный selfie-search на сайте;
- передача папки или общей ссылки без персонального Promo и сохранённого search
  context.

Все варианты требуют больше инициативы посетителя и хуже используют момент его
выхода из СПА.

## 5. Value Proposition

- Участник сразу видит свои фотографии и продолжает session одним QR scan.
- Фотограф своевременно привлекает внимание потенциального покупателя.
- СПА получает автоматический Promo без полноценного touchscreen kiosk.
- Фотограф и staff могут скрывать ошибочные Photo, восстанавливать их и видеть
  недавнее состояние ingest/processing без отдельной queueing-системы.
- Команда получает correlated diagnostics с явными evidence gaps для настройки
  камеры, pipeline, thresholds, UX и latency.

## 6. Product Concept

Первый pilot проверяет контур:

```text
authenticated independent JPEG upload for selected СПА/date
→ searchable inventory
→ automatic sensor-triggered reference series
→ best-effort face search
→ четыре low-quality preview без watermark
→ QR continuation без повторного selfie
→ phone landing с СПА, датой, teaser и N
```

Обрабатываются до пяти лучших face detections. Group flow поддерживается текущим
алгоритмом: один человек может занять несколько detection slots, а покрытие
каждого уникального участника не гарантируется. `N` — union уникальных
`photo_id`, прошедших calibrated threshold для обработанных detections; четыре
Promo-фотографии являются только teaser.

Post-pilot paid product продаёт весь найденный пакет за одну фиксированную сумму
и выдаёт originals после оплаты.

Photo Inventory Operations используют тот же Photo inventory: role-scoped soft
delete/restore, два глобальных admin actions и прямые recent-statistics queries.

## 7. MVP Scope

- одна выбранная СПА и ограниченная группа тестировщиков;
- 43-inch landscape display, baseline 16:9 / 1920×1080;
- automatic sensor-triggered capture с дистанции 3–5 метров;
- authenticated direct web upload готовых JPEG после выбора СПА и
  authoritative `visit_date`, с независимым результатом для каждого файла и
  без Batch/manifest/confirmation;
- выбор Photo по СПА, authoritative `visit_date` и effective `captured_at`;
  фотограф может soft-delete/restore только собственные uploads, а
  operator/developer — любые Photo в доступной СПА;
- project-wide `restore all soft deleted` и подтверждённый fixed-snapshot
  `hard delete ALL softed media` через общий worker с ожиданием, progress и
  restart-resume; purge блокирует restore snapshot members до завершения, не
  прерывает уже идущий upload и сохраняет Promo sessions, core Attempts и
  diagnostic evidence, а клиенты пропускают отсутствующую media;
- отдельные per-СПА `new`, `unprocessed`, `processed` и `failed` counters за
  1/5/60 минут с polling каждые пять секунд;
- background processing и exact face search в пределах СПА, даты и совместимой
  pipeline revision;
- best-effort group processing до пяти detections без tracking/clustering;
- Promo при наличии четырёх уникальных подходящих фотографий;
- четыре low-quality preview и QR без watermark;
- QR continuation page без нового selfie: СПА, дата, teaser, `N` и post-pilot
  CTA полного пакета;
- core Attempt каждого server-admitted request; подробные protected diagnostic
  evidence присоединяются best-effort, и их отсутствие у существующего server
  Attempt отображается как `incomplete`; client-only offline event может не
  оставить server record;
- developer-only `Attempts`, `Log Explorer` и `Calibration` через backend и
  PostgreSQL, создаваемые в этом проекте;
- failure mode с локальной рекламой, best-effort diagnostic event и коротким
  неблокирующим сообщением при неудачной связи с сервером;
- controlled acceptance run из 20 попыток.

## 8. Non-goals

- публичный rollout на обычных посетителях;
- payment, receipt, refund и фактическая выдача originals;
- продажа отдельных фотографий;
- standalone selfie-search и повторный selfie после QR;
- Яндекс Диск и другие external ingest channels;
- watermark на любых preview;
- гарантия полного покрытия каждого человека в группе;
- production-grade validation по 20 попыткам;
- RAW, identity clustering, ANN, Redis/Celery/Kafka, Kubernetes, GPU-first и
  полноценный kiosk.
- отдельный purge worker, per-photo `purge_pending`, purge jobs table,
  materialized recent counters и WebSocket/SSE для queue statistics.

## 9. Success Metrics

- Минимум 19 из 20 попыток показывают полностью видимый и сканируемый QR менее
  чем за 10 секунд от `reference_series_ready_at`.
- Landing каждой завершённой попытки правильно показывает СПА, `visit_date`,
  доступный teaser и issued `N`; hard-purged media пропускается без invalidation
  session или пересчёта `N`.
- Для каждого server-admitted request создан core Attempt с correlation ID и
  stage timestamps; client-only offline attempt остаётся best-effort, а
  отсутствие подробных evidence видно как `incomplete`.
- Не менее 95% независимо принятых unique JPEG становятся searchable менее чем
  за 15 минут от server-side `photo.accepted_at`.
- Role-scoped soft delete немедленно исключает Photo из новых search/results и
  statistics, но не ломает уже выданную session; restore возвращает сохранённое
  состояние без повторного upload/processing.
- Один подтверждённый global hard purge возобновляет fixed snapshot после
  process restart, запрещает restore его members до завершения, показывает
  completed/total progress и удаляет Photo-owned media/state, сохраняя Promo
  sessions, core Attempts и diagnostic evidence; отсутствующая media
  пропускается клиентами.
- Per-СПА counters за 1/5/60 минут соответствуют принятым определениям и
  обновляются polling каждые пять секунд.

Метрики доказывают работоспособность smoke-pilot.

## 10. Constraints

- Проект находится только на стадии документации и design: working application,
  backend, worker и deployed runtime ещё не существуют.
- один центральный CPU-only сервер в РФ и одна pilot СПА;
- без external cloud face-recognition API;
- capture запускается автоматически, без действия участника;
- только участники pilot и 90-day diagnostics;
- no-watermark policy для всех preview; originals в pilot не выдаются;
- PostgreSQL/MinIO не публикуются наружу, public boundary использует HTTPS;
- поиск ограничен СПА, датой/периодом и совместимой pipeline revision;
- effective `captured_at` использует reliable EXIF в timezone СПА, затем
  server-side start time загрузки конкретного файла, затем 01:00 на
  authoritative `visit_date`;
- `Photo` и её serving-pipeline `pending` state принимаются одной короткой
  PostgreSQL transaction; будущая queue должна переживать restart backend/worker;
- Photo Inventory Operations используют один active/soft-deleted marker,
  один resumable global purge run, общий `BackgroundPhotoWorker` и прямые
  PostgreSQL queries;
- Calibration может выполняться на общем `BackgroundPhotoWorker`, временно
  задерживать ingest и после interruption перезапускается разработчиком вручную;
- архитектура усложняется только после измеримого bottleneck.

## 11. Assumptions

- У каждого тестировщика заранее есть минимум четыре searchable фотографии.
- Фотограф загружает JPEG сразу после законченной съёмочной серии.
- Serving pipeline и reference threshold откалиброваны до acceptance run.
- Конкретные camera, lens, sensor и lighting выбираются после обследования СПА.

## 12. Risks

- group algorithm может повторно выбрать одного человека и пропустить другого;
- motion blur, pose, lighting и размер лица могут сорвать поиск;
- поздний upload лишает Promo актуальных снимков;
- поиск может временно видеть неполный набор фотографий выбранных СПА/date, пока
  фотограф продолжает upload;
- crash между object upload и per-photo DB commit может оставить orphan object
  и потерять admission одной фотографии; повторный upload считается достаточным;
- fallback effective `captured_at` может лишь приблизительно отражать время
  съёмки, что принято ради KISS time-range selection;
- global hard purge может задержать Photo processing на общем worker; uploads
  могут продолжиться и временно увеличить durable backlog;
- Calibration во время debugging может временно ухудшить ingest SLO;
- отсутствие watermark облегчает копирование teaser, хотя low-quality ограничивает
  их коммерческую ценность;
- один сервер и один realtime process создают latency/availability risk;
- необратимая потеря единственного primary disk/server уничтожит persisted data;
  отдельный backup в pilot не создаётся;
- 20 попыток недостаточны для публичного production rollout.

## 13. Open Questions

- Какая СПА и геометрия прохода выбраны для pilot?
- Какие camera, lens, passage sensor и lighting проходят validation?
- Какая field validation обязательна перед запуском на реальных посетителях?
- Кто является экономическим заказчиком post-pilot продукта?
- Какие package threshold, payment, receipt/refund и download rules применяются
  после pilot?

Эти вопросы не блокируют PRD pilot; публичный launch не входит в текущий scope.

## 14. PRD Input Summary

PRD описывает только one-СПА pilot и заканчивается проверенным QR
continuation. Обязательные решения: automatic Promo, authenticated JPEG upload,
четыре no-watermark teaser, continuation без selfie, текущий best-effort group
algorithm, core Attempt для server-admitted request с best-effort offline/
diagnostic evidence, 90-day retention ordinary attempt/evidence и performance
acceptance `19/20 under 10s`.
Developer logging, attempt investigation, manual annotation и explainable
parameter recommendations определены в `IDEA_DEBUG.md` и также являются входом
PRD. Photo Inventory Operations включают role-scoped time-range soft
delete/restore, global restore-all, fixed-snapshot resumable hard purge с
Promo session/Attempt/evidence retention, restore rejection для snapshot members
и per-СПА 1/5/60-minute statistics с five-second polling. Payment и originals
остаются post-pilot context.

## 15. Decision

### Decision

proceed
