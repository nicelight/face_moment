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
  - `IDEA_APP.md`
  - `IDEA_INGEST.md`
  - `IDEA_OS.md`

## 1. One-liner

Face Moment автоматически находит профессиональные фотографии заранее
согласившихся участников закрытого SPA-pilot, показывает четыре персональных
teaser на Promo display и переносит найденную session на телефон по QR без
повторного selfie.

## 2. Target Users

- Участник pilot — заранее информированный и согласившийся тестировщик.
- Фотограф — загружает свежие готовые JPEG и получает новый канал контакта с
  потенциальным покупателем.
- Оператор Face Moment/SPA — контролирует batches, searchable readiness, Promo и
  диагностику.
- После pilot: посетитель SPA как покупатель полного пакета фотографий.

Экономический заказчик будущего продукта пока является гипотезой: SPA, фотограф
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
выхода из SPA.

## 5. Value Proposition

- Участник сразу видит свои фотографии и продолжает session одним QR scan.
- Фотограф своевременно привлекает внимание потенциального покупателя.
- SPA получает автоматический Promo без полноценного touchscreen kiosk.
- Команда получает воспроизводимые diagnostics для настройки камеры, pipeline,
  thresholds, UX и latency.

## 6. Product Concept

Первый pilot проверяет контур:

```text
authenticated JPEG batch upload
→ searchable inventory
→ automatic sensor-triggered reference series
→ best-effort face search
→ четыре low-quality preview без watermark
→ QR continuation без повторного selfie
→ phone landing с SPA, датой, teaser и N
```

Обрабатываются до пяти лучших face detections. Group flow поддерживается текущим
алгоритмом: один человек может занять несколько detection slots, а покрытие
каждого уникального участника не гарантируется. `N` — union уникальных
`photo_id`, прошедших calibrated threshold для обработанных detections; четыре
Promo-фотографии являются только teaser.

Post-pilot paid product продаёт весь найденный пакет за одну фиксированную сумму
и выдаёт originals после оплаты.

## 7. MVP Scope

- одна выбранная SPA и закрытая группа consented testers;
- 43-inch landscape display, baseline 16:9 / 1920×1080;
- automatic sensor-triggered capture с дистанции 3–5 метров;
- authenticated direct web upload готовых JPEG с подтверждением SPA,
  authoritative `visit_date` и batch manifest;
- background processing и exact face search в пределах SPA, даты и совместимой
  pipeline revision;
- best-effort group processing до пяти detections без tracking/clustering;
- Promo при наличии четырёх уникальных подходящих фотографий;
- четыре low-quality preview и QR без watermark;
- QR continuation page без нового selfie: SPA, дата, teaser, `N` и post-pilot
  CTA полного пакета;
- private diagnostic bundle каждой попытки с retention 90 дней;
- failure mode с локальной рекламой и diagnostic event;
- controlled acceptance run из 20 попыток.

## 8. Non-goals

- публичный rollout на обычных посетителях;
- payment, receipt, refund и фактическая выдача originals;
- продажа отдельных фотографий;
- standalone selfie-search и повторный selfie после QR;
- Яндекс Диск и другие external ingest channels;
- watermark на любых preview;
- гарантия полного покрытия каждого человека в группе;
- доказательство production FAR/recall по 20 попыткам;
- RAW, identity clustering, ANN, Redis/Celery/Kafka, Kubernetes, GPU-first и
  полноценный kiosk.

## 9. Success Metrics

- Ни одна из 20 попыток не показывает вручную подтверждённую фотографию
  постороннего человека на Promo.
- Минимум 19 из 20 ожидаемо успешных попыток показывают полностью видимый и
  сканируемый QR менее чем за 10 секунд от `reference_series_ready_at`.
- Landing каждой успешной попытки правильно показывает SPA, `visit_date`, teaser
  и `N`.
- Для каждой попытки, включая timeout/no-match/incorrect, создан diagnostic
  bundle.
- Не менее 95% JPEG подтверждённых batches становятся searchable менее чем за
  15 минут от `batch.confirmed_at`; задержка фотографа до подтверждения измеряется
  отдельно.

Метрики доказывают smoke-pilot работоспособность, но не production safety.
Для group attempt посторонней считается фотография без корректного match хотя бы
с одним участником текущей reference-сцены; другие люди на том же коммерческом
кадре не делают его ошибочным автоматически.

## 10. Constraints

- один центральный CPU-only сервер в РФ и одна pilot SPA;
- без external cloud face-recognition API;
- capture запускается автоматически, без действия участника;
- только pre-consented testers и 90-day private diagnostics;
- no-watermark policy для всех preview; originals в pilot не выдаются;
- PostgreSQL/MinIO не публикуются наружу, public boundary использует HTTPS;
- поиск ограничен SPA, датой/периодом и совместимой pipeline revision;
- архитектура усложняется только после измеримого bottleneck.

## 11. Assumptions

- У каждого тестировщика заранее есть минимум четыре searchable фотографии.
- Фотограф загружает JPEG сразу после законченной съёмочной серии.
- Serving pipeline и reference threshold откалиброваны до acceptance run.
- Consent на automatic capture, Promo и diagnostics фиксируется до участия.
- Diagnostic bundles доступны только назначенным операторам.
- Конкретные camera, lens, sensor и lighting выбираются после обследования SPA.

## 12. Risks

- false match может показать чужую фотографию;
- group algorithm может повторно выбрать одного человека и пропустить другого;
- motion blur, pose, lighting и размер лица могут сорвать поиск;
- поздний upload лишает Promo актуальных снимков;
- diagnostic bundles содержат чувствительные biometric-like данные;
- отсутствие watermark облегчает копирование teaser, хотя low-quality ограничивает
  их коммерческую ценность;
- один сервер и один realtime process создают latency/availability risk;
- 20 попыток недостаточны для публичного production rollout.

## 13. Open Questions

- Какая SPA и геометрия прохода выбраны для pilot?
- Какие camera, lens, passage sensor и lighting проходят validation?
- Как фиксируются consent, его отзыв и досрочное удаление diagnostics?
- Кто имеет доступ к diagnostics и какой audit trail обязателен?
- Какие final QR/browser TTL и expired-session UX используются?
- Какая field validation обязательна перед запуском на реальных посетителях?
- Кто является экономическим заказчиком post-pilot продукта?
- Какие package threshold, payment, receipt/refund и download rules применяются
  после pilot?

Эти вопросы не блокируют PRD закрытого pilot, но соответствующие privacy и field
validation решения блокируют публичный launch.

## 14. PRD Input Summary

PRD описывает только закрытый one-SPA pilot и заканчивается проверенным QR
continuation. Обязательные решения: automatic Promo, authenticated JPEG upload,
четыре no-watermark teaser, continuation без selfie, текущий best-effort group
algorithm, 90-day diagnostics и acceptance `19/20 under 10s` при нуле чужих
фотографий. Payment и originals остаются post-pilot context.

## 15. Decision

### Decision

proceed
