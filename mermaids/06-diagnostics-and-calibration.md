# 6. Diagnostics and calibration

Developer-only контур превращает одну проблемную attempt в объяснимое расследование и ручное решение по параметрам.

```mermaid
flowchart LR
    browser["Browser events:<br/>trigger, request, response,<br/>Promo render, QR visible"]
    server["Server stages:<br/>queue, inference, vector search,<br/>candidate pools, response"]
    config["Applied context:<br/>release, pipeline revision,<br/>threshold, quality gates"]
    artifacts["Protected artifacts:<br/>reference frames, crops,<br/>normalized images, Promo screenshot"]

    attempt["Attempt<br/>единый correlation ID<br/>stage timestamps + outcome + issue tags"]
    logs[("Structured logs в PostgreSQL<br/>без images, embeddings, secrets,<br/>request bodies и session replay")]
    bundle[("Diagnostic bundle в private storage<br/>manifest + authorized artifact links")]

    operator["Оператор"]
    developer["Разработчик"]
    sanitized["Sanitized view:<br/>outcome + timeline + latency + issue tags"]
    detail["Full attempt detail:<br/>detections, repeated detections,<br/>matches, pools, teasers, N"]
    annotation["Manual ground truth:<br/>participant name + correct / wrong / missed"]
    calibration["Calibration"]

    profiles["Threshold profiles:<br/>Best face match<br/>Balance<br/>Minimum missed faces"]
    gates["Одномерные quality-gate proposals:<br/>face size, confidence, blur,<br/>brightness, yaw/pitch/roll"]
    manual["Разработчик вручную применяет<br/>выбранное serving setting"]

    browser --> attempt
    server --> attempt
    config --> attempt
    browser --> logs
    server --> logs
    artifacts --> bundle
    attempt --> logs
    attempt --> bundle

    operator --> sanitized
    attempt --> sanitized

    developer --> detail
    attempt --> detail
    logs --> detail
    bundle --> detail
    detail --> annotation --> calibration
    calibration --> profiles --> manual
    calibration --> gates --> manual

    retention["Retention:<br/>technical logs — 30 дней<br/>ordinary attempts/bundles — 90 дней<br/>promoted curated case — до удаления"]
    logs -.-> retention
    bundle -.-> retention

    prohibition["Никогда не применять recommendation автоматически"]
    prohibition -.-> calibration
    prohibition -.-> manual
```

## Как пользоваться

1. Найти slow/failed/suspicious attempt по времени, status, release, pipeline, latency или issue tags.
2. Локализовать задержку по единому browser/server timeline.
3. Проверить фактические detections, candidate pools, teasers, `N`, версии и параметры.
4. Добавить ground truth и открыть вклад в threshold или отдельный quality gate.
5. Сравнить release/config sets и вручную применить выбранное изменение.

Источники: [IDEA_DEBUG.md](../IDEA_DEBUG.md), [PRD](../.memory-bank/prd.md), [Glossary](../.memory-bank/glossary.md).
