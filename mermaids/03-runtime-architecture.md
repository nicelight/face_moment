# 3. Runtime architecture

Минимальная single-server топология pilot. Это целевая архитектура, а не утверждение о текущей степени реализации.

```mermaid
flowchart LR
    photographer["Фотограф / admin browser"]
    participant_phone["Телефон участника"]

    subgraph spa_site["Pilot СПА"]
        sensor["Passage sensor"]
        camera["Camera stream"]
        display["43-inch display"]
        assets[("Локально закэшированная реклама<br/>prePromo / audio assets")]
        client["SpaPromoClient в Chromium<br/>ring buffer + state machine + QR render"]

        sensor --> client
        camera --> client
        assets --> client
        client --> display
    end

    subgraph server["Центральный CPU-only сервер в РФ"]
        edge["HTTPS public boundary<br/>reverse proxy / rate limits"]
        backend["Backend + web UI<br/>upload, Photo Inventory Operations,<br/>QR, Attempts, Log Explorer, Calibration"]
        worker["1 × BackgroundPhotoWorker<br/>Photo processing + Calibration + hard purge"]
        realtime["1 × RealtimeFaceService<br/>one inference slot + busy + deadline"]
        packages["Shared modular-monolith packages<br/>serving_control | inventory | processing<br/>promo | diagnostics + platform/auth"]

        subgraph engines["FaceEngine adapters"]
            face_engine["FaceEngine interface<br/>выбор compatible serving revision"]
            sface["OpenCV YuNet + SFace"]
            buffalo["InsightFace SCRFD + Buffalo M"]
            face_engine --> sface
            face_engine --> buffalo
        end

        postgres[("PostgreSQL + pgvector<br/>Photo visibility, pipeline states,<br/>global purge run, exact vectors,<br/>Attempts and evidence")]
        minio[("Private MinIO / S3 storage<br/>originals, previews, thumbnails,<br/>protected diagnostic artifacts")]
        edge --> backend
        edge --> realtime

        backend -.-> packages
        worker -.-> packages
        realtime -.-> packages
        backend --> postgres
        backend --> minio
        backend -->|"start/read fixed-snapshot purge<br/>poll per-СПА counters every 5 sec"| postgres
        worker -->|"claim pending / publish terminal state"| postgres
        worker -->|"read original / write derivatives"| minio
        worker --> face_engine
        realtime -->|"scope + exact cosine search"| postgres
        realtime -->|"read previews / write diagnostics"| minio
        realtime --> face_engine

    end

    photographer -->|"HTTPS JPEG upload + admin"| edge
    client -->|"sync HTTPS request<br/>attempt_id + spa_client_token"| edge
    edge -->|"4 preview URLs + QR session"| client
    client -->|"idempotent display acknowledgement"| edge
    participant_phone -->|"HTTPS QR continuation"| edge

    rules["KISS boundaries:<br/>no realtime waiter queue, Redis/broker or ANN<br/>no extra/purge worker, per-photo purge state,<br/>counter store, WS/SSE or backup guarantee"]
    rules -.-> backend
```

## Ключевые границы

- `BackgroundPhotoWorker` и `RealtimeFaceService` разделены из-за разных latency и lifecycle требований.
- Пять capability slices являются package ownership, а не отдельными services.
- Realtime не ставит запросы в waiter queue: занятый slot возвращает `busy`.
- Serving pipeline заранее загружается и прогревается; второй pipeline нужен только при доказанной необходимости benchmark-а.
- `inventory` владеет active/soft-deleted marker, direct PostgreSQL counters и
  одним resumable global purge run; worker ждёт текущую операцию без preemption.
- Hard purge удаляет Photo/media/faces/pipeline и Promo result/session, но
  сохраняет core Attempt и diagnostic evidence.
- PostgreSQL, MinIO и внутренние service ports не публикуются наружу.
- Локальный HDMI client и будущий remote client используют один `SpaPromoClient` contract.

Источники: [Architecture](../arch_vision.md), [IDEA_OS.md](../IDEA_OS.md),
[IDEA_APP.md](../IDEA_APP.md), [PRD](../.memory-bank/prd.md).
