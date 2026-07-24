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
        promo_client["SpaPromoClient<br/>advertising + capture + Promo"]
        search["Exact scoped face search"]
        continuation["Session-wide QR continuation"]
        operations["Photo Inventory Operations<br/>soft delete / restore / global purge<br/>per-СПА 1/5/60-minute counters"]
        attempt_view["Sanitized attempts"]
        diagnostics["Attempts + Log Explorer + Calibration<br/>developer-only"]
    end

    photographer -->|"выбирает СПА/date<br/>независимо загружает JPEG"| upload
    upload -->|"accepted Photo → pending → ready"| inventory

    sensor --> promo_client
    camera --> promo_client
    participant -->|"проходит capture-zone без действий"| promo_client
    promo_client -->|"reference series"| search
    inventory --> search
    serving --> search
    search -->|"4 teasers + QR session"| promo_client

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
- Оператор видит только sanitized attempt summary; protected artifacts и Calibration доступны разработчику.
- Фотограф soft-delete/restore только свои uploads; оператор/разработчик могут
  действовать в доступных СПА, а global restore/purge охватывает весь проект.
- Soft-deleted Photo отсутствует в новых search/results/statistics, но уже
  выданная session продолжает использовать media. Hard purge сохраняет session,
  core Attempt и diagnostic evidence; отсутствующая media пропускается.
- Повторные QR scans используют один session-wide browser access context без
  per-device grants.

Источники: [PRD](../.memory-bank/prd.md),
[Architecture](../arch_vision.md), [Product
Brief](../.memory-bank/analysis/product-brief.md),
[Glossary](../.memory-bank/glossary.md).
