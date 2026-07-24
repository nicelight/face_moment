# 4. Ingest, processing and inventory lifecycle

Каждый JPEG проходит независимый admission. Photo processing state,
active/soft-deleted visibility и один global hard-purge run остаются разными
KISS-контурами.

```mermaid
flowchart TD
    subgraph admission["Independent Photo admission"]
        auth["Фотограф аутентифицирован"]
        scope["Выбрать СПА + authoritative visit_date"]
        upload["Один JPEG через HTTPS backend<br/>server-side file upload-start"]
        object["Private MinIO object<br/>уникальный opaque key"]
        decode{"JPEG поддерживается<br/>и декодируется?"}
        captured["Effective captured_at:<br/>reliable EXIF in СПА timezone<br/>else file upload-start<br/>else visit_date 01:00"]
        checksum["Вычислить SHA-256"]
        duplicate{"Уже существует тот же<br/>spa_id + visit_date + checksum?"}
        rejected["Rejected<br/>удалить candidate object<br/>не создавать Photo/pending"]
        duplicate_end["Duplicate<br/>idempotent delete нового object<br/>не создавать Photo/pending"]
        create["Один PostgreSQL commit:<br/>Photo + accepted_at + pending"]
        orphan["Принятый crash-window:<br/>private orphan / повторный upload"]

        auth --> scope --> upload --> object --> decode
        object -. "crash до DB commit" .-> orphan
        decode -- "нет" --> rejected
        decode -- "да" --> captured --> checksum --> duplicate
        duplicate -- "да" --> duplicate_end
        duplicate -- "нет" --> create
    end

    subgraph pipeline["Photo pipeline state — PostgreSQL durable queue"]
        pending["pending"]
        claim["Один BackgroundPhotoWorker<br/>atomic claim"]
        processing["processing"]
        derivatives["preview + thumbnail + pHash"]
        engine["Native serving FaceEngine<br/>detect + align + embedding"]
        result{"Результат"}
        ready["ready<br/>searchable_at + faces"]
        nofaces["no_faces<br/>terminal, not searchable"]
        failed["failed<br/>status_changed_at + error"]
        retry{"attempts < 3?"}
        restart["Worker restart:<br/>processing → pending<br/>начать с начала"]
        metric["ingest_to_searchable success:<br/>preview готов AND ready"]

        create --> pending --> claim --> processing --> derivatives --> engine --> result
        result -- "лица найдены" --> ready --> metric
        result -- "обработано без лиц" --> nofaces
        result -- "ошибка" --> retry
        retry -- "да" --> pending
        retry -- "нет" --> failed
        processing -. "process crash" .-> restart --> pending
    end

    subgraph inventory["Inventory visibility and project-wide purge"]
        active["Photo active<br/>доступна согласно pipeline state"]
        soft["Photo soft_deleted<br/>все данные сохранены<br/>new search/results/stats excluded<br/>issued-session media остаётся доступной"]
        select["СПА + visit_date + captured_at range<br/>photographer: own uploads<br/>operator/developer: accessible СПА"]
        restore_guard{"Target Photo входит в confirmed<br/>non-terminal purge snapshot?"}
        restore_all["restore all soft deleted<br/>весь проект"]
        confirm["Confirm hard delete ALL softed media<br/>зафиксировать global snapshot"]
        reject_restore["Reject restore snapshot members<br/>до completed"]
        wait["confirmed_waiting<br/>ждать текущую worker operation<br/>human-readable process name"]
        purge["running<br/>same worker, completed / total<br/>restart resumes snapshot"]
        remove["Удалить Photo + media + faces + pipeline"]
        retain["Сохранить Promo sessions + core Attempts<br/>и diagnostic evidence<br/>client skips missing media"]
        done["completed"]
        stats["Per-СПА direct PostgreSQL counters<br/>1 / 5 / 60 min, poll 5 sec<br/>active Photos only"]

        create --> active
        select --> active
        active -->|"soft delete"| soft
        soft -->|"restore"| restore_guard
        restore_all --> restore_guard
        restore_guard -- "да" --> reject_restore
        restore_guard -- "нет" --> active
        soft --> confirm --> wait --> purge --> remove --> done
        remove -.-> retain
        active -.-> stats
    end

    worker_busy["Shared worker current operation:<br/>Photo processing / Calibration / cleanup"]
    worker_busy --> wait
    ordinary_upload["Ordinary uploads may continue;<br/>in-progress upload is not interrupted"]
    ordinary_upload -.-> create
```

## Семантика

- `ready` означает searchable face records конкретной `pipeline_revision`;
  `no_faces` является terminal outcome, но остаётся searchable-SLO breach.
- Повторное at-least-once выполнение не дублирует `photo_faces` или derivatives.
- Soft delete меняет один visibility marker и блокирует новые search/results,
  но не ломает уже выданную session; restore не запускает processing.
- `new` использует `accepted_at`; `unprocessed` — in-window accepted и текущие
  `pending|processing`; `processed`/`failed` используют соответствующий
  transition time. Все counters исключают soft-deleted Photos.
- Global purge snapshot фиксируется при confirmation. Soft deletes после
  confirmation ждут следующего запуска, а restore snapshot members отклоняется
  до completion.
- Batch, manifest, confirmation upload-а, per-photo `purge_pending`, отдельная
  jobs table, deletion worker, counter store и distributed transaction
  отсутствуют.

Источники: [Architecture](../.memory-bank/architecture/system-architecture.md),
[Lifecycle](../.memory-bank/states/lifecycle-map.md),
[IDEA_INGEST.md](../IDEA_INGEST.md), [PRD](../.memory-bank/prd.md).
