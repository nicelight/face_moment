# 1. Product context and roles

Диаграмма показывает участников, текущую границу one-СПА pilot и отдельную post-pilot зависимость.

```mermaid
flowchart LR
    photographer["Фотограф"]
    participant["Участник pilot"]
    operator["Оператор Face Moment / СПА"]
    developer["Разработчик приложения"]
    sensor["Датчик прохода"]
    camera["Камера"]
    phone["Телефон участника"]
    future["Main selfie-search / purchase page<br/>отдельная post-pilot зависимость"]

    subgraph fm["Face Moment — текущий one-СПА pilot"]
        upload["Independent JPEG upload<br/>selected СПА + visit_date"]
        inventory["Searchable inventory"]
        serving["Serving control<br/>active visit_date + settings"]
        promo_client["SpaPromoClient<br/>advertising + local face proposals + Promo"]
        search["processing:<br/>server-authoritative selection +<br/>exact scoped face search"]
        promo["promo:<br/>core Attempt + result assembly +<br/>Promo/search session"]
        continuation["Session-wide QR continuation"]
        operations["Photo Inventory Operations<br/>soft delete / restore / global purge<br/>per-СПА 1/5/60-minute counters"]
        attempt_view["Sanitized Attempts<br/>operator role-scoped"]
        diagnostics["Developer-only protected detail:<br/>names + annotations + logs + Calibration"]
    end

    photographer -->|"выбирает СПА/date<br/>независимо загружает JPEG"| upload
    upload -->|"accepted Photo → pending → ready"| inventory

    promo_client -->|"authenticated 10 s HTTP long-poll<br/>fixed mDNS .local"| sensor
    sensor -->|"event response"| promo_client
    camera --> promo_client
    participant -->|"проходит capture-zone без действий"| promo_client
    promo_client -->|"Bearer-authenticated bounded request:<br/>первые ≤20 chronological occurrence crops + metadata<br/>zero → manifest only<br/>без full frames / local ranking / top-5"| promo
    inventory --> search
    serving --> search
    promo -->|"typed direct call"| search
    search -->|"ordered threshold-valid match sets"| promo
    promo -->|"4 media references + QR URL"| promo_client

    participant -->|"сканирует QR"| phone
    phone --> continuation
    continuation -->|"Перейти к покупке или expired redirect"| future

    operator --> operations
    operator --> serving
    operator --> attempt_view
    photographer -->|"только собственные Photos"| operations
    developer --> diagnostics
    developer --> operations
    operations -.->|"active/soft-deleted visibility<br/>shared-worker hard purge"| inventory
    diagnostics -.->|"explicit audited apply"| serving
```

## Что важно

- Promo display завлекает, но не является touchscreen kiosk.
- В pilot участник не загружает selfie и не получает original.
- Операторский Attempts view содержит только sanitized summary. Participant
  names, manual annotations, detailed logs, Calibration и protected non-media
  доступны разработчику; capture-derived media не становится developer-only
  только из-за image content.
- Фотограф soft-delete/restore только свои uploads; оператор/разработчик могут
  действовать в доступных СПА, а global restore/purge охватывает весь проект.
- Soft-deleted Photo отсутствует в новых search/results/statistics, но уже
  выданная session продолжает использовать media. Hard purge сохраняет session,
  core Attempt и diagnostic evidence; отсутствующая media пропускается.
- Повторные QR scans используют один session-wide browser access context без
  per-device grants.

Источники: [PRD](../.memory-bank/prd.md),
[Features](../.memory-bank/features/index.md),
[Architecture](../.memory-bank/architecture/system-architecture.md),
[Boundary map](../.memory-bank/contracts/boundary-map.md),
[Lifecycle](../.memory-bank/states/lifecycle-map.md),
[Glossary](../.memory-bank/glossary.md).
