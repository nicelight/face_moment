# 4. Ingest and processing lifecycle

Каждый JPEG проходит независимый admission и получает собственное
pipeline-specific состояние.

```mermaid
flowchart TD
    auth["Фотограф аутентифицирован"]
    scope["Выбрать СПА + authoritative visit_date"]
    upload["Один JPEG через HTTPS backend"]
    object["Private MinIO object<br/>уникальный opaque key"]
    decode{"JPEG поддерживается<br/>и декодируется?"}
    checksum["Вычислить SHA-256"]
    duplicate{"Уже существует тот же<br/>spa_id + visit_date + checksum?"}
    rejected["Rejected<br/>удалить candidate object<br/>не создавать Photo/pending"]
    duplicate_end["Duplicate<br/>idempotent delete нового object<br/>не создавать Photo/pending"]
    create["Один PostgreSQL commit:<br/>Photo + accepted_at + pending"]
    orphan["Принятый риск crash-window:<br/>private orphan / повторный upload"]
    pending["state = pending<br/>durable queue"]
    claim["BackgroundPhotoWorker<br/>atomic pending → processing"]
    processing["state = processing"]
    derivatives["EXIF orientation fix<br/>preview + thumbnail + pHash"]
    engine["Native serving FaceEngine:<br/>detect + align + embedding"]
    result{"Результат обработки"}
    ready["state = ready<br/>searchable_at установлен<br/>photo_faces доступны exact search"]
    nofaces["state = no_faces<br/>terminal, но JPEG не searchable"]
    failed["state = failed<br/>last_error сохранён"]
    retry{"attempts < 3?"}
    restart["Worker restart:<br/>processing → pending<br/>начать с начала"]
    metric["ingest_to_searchable success:<br/>preview готов AND serving state = ready"]

    auth --> scope --> upload --> object --> decode
    object -. "crash до DB commit" .-> orphan
    decode -- "нет" --> rejected
    decode -- "да" --> checksum --> duplicate
    duplicate -- "да" --> duplicate_end
    duplicate -- "нет" --> create --> pending --> claim --> processing --> derivatives --> engine --> result
    result -- "лица найдены" --> ready --> metric
    result -- "обработано без лиц" --> nofaces
    result -- "ошибка" --> retry
    retry -- "да" --> pending
    retry -- "нет" --> failed
    processing -. "process crash" .-> restart --> pending
```

## Семантика состояний

- `ready` означает, что searchable face records созданы для конкретной `pipeline_revision`.
- `no_faces` — успешный terminal processing outcome, но остаётся breach метрики searchable.
- `pending`, `processing`, `failed` и `no_faces` после 15 минут остаются SLO breaches.
- Повторное at-least-once выполнение не должно дублировать `photo_faces` или производные файлы.
- `visit_date` выбирает фотограф; EXIF `captured_at` остаётся вторичной метаданной.
- Accepted original сохраняет первоначальный opaque key без MinIO move/copy.
- Batch, manifest, confirmation, отдельная jobs table и distributed transaction отсутствуют.

Источники: [Architecture](../arch_vision.md),
[IDEA_INGEST.md](../IDEA_INGEST.md), [IDEA_APP.md](../IDEA_APP.md),
[Glossary](../.memory-bank/glossary.md).
