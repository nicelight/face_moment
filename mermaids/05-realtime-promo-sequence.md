# 5. Realtime Promo sequence

Последовательность одной автоматической attempt: от sensor trigger до Promo или безопасного возврата к рекламе.

```mermaid
sequenceDiagram
    autonumber
    actor Person as Участник pilot
    participant Sensor as Passage sensor
    participant Client as SpaPromoClient
    participant Edge as HTTPS edge
    participant API as RealtimeFaceService
    participant Backend as Backend / promo
    participant Engine as Serving FaceEngine
    participant DB as PostgreSQL + pgvector
    participant Store as MinIO
    actor Phone as Телефон

    Note right of Client: advertising — camera stream и ring buffer уже активны
    Person->>Sensor: Проходит capture-zone
    Sensor->>Client: trigger at t = 0
    Client->>Client: создать UUID attempt_id
    Client->>Client: capturing — показать non-personal prePromo
    Client->>Client: собрать pre/post-trigger reference series
    Client->>Edge: sync HTTPS request<br/>attempt_id + reference series + spa_client_token
    alt Transport/offline failure до server admission
        Edge--xClient: network error / no response
        Client->>Client: вернуться к рекламе без success cooldown<br/>5–10 sec: Попытка связи с сервером<br/>была не успешна в hh:mm:ss
        Note right of Client: Новое сообщение может сразу заменить текущее
        Client-->>Backend: optional best-effort offline metadata<br/>только если transport станет доступен
        Note right of Backend: Durable delivery и server Attempt не гарантируются
    else Request admitted by server
        Edge->>API: authenticated bounded request

        API->>DB: token_hash → spa_id<br/>ServingContext + active visit_date
        API->>DB: создать core Attempt<br/>processing_status = accepted

        alt inference slot занят
            API->>DB: processing_status = no_success<br/>issue_tag = busy
            API-->>Edge: 2xx typed outcome = busy
            Edge-->>Client: 2xx busy
            Client->>Client: вернуться к локальной рекламе<br/>без success cooldown
        else inference slot свободен
            API->>DB: processing_status = searching
            API->>Engine: detect faces, quality-rank<br/>выбрать не более 5 detections

            loop До 5 quality-ranked selected detections
                API->>Engine: native alignment / query embedding
                Engine-->>API: quality values + compatible embedding
                API->>DB: exact cosine search<br/>active Photo + revision + spa_id<br/>visit_date + threshold
                DB-->>API: threshold-valid matches
                API->>API: unique union + reserved_photo_ids<br/>pHash diversity ranking
            end

            API->>API: N = cardinality(unique session_result_photo_ids)

            alt Получены не менее 4 unique valid teasers до server deadline
                API->>Store: получить low-quality previews
                Store-->>API: preview objects
                API->>DB: сохранить immutable result/session<br/>processing_status = result_issued<br/>display_status = pending
                API-->>Edge: 4 teasers + QR ticket + expiry
                Edge-->>Client: result_issued
                Client->>Client: decode 4 teasers<br/>Chime + transition prePromo → Promo
                Client->>Client: показать ровно 4 teasers<br/>и полностью видимый QR
                Client->>Edge: idempotent display acknowledgement
                Edge->>Backend: confirm display outcome
                Backend->>DB: display_status = confirmed
                Note right of Client: Только confirmed запускает success cooldown<br/>и считается Promo success

                Phone->>Edge: открыть QR ticket
                Edge->>Backend: QR continuation
                Backend->>DB: открыть/reuse session-wide browser access<br/>30 min first-open + shared 60 min idle
                Backend-->>Edge: clean session URL + no-store content
                Edge-->>Phone: та же СПА + visit_date + teaser + N
                Note right of Client: result duration и cooldown<br/>независимы от QR/session TTL
            else Меньше 4 teasers, low quality, no-match или deadline
                API->>DB: processing_status = no_success / deadline
                API-->>Edge: 2xx typed domain outcome
                Edge-->>Client: 2xx non-success outcome
                Client->>Client: отбросить stale response<br/>вернуться к локальной рекламе
                Note right of Client: Chime и Promo не запускаются<br/>success cooldown отсутствует
            else Internal/upstream technical failure
                API->>DB: processing_status = internal_failure
                API-->>Edge: 5xx
                Edge-->>Client: 5xx
                Client->>Client: вернуться к рекламе<br/>5–10 sec: Попытка связи с сервером<br/>была не успешна в hh:mm:ss
            end
        end

        opt Detailed diagnostics доступны
            Client-->>Backend: best-effort browser events по attempt_id
            API-->>Backend: best-effort server evidence по attempt_id
            Backend->>DB: complete либо incomplete evidence projection
        end
    end
```

## Алгоритмические ограничения pilot

- Selected detection — occurrence лица, а не уникальный человек; tracking и identity deduplication отсутствуют.
- Embeddings разных detections не объединяются, а pipeline revisions никогда не смешиваются.
- `pHash` влияет только на разнообразие уже прошедших threshold фотографий.
- Promo существует только при четырёх уникальных valid teasers; partial result запрещён.
- Realtime waiter queue отсутствует; concurrent request получает `busy`.
- Server response не доказывает показ Promo: нужен отдельный display acknowledgement.
- Если display window завершился без acknowledgement, `unconfirmed` выводится
  при чтении; отдельный scheduler не нужен.
- Client-only offline trigger может не создать server Attempt; его metadata
  доставляется только best-effort без durable outbox.

Источники: [Architecture](../.memory-bank/architecture/system-architecture.md),
[IDEA_APP.md](../IDEA_APP.md),
[PRD](../.memory-bank/prd.md), [Glossary](../.memory-bank/glossary.md).
