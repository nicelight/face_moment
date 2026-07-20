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
        backend["Backend + web UI<br/>upload, admin, QR landing,<br/>Attempts, Log Explorer, Calibration"]
        worker["1 × BackgroundPhotoWorker<br/>последовательная обработка"]
        realtime["1 × RealtimeFaceService<br/>sync HTTP, inference concurrency = 1,<br/>bounded in-memory queue + deadline"]

        subgraph engines["FaceEngine adapters"]
            face_engine["FaceEngine interface<br/>выбор compatible serving revision"]
            sface["OpenCV YuNet + SFace"]
            buffalo["InsightFace SCRFD + Buffalo M"]
            face_engine --> sface
            face_engine --> buffalo
        end

        postgres[("PostgreSQL + pgvector<br/>domain state, jobs, exact vectors,<br/>events, logs, annotations")]
        minio[("Private MinIO / S3 storage<br/>originals, previews, thumbnails,<br/>protected diagnostic artifacts")]
        backup[("Backup на другом физическом носителе / сервере")]

        edge --> backend
        edge --> realtime

        backend --> postgres
        backend --> minio
        worker -->|"claim jobs / publish states"| postgres
        worker -->|"read original / write derivatives"| minio
        worker --> face_engine
        realtime -->|"scope + exact cosine search"| postgres
        realtime -->|"read previews / write diagnostics"| minio
        realtime --> face_engine

        postgres --> backup
        minio --> backup
    end

    photographer -->|"HTTPS JPEG upload + admin"| edge
    client -->|"sync HTTPS request<br/>Authorization: spa_client_token"| edge
    edge -->|"4 preview URLs + QR session"| client
    participant_phone -->|"HTTPS QR continuation"| edge

    rules["KISS boundaries:<br/>no Redis/broker, no ANN, no Kubernetes,<br/>no GPU-first, no external face API"]
    rules -.-> backend
```

## Ключевые границы

- `BackgroundPhotoWorker` и `RealtimeFaceService` разделены из-за разных latency и lifecycle требований.
- Serving pipeline заранее загружается и прогревается; второй pipeline нужен только при доказанной необходимости benchmark-а.
- PostgreSQL, MinIO и внутренние service ports не публикуются наружу.
- Локальный HDMI client и будущий remote client используют один `SpaPromoClient` contract.

Источники: [IDEA_OS.md](../IDEA_OS.md), [IDEA_APP.md](../IDEA_APP.md), [PRD](../.memory-bank/prd.md).
