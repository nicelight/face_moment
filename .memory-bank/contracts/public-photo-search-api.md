---
description: Публичный поиск, разрешённая галерея и уменьшенные preview bytes.
status: active
last_updated: 2026-10-03
source_of_truth:
  - .memory-bank/contracts/public-photo-search-api.md
---
# Public Photo Search API

## Границы

`promo` организует flow; `processing` владеет query/search/rendering,
`inventory` — active Photo и private original projections, `serving_control` —
venue/model/settings projections. [Профиль](../domains/browser-search-profile.md)
и [FR-PUB / AC-PUB](../prd.md#h-public-selfie-search-and-purchase--accepted-extension-2026-10-03)
задают правила. Promo/QR endpoints и их date scope не меняются.

| Endpoint | Вход → выход |
|---|---|
| `GET /api/public/venues` | Активные площадки: id, name; без Photo/session данных. |
| `POST /api/public/search` | Multipart: JPEG `selfie`, JSON `venue_ids`, optional strict bool `confirm_reset` → outcome; при success result_id, personal_count, venues[{id,name,dates,personal,common}]. Photo item: id,visit_date,preview_url,is_free. |
| `GET /api/public/results/{id}` | Cookie своего профиля, его текущий result → та же галерея. |
| `GET /api/public/results/{id}/previews/{photo_id}` | Membership результата и active доступная Photo → уменьшенный `image/jpeg`; originals не возвращаются. |

`venue_ids` — 1–3 различных существующих active UUID; иначе `422` до inference.
JPEG: MIME/сигнатура, размер <=2 MiB, каждая сторона <=4096 и decoded pixels
<=4096² проверяются до inference. Модель уже warmed в RealtimeFaceService;
запрос использует существующий один slot/deadline, без ожидательной очереди.
Public admission не ожидает занятый Promo slot: возвращает busy; decode/resize
не блокируют event loop. Existing Promo latency/QR regression проверяется вместе
с конкурирующим public запросом, без нового performance target.
`busy|deadline|retake_required|confirmation_required|face_denied|no_matches`
не являются успешной галереей. Technical failures — общие HTTP statuses.

`processing` готовит текущее лицо native adapter и ищет exact cosine только
active совместимые `ready` Photos выбранных площадок по всем visit_date.
До изменения А/Б используется единый quality gate: native confidence >= максимума
`min_query_face_quality` выбранных площадок из immutable admission snapshot.
Native detector settings берутся из общей serving revision; ровно одно лицо
обязательно. Это не новый blur/pose gate. После допуска per-venue similarity
threshold сохраняется; Promo date settings
не применяются. Порог А/Б берётся отдельно. Внутри площадки личные фото
сортируются по visit_date, затем similarity DESC/id; общие — по visit_date/id.
Общие active `no_faces` берутся только за даты её личных совпадений; площадка
без совпадений не раскрывает общие. Общие всегда free; личные free при free venue.

## Browser и media

Камера/IndexedDB/compression/progress: [FT-013 AC-001..003](../features/FT-013.md#acceptance-criteria).
История сохраняет каждый capture, включая retake/отказ/failed search;
на сервер отправляется только текущий снимок после «Найти меня».

Gallery renderer использует private original через `inventory` projection,
ориентацию и JPEG encoding `processing`; возвращает JPEG шириной 640 px,
с сохранением пропорций (маленький source допускает upscale только preview).
Это отдельный on-demand gallery path: существующие derivatives, pHash,
`no_faces` terminal/non-searchable state и исторические строки не меняются.
Работа object IO/decode/encode выполняется вне event loop в ограниченном
исполнителе backend, один render одновременно; при занятости `429` и повтор
клиентом. Raw original, object key и presigned URL наружу не выходят.
Frontend накладывает снимаемый watermark только на личные preview; Promo/QR
изображения не меняются. Удалённая/недоступная Photo → `404` без подстановки.

## Защита и проверка

Edge направляет только `/api/public/search` в RealtimeFaceService; остальные
public routes обслуживает backend. Missing cookie на защищённом API→401, чужой
result/photo→404; search может создать профиль по Browser Search Profile.
Все JSON используют schema_version=1; unknown request fields→422.

Public JSON/media: HTTPS, no-store, no-referrer; cookie/token/selfie/embedding
не входят в logs. POST требует совпадающий Origin, CORS отсутствует.
Configured IP/profile rate limits проверяются до inference; превышение `429`.
Staff настройка Developer-only порога: `GET|PUT /api/serving/public-search-settings`,
JSON `{profile_similarity_threshold}` — finite [-1,1]; существующие staff
session/CSRF обязательны. Другие reference settings эта запись не меняет.

Fixtures: scope 0/4/foreign venues, все даты, no-match, А/Б, corrupted/multiface,
профиль чужого результата, matched-date `no_faces`, historical originals;
decoded preview width>=320 и отсутствие original bytes. Browser проверяет
network до Submit, IndexedDB/quota и watermark. Compression пары проверяют
face count/gate/embedding/matches, не объявляют новую гарантию accuracy.
