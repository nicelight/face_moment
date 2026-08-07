# 3. Runtime architecture

Минимальная single-server топология pilot. Это целевая архитектура, а не утверждение о текущей степени реализации.

```mermaid
flowchart LR
    staff["Staff browsers:<br/>photographer / operator / developer"]
    participant_phone["Телефон участника"]

    subgraph spa_site["Pilot СПА"]
        sensor["ESP32 passage sensor<br/>fixed mDNS .local"]
        camera["Camera stream"]
        display["43-inch display"]
        assets[("Локально закэшированная реклама<br/>prePromo / audio assets")]
        client["SpaPromoClient<br/>ring buffer + local face proposals<br/>state machine + QR render"]

        client -->|"authenticated HTTP long-poll<br/>one request, 10 s timeout"| sensor
        sensor -->|"event response"| client
        camera --> client
        assets --> client
        client --> display
    end

    subgraph server["Центральный CPU-only сервер в РФ"]
        edge["HTTPS public boundary<br/>reverse proxy / rate limits"]
        backend["Backend + web UI<br/>upload, Photo Inventory Operations,<br/>QR, Attempts, Log Explorer, Calibration"]
        worker["1 × BackgroundPhotoWorker<br/>Photo processing + Calibration + hard purge<br/>+ retention cleanup when routed here"]
        realtime["1 × RealtimeFaceService<br/>one inference slot + busy + deadline"]
        packages["Shared modular-monolith packages<br/>serving_control | inventory | processing<br/>promo | diagnostics + staff_access"]

        subgraph engines["FaceEngine adapters"]
            face_engine["FaceEngine interface<br/>выбор compatible serving revision"]
            sface["OpenCV SFace pipeline"]
            buffalo["InsightFace SCRFD + Buffalo M"]
            face_engine --> sface
            face_engine --> buffalo
        end

        postgres[("PostgreSQL + pgvector<br/>Photo visibility, pipeline states,<br/>global purge run, exact vectors,<br/>Attempts and evidence")]
        minio[("Private MinIO / S3 storage<br/>commercial Photo media<br/>+ optional diagnostic media")]
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
        realtime -->|"Attempt/session writes +<br/>exact pgvector reads through owners"| postgres
        realtime -->|"read private ready previews<br/>through processing projection"| minio
        realtime --> face_engine

    end

    staff -->|"authenticated HTTPS UI/API"| edge
    client -->|"Bearer-authenticated sync HTTPS multipart<br/>first ≤20 chronological crops + metadata"| edge
    edge -->|"compact typed outcome:<br/>4 opaque media refs + QR URL"| client
    client -->|"Bearer-authenticated teaser GETs<br/>+ idempotent display acknowledgement"| edge
    participant_phone -->|"HTTPS QR continuation"| edge

    rules["KISS boundaries:<br/>no realtime waiter queue, Redis/broker or ANN<br/>no extra/purge worker, per-photo purge state,<br/>counter store, WS/SSE or backup guarantee"]
    rules -.-> backend
```

## Ключевые границы

- `BackgroundPhotoWorker` и `RealtimeFaceService` разделены из-за разных latency и lifecycle требований.
- Пять capability slices являются package ownership, а не отдельными services.
- Realtime не ставит запросы в waiter queue: занятый slot возвращает `busy`.
- Client не ранжирует/top-5/deduplicate proposals и отправляет первые не более
  20 occurrences в chronological traversal order; zero-proposal request
  содержит только manifest.
- Общий request body ограничен `20 MiB`: больший body получает HTTP `413` до
  domain admission без core Attempt, oversize domain outcome или выбора subset.
- Realtime заранее загружает и прогревает только active serving revision;
  worker/Calibration могут использовать обе зарегистрированные native engine
  implementations, не смешивая revisions и не создавая ensemble.
- `inventory` владеет active/soft-deleted marker, direct PostgreSQL counters и
  одним resumable global purge run; worker ждёт текущую операцию без preemption.
- Hard purge удаляет Photo/media/faces/pipeline states, но сохраняет Promo
  result/session, core Attempt и diagnostic evidence; clients пропускают
  отсутствующую media.
- PostgreSQL, MinIO и внутренние service ports не публикуются наружу.
- Локальный HDMI client и будущий remote client используют один `SpaPromoClient` contract.

Источники:
[Architecture](../.memory-bank/architecture/system-architecture.md),
[Boundary map](../.memory-bank/contracts/boundary-map.md),
[Realtime Attempt API](../.memory-bank/contracts/realtime-attempt-api.md),
[Promo Display API](../.memory-bank/contracts/promo-display-api.md),
[QR Continuation API](../.memory-bank/contracts/qr-continuation-api.md),
[Foundation](../.memory-bank/foundation.md).
