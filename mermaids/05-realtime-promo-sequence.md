# 5. Realtime Promo sequence

Последовательность одной автоматической attempt: от sensor trigger до Promo или безопасного возврата к рекламе.

```mermaid
sequenceDiagram
    autonumber
    actor Person as Участник pilot
    participant Sensor as Passage sensor
    participant Client as SpaPromoClient
    participant API as RealtimeFaceService
    participant Engine as Serving FaceEngine
    participant DB as PostgreSQL + pgvector
    participant Store as MinIO
    actor Phone as Телефон

    Note over Client: advertising; camera stream и ring buffer уже активны
    Person->>Sensor: Проходит capture-zone
    Sensor->>Client: trigger at t = 0
    Client->>Client: capturing; показать non-personal prePromo
    Client->>Client: собрать pre/post-trigger reference series
    Client->>Client: выбрать до 5 quality-ranked selected detections
    Client->>API: sync HTTPS request(reference series, spa_client_token)

    API->>DB: token_hash maps to spa_id;<br/>active visit_date, serving revision, threshold
    API->>API: bounded queue + request deadline

    loop Для каждой selected detection
        API->>Engine: native detection / alignment / query embedding
        Engine-->>API: quality values + compatible embedding
        API->>DB: exact cosine search<br/>revision + spa_id + visit_date + threshold
        DB-->>API: threshold-valid matches
        API->>API: добавить unique IDs в session_result_photo_ids;<br/>исключить reserved_photo_ids;<br/>pHash farthest-first для diversity
    end

    API->>API: N = cardinality(unique session_result_photo_ids)

    alt Получены >= 4 unique valid teasers до deadline
        API->>DB: сохранить Attempt + Promo/search session + timestamps
        API->>Store: получить low-quality previews
        Store-->>API: preview objects
        API-->>Client: 4 teaser previews + QR URL/token + expiry
        Client->>Client: Chime; transition prePromo → Promo
        Client->>Client: показать ровно 4 teasers и полностью видимый QR
        Phone->>API: открыть QR
        API->>DB: проверить session и TTL
        API-->>Phone: та же СПА + visit_date + teaser + N
        Note over Client: result duration и capture cooldown независимы от QR TTL
    else < 4 teasers, low quality, no-match, timeout или error
        API->>DB: записать non-success Attempt и stage evidence
        API-->>Client: no-success / error
        Client->>Client: отбросить stale response;<br/>вернуться к локальной рекламе
        Note over Client: Chime и Promo не запускаются;<br/>success cooldown отсутствует
    end
```

## Алгоритмические ограничения pilot

- Selected detection — occurrence лица, а не уникальный человек; tracking и identity deduplication отсутствуют.
- Embeddings разных detections не объединяются, а pipeline revisions никогда не смешиваются.
- `pHash` влияет только на разнообразие уже прошедших threshold фотографий.
- Promo существует только при четырёх уникальных valid teasers; partial result запрещён.

Источники: [IDEA_APP.md](../IDEA_APP.md), [PRD](../.memory-bank/prd.md), [Glossary](../.memory-bank/glossary.md).
