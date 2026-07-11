# Face Moment: приложение


Обновлено: 2026-07-11

## 0. Статус документа

Этот документ фиксирует продуктовую концепцию, принятые архитектурные решения и границы MVP.

Используются четыре статуса:

- **Требование** — поведение, которое система обязана обеспечивать.
- **Принятое архитектурное решение** — текущий способ реализации, выбранный осознанно.
- **Рекомендация** — предпочтительная стартовая реализация, которую можно
  упростить или заменить без изменения продуктовых требований и принятых
  архитектурных границ.
- **Кандидат на будущее** — возможное усложнение, которое нельзя добавлять без измеримой необходимости.

### Правило для разработчиков и AI-агентов

Принятые решения нельзя заменять на Redis, Celery, RQ, Kafka, ANN-индексы, автоматическую кластеризацию, распределённый scheduler или другие более сложные механизмы только потому, что они считаются типичными для подобных систем.

Архитектуру разрешено усложнять только если одновременно выполнены два условия:

1. Текущая реализация не выполняет зафиксированный SLA или создаёт подтверждённую проблему.
2. Проблема подтверждена метриками, benchmark-ом или эксплуатационными данными.

**Почему принято:** проект следует KISS. Сложность добавляется для решения уже наблюдаемой проблемы, а не для гипотетического будущего масштаба.

Рекомендации не являются MVP gates. Их разрешено не реализовывать, если более
простое решение сохраняет корректность, наблюдаемость обязательных SLA и
принятые архитектурные границы.

---

## 1. Суть проекта

В SPA-центрах фотографы делают фотографии посетителей. После посещения клиент должен найти свои фотографии по селфи, выбрать их, оплатить и скачать оригиналы.

Также на выходе из SPA устанавливается промо-экран с камерой. Он делает reference-кадры посетителя, находит его фотографии и показывает несколько preview и QR-код для перехода на телефон.

### 1.1 Масштаб

- один центральный сервер в РФ;
- 10–15 SPA;
- 150–200 коммерческих фотографий в день на один SPA;
- суммарно 1 500–3 000 фотографий в день;
- 45 000–90 000 фотографий за 30 дней;
- хранение истории минимум один месяц;
- inference выполняется на центральном сервере без внешних cloud face-recognition API.

### 1.2 Главная продуктовая формула

~~~text
фотографии заранее загружаются и индексируются
+
клиент предоставляет query-фото лица
+
система выполняет поиск только внутри нужного SPA и периода
+
клиент получает preview, оплачивает и скачивает оригиналы
~~~

### 1.3 Критическая операционная зависимость

Промо-экран сможет найти только те фотографии, которые уже загружены и обработаны.

Необходимо измерять время:

~~~text
фотография загружена
→ создан preview
→ обнаружены лица
→ созданы embeddings
→ фотография доступна для поиска
~~~

Целевая метрика: `ingest_to_searchable_p95`.

**Почему принято:** скорость inference не имеет значения, если коммерческие фотографии ещё не попали в поисковую базу. Эта метрика выявляет реальный bottleneck загрузки и фоновой обработки.

---

## 2. Пользовательские сценарии

### 2.1 Поиск через сайт

1. Клиент открывает общую ссылку или ссылку с уже заданным SPA/визитом.
2. Выбирает SPA и дату, если они не заданы ссылкой.
3. Загружает селфи или делает live-selfie.
4. Система проверяет качество лица.
5. `RealtimeFaceService` создаёт embedding активным pipeline данного SPA.
6. Выполняется точный поиск среди embeddings той же `pipeline_revision`.
7. Поиск ограничивается `spa_id` и датой, визитом или временным окном.
8. Клиент получает preview с watermark.
9. Выбирает фотографии, оплачивает и скачивает оригиналы.

## 3. Принятая топология приложения

### 3.2 Минимальное разделение процессов

Система не разбивается на множество микросервисов. Отдельными процессами выделяются только:

1. backend;
2. `BackgroundPhotoWorker`;
3. `RealtimeFaceService`.

**Почему принято:** отдельные процессы нужны для независимого жизненного цикла моделей и закрепления за CPU. Дальнейшее дробление не даёт измеримой пользы на текущем масштабе.

---

## 4. Face recognition pipelines

### 4.1 Поддерживаемые pipelines

1. `opencv_sface`
   - detector: OpenCV YuNet;
   - recognizer: OpenCV SFace.

2. `insightface_buffalo_m`
   - detector: SCRFD из model pack;
   - recognizer: Buffalo M.

Для каждого SPA в админке выбирается обслуживающий pipeline.

**Почему принято:** SFace является лёгким CPU-вариантом, а Buffalo M используется как более сильный кандидат и benchmark baseline. Реальное решение между ними принимается на данных проекта.

### 4.2 Только родной preprocessing каждой модели

Общий preprocessing ограничивается:

~~~text
проверка формата
→ исправление EXIF orientation
→ ограничение размера изображения
→ базовая проверка blur / brightness
→ передача изображения выбранному FaceEngine
~~~

Модельно-зависимый pipeline полностью находится внутри adapter-а.

#### SFace

~~~text
image
→ YuNet detection
→ bbox + landmarks
→ FaceRecognizerSF.alignCrop
→ SFace feature
→ нормализованный embedding
~~~

#### Buffalo M

~~~text
image
→ InsightFace FaceAnalysis.get
→ SCRFD detection
→ штатные landmarks и alignment InsightFace
→ Buffalo M recognition
→ normed_embedding
~~~

Crop, bbox, landmarks и alignment одного pipeline не переиспользуются другим pipeline.

**Почему принято:** YuNet/SFace и SCRFD/Buffalo M имеют разные detectors и правила подготовки лица. Общий crop или alignment ухудшит качество и сделает сравнение моделей некорректным.

### 4.3 FaceEngine adapter

Остальная система работает через общий интерфейс:

~~~python
class FaceEngine:
    pipeline_revision_id: str
    embedding_dim: int

    def process_image(self, image) -> list[FaceResult]:
        ...

    def create_query_embedding(self, image) -> QueryFaceResult:
        ...
~~~

Реализации:

- `OpenCvSFaceEngine`;
- `InsightFaceBuffaloMEngine`.

**Почему принято:** adapter изолирует несовместимый preprocessing моделей, но не создаёт отдельную бизнес-логику для каждой модели.

### 4.4 Неизменяемая pipeline revision

Каждая версия pipeline получает собственный `pipeline_revision_id`, который фиксирует:

- detector и его версию;
- recognizer и его версию;
- checksum весов;
- preprocessing/alignment version;
- embedding dimension;
- normalization version.

Embeddings сравниваются только внутри одной `pipeline_revision_id`.

**Почему принято:** одинаковое имя модели не гарантирует совместимость embeddings после смены весов, detector-а или preprocessing. Revision предотвращает скрытое смешивание несовместимых векторов.

### 4.5 Режимы обработки

#### `active_only`

Production-режим: фотография обрабатывается только обслуживающим pipeline SPA.

#### `dual_benchmark`

Рекомендуемый пилотный режим: SFace и Buffalo M независимо выполняют полный
detection, preprocessing и embedding extraction на одной фотографии.

Клиентская выдача всё равно строится только по одному обслуживающему pipeline.

`dual_benchmark` не является обязательным режимом MVP и может выполняться
отдельным offline benchmark-ом.

**Почему принято:** `active_only` сохраняет производительность production, а
`dual_benchmark` рекомендуется только тогда, когда нужен честный online-срез на
одинаковых реальных данных без multi-model ensemble в клиентском поиске.

### 4.6 Безопасное переключение pipeline

**Статус: рекомендация.** Serving/pending migration нужна, только если в пилоте
действительно требуется менять pipeline без окна неполной выдачи. Базовый MVP
может работать с одной заранее выбранной serving revision.

Для SPA хранятся:

~~~text
serving_pipeline_revision
pending_pipeline_revision: nullable
processing_mode
~~~

Переключение выполняется так:

1. Админ выбирает новый pipeline как `pending`.
2. PostgreSQL создаёт jobs для отсутствующих состояний и embeddings.
3. Пока идёт миграция, новые фотографии обрабатываются serving и pending pipelines.
4. Coverage pending pipeline считается по состояниям `ready` и `no_faces`.
5. После полного покрытия, успешного прогрева модели и наличия калибровки для
   `pipeline_code` pending pipeline атомарно становится serving.
6. Старые embeddings можно удалить позже по отдельной подтверждённой операции.

Нельзя менять serving pipeline, если часть активного периода не имеет terminal
state `ready | no_faces` или для соответствующего `pipeline_code` отсутствуют
откалиброванные thresholds. Управление pending pipeline через админку является
рекомендацией; ту же операцию можно выполнить простым административным command.

**Почему принято:** мгновенное переключение создаёт период, когда часть новых или старых фотографий невозможно найти. Минимальная схема serving/pending устраняет эту дыру без сложного orchestration.

---

## 5. Модель данных лиц

### 5.1 Главное правило

Одна строка `photo_faces` означает:

> конкретная pipeline revision обнаружила конкретное лицо на конкретной фотографии.

SFace и Buffalo M создают независимые строки, даже если физически обнаружили одного человека.

Не создаётся общая сущность личности и не выполняется автоматическое связывание результатов разных detectors.

**Почему принято:** YuNet и SCRFD могут найти разное количество лиц и получить разные bbox/landmarks. Общая запись `detected_face` создавала бы ложное предположение об их взаимно-однозначном соответствии.

### 5.2 Основные таблицы

#### `spas`

~~~text
id
name
serving_pipeline_revision_id
pending_pipeline_revision_id
processing_mode
min_query_face_quality
created_at
updated_at
~~~

`pending_pipeline_revision_id` и изменяемый `processing_mode` нужны только при
включении рекомендуемых serving/pending или `dual_benchmark` flows. Минимальный
MVP может хранить только serving revision и фиксированный `active_only`.

#### `photos`

~~~text
id
spa_id
batch_id
captured_at
visit_date
original_path
preview_path
thumbnail_path
width
height
checksum_sha256
created_at
~~~

#### `pipeline_revisions`

~~~text
id
pipeline_code
detector_version
recognizer_version
weights_sha256
preprocessing_version
normalization_version
embedding_dim
created_at
~~~

#### `pipeline_thresholds`

~~~text
spa_id
pipeline_code: opencv_sface | insightface_buffalo_m
query_source: selfie | reference
threshold
calibration_id
calibrated_at

UNIQUE(spa_id, pipeline_code, query_source)
~~~

Threshold хранится на уровне типа модели и SPA, а не на уровне
`pipeline_revision_id`. Наличие `calibration_id` и `calibrated_at` означает, что
данная комбинация `spa_id + pipeline_code + query_source` откалибрована и может
использоваться для serving. Если калибровки нет, переключение блокируется, а
админке рекомендуется предложить запуск или регистрацию калибровки.

**Почему принято:** type-level threshold соответствует умеренному KISS и не
создаёт отдельную настройку для каждой revision. `calibration_id` сохраняет
происхождение значения без связывания threshold с revision.

#### `photo_pipeline_states`

~~~text
photo_id
pipeline_revision_id
status: pending | processing | ready | no_faces | failed
searchable_at
last_error

UNIQUE(photo_id, pipeline_revision_id)
~~~

`ready` означает, что обработка завершена и searchable face records созданы.
`no_faces` является успешным terminal state без найденных лиц. Coverage pipeline
считается как доля `ready + no_faces` среди ожидаемых фотографий; `failed` в
coverage не входит. `photos.searchable_at` не хранится: доступность фотографии
для текущего serving pipeline определяется по `photo_pipeline_states`.

**Почему принято:** отдельное состояние устраняет неоднозначность между «ещё не
обработано», «обработано без лиц» и «обработка завершилась ошибкой», не создавая
сложного workflow engine.

#### `photo_faces`

~~~text
id
photo_id
pipeline_revision_id
face_index
bbox_x
bbox_y
bbox_w
bbox_h
landmarks_json
detection_confidence
quality_score
blur_score
brightness_score
pose_yaw
pose_pitch
pose_roll
embedding vector
created_at

UNIQUE(photo_id, pipeline_revision_id, face_index)
~~~

Колонка `embedding` использует pgvector без ANN-индекса. Размерность проверяется adapter-ом относительно `pipeline_revisions.embedding_dim`.

**Почему принято:** одна таблица сохраняет простую модель данных при разных размерностях embeddings. Отсутствие ANN-индексов снимает требование иметь отдельный индекс для каждой размерности.

### 5.3 Никакой автоматической identity clustering

В MVP отсутствуют:

- person/identity clusters;
- cluster centroids;
- автоматическое объединение лиц одного человека;
- автоматическое связывание SFace и Buffalo M detections.

Результаты поиска только группируются и дедуплицируются по `photo_id`.

**Почему принято:** кластеризация может ошибочно объединить разных людей или разделить одного человека. При текущем размере отфильтрованной выборки она не нужна для скорости поиска.

---

## 6. Поиск по embeddings

### 6.1 Точный поиск pgvector

Поиск выполняется без HNSW и IVFFlat.

Последовательность:

~~~text
query embedding
→ WHERE pipeline_revision_id = serving pipeline
→ WHERE spa_id = selected SPA
→ WHERE captured_at входит в дату / visit / time window
→ точное cosine distance по оставшимся векторам
→ фильтр по calibrated threshold для SPA, pipeline code и query source
→ сортировка
→ группировка по photo_id
→ preview
~~~

Обычные B-tree индексы используются для `spa_id`, `captured_at`, `photo_id` и `pipeline_revision_id`.

**Почему принято:** даже при 10–15 SPA запрос ограничен одним SPA и коротким периодом. Exact search проще, детерминирован и не теряет recall, а ANN пока не решает измеримой проблемы.

### 6.2 Условия принятия совпадения

В MVP используются только:

~~~text
query_face_quality >= min_query_face_quality
AND
cosine_similarity >= threshold[spa_id][pipeline_code][query_source]
~~~

Threshold калибруется отдельно для:

- SFace selfie;
- SFace reference-camera;
- Buffalo M selfie;
- Buffalo M reference-camera.

Значения редактируются отдельно для каждого SPA в админке. Threshold не
привязывается к `pipeline_revision_id`.

### 6.3 Top-1 / top-2 margin не используется

`min_top1_top2_margin` удаляется из модели данных, админки и алгоритма поиска.

**Почему принято:** top-1 и top-2 могут быть двумя разными фотографиями одного и того же клиента. Маленький margin в таком случае подтверждает совпадение, а не опровергает его.

### 6.4 Multi-frame consistency

В MVP query embedding создаётся из одного лучшего reference-кадра.

Сравнение по двум лучшим кадрам является кандидатом на будущее и добавляется только если benchmark покажет недостаточную точность одного кадра.

**Почему принято:** второй embedding увеличивает CPU latency. Сначала необходимо измерить, даёт ли он значимый прирост качества на реальных кадрах.

---

## 7. Фоновая обработка без брокера очередей

### 7.1 Один BackgroundPhotoWorker

Обычные фотографии обрабатывает один отдельный процесс:

~~~text
забрать pending job из PostgreSQL
→ загрузить original
→ создать preview и thumbnail
→ запустить нужный FaceEngine
→ сохранить photo_faces
→ обновить photo_pipeline_states
→ перейти к следующей job
~~~

Worker обрабатывает одну фотографию за раз. Внутри одной операции
OpenCV/ONNX/OpenVINO могут использовать несколько CPU-ядер; конкретные cpuset и
thread limits являются deployment-рекомендацией из `IDEA_OS.md`, а не
требованием приложения.

**Почему принято:** один последовательный worker устраняет конкуренцию нескольких inference-процессов и проще диагностируется. При 1 500–3 000 фото в день его достаточность сначала проверяется benchmark-ом.

### 7.2 PostgreSQL как очередь фоновых jobs

**Статус: рекомендация.** Обязательная граница состоит в том, что background
processing остаётся в PostgreSQL и не требует внешнего broker-а. Развитая job
schema, автоматический recovery, fixed ordering и retry являются рекомендуемой
production-профильной реализацией, а не требованием MVP.

Рекомендуемая таблица:

#### `photo_processing_jobs`

~~~text
id
photo_id
pipeline_revision_id
job_type
status: pending | processing | completed | failed
attempts
next_attempt_at
locked_at
locked_by
last_error
created_at
started_at
finished_at

UNIQUE(photo_id, pipeline_revision_id, job_type)
~~~

Worker атомарно забирает одну job через транзакцию. Для развитого варианта
рекомендуется `FOR UPDATE SKIP LOCKED`, возврат зависшей `processing` job в
`pending` после timeout и ограниченное число retry. Более простой single-worker
MVP может использовать обычный transactional claim и ручной повтор failed jobs.

Для развитого варианта рекомендуется простое детерминированное правило выбора:

1. новые фотографии для serving pipeline;
2. недостающие embeddings pending pipeline;
3. `dual_benchmark` и массовая переобработка;
4. ограниченная порция cleanup-задач.

Это можно реализовать одним SQL `ORDER BY` без поля произвольного priority и без
отдельных очередей. Fixed ordering не является обязательным, пока в MVP нет
одновременного backlog разных классов jobs.

**Почему принято:** PostgreSQL уже является обязательной частью проекта и
достаточен для одного фонового consumer-а. Рекомендуемый фиксированный порядок
не позволяет массовой переобработке заблокировать новые фотографии, но не
требует внешнего broker-а, нескольких priority queues или scheduler-а.

### 7.3 Что обрабатывает тот же worker

**Статус: рекомендация.** При наличии соответствующих jobs тот же worker может
выполнять:

- первичную обработку фотографий;
- пересчёт missing embeddings;
- переобработку после смены pipeline;
- `dual_benchmark` jobs;
- периодическую очистку истёкших временных файлов и sessions.

В MVP допустимо реализовать только первичную обработку. Backfill, переобработка,
`dual_benchmark` и cleanup подключаются по фактической необходимости; отдельные
workers и очереди для них заранее не создаются.

**Почему принято:** если эти задачи появляются, один worker остаётся самым
простым местом их выполнения и не требует параллельных очередей на текущем
масштабе.

### 7.4 Условие масштабирования background processing

**Статус: рекомендация для следующего минимального шага, не требование MVP.**

Второй PostgreSQL-worker разрешено добавить, если выполняется хотя бы одно условие:

- `ingest_to_searchable_p95` устойчиво превышает целевое значение;
- возраст самой старой pending job растёт во время обычной дневной нагрузки;
- worker не успевает обработать суточный объём до следующего рабочего периода.

Если второй consumer действительно нужен, рекомендуется использовать ту же
таблицу и `SKIP LOCKED`; Redis/Celery для этого не требуются.

**Почему принято:** схема допускает простое горизонтальное увеличение числа consumers, но не оплачивает эту сложность заранее.

### 7.5 Идемпотентность worker

**Принятое архитектурное решение:** jobs выполняются по модели at-least-once, но
повтор одной комбинации `(photo_id, pipeline_revision_id, job_type)` должен
приводить к тому же итоговому состоянию без дублирования результатов.

Original и pipeline revision неизменяемы. Worker выполняет тяжёлую обработку вне
транзакции, а затем одной PostgreSQL-транзакцией проверяет актуальный
`locked_by = worker_id:claim_uuid`, полностью заменяет `photo_faces`, обновляет
`photo_pipeline_states` в `ready | no_faces` и помечает job как `completed`.
Повтор terminal job становится no-op; автоматический lease recovery остаётся
рекомендацией.

Preview и thumbnail сначала записываются в MinIO по детерминированному versioned
key, после чего key публикуется в БД. Возможный orphan безопасно удаляется позже;
distributed transaction и exactly-once infrastructure не требуются.

**Почему принято:** схема переживает crash и retry средствами уже выбранных
PostgreSQL и MinIO, не добавляя broker, coordinator или новый workflow engine.

---

## 8. RealtimeFaceService

### 8.1 Назначение

Отдельный синхронный HTTP-сервис обрабатывает:

- reference-кадры с промо-экранов;
- selfie/live-selfie запросы с сайта.

Сервис выполняет:

~~~text
validate image
→ select FaceEngine for SPA
→ detect and quality check
→ create query embedding
→ exact pgvector search
→ create search/promo session
→ return preview result
~~~

**Почему принято:** reference и selfie search являются короткими интерактивными операциями с одинаковым pipeline и одинаковыми требованиями к latency. Один сервис исключает дублирование моделей и логики.

### 8.2 Постоянно загруженные модели

RealtimeFaceService загружает SFace и Buffalo M при старте и выполняет тестовый inference до получения пользовательских запросов.

**Почему принято:** разные SPA могут одновременно использовать разные pipelines. Загрузка модели по первому запросу создаёт непредсказуемую задержку, поэтому обе модели должны быть заранее готовы.

### 8.3 Контракт SpaPromoClient

Локальный HDMI-display центрального сервера и отдельные клиенты остальных SPA
используют один логический контракт `SpaPromoClient`:

~~~text
захватить 3-5 кадров
→ локально выбрать лучший кадр
→ отправить один синхронный HTTPS request с spa_client_token
→ получить previews + QR + result_ttl
→ показать результат до истечения TTL
→ вернуться к локально закэшированной рекламе
~~~

`spa_client_token` является простым секретом клиента. Сервер хранит отображение
`token_hash -> spa_id`, определяет SPA только по token и не доверяет `spa_id` из
request body. Token передаётся в HTTP authorization header, не помещается в URL
и не записывается в application logs.

Ответ возвращается в том же HTTP request/response. SSE и WebSocket для этого
сценария не используются. При timeout или сетевой ошибке клиент отбрасывает
устаревший запрос, продолжает показывать рекламу и может повторить операцию только
со свежим кадром.

**Почему принято:** результат нужен только инициировавшему его клиенту и готовится
в рамках короткой синхронной операции. Request/response проще отдельного event
channel и исключает маршрутизацию событий между display-клиентами.

### 8.4 Concurrency и короткая очередь в памяти

Стартовая конфигурация RealtimeFaceService:

- один процесс;
- inference concurrency: 1;
- ограниченная FIFO-очередь в памяти;
- deadline для каждого запроса;
- устаревшие reference-запросы не обрабатываются;
- при перезапуске сервиса `SpaPromoClient` повторяет запрос только со свежим
  reference-кадром.

Это не durable job queue и не требует Redis.

**Почему принято:** reference-запрос полезен только несколько секунд. Сохранять устаревшие запросы в надёжной внешней очереди бессмысленно; ограниченная очередь нужна только для кратковременного столкновения запросов от разных SPA.

## 9. Метрики p50/p95/p99

Для проверки обязательных SLA достаточно сохранять данные для трёх базовых
показателей: `trigger_to_preview_p95`, `realtime_queue_wait_p95` и
`ingest_to_searchable_p95`. Детальная телеметрия ниже является рекомендацией и
не блокирует минимальный MVP.

### 9.1 Рекомендуемые realtime timestamps

Для каждого realtime-запроса сохраняются:

~~~text
triggered_at
received_at
processing_started_at
embedding_finished_at
search_finished_at
response_finished_at
displayed_at: nullable
status
spa_id
pipeline_revision_id
query_source
~~~

Из них рассчитываются:

- `network_to_server_ms`;
- `queue_wait_ms`;
- `inference_ms`;
- `vector_search_ms`;
- `server_total_ms`;
- `trigger_to_preview_ms`.

### 9.2 Рекомендуемые percentiles

Рекомендуется рассчитывать p50/p95/p99 в PostgreSQL через `percentile_cont` за
выбранный период и, когда это полезно, отдельно по SPA, pipeline и query source.

Не требуется отдельный Prometheus/Grafana stack для MVP.

**Почему принято:** PostgreSQL уже хранит события и способен вычислять
необходимые перцентили без обязательного отдельного monitoring stack. Разрезы
добавляются только тогда, когда помогают диагностировать измеримую проблему.

### 9.3 Рекомендуемые расширенные показатели

- `trigger_to_preview_p50/p95/p99`;
- `realtime_queue_wait_p50/p95/p99`;
- `inference_p50/p95/p99`;
- `vector_search_p50/p95/p99`;
- `ingest_to_searchable_p50/p95/p99`;
- oldest pending background job;
- доля rejected/expired realtime requests;
- coverage serving pipeline по `ready + no_faces`;
- доля `pending | processing | failed` по pipeline revision.

**Почему принято:** разделение этапов показывает реальный источник задержки: сеть, ожидание свободного сервиса, inference, поиск или background backlog.

---

## 10. Benchmark моделей

SFace и Buffalo M сравниваются на размеченных реальных данных SPA.

Нужны:

- genuine pairs: фотографии одного человека;
- impostor pairs: фотографии разных людей;
- site-selfie samples;
- reference-camera samples;
- сложные случаи: движение, плохой свет, pose, частичное перекрытие.

Метрики:

- search-level false accept rate;
- recall/TAR при заданном false accept rate;
- доля запросов без результата;
- latency p50/p95/p99;
- processing failures;
- влияние качества и размера лица.

Raw-значения `manual_false_positive_count` без числа поисков не используются как основная метрика.

Результат принятой калибровки получает `calibration_id` и записывает type-level
thresholds для конкретного SPA и query source через админку. Отдельная запись на
каждую pipeline revision не создаётся.

**Почему принято:** threshold и выбор модели нельзя надёжно определить по публичным benchmark-ам. Решение должно учитывать реальные камеры, освещение и фотографии проекта.

---

## 13. Админка

### 13.1 Минимальная админка

- batch upload с checksum и повторной отправкой;
- привязка к SPA и дате;
- базовый статус originals, preview и `photo_pipeline_states`;
- выбор serving pipeline для SPA;
- редактирование thresholds для каждого SPA.

### 13.2 Threshold settings

Администратор выбирает SPA и может изменить четыре type-level значения:

- SFace для `selfie`;
- SFace для `reference`;
- Buffalo M для `selfie`;
- Buffalo M для `reference`.

Для каждого значения показываются `calibration_id` и `calibrated_at`. Thresholds
не создаются и не редактируются отдельно для pipeline revisions. Если нужная
комбинация `pipeline_code + query_source` не откалибрована, переключение serving
pipeline блокируется и админка предлагает зарегистрировать или запустить
калибровку.

### 13.3 Рекомендуемое расширенное управление pipeline

Следующие возможности полезны для длительной эксплуатации, но не являются
требованием MVP:

- `pending_pipeline_revision`;
- UI control для `active_only` / `dual_benchmark`;
- coverage каждой pipeline revision по `ready + no_faces`;
- запуск reprocess missing states/embeddings;
- просмотр и повтор failed jobs;
- состояния моделей: missing/loading/warming/ready/error.

### 13.4 Рекомендуемая техническая диагностика

- p50/p95/p99 queue wait, inference и trigger-to-preview;
- число expired/rejected requests;
- текущая длина in-memory realtime queue;
- oldest background job;
- ingest-to-searchable p50/p95/p99;
- фактический CPU set RealtimeFaceService;
- число разрешённых inference threads.

Эти показатели можно сначала получать через SQL, logs и deployment diagnostics.
Отдельные UI-панели добавляются только при подтверждённой операционной пользе.

В админке нет кнопок pause/resume workers, priority, `reference_mode` и Redis TTL.

**Почему принято:** минимальная админка покрывает загрузку, serving pipeline и
обязательную настройку thresholds. Coverage, pending management, model states,
CPU sets, thread limits и богатые percentile-разрезы остаются рекомендациями и
не раздувают первый MVP.

---

## 14. Техническая приватность и доступ

Минимальная схема доступа:

~~~text
spa_id + visit date/time window
+
короткоживущая search/promo session
+
selfie/reference match
~~~

Требования:

- preview с watermark;
- маленькие preview на публичном экране;
- оригиналы только после оплаты;
- короткоживущие signed download URLs через публичный HTTPS endpoint backend;
- TTL для QR/search sessions;
- временные selfie/reference-файлы удаляются после истечения session;
- все запросы имеют rate limit;
- каждый `SpaPromoClient` аутентифицируется своим простым
  `spa_client_token`, по которому сервер определяет `spa_id`;
- локальный Chromium запускается непривилегированным OS-user `display` со
  штатным sandbox; флаг `--no-sandbox` запрещён;
- административные SSH, `sudo`, Docker и deployment secrets доступны только
  OS-user `facemoment`;
- PostgreSQL и MinIO доступны только внутри server/Docker network и не
  публикуются наружу;
- preview и originals отдаются через HTTPS backend; signed URL не открывает
  прямой внешний доступ к MinIO;
- visit code/браслет/чек может быть добавлен как дополнительное ограничение поиска.

**Почему принято:** face similarity не должна быть единственным механизмом
доступа к оригиналам. Ограничение области поиска одновременно снижает риск
неправильной выдачи и ускоряет exact search. Простой client token создаёт
необходимую привязку display к SPA без mTLS, VLAN или сложного RBAC.

---

## 15. Что входит в MVP приложения

1. Минимальная админка, batch upload и type-level thresholds для каждого SPA.
2. PostgreSQL + pgvector exact search.
3. MinIO/S3-compatible storage без внешней публикации.
4. `photo_pipeline_states` как источник searchable state и coverage.
5. Один PostgreSQL-backed `BackgroundPhotoWorker`.
6. Один синхронный `RealtimeFaceService`.
7. Синхронный HTTP contract для `SpaPromoClient` и простой
   `spa_client_token -> spa_id` mapping.
8. Постоянно загруженные SFace и Buffalo M.
9. `FaceEngine` adapters с родным preprocessing.
10. Pipeline-specific `photo_faces`.
11. Один выбранный serving pipeline на уровне SPA и режим `active_only`.
12. Поиск по selfie/live-selfie.
13. Галерея preview с watermark.
14. Оплата и выдача signed download URL через HTTPS backend.
15. Минимальные p95-метрики для realtime queue, trigger-to-preview и
    ingest-to-searchable.
16. Benchmark SFace и Buffalo M на реальных данных.

### 15.1 Рекомендуется после минимального MVP

- `dual_benchmark` как online-режим;
- serving/pending migration и backfill;
- fixed ordering разных классов jobs;
- автоматический recovery зависших jobs и retry;
- benchmark, backfill и cleanup в одном worker;
- масштабирование consumers через `SKIP LOCKED`;
- coverage/model-state/pending controls в админке;
- богатые p50/p95/p99 разрезы, CPU sets и thread-limit diagnostics.

Эти рекомендации можно включить раньше только при подтверждённой пользе для
пилота; они не являются условиями готовности базового MVP.

## 16. Что осознанно не входит в MVP приложения

- Redis;
- Celery, RQ, Arq и другие queue frameworks;
- несколько priority queues;
- pause/resume background processing;
- `reference_mode` и `ResourceManager`;
- динамическая приоритизация CPU;
- HNSW и IVFFlat;
- автоматическая identity clustering;
- cluster centroids;
- top-1/top-2 margin;
- multi-model ensemble в клиентской выдаче;
- distributed scheduler;
- собственное обучение face-recognition модели;
- сложная CRM и ретушь фотографий.

**Почему принято:** ни один из этих механизмов пока не решает подтверждённый bottleneck. Их добавление увеличит стоимость разработки, тестирования и эксплуатации.

## 17. Условия пересмотра архитектуры приложения

| Текущее решение | Когда разрешено пересмотреть | Следующий минимальный шаг |
|---|---|---|
| Exact pgvector search | vector_search_p95 становится значимой частью SLA после фильтрации | исследовать HNSW на реальном наборе |
| PostgreSQL jobs | PostgreSQL polling/locking подтверждённо ограничивает throughput | рассмотреть простой broker |
| Один лучший reference-кадр | качество поиска не достигает целевого FAR/recall | проверить fusion двух кадров |
| Нет identity clustering | появляется подтверждённая продуктовая задача идентичности между визитами | проектировать clustering отдельно |

**Почему принято:** таблица задаёт измеримые границы. Агенты не должны предлагать следующий уровень сложности до выполнения соответствующего условия.

## 18. Основные технические риски приложения

### 18.1 Одновременные realtime-запросы

10–15 SPA могут отправить reference/selfie запросы одновременно. Риск контролируется bounded in-memory queue, deadline и метрикой queue wait.

### 18.2 Задержка загрузки коммерческих фотографий

Если фотографии загружаются в конце дня, промо-поиск не сможет найти их при выходе клиента. Необходимо согласовать workflow фотографа и измерять ingest-to-searchable.

### 18.3 Качество камеры

Плохой свет, motion blur, pose и несколько людей могут влиять сильнее, чем выбор между SFace и Buffalo M. Камера, освещение и зона захвата должны тестироваться вместе с моделями.

### 18.4 Ошибочный threshold

Слишком низкий threshold показывает чужие фотографии, слишком высокий пропускает
нужные. Значения нельзя брать только из документации моделей; они калибруются на
данных проекта отдельно по SPA, pipeline code и query source и редактируются в
админке.

### 18.5 Переключение pipeline

Если serving/pending migration включена, неполное покрытие pending pipeline
создаёт missing results. Serving меняется только после coverage по
`ready + no_faces` и проверки type-level calibration.

## 19. Финальная архитектурная формула приложения

~~~text
Python/FastAPI backend
+
PostgreSQL + pgvector exact search
+
MinIO/S3-compatible storage
+
одна PostgreSQL-таблица фоновых jobs
+
один последовательный BackgroundPhotoWorker
+
один синхронный RealtimeFaceService
+
синхронный HTTP SpaPromoClient с простым spa_client_token
+
facemoment для администрирования + непривилегированный display с Chromium sandbox
+
SFace и Buffalo M с родным preprocessing
+
pipeline-specific face records и photo_pipeline_states
+
type-level thresholds для каждого SPA
+
никаких Redis/Celery/priority/pause/ANN/clustering/margin
+
развитые jobs, pending management, CPU diagnostics и богатые percentiles
остаются рекомендациями
~~~

Главный принцип:

> Сначала простая измеримая система. Новая инфраструктурная сложность добавляется только после того, как текущий bottleneck подтверждён реальными метриками.
