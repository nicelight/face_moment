# 6. Diagnostics and calibration

Для server-admitted request core Attempt сохраняет обязательный outcome и
timeline; protected evidence, annotation и Calibration образуют отдельный
developer-only контур, а оператор получает только sanitized view. Client-only
offline event может не оставить server record.

```mermaid
flowchart LR
    browser["Server-admitted browser stages:<br/>reference ready, request, response,<br/>Promo render, display acknowledgement"]
    server["Server stages:<br/>accepted, inference, vector search,<br/>candidate pools, response"]
    config["Applied context:<br/>release, pipeline revision,<br/>threshold, quality gates"]
    artifacts["Optional protected artifacts:<br/>selected frames/crops,<br/>normalized images, Promo screenshot"]

    attempt["Server-admitted core Attempt до inference<br/>client-generated attempt_id<br/>processing + display outcome"]
    offline["Client-only offline event<br/>best-effort; server record может отсутствовать"]
    logs[("Structured logs в PostgreSQL<br/>без images, embeddings, secrets,<br/>request bodies и session replay")]
    evidence[("Best-effort diagnostic evidence<br/>events + authorized artifact links")]
    evidence_state["collecting → complete | incomplete → expired"]

    operator["Оператор"]
    developer["Разработчик"]
    sanitized["Sanitized view:<br/>outcome + timeline + latency + issue tags"]
    detail["Full attempt detail:<br/>detections, repeated detections,<br/>matches, pools, teasers, N"]
    annotation["Manual ground truth:<br/>participant name + correct / wrong / missed"]
    calibration["Calibration"]

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
    calibration --> worker
    worker --> profiles --> manual
    worker --> gates --> manual
    worker -. "restart" .-> interrupted
    developer -. "manual rerun" .-> calibration

    retention["Retention:<br/>technical logs — 30 дней<br/>ordinary attempts/evidence — 90 дней<br/>promoted curated case — до удаления"]
    logs -.-> retention
    attempt -.-> retention
    evidence -.-> retention

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
сервере. Отдельный diagnostic anchor, priority scheduler и отдельный Calibration
worker не создаются.
Photo hard purge не каскадирует в Promo session, core Attempt или diagnostic
evidence; missing media пропускается при UI/device loading.

Источники: [Architecture](../arch_vision.md), [IDEA_DEBUG.md](../IDEA_DEBUG.md),
[PRD](../.memory-bank/prd.md), [Glossary](../.memory-bank/glossary.md).
