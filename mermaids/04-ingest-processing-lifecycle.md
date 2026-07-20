# 4. Ingest and processing lifecycle

Диаграмма разделяет pre-confirmation validation, immutable Batch и pipeline-specific состояние фотографии.

```mermaid
flowchart TD
    auth["Фотограф аутентифицирован"]
    draft["Draft Batch:<br/>одна СПА + один authoritative visit_date"]
    upload["Multi-file JPEG upload"]
    decode{"JPEG поддерживается<br/>и декодируется?"}
    checksum["Вычислить SHA-256"]
    duplicate{"Уже существует тот же<br/>spa_id + visit_date + checksum?"}
    rejected["Rejected file<br/>не входит в confirmed manifest"]
    duplicate_end["Удалить вторую копию<br/>показать duplicate<br/>не создавать photo/job/result"]
    accepted["Accepted pre-confirmation file"]
    review["Фотограф проверяет accepted / rejected / warnings"]
    confirm["Confirm Batch:<br/>manifest и confirmed_at неизменяемы"]
    original["Сохранить private original в MinIO"]
    create["Идемпотентно создать Photo,<br/>photo_pipeline_state = pending<br/>и serving processing job"]
    claim["BackgroundPhotoWorker<br/>транзакционно claim одной job"]
    processing["state = processing"]
    derivatives["EXIF orientation fix<br/>preview + thumbnail + pHash"]
    engine["Native serving FaceEngine:<br/>detect + align + embedding"]
    result{"Результат обработки"}
    ready["state = ready<br/>searchable_at установлен<br/>photo_faces доступны exact search"]
    nofaces["state = no_faces<br/>terminal, но JPEG не searchable"]
    failed["state = failed<br/>last_error сохранён"]
    retry["Ручной или ограниченный retry<br/>той же idempotency key"]
    metric["ingest_to_searchable success:<br/>preview готов AND serving state = ready"]

    auth --> draft --> upload --> decode
    decode -- "нет" --> rejected --> review
    decode -- "да" --> checksum --> duplicate
    duplicate -- "да" --> duplicate_end --> review
    duplicate -- "нет" --> accepted --> review
    review --> confirm --> original --> create --> claim --> processing --> derivatives --> engine --> result
    result -- "лица найдены" --> ready --> metric
    result -- "обработано без лиц" --> nofaces
    result -- "ошибка" --> failed --> retry --> claim
```

## Семантика состояний

- `ready` означает, что searchable face records созданы для конкретной `pipeline_revision`.
- `no_faces` — успешный terminal processing outcome, но остаётся breach метрики searchable.
- Повторное at-least-once выполнение не должно дублировать `photo_faces` или производные файлы.
- `visit_date` берётся из подтверждённой формы; EXIF `captured_at` остаётся вторичной метаданной.

Источники: [IDEA_INGEST.md](../IDEA_INGEST.md), [IDEA_APP.md](../IDEA_APP.md), [Glossary](../.memory-bank/glossary.md).
