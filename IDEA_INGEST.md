# Face Moment: поступление фотографий

Обновлено: 2026-07-24

## 0. Статус и граница первого pilot

Документ описывает актуальный ingest-контур первого one-СПА pilot. Продуктовые
требования определяет `.memory-bank/prd.md`, а принятые архитектурные решения —
`arch_vision.md`.

Работающего ingest/backend пока нет. Flow, состояния и границы ниже описывают
target design для будущей реализации.

В pilot:

- фотограф загружает только готовые JPEG через authenticated HTTPS web app;
- перед загрузкой фотограф выбирает СПА и authoritative `visit_date`;
- каждый JPEG принимается независимо;
- Batch, manifest, confirmation и aggregate upload commit отсутствуют;
- MinIO, PostgreSQL и внутренние service ports не доступны браузеру напрямую;
- Яндекс Диск, photographer cloud OAuth, RAW и другие external ingest channels
  остаются post-pilot направлениями.

## 1. Независимый per-photo flow

Для каждого выбранного JPEG выполняется отдельный flow:

```text
authenticated HTTPS upload через backend
→ private object с уникальным opaque key в MinIO
→ decode и проверка JPEG, compressed bytes и decoded pixels
→ SHA-256
→ проверка UNIQUE(spa_id, visit_date, checksum_sha256)
→ effective captured_at:
  reliable EXIF в timezone СПА
  иначе server-side start time upload этого файла
  иначе 01:00 authoritative visit_date
→ один короткий PostgreSQL commit:
  Photo + accepted_at + serving-pipeline pending state
→ независимый accepted | rejected | duplicate outcome
```

Фотограф не подтверждает группу файлов. Завершение одного upload не зависит от
остальных выбранных файлов, а другой reader может увидеть уже готовую часть
фотографий, пока загрузка продолжается.

## 2. Authoritative scope

Фотограф выбирает:

```text
spa_id
visit_date
```

Значения сохраняются с каждой принятой Photo. `visit_date` не заменяется
filename, upload time или browser clock. Для сортировки и inventory time-range
каждая Photo получает effective `captured_at`:

1. reliable EXIF time, интерпретированный в timezone выбранного СПА;
2. иначе server-side start time upload данного файла;
3. иначе 01:00 выбранного authoritative `visit_date`.

Отдельного manual-resolution пути для отсутствующего/ненадёжного EXIF нет.

Фотография, ошибочно загруженная под неверными СПА или `visit_date`, не получает
специальный correction workflow в pilot. Риск принят оператором.

## 3. Валидация JPEG

Backend проверяет каждый файл независимо:

- разрешённый JPEG media type;
- максимальный размер compressed payload;
- успешный decode;
- ограничения width/height и decoded pixels;
- корректность EXIF orientation;
- вычисление SHA-256 по принятому byte contract.

Invalid или undecodable файл получает `rejected` и не создаёт Photo либо
processing state.

## 4. Уникальность и повторная загрузка

Логическая уникальность:

```text
UNIQUE(spa_id, visit_date, checksum_sha256)
```

Практический arbiter — database constraint через
`INSERT ... ON CONFLICT DO NOTHING RETURNING`.

При duplicate:

- новая Photo не создаётся;
- `pending` state не создаётся;
- duplicate не входит в ingest SLO population, search, teaser или `N`;
- удаляется только новый object с уникальным key;
- ранее принятая Photo остаётся без изменений.

Повторная загрузка после browser/network interruption использует тот же обычный
flow. Отдельный resumable-upload lifecycle не нужен.

## 5. PostgreSQL и MinIO

MinIO PUT не входит в PostgreSQL transaction. После успешной object upload одна
короткая database transaction создаёт:

```text
Photo
photo.accepted_at
photo_pipeline_state(status = pending, serving pipeline revision)
```

Crash между MinIO PUT и database commit может оставить один private orphan и
потерять admission одной фотографии. Повторная загрузка считается достаточным
восстановлением; outbox, distributed transaction и reconciliation workflow для
данного окна не требуются.

Accepted original сохраняет первоначальный opaque key без move/copy.

## 6. Background processing и recovery

`photo_pipeline_states` одновременно хранит searchable state и образует
PostgreSQL-backed очередь единственного `BackgroundPhotoWorker`:

```text
pending → processing → ready | no_faces | failed
```

- `ready` означает готовые preview и searchable face records совместимой
  pipeline revision;
- `no_faces` — terminal processing outcome без searchable лица;
- при startup старые `processing` возвращаются в `pending`;
- обработка после crash начинается с начала;
- final transaction полностью заменяет face set и публикует terminal state;
- bounded retry limit предотвращает бесконечный poison-file loop.

Lease, `claim_token`, fencing, `SKIP LOCKED`, отдельная jobs table и несколько
worker replicas не входят в текущую модель.

Тот же worker выполняет явно запущенную Calibration и подтверждённый global
hard purge. Purge ждёт завершения текущей операции без preemption, затем
обрабатывает fixed snapshot soft-deleted Photos. Per-photo `purge_pending`,
purge jobs table и отдельный deletion worker отсутствуют.

## 7. Ingest SLO

Метрика рассчитывается отдельно для каждой independently accepted unique Photo:

```text
start = photo.accepted_at
success = preview готов AND serving-pipeline state = ready
duration = searchable_at - photo.accepted_at
```

Цель pilot: не менее 95% population становятся searchable менее чем за
15 минут.

Population:

- входят все independently accepted unique JPEG;
- `pending`, `processing`, `failed` и `no_faces` после 15 минут считаются breach;
- rejected, checksum duplicates и non-serving processing states исключаются.

Незавершённый период загрузки может временно давать неполные или вводящие в
заблуждение aggregate metrics. Batch-level SLO coordination не требуется.
Developer-triggered Calibration может занять общий worker и временно задержать
processing; отдельный scheduler ради этого не создаётся.

## 8. Наблюдаемость фотографа и оператора

Фотографу достаточно видеть:

- `accepted | rejected | duplicate`;
- текущий `pending | processing | ready | no_faces | failed`;
- понятную причину reject/failure;
- возможность повторно загрузить файл.

Admin UI каждые пять секунд polling-ом получает для каждого СПА отдельные окна
1, 5 и 60 минут:

- `new` — active unique Photos с `accepted_at` внутри окна;
- `unprocessed` — active Photos, принятые внутри окна и сейчас находящиеся в
  `pending | processing`;
- `processed` — active Photos, перешедшие в `ready | no_faces` внутри окна;
- `failed` — active Photos, перешедшие в `failed` внутри окна.

Показатели считаются прямыми PostgreSQL queries по уже необходимым Photo и
pipeline-state timestamps. Soft-deleted Photos исключаются. WebSocket, SSE,
materialized counter storage, отдельный message broker или observability
datastore не нужны.

## 9. Photo Inventory Operations

Фотограф может выбирать Photo по СПА, authoritative `visit_date` и effective
`captured_at` range, затем soft-delete/restore только собственные uploads.
Оператор и разработчик могут выполнять те же действия для любой Photo в
доступном СПА.

Soft delete меняет один active marker и сразу исключает Photo из search,
participant media access и статистики, сохраняя Photo, media, faces и pipeline
state. Restore возвращает preserved state без re-upload/reprocessing.

В Admin settings доступны две project-wide операции для оператора/разработчика:

- `restore all soft deleted`;
- подтверждаемая `hard delete ALL softed media`.

Hard purge фиксирует snapshot всех soft-deleted Photos на момент confirmation и
использует один resumable global run с completed/total progress. После restart
worker продолжает тот же snapshot. Удаляются Photo,
original/preview/thumbnail, faces, pipeline states и Promo results/sessions,
содержащие Photo; core Attempts и diagnostic evidence сохраняются по обычной
retention policy. Upload, уже находящийся в процессе, не прерывается; ordinary
uploads могут продолжить создавать обычный `pending` backlog.

## 10. Durability boundary

Очередь уже принятых `pending`/`processing` фотографий должна переживать обычный
restart backend/worker и продолжать обработку.

Отдельные backup, replication, snapshots и восстановление после необратимой
потери единственного primary disk/server в pilot отсутствуют. Потеря persisted
data при таком отказе является принятым риском.

## 11. Post-pilot направления

После отдельного product decision могут появиться:

- external ingest channels;
- resumable upload для доказанно больших или нестабильных загрузок;
- дополнительные worker replicas с новой concurrency-моделью;
- отдельная durability policy для paid flow/public rollout.

Стабильные `photo_id`, original ownership в `inventory`, serving-compatible
pipeline state и per-photo uniqueness сохраняют достаточный extension seam без
реализации будущих механизмов в pilot.
