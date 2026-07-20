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
        upload["Authenticated JPEG uploader"]
        inventory["Searchable inventory"]
        promo_client["SpaPromoClient<br/>advertising + capture + Promo"]
        search["Exact scoped face search"]
        continuation["QR continuation page"]
        operations["Batch readiness + active visit_date<br/>sanitized attempts"]
        diagnostics["Attempts + Log Explorer + Calibration<br/>developer-only"]
    end

    photographer -->|"создаёт и подтверждает Batch"| upload
    upload --> inventory

    sensor --> promo_client
    camera --> promo_client
    participant -->|"проходит capture-zone без действий"| promo_client
    promo_client -->|"reference series"| search
    inventory --> search
    search -->|"4 teasers + QR session"| promo_client

    participant -->|"сканирует QR"| phone
    phone --> continuation
    continuation -->|"Перейти к покупке или expired redirect"| future

    operator --> operations
    developer --> diagnostics
    operations --> inventory
    diagnostics -.->|"коррелированное расследование и ручные настройки"| search
```

## Что важно

- Promo display завлекает, но не является touchscreen kiosk.
- В pilot участник не загружает selfie и не получает original.
- Оператор видит только sanitized attempt summary; protected artifacts и Calibration доступны разработчику.

Источники: [Product Brief](../.memory-bank/analysis/product-brief.md), [PRD](../.memory-bank/prd.md), [Glossary](../.memory-bank/glossary.md).
