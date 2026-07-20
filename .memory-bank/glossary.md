---
description: Канонический словарь терминов со специальным значением в Face Moment.
status: active
last_updated: 2026-07-20
---
# Glossary


## Scope And Roles

| Термин | Значение в Face Moment | Не путать с |
|---|---|---|
| `СПА` | Каноническое русское обозначение физической СПА-площадки/venue, к которой привязаны фотографии, client token, рабочая дата, serving pipeline и search scope. | Англоязычной аббревиатурой `single-page application`. `one-СПА pilot` означает одну площадку, а не один frontend. |
| `one-СПА pilot` | Контролируемый smoke pilot на одной СПА-площадке и группе тестировщиков. Он заканчивается проверенной QR continuation page. | Target capacity на 10–15 СПА, публичным rollout, payment или выдачей originals. |
| `Promo display` / `display mode` | Экран с локальной рекламой между попытками, автоматическим capture и успешным Promo из четырёх teasers и QR. | Полноценным kiosk: на экране нет touch-навигации, оплаты или скачивания. |
| `SpaPromoClient` | Логический browser client одной СПА: ведёт camera ring buffer, принимает sensor trigger, формирует reference series, вызывает realtime search и управляет display states. Локальный HDMI и remote computer реализуют один contract. | Backend, `RealtimeFaceService` или самой СПА-площадкой. |
| `Face Moment / СПА operator` | Роль, которая управляет рабочей датой и операционным состоянием и видит только sanitized attempt summary: outcome, timeline, latency и issue tags. | `Application developer`, которому доступны protected artifacts, имена, annotations, detailed logs и Calibration. |
| `Application developer` | Единственная product role с полным доступом к protected diagnostic artifacts, participant names в annotations, detailed logs, Log Explorer и Calibration; serving-setting changes применяет вручную. | OS user `facemoment` или оператором с sanitized-доступом. |
| `facemoment` / `display` | Два OS users центрального сервера: `facemoment` администрирует SSH, `sudo` и Docker; `display` автоматически запускает sandboxed Chromium без административных прав. | Product roles оператора и участника pilot. |

## Ingest And Search Inventory

| Термин | Значение в Face Moment | Не путать с |
|---|---|---|
| `Photo` / коммерческая фотография | Готовый JPEG фотографа для поиска и будущей продажи. Логическая ingest-уникальность задаётся `(spa_id, visit_date, checksum_sha256)`. | Reference frame, face crop, Promo screenshot или другим diagnostic artifact. |
| Original / preview | Original — приватный полноразмерный JPEG фотографа; preview — производное low-quality изображение без watermark для Promo/phone landing. В pilot original не выдаётся участнику. | Diagnostic image или teaser selection: teaser ссылается на выбранный preview, а не задаёт новый тип файла. |
| `Batch` | Контейнер ingest для готовых коммерческих JPEG одной СПА и одной подтверждённой рабочей даты; после confirmation его manifest и `confirmed_at` неизменяемы. В один день допустимо несколько batches. | `Reference series`, которая снимается display client во время попытки поиска. |
| Confirmed batch manifest | Зафиксированный при confirmation список принятых уникальных JPEG. Pre-confirmation rejects и checksum duplicates в него не входят. | Предварительным списком upload-файлов до validation и confirmation. |
| `visit_date` | Подтверждённая business date коммерческих фотографий и authoritative дневной scope поиска. | EXIF `captured_at`, upload time, client clock или именем файла. |
| Active working `visit_date` | Выбранная оператором server-side дата, которую используют автоматические attempts данной СПА, пока оператор её не изменит. | Автоматически выбранной датой последнего batch или значением из request body `SpaPromoClient`. |
| `captured_at` | Вторичное время съёмки из EXIF для сортировки, diagnostics и, при подтверждённых clock/timezone, дополнительного time window. | Authoritative `visit_date`; `captured_at` не может молча её заменить. |
| `pipeline_code` | Тип face pipeline, сейчас `opencv_sface` или `insightface_buffalo_m`. Threshold хранится на уровне СПА, `pipeline_code` и `query_source`. | `pipeline_revision_id`. |
| `query_source` | Происхождение query face: `reference` для display camera или `selfie` для post-pilot selfie flow. Pilot-serving требует калибровки `reference`. | Источником commercial photos или ingest channel. |
| Pipeline revision | Неизменяемая compatibility identity detector, recognizer, весов, preprocessing/alignment, normalization и embedding dimension. Embeddings сравниваются только внутри одной revision. | Названием/типом модели (`pipeline_code`) или изменяемым serving choice СПА. |
| Serving pipeline | Одна выбранная и pre-warmed pipeline revision, которая обслуживает participant-facing поиск данной СПА. | Benchmark-сравнением двух pipelines или multi-model ensemble. |
| Photo pipeline state | Состояние пары photo + pipeline revision: `pending`, `processing`, `ready`, `no_faces` или `failed`. `ready` означает наличие searchable face records; `no_faces` — успешное завершение обработки без лиц. | Общим состоянием batch или background job. |
| `searchable` | Фото доступно exact search через `ready` state совместимой serving revision. Для успеха `ingest_to_searchable` также должен быть готов preview. | Terminal `no_faces`: он завершает processing, но не делает JPEG searchable и остаётся SLO breach. |
| `Photo face` | Одно лицо, обнаруженное конкретной pipeline revision на конкретной коммерческой фотографии. Результаты разных pipelines являются независимыми records. | Person identity или связью одного физического человека между кадрами/pipelines. |
| pHash diversity | Ранжирование уже threshold-valid фотографий по Hamming distance perceptual hashes для визуально разнообразного Promo. | SHA-256 ingest uniqueness или face-match gate; pHash не допускает слабый match в результат. |
| Face-match threshold | Calibrated нижняя граница cosine similarity для комбинации СПА + `pipeline_code` + `query_source`; она не привязана к отдельной revision. | Query-face quality gate, pHash diversity или top-1/top-2 margin. |
| Quality gate | Проверка пригодности query detection по face size, detection confidence, blur, brightness или pose. В Calibration каждый gate анализируется отдельно. | Face-match threshold либо совместной многомерной оптимизацией всех параметров. |

## Capture, Matching And Promo Result

| Термин | Значение в Face Moment | Не путать с |
|---|---|---|
| Reference series | Sensor-triggered набор кадров из постоянного video stream и ring buffer в настроенном pre/post-trigger окне. Из него выбираются query detections. | Photographer `Batch` или standalone selfie; selfie в текущем pilot не снимается. |
| Selected detection | Каноническое название одной quality-ranked face occurrence из reference series, независимо запускающей поиск. В discovery docs также встречаются `query detection`, `reference detection` и `face candidate`; всего выбирается не более пяти. | Уникальным физическим человеком: один человек может дать несколько selected detections. |
| Best-effort group search | Обработка до пяти selected detections без tracking, identity clustering и cross-frame person deduplication. Результат может содержать нескольких людей, но полное покрытие группы не гарантируется. | Обещанием отдельного slot для каждого участника. |
| Promo candidate pools | `matched_candidates` — threshold-valid scoped matches текущей detection с готовым preview; `diverse_candidates` — глобально предпочтённые по pHash diversity; `fallback_candidates` — threshold-valid резерв; `reserved_photo_ids` не допускает повтор одной фотографии при обработке следующих detections. | `session_result_photo_ids`: candidate pools выбирают четыре teasers, а session result хранит полный unique union matches. |
| Teaser | Одна из ровно четырёх уникальных low-quality фотографий без watermark, выбранных для успешного Promo. | Всем найденным пакетом или original. |
| `session_result_photo_ids` | Union всех уникальных `photo_id`, прошедших обычный calibrated threshold хотя бы для одной processed selected detection. | Четырьмя teaser IDs; teaser IDs являются подмножеством этого union. |
| `N` | Cardinality `session_result_photo_ids`, показанная на phone landing. | Числом teasers: успешный Promo всегда содержит четыре teasers, а `N` может быть больше четырёх. |
| `prePromo` | Неперсональное заранее подготовленное видео, показываемое во время capture/search; оно не использует reference frames или текущие search results. | Успешным `Promo`. |
| `Promo` | Успешное display state/result с ровно четырьмя valid unique teasers и полностью видимым QR. Partial result не является Promo. | Входной `prePromo`, локальной рекламой между попытками или phone landing. |
| `preChime` / `Chime` | Необязательные audio asset types: тихий `preChime` сопровождает начало `prePromo`, а `Chime` — только успешный переход к `Promo`. | Success gate: отсутствие audio asset не должно блокировать QR result. |

## Sessions, Attempts And Timers

| Термин | Значение в Face Moment | Не путать с |
|---|---|---|
| Promo/search session | Короткоживущий персональный context, связывающий СПА, authoritative `visit_date`, четыре teaser IDs, `session_result_photo_ids`, `N`, QR token и expiry state. | `Attempt`, browser session или diagnostic bundle. |
| QR continuation | Открытие на телефоне той же Promo/search session без повторного selfie и без переноса истёкших персональных данных. | Новым standalone selfie search. |
| Attempt | Одна принятая автоматическая capture/search/display execution со stage timestamps и outcome, включая unsuccessful outcome. Игнорируемый sensor event во время занятого состояния не создаёт новую attempt. | Только successful Promo или QR session. |
| `RESULT_DISPLAY_SECONDS` / result display duration | Время показа успешного Promo на display; после него экран возвращается к рекламе. | QR lifetime: завершение показа не инвалидирует QR session. |
| `CAPTURE_COOLDOWN_SECONDS` / successful-capture cooldown | Период запрета нового capture, который начинается только после фактического показа успешного Promo. | Capture/search lock и failure path: при неуспехе свежий capture разрешается сразу после завершения обработки. |
| `QR_SESSION_TTL_SECONDS` / QR first-open TTL | Окно первого открытия QR: 30 минут от `qr_issued_at`. | Browser idle TTL после успешного первого открытия. |
| `BROWSER_SESSION_IDLE_TTL_SECONDS` / browser session idle TTL | 60 минут без активности уже открытой phone session. | Result display duration или QR first-open TTL. |

## Diagnostics And Calibration

| Термин | Значение в Face Moment | Не путать с |
|---|---|---|
| `diagnostic_session_id` / `correlation_id` | Один логический correlation identifier попытки, связывающий browser events, server stages, configuration, search decisions, logs и artifacts. Точное имя поля может быть унифицировано в SDD. | Promo/search session token или participant identity. |
| Diagnostic bundle | Защищённые image artifacts попытки плюс versioned manifest, indexed events, decisions, configuration, timestamps и evidence фактически показанного Promo/QR. Ordinary bundle хранится 90 дней. | Structured logs: изображения и крупные/sensitive payloads в log records запрещены. |
| Structured log record | Неблокирующее browser/server событие, связанное с correlation ID там, где это применимо. Technical logs хранятся 30 дней и не содержат images, embeddings, auth headers, cookies, tokens, request bodies или session replay. | Diagnostic artifact или долговременный calibration dataset. |
| `Attempts` | Role-scoped UI для поиска попыток и investigation по attempt-level timeline, parameters, decisions, logs и artifacts; operator получает sanitized subset, developer — полный разрешённый detail. | `Log Explorer`, который ищет отдельные log records глобально. |
| `Log Explorer` | Developer-only UI глобального поиска structured browser/server logs через backend/PostgreSQL с переходом к связанной attempt. | Прямым browser-доступом к PostgreSQL или отдельным observability datastore. |
| Annotation | Developer-only ground truth на уровне person/detection с разрешённым именем pilot participant и outcome `correct`, `wrong/false` или `missed`. Exact normalized storage vocabulary остаётся за SDD. | Автоматическим identity cluster или общей записью имени в technical logs. |
| Promoted calibration case | Вручную выбранный воспроизводимый subset attempt: нужные source frames/crops, фактически снятый selfie при его наличии, versions/parameters, scores и annotations. Хранится до явного удаления. | Продлением retention всего diagnostic bundle: прочая reference series, Promo screenshot и technical logs удаляются по обычным срокам. |
| `Calibration` | Developer-only UI, использующий annotated attempts для сравнения pipelines/releases/config sets и расчёта объяснимых recommendations. | Автоматическим изменением serving settings или отдельной experimentation platform. |
| Calibration recommendation | Объяснимое предложение threshold или одного quality gate, рассчитанное по annotated attempts. Оно никогда не меняет serving settings автоматически. | Автоматическим optimizer или совместным подбором нескольких quality gates. |
| `Best face match` | Threshold profile, минимизирующий false matches; при равенстве предпочитает больше correct matches. | `Balance` или `Minimum missed faces`. |
| `Balance` | Threshold profile компромисса между correct, false и missed. Точная формула намеренно остаётся решением SDD. | Уже утверждённой численной формулой. |
| `Minimum missed faces` | Threshold profile, минимизирующий missed results; при равенстве предпочитает меньше false matches. | Гарантией полного group coverage. |

## Metrics And Time Anchors

| Термин | Значение в Face Moment | Не путать с |
|---|---|---|
| `reference_series_ready_at` | Момент, когда sensor-triggered reference series уже сформирована и готова к realtime processing. | `sensor_triggered_at`; задержка capture до готовности не входит в основной `<10 s` acceptance interval. |
| `qr_fully_visible_at` | Момент, когда QR полностью отрисован на display и готов к сканированию. | Временем server response или началом Promo transition. |
| `reference_ready_to_qr` | `qr_fully_visible_at - reference_series_ready_at`; основной realtime acceptance interval pilot. Gate: `<10_000 ms` минимум в 19 из 20 controlled attempts. | `trigger_to_preview`, который остаётся end-to-end diagnostic metric. |
| `ingest_to_searchable` | Для каждого unique accepted JPEG confirmed manifest: от `batch.confirmed_at` до готового preview и `ready` state serving revision. `pending`, `processing`, `failed` и `no_faces` после 15 минут остаются breaches; rejects, duplicates и non-serving jobs исключены. | Задержкой фотографа от съёмки до confirmation. |

## Source Basis

- [.memory-bank/prd.md](prd.md): authoritative pilot vocabulary and resolved
  semantics.
- [.memory-bank/analysis/product-brief.md](analysis/product-brief.md): accepted
  pilot scope and actor/value framing.
- [IDEA_APP.md](../IDEA_APP.md): application, face-search, Promo/session and
  pipeline terminology.
- [IDEA_DEBUG.md](../IDEA_DEBUG.md): attempts, logs, annotations and Calibration
  terminology.
- [IDEA_INGEST.md](../IDEA_INGEST.md): batch, `visit_date`, manifest and
  searchable metric semantics.
- [IDEA_OS.md](../IDEA_OS.md): display topology, OS-user boundary and deployment
  terminology.

## Usage Notes

- В новых документах использовать `selected detection`, когда речь идёт о
  выбранном face occurrence, и не заменять его словом «человек».
- Всегда уточнять, идёт ли речь о четырёх teaser IDs или о полном
  `session_result_photo_ids`/`N`.
- Не использовать `batch`, `reference series`, `attempt`, Promo/search session,
  browser session и diagnostic bundle как взаимозаменяемые понятия.
- В человекочитаемом тексте использовать `СПА`. Машинные identifiers, включая
  `spa_id`, `spa_client_token` и `SpaPromoClient`, сохраняют ASCII-написание.
