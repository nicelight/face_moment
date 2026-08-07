# 6. Diagnostics and calibration

Для server-admitted request core Attempt сохраняет обязательный outcome и
timeline; protected diagnostic data/actions остаются developer-only, а
capture-derived media не получает этот статус только из-за image content.
Операторский Attempts view остаётся sanitized. Client-only offline event может
не оставить server record.

```mermaid
flowchart LR
    browser["Client-local markers:<br/>processing start, request-send start,<br/>response received<br/>+ Promo/QR stages"]
    server["Server stages:<br/>accepted, inference, vector search,<br/>candidate pools, response"]
    config["Applied context:<br/>release, pipeline revision,<br/>threshold, quality gates"]
    artifacts["Optional diagnostic media:<br/>received crops / normalized images<br/>+ Promo evidence"]

    attempt["Server-admitted core Attempt до inference<br/>client-generated attempt_id<br/>processing + display outcome"]
    offline["Client-only offline event<br/>best-effort; server record может отсутствовать"]
    logs[("Structured logs в PostgreSQL<br/>без embeddings, credentials/tokens,<br/>names, commercial originals,<br/>personalized data и session replay")]
    evidence[("Best-effort diagnostic evidence<br/>events + data-class-aware links")]
    evidence_state["collecting → complete | incomplete → expired"]

    operator["Оператор"]
    developer["Разработчик"]
    sanitized["Sanitized view:<br/>outcome + timeline + latency + issue tags"]
    detail["Developer detail:<br/>detections, decisions, logs,<br/>annotations, Calibration"]
    annotation["Manual ground truth:<br/>participant name + correct / wrong / missed"]
    calibration["Calibration"]
    evaluation["Offline evaluation:<br/>SFace ↔ Buffalo M<br/>annotated curated cases"]

    profiles["Threshold profiles:<br/>Best face match<br/>Balance<br/>Minimum missed faces"]
    gates["Одномерные quality-gate proposals:<br/>face size, confidence, blur,<br/>brightness, yaw/pitch/roll"]
    worker["Shared BackgroundPhotoWorker<br/>Calibration может задержать Photo processing"]
    interrupted["Worker restart:<br/>Calibration = failed | interrupted<br/>Photo processing возобновляется"]
    manual["Explicit audited call<br/>через serving_control"]

    browser --> attempt
    server --> attempt
    config --> attempt
    offline -. "если доставлен" .-> logs
    offline -. "если доставлен" .-> evidence
    browser --> logs
    server --> logs
    artifacts --> evidence
    attempt --> logs
    attempt --> evidence
    evidence --> evidence_state

    operator --> sanitized
    attempt --> sanitized

    developer --> detail
    attempt --> detail
    logs --> detail
    evidence --> detail
    detail --> annotation --> calibration
    calibration --> worker --> evaluation
    evaluation --> profiles --> manual
    evaluation --> gates --> manual
    worker -. "restart" .-> interrupted
    developer -. "manual rerun" .-> calibration

    retention["Retention:<br/>technical logs — 30 дней<br/>ordinary attempts/evidence — 90 дней<br/>promoted curated case — до удаления"]
    logs -.-> retention
    attempt -.-> retention
    evidence -.-> retention

    cleanup["Owner-ordered cleanup:<br/>promo orchestrates latest result;<br/>каждый capability удаляет только свои данные"]
    cleanup -.-> retention

    prohibition["Никогда не применять recommendation автоматически"]
    prohibition -.-> calibration
    prohibition -.-> manual

    hard_purge["Photo hard purge:<br/>media + face/pipeline удалены"]
    preserved["Promo session + core Attempt + diagnostic evidence<br/>сохраняются; client skips missing media"]
    hard_purge -.-> preserved
    attempt --> preserved
    evidence --> preserved
```

## Как пользоваться

1. Найти slow/failed/suspicious attempt по времени, status, release, pipeline, latency или issue tags.
2. Локализовать задержку по единому browser/server timeline.
3. Проверить фактические detections, candidate pools, teasers, `N`, версии и параметры.
4. Добавить ground truth и открыть вклад в threshold или отдельный quality gate.
5. Сравнить release/config sets и вручную применить выбранное изменение.

Detailed evidence не является prerequisite participant flow. Для существующего
server Attempt отсутствующий или незавершённый evidence set отображается как
`incomplete`; client-only offline event может полностью отсутствовать на
сервере. Capture-derived media может логироваться, кэшироваться, храниться или
отдаваться без developer-only media authorization, но ни один такой механизм
не обязателен. Reference-frame upload и proof local-detector misses не требуются.
Отдельный diagnostic anchor, priority scheduler и отдельный Calibration worker
не создаются.
Photo hard purge не каскадирует в Promo session, core Attempt или diagnostic
evidence; missing media пропускается при UI/device loading.

Источники: [Architecture](../.memory-bank/architecture/system-architecture.md),
[Boundary map](../.memory-bank/contracts/boundary-map.md),
[Lifecycle](../.memory-bank/states/lifecycle-map.md),
[FT-007](../.memory-bank/features/FT-007.md),
[FT-008](../.memory-bank/features/FT-008.md),
[FT-009](../.memory-bank/features/FT-009.md),
[FT-010](../.memory-bank/features/FT-010.md),
[FT-011](../.memory-bank/features/FT-011.md),
[Calibration verification](../.memory-bank/testing/calibration.md).
