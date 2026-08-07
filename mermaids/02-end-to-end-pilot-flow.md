# 2. End-to-end pilot flow

Сквозной путь от независимой загрузки JPEG до продолжения той же персональной
session на телефоне.

```mermaid
flowchart TD
    start(["Фотограф выбирает СПА<br/>и authoritative visit_date"])

    subgraph ingest["A. Ingest"]
        upload["Независимо загрузить JPEG<br/>через HTTPS backend"]
        validate{"Файл валиден и уникален<br/>для spa_id + visit_date + SHA-256?"}
        reject["Показать rejected / duplicate<br/>не создавать Photo или pending"]
        admit["Per-photo PostgreSQL commit:<br/>Photo + accepted_at + pending"]
        effective_time["Effective captured_at:<br/>reliable EXIF in СПА timezone<br/>else file upload-start, else visit_date 01:00"]
        process["BackgroundPhotoWorker:<br/>preview + native FaceEngine + embeddings"]
        searchable{"Preview готов и serving state = ready?"}
        inventory["Searchable inventory"]
        breach["pending / processing / failed / no_faces<br/>после 15 мин = SLO breach"]
    end

    subgraph realtime["B. Automatic Promo"]
        advertising["Локальная реклама"]
        trigger["ESP32 HTTP long-poll / test trigger"]
        reference["Client-generated attempt_id<br/>reference series → chronological BlazeFace<br/>first ≤20 crops + metadata in traversal order<br/>zero proposals → manifest only<br/>no client ranking / subset"]
        boundary{"Realtime boundary result"}
        rejected["Pre-admission response:<br/>401 / 413 / 422 / 429 / 503 / technical 5xx<br/>no core Attempt / domain outcome"]
        offline["Client-only offline:<br/>вернуться к рекламе без cooldown<br/>5–10 sec: Попытка связи с сервером<br/>была не успешна в hh:mm:ss<br/>новое сообщение может заменить старое<br/>metadata best-effort, server record может отсутствовать"]
        attempt["Server-admitted core Attempt<br/>до inference"]
        exact["Server quality-ranks/selects ≤5 occurrences;<br/>exact cosine search:<br/>revision + СПА + active visit_date + threshold"]
        assemble["session_result_photo_ids = unique union<br/>pHash ранжирует только valid matches"]
        enough{"Есть 4 уникальных<br/>threshold-valid teasers?"}
        failure["Finalize core Attempt<br/>evidence best-effort<br/>вернуться к рекламе без cooldown"]
        issued["result_issued<br/>display_status = pending"]
        render["Получить и decode 4 teasers<br/>сгенерировать QR локально"]
        visible{"Все 4 teasers и QR<br/>полностью видимы до expiry?"}
        display_failed["Best-effort failed report<br/>или derived unconfirmed<br/>без Promo success/cooldown"]
        ack["Idempotent confirmed acknowledgement<br/>display_status = confirmed<br/>success cooldown"]
    end

    subgraph phone_flow["C. QR continuation"]
        scan["Участник сканирует QR"]
        first_open{"QR ticket открыт<br/>строго до 30 min boundary?"}
        shared["Открыть/reuse один session-wide<br/>browser access context"]
        idle{"Менее 60 min без explicit<br/>participant activity?"}
        landing["Та же session:<br/>СПА + visit_date + доступный teaser + N"]
        redirect["Redirect на main Face Moment page<br/>без данных expired session"]
        external["Post-pilot selfie-search / purchase page"]
    end

    evidence["Для server-admitted request:<br/>core Attempt обязателен<br/>detailed evidence best-effort<br/>gap = incomplete"]

    start --> upload --> validate
    validate -- "нет" --> reject
    validate -- "да" --> effective_time --> admit --> process --> searchable
    searchable -- "да" --> inventory
    searchable -- "нет" --> breach

    inventory --> advertising
    advertising --> trigger --> reference --> boundary
    boundary -- "нет HTTP response" --> offline --> advertising
    boundary -- "transport/auth/validation/readiness reject" --> rejected --> advertising
    boundary -- "200 admitted outcome" --> attempt --> exact --> assemble --> enough
    enough -- "нет" --> failure --> advertising
    enough -- "да" --> issued --> render --> visible
    visible -- "нет" --> display_failed --> advertising
    visible -- "да" --> ack --> advertising
    visible -- "QR уже доступен; ack его не включает" --> scan --> first_open
    first_open -- "нет" --> redirect --> external
    first_open -- "да" --> shared --> idle
    idle -- "да" --> landing --> external
    idle -- "нет" --> redirect

    attempt -.-> evidence
    exact -.-> evidence
    ack -.-> evidence
    failure -.-> evidence

    inventory_ops["Photo Inventory Operations:<br/>soft delete/restore + direct 1/5/60 counters<br/>fixed purge; restore snapshot members rejected<br/>existing sessions skip hard-purged media"]
    inventory -.-> inventory_ops
```

## Acceptance anchors

- Не менее 95% independently accepted unique JPEG должны стать searchable менее
  чем за 15 минут от `photo.accepted_at`.
- Не менее 19 из 20 controlled attempts должны получить подтверждённый полностью
  видимый QR менее чем за 10 секунд по client monotonic interval от
  `reference_series_ready`, включая local processing и request send.
- Иностранная фотография в четырёх teasers или в `N` делает attempt некорректной; полное покрытие каждого человека группы не обещается.
- Soft-deleted Photos исключены из новых search/results/statistics, но уже
  выданная session продолжает использовать media. Hard purge удаляет
  Photo-owned данные, сохраняет session/core Attempt/evidence, а client
  пропускает отсутствующую media без пересчёта `N`.

Источники: [PRD](../.memory-bank/prd.md),
[Architecture](../.memory-bank/architecture/system-architecture.md),
[Boundary map](../.memory-bank/contracts/boundary-map.md),
[Photo Admission](../.memory-bank/domains/photo-admission.md),
[Photo Processing](../.memory-bank/domains/photo-processing.md),
[Realtime Attempt API](../.memory-bank/contracts/realtime-attempt-api.md),
[Promo Display API](../.memory-bank/contracts/promo-display-api.md),
[QR Continuation API](../.memory-bank/contracts/qr-continuation-api.md).
