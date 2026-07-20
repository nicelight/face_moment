# 2. End-to-end pilot flow

Сквозной путь от подтверждения Batch до продолжения той же персональной session на телефоне.

```mermaid
flowchart TD
    start(["Фотограф закончил серию съёмки"])

    subgraph ingest["A. Ingest"]
        create["Создать Batch<br/>выбрать СПА + authoritative visit_date"]
        upload["Загрузить готовые JPEG по HTTPS"]
        validate{"Файл валиден и уникален<br/>для spa_id + visit_date + SHA-256?"}
        reject["Показать reject / duplicate<br/>не добавлять в manifest и N"]
        confirm["Подтвердить immutable manifest<br/>зафиксировать confirmed_at"]
        process["BackgroundPhotoWorker:<br/>preview + native FaceEngine + embeddings"]
        searchable{"Preview готов и serving state = ready?"}
        inventory["Searchable inventory"]
        breach["pending / processing / failed / no_faces<br/>после 15 мин = SLO breach"]
    end

    subgraph realtime["B. Automatic Promo"]
        advertising["Локальная реклама"]
        trigger["Sensor trigger"]
        reference["Ring buffer + reference series<br/>до 5 selected detections"]
        exact["Exact cosine search:<br/>revision + СПА + active visit_date + threshold"]
        assemble["session_result_photo_ids = unique union<br/>pHash ранжирует только valid matches"]
        enough{"Есть 4 уникальных<br/>threshold-valid teasers?"}
        failure["Вернуться к рекламе<br/>без Chime и cooldown<br/>записать diagnostics"]
        promo["Promo: ровно 4 teasers + QR<br/>никаких partial/stale results"]
    end

    subgraph phone_flow["C. QR continuation"]
        scan["Участник сканирует QR"]
        valid{"QR first-open TTL / browser idle TTL<br/>ещё действуют?"}
        landing["Та же session:<br/>СПА + visit_date + teaser + N"]
        redirect["Redirect на main Face Moment page<br/>без данных expired session"]
        external["Post-pilot selfie-search / purchase page"]
    end

    evidence["Каждая принятая attempt:<br/>correlation ID + stage timestamps + diagnostic bundle"]

    start --> create --> upload --> validate
    validate -- "нет" --> reject
    validate -- "да" --> confirm --> process --> searchable
    searchable -- "да" --> inventory
    searchable -- "нет" --> breach

    inventory --> advertising
    advertising --> trigger --> reference --> exact --> assemble --> enough
    enough -- "нет" --> failure --> advertising
    enough -- "да" --> promo --> scan --> valid
    valid -- "да" --> landing --> external
    valid -- "нет" --> redirect --> external

    reference -.-> evidence
    exact -.-> evidence
    promo -.-> evidence
    failure -.-> evidence
```

## Acceptance anchors

- Не менее 95% unique accepted JPEG должны стать searchable менее чем за 15 минут от `batch.confirmed_at`.
- Не менее 19 из 20 controlled attempts должны показать полностью видимый QR менее чем за 10 секунд от `reference_series_ready_at`.
- Иностранная фотография в четырёх teasers или в `N` делает attempt некорректной; полное покрытие каждого человека группы не обещается.

Источники: [PRD](../.memory-bank/prd.md), [IDEA_INGEST.md](../IDEA_INGEST.md), [IDEA_APP.md](../IDEA_APP.md).
