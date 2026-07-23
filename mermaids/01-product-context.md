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
        operations["Photo readiness<br/>sanitized attempts"]
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
    developer --> diagnostics
    operations -.->|"наблюдает readiness"| inventory
    diagnostics -.->|"explicit audited apply"| serving
```

## Что важно

- Promo display завлекает, но не является touchscreen kiosk.
- В pilot участник не загружает selfie и не получает original.
- Оператор видит только sanitized attempt summary; protected artifacts и Calibration доступны разработчику.
- Повторные QR scans используют один session-wide browser access context без
  per-device grants.

Источники: [PRD](../.memory-bank/prd.md),
[Architecture](../arch_vision.md), [Product
Brief](../.memory-bank/analysis/product-brief.md),
[Glossary](../.memory-bank/glossary.md).
