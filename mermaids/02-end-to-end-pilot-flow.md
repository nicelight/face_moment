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
        process["BackgroundPhotoWorker:<br/>preview + native FaceEngine + embeddings"]
        searchable{"Preview готов и serving state = ready?"}
        inventory["Searchable inventory"]
        breach["pending / processing / failed / no_faces<br/>после 15 мин = SLO breach"]
    end

    subgraph realtime["B. Automatic Promo"]
        advertising["Локальная реклама"]
        trigger["Sensor trigger"]
        reference["Client-generated attempt_id<br/>ring buffer + reference series"]
        attempt["Core Attempt до inference"]
        exact["Exact cosine search:<br/>revision + СПА + active visit_date + threshold"]
        assemble["session_result_photo_ids = unique union<br/>pHash ранжирует только valid matches"]
        enough{"Есть 4 уникальных<br/>threshold-valid teasers?"}
        failure["Finalize core Attempt<br/>evidence best-effort<br/>вернуться к рекламе без cooldown"]
        issued["result_issued<br/>display_status = pending"]
        render["Decode 4 teasers<br/>показать полностью видимый QR"]
        ack["Idempotent display acknowledgement<br/>display_status = confirmed"]
    end

    subgraph phone_flow["C. QR continuation"]
        scan["Участник сканирует QR"]
        valid{"30 min first-open / shared 60 min idle<br/>ещё действуют?"}
        landing["Та же session:<br/>СПА + visit_date + teaser + N"]
        redirect["Redirect на main Face Moment page<br/>без данных expired session"]
        external["Post-pilot selfie-search / purchase page"]
    end

    evidence["Core Attempt обязателен<br/>detailed evidence best-effort<br/>gap = incomplete"]

    start --> upload --> validate
    validate -- "нет" --> reject
    validate -- "да" --> admit --> process --> searchable
    searchable -- "да" --> inventory
    searchable -- "нет" --> breach

    inventory --> advertising
    advertising --> trigger --> reference --> attempt --> exact --> assemble --> enough
    enough -- "нет" --> failure --> advertising
    enough -- "да" --> issued --> render --> ack --> scan --> valid
    valid -- "да" --> landing --> external
    valid -- "нет" --> redirect --> external

    attempt -.-> evidence
    exact -.-> evidence
    ack -.-> evidence
    failure -.-> evidence
```

## Acceptance anchors

- Не менее 95% independently accepted unique JPEG должны стать searchable менее
  чем за 15 минут от `photo.accepted_at`.
- Не менее 19 из 20 controlled attempts должны получить подтверждённый полностью
  видимый QR менее чем за 10 секунд по client monotonic interval от
  `reference_series_ready`.
- Иностранная фотография в четырёх teasers или в `N` делает attempt некорректной; полное покрытие каждого человека группы не обещается.

Источники: [PRD](../.memory-bank/prd.md),
[Architecture](../arch_vision.md), [IDEA_INGEST.md](../IDEA_INGEST.md),
[IDEA_APP.md](../IDEA_APP.md).
