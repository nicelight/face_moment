# Face Moment: сервер, ОС и display/kiosk

Обновлено: 2026-07-17

## 0. Статус документа

Этот документ фиксирует инфраструктурную часть концепции: центральный сервер,
серверную ОС, базовую настройку, Docker, рекомендации по CPU isolation, storage,
backup, hardware и display/kiosk с рекламой.

Первый pilot — one-SPA smoke test с тестировщиками. Топология на 10–15 SPA
является target capacity после pilot, а
payment/download originals — post-pilot product flow.

Продуктовая логика приложения, face-recognition pipeline, поиск, модель данных,
админка, оплата и выдача оригиналов вынесены в `IDEA_APP.md`.

Используются четыре статуса:

- **Требование** — поведение, которое система обязана обеспечивать.
- **Принятое архитектурное решение** — текущий способ реализации, выбранный осознанно.
- **Рекомендация** — предпочтительная стартовая реализация, которую можно
  упростить или заменить без изменения требований и принятых архитектурных
  границ.
- **Кандидат на будущее** — возможное усложнение, которое нельзя добавлять без измеримой необходимости.

### Правило для разработчиков и AI-агентов

Серверную архитектуру нельзя усложнять Redis, Celery, RQ, Kafka,
распределённым scheduler, Kubernetes, отдельными inference-серверами в каждом SPA,
GPU-инфраструктурой или внешним monitoring stack только потому, что они типичны
для похожих систем.

Архитектуру разрешено усложнять только если одновременно выполнены два условия:

1. Текущая реализация не выполняет зафиксированный SLA или создаёт подтверждённую проблему.
2. Проблема подтверждена метриками, benchmark-ом или эксплуатационными данными.

**Почему принято:** проект следует KISS. Сложность добавляется для решения уже
наблюдаемой проблемы, а не для гипотетического будущего масштаба.

Рекомендации не являются MVP gates. Их разрешено не реализовывать, если более
простое deployment-решение сохраняет работоспособность, корректность и
наблюдаемость базовых SLA.

---

## 1. Deployment-контекст

First pilot profile:

- один центральный CPU-only сервер в РФ;
- одна пока не выбранная SPA и один `SpaPromoClient`;
- один Promo display с автоматическим sensor-triggered capture;
- выбранная группа тестировщиков;
- preview и QR continuation без payment/download.

После выбора площадки один и тот же logical client может работать на локальном
HDMI центрального сервера или на отдельном remote display-компьютере. Конкретный
вариант не является Product Brief gate.

Target capacity после pilot:

- один центральный сервер в РФ;
- 10-15 SPA;
- 150-200 коммерческих фотографий в день на один SPA;
- суммарно 1 500-3 000 фотографий в день;
- 45 000-90 000 фотографий за 30 дней;
- хранение истории минимум один месяц;
- inference выполняется на центральном сервере без внешних cloud face-recognition API.

На центральном сервере работают:

- backend API и админка;
- PostgreSQL + pgvector;
- MinIO/S3-compatible object storage;
- один `BackgroundPhotoWorker`;
- один `RealtimeFaceService`;
- выбранный serving face pipeline; второй pipeline — только для benchmark или
  post-pilot multi-SPA режима;
- сервис выдачи preview и QR continuation;
- KDE Plasma и один локальный `SpaPromoClient` на подключённом HDMI-мониторе.

Выдача paid originals через signed URLs добавляется после pilot.

Центральный сервер по HDMI может обслуживать только один физически подключённый
экран. При расширении в других SPA работают отдельные `SpaPromoClient` с камерой,
удалённым датчиком движения и экраном. Каждый client постоянно получает видеопоток,
хранит короткий кольцевой буфер, по сигналу датчика формирует настраиваемую
reference-серию и отправляет её синхронным HTTPS request в
`RealtimeFaceService`. Полный capture/search/display алгоритм является частью
[IDEA_APP.md](IDEA_APP.md), разделы 6.4–6.5 и 8.3–8.4; инфраструктурный документ
его не дублирует.

Каждому `SpaPromoClient` выдаётся простой `spa_client_token`. Сервер хранит
отображение `token_hash -> spa_id` и не принимает `spa_id` из request body как
источник истины.

**Почему принято:** централизованная схема упрощает развёртывание, обновление
моделей, мониторинг, резервное копирование и поддержку 10-15 объектов. Текущий
объём не требует отдельного inference-сервера в каждом SPA. Одинаковый
request/response contract сохраняет простую топологию для локального HDMI-display
и удалённых SPA без отдельного event transport.

---

## 2. Display mode вместо kiosk mode

Promo display выполняет только:

- захват кадров;
- показ рекламы между поисковыми событиями;
- показ найденных low-quality preview без watermark;
- показ QR-кода;
- автоматическое восстановление соединения после сетевого сбоя.

На display нет сенсорной навигации, оплаты и скачивания. В первом pilot телефон
проверяет только QR continuation page; payment и выдача originals выполняются
после pilot.

**Почему принято:** телефон клиента уже предоставляет привычный интерфейс для
выбора, оплаты и скачивания. Полноценный kiosk mode не даёт
достаточной пользы для своей сложности.

### 2.1 Display-приложение

Promo-интерфейс реализуется как web-приложение, открытое в Chromium на весь
экран.

Поведение:

~~~text
обычный режим
-> показ рекламных слайдов или видео
-> сигнал удалённого датчика движения
-> показать prePromo и воспроизвести доступный preChime
-> сформировать reference-серию из постоянного видеопотока
-> отправить синхронный HTTPS request с spa_client_token
-> при успехе получить четыре previews + QR continuation URL/token + qr_expires_at
-> воспроизвести доступный Chime и показать Promo
-> истекло RESULT_DISPLAY_SECONDS
-> возврат к рекламе
~~~

Четыре независимые настройки не объединяются в один `result_ttl`:

~~~text
RESULT_DISPLAY_SECONDS=20
CAPTURE_COOLDOWN_SECONDS=60
QR_SESSION_TTL_SECONDS=900
BROWSER_SESSION_IDLE_TTL_SECONDS=1800
~~~

Это стартовые configurable defaults. Истечение display duration не завершает QR
session, а cooldown независимо ограничивает следующий успешный capture.

`SpaPromoClient` самостоятельно инициирует каждый поиск и получает результат тем
же синхронным HTTP request/response. SSE и WebSocket не используются. При timeout
или потере сети client отбрасывает устаревший request, продолжает показывать
локально закэшированную рекламу и повторяет поиск только со свежим кадром.

**Почему принято:** web-приложение проще обновлять централизованно, чем отдельное
desktop-приложение. Результат нужен только инициировавшему его display, поэтому
синхронный request/response проще отдельного event channel и не требует
маршрутизации событий между SPA.

### 2.2 Поведение при нескольких лицах

Из reference-серии выбирается до пяти лучших face detections независимо от
того, принадлежат ли они разным людям или одному человеку на разных кадрах.
Tracking и дедупликация людей между кадрами не выполняются. Каждая detection
последовательно запускается на поиск; итоговый Promo показывается только после
формирования четырёх уникальных `photo_id`. Точный candidate-pool и pHash
алгоритм определён в [IDEA_APP.md](IDEA_APP.md), раздел 6.5.

Это best-effort group search: один физический человек может занять несколько
detection slots, а полное покрытие каждого участника группы не гарантируется.
Такое поведение принято для первого pilot и не требует изменения текущего
алгоритма. `N` на phone landing является union уникальных `photo_id`, прошедших
обычный calibrated threshold для обработанных selected detections.

Если четыре фотографии не найдены, prePromo без дополнительного звука
возвращается к рекламе, cooldown не запускается и новый capture снова разрешён.

---

## 3. Серверная ОС и базовая конфигурация

### 3.1 Kubuntu LTS

Серверная ОС — Kubuntu 26.04 LTS с KDE Plasma.

KDE используется для:

- графической установки и первоначальной настройки неподготовленным человеком;
- проверки сети, HDMI, звука, камеры и браузера;
- организации первого удалённого доступа;
- работы локального display-клиента на HDMI-мониторе.

Дополнительное потребление KDE порядка нескольких гигабайт RAM допустимо для
сервера с 64 GB RAM.

**Почему принято:** сервер физически разворачивает неподготовленный пользователь,
а монитор является частью продукта. Kubuntu уменьшает риск ошибок первоначальной
установки и одновременно предоставляет готовую графическую среду для
display-приложения.

### 3.2 Два системных пользователя

Используются ровно два обычных пользователя системы:

1. `facemoment`
   - SSH и удалённый доступ;
   - `sudo`;
   - управление Docker;
   - доступ к deployment-конфигурации и server secrets;
   - без autologin и без запуска Chromium/display-приложения.

2. `display`
   - автоматический вход в KDE;
   - запуск Chromium/display-приложения;
   - доступ к камере и локальному `spa_client_token`;
   - без `sudo`, SSH, Docker group и доступа к deployment-конфигурации или
     server secrets.

Дополнительные системные пользователи для приложения не создаются.

**Почему принято:** один дополнительный непривилегированный user создаёт простую
OS-level границу. Компрометация Chromium остаётся в пределах `display` и не даёт
доступ к `sudo`, Docker socket, SSH или secrets центрального сервера.

### 3.3 Независимый запуск Docker

Устанавливается Docker Engine, а не Docker Desktop.

`docker.service` и `containerd.service` запускаются systemd при загрузке ОС до
входа пользователя в KDE. Все постоянные контейнеры имеют Compose policy:

~~~yaml
restart: unless-stopped
~~~

После первоначального `docker compose up -d` backend, PostgreSQL, MinIO,
`BackgroundPhotoWorker` и `RealtimeFaceService` запускаются независимо от
графической сессии.

Падение или перезапуск KDE/Chromium не должен останавливать серверные контейнеры.

**Почему принято:** графическая сессия нужна только для локального display и
обслуживания. Backend должен начать работу сразу после загрузки ОС и продолжать
работу независимо от состояния GUI.

### 3.4 Автоматический display-сеанс

Настраиваются:

- автоматический вход пользователя `display` через SDDM;
- user-level systemd service для запуска Chromium;
- Chromium на весь экран с display URL данного SPA;
- Chromium запускается с включённым штатным sandbox; флаг `--no-sandbox`
  запрещён;
- `Restart=always` и короткая задержка перезапуска браузера;
- отключение первого запуска, crash bubble и лишних диалогов браузера;
- отключение сна, suspend, блокировки экрана и гашения HDMI;
- автоматическое восстановление display-страницы после сетевой ошибки.

Так как Kubuntu 26.04 использует Wayland, управление гашением экрана выполняется
через Plasma Power Management и системные sleep targets, а не через устаревший
`xset`.

**Почему принято:** Chromium может упасть или потерять соединение, но display
должен восстанавливаться без участия локального пользователя.

### 3.5 Минимальная network/access configuration

Стартовая конфигурация:

- host firewall использует default deny для входящих соединений;
- наружу открыты только TCP 443 для HTTPS и TCP 22 для SSH;
- SSH разрешает вход только по ключу, password authentication отключён;
- PostgreSQL, MinIO и внутренние порты контейнеров не публикуются на внешнем
  network interface и доступны только через internal Docker network;
- backend API, `RealtimeFaceService` и previews доступны через один внешний
  HTTPS entry point; signed download endpoint является post-pilot;
- `spa_client_token` передаётся в authorization header, хранится на сервере в
  виде hash и не попадает в URL или application logs;
- diagnostic route отделён от Promo/QR routes;
- diagnostic objects имеют обязательный 90-day lifecycle;
- Docker daemon/API не публикуется наружу.

Сохраняются Kubuntu, Chromium и autologin пользователя `display`. Административные
операции выполняются только пользователем `facemoment`. В MVP не добавляются
другие Unix users, mTLS, VLAN, сложный RBAC или headless-топология.

**Почему принято:** разделение `facemoment`/`display`, единый HTTPS entry point
и простой per-client token сохраняют понятную network/process topology без
дополнительной инфраструктуры.

---

## 4. CPU, процессы и рекомендуемая изоляция

### 4.1 Минимальное разделение процессов

Система не разбивается на множество микросервисов. Отдельными процессами
выделяются только:

1. backend;
2. `BackgroundPhotoWorker`;
3. `RealtimeFaceService`.

**Почему принято:** отдельные процессы нужны для независимого жизненного цикла
моделей и позволяют применить CPU isolation, если она потребуется. Дальнейшее
дробление не даёт измеримой пользы на текущем масштабе.

### 4.2 Рекомендуемый CPU isolation profile

**Статус: рекомендация, не требование MVP.** Конкретная CPU-топология выбирается
по benchmark на фактическом hardware. Пилотная отправная точка:

- процессор класса Intel Core i5-13400 с 10 физическими ядрами;
- realtime CPU set: 2 физических P-core и оба их Hyper-Thread для
  `RealtimeFaceService`;
- background CPU set: остальные P-core и E-core для worker, backend, PostgreSQL,
  MinIO и Chromium;
- realtime и background CPU sets не пересекаются;
- Docker Compose `cpuset` рекомендуется задавать всем контейнерам, а не только
  `RealtimeFaceService`;
- internal thread pools OpenCV, ONNX Runtime, OpenVINO, OpenMP и BLAS
  рекомендуется ограничивать числом logical CPU соответствующего set.

CPU-набор задаётся deployment-конфигурацией и может быть изменён с перезапуском
процессов без изменения кода. Точное число P-core, наличие Hyper-Thread и сами
CPU IDs не являются application contract.

**Почему принято:** рекомендуемое статическое разделение может улучшить
предсказуемость realtime latency без остановки background worker, priority
scheduler, Redis-флагов и кооперативной паузы. Если baseline без pinning уже
выполняет SLA, дополнительная настройка не обязательна.

### 4.3 Никакой приоритизации и остановки процессов

В системе отсутствуют:

- `reference_mode`;
- pause/resume фонового worker-а;
- priority jobs;
- hard preemption;
- `ResourceManager`;
- Redis-флаги управления CPU.

Background worker продолжает работу во время reference-запроса. Если
рекомендуемый isolation profile включён, background-процессы не используют
realtime CPU set.

**Почему принято:** при необходимости статическая CPU isolation решает задачу
проще динамического управления. Динамическая приоритизация добавляла бы race
conditions, зависшие паузы и сложное восстановление jobs.

### 4.4 Рекомендуемая настройка host и GUI

Если CPU isolation включена, рекомендуется:

- назначить `RealtimeFaceService` realtime CPU set через Docker `cpuset`;
- назначить worker, backend, PostgreSQL и MinIO background CPU set через Docker
  `cpuset`;
- назначить Chromium background CPU set через отдельную `CPUAffinity` в
  user-level systemd service;
- ограничивать остальные host/GUI-процессы через systemd `AllowedCPUs` или
  `CPUAffinity` только если benchmark показывает их влияние на latency.

Более строгая kernel isolation рассматривается только при подтверждённом
нарушении latency SLA.

**Почему принято:** непересекающиеся sets устраняют ложное предположение, что
один `cpuset` автоматически резервирует CPU от остальных процессов. При этом
полная kernel isolation и обязательное ограничение всей KDE-сессии для MVP
остаются избыточными.

### 4.5 Условия масштабирования

Перераспределение CPU или второй экземпляр `RealtimeFaceService` разрешены, если:

- `realtime_queue_wait_p95` устойчиво превышает 2 секунды;
- configured search deadline регулярно исчерпывается;
- сервис регулярно отклоняет запросы из-за заполнения in-memory queue.

Второй PostgreSQL-worker разрешено добавить, если выполняется хотя бы одно
условие:

- `ingest_to_searchable_p95` устойчиво превышает целевое значение;
- возраст самой старой pending job растёт во время обычной дневной нагрузки;
- worker не успевает обработать суточный объём до следующего рабочего периода.

**Почему принято:** масштабирование должно происходить по измеренным очередям и
backlog, а не заранее.

---

## 5. Storage и backup

### 5.1 Расчёт центрального объёма

~~~text
45 000-90 000 фото в месяц
~~~

Это target-capacity оценка для 10–15 SPA, а не storage gate первого pilot.
Оценка только для originals:

| Средний размер | 45 000 фото | 90 000 фото |
|---:|---:|---:|
| 5 MB | 225 GB | 450 GB |
| 10 MB | 450 GB | 900 GB |
| 15 MB | 675 GB | 1.35 TB |
| 25 MB | 1.125 TB | 2.25 TB |

Дополнительно нужны preview, thumbnails, БД, временные файлы, логи и свободное
место для стабильной работы.

2 TB больше не считается гарантированно достаточным объёмом для 10-15 SPA.
Стартовый ориентир — не менее 4 TB usable primary storage с уточнением после
измерения реального среднего размера фотографии.

**Почему принято:** прежняя оценка 2 TB относилась к одному SPA. Центральный
сервер увеличивает месячный объём до 15 раз.

### 5.2 Object storage

Originals, previews и thumbnails хранятся в MinIO или совместимом S3 object
storage на центральном сервере.

PostgreSQL хранит только object keys и метаданные.

**Почему принято:** object storage упрощает атомарную загрузку, lifecycle, выдачу
короткоживущих signed URLs и возможный перенос файлов на отдельное хранилище без
изменения бизнес-логики.

### 5.3 Diagnostic storage первого pilot

Raw reference series, normalized images, face crops и screenshot Promo хранятся
в отдельном object-storage prefix. PostgreSQL хранит versioned manifest,
`diagnostic_session_id/correlation_id`, timestamps и индексируемые annotations.

Diagnostic objects автоматически удаляются через 90 дней. Их фактический объём
измеряется отдельно и учитывается при sizing pilot storage. Полезный case можно
вручную перенести в calibration/benchmark dataset.

### 5.4 Резервная копия

Backup originals и PostgreSQL должен находиться на другом физическом носителе
или сервере. MinIO на одном диске не является резервной копией.

Diagnostic data не включается в долгоживущий backup из-за 90-day lifecycle.

**Почему принято:** центральный сервер является единой точкой хранения для
10-15 SPA; отказ одного NVMe не должен уничтожить все коммерческие оригиналы.

---

## 6. Hardware

Target deployment reference для 10–15 SPA:

~~~text
Intel Core i5-13400 или CPU не слабее
64 GB RAM рекомендуется для центрального сервера
не менее 4 TB usable NVMe для primary storage
отдельное backup storage
Kubuntu 26.04 LTS
PostgreSQL + pgvector
MinIO
ONNX Runtime / OpenVINO / OpenCV / InsightFace
без GPU на старте
~~~

32 GB RAM допустимы для раннего прототипа, но не фиксируются как целевая
production-конфигурация на 10-15 SPA.

Для one-SPA pilot точные CPU, RAM и storage подтверждаются benchmark и sizing;
4 TB не является обязательным pilot gate.

### 6.1 Display/capture baseline первого pilot

- 43-inch landscape display;
- 16:9 и logical viewport 1920x1080;
- capture distance 3–5 метров;
- exact camera, lens, passage sensor и lighting выбираются после обследования
  площадки и проверки face size, blur, pose и exposure.

**Почему принято:** CPU-only сервер достаточен для проверки текущего объёма, а
окончательный размер CPU/RAM определяется по `ingest_to_searchable` и realtime
percentiles. GPU не добавляется до подтверждения CPU bottleneck-а.

---

## 7. Операционные метрики

Product acceptance metric первого pilot:

~~~text
reference_ready_to_qr_ms =
    qr_fully_visible_at - reference_series_ready_at
~~~

Минимум 19 из 20 ожидаемо успешных попыток должны иметь
`reference_ready_to_qr_ms < 10_000`. `trigger_to_preview` остаётся отдельной
end-to-end diagnostic metric и не подменяет этот anchor.

Минимально обязательны также `realtime_queue_wait_p95`,
`ingest_to_searchable_p95` и контроль свободного места. Один correlation ID
связывает timestamps:

~~~text
sensor_triggered_at
reference_series_ready_at
request_sent_at
received_at
processing_started_at
response_finished_at
response_received_at
qr_fully_visible_at
~~~

Расширенный набор:

- `reference_ready_to_qr_p50/p95/p99`;
- `trigger_to_preview_p50/p95/p99`;
- `realtime_queue_wait_p50/p95/p99`;
- `ingest_to_searchable_p50/p95/p99`;
- oldest pending background job;
- доля rejected/expired realtime requests;
- coverage serving pipeline по `ready + no_faces`;
- доля `pending | processing | failed` по pipeline revision;
- фактический CPU set `RealtimeFaceService`;
- число разрешённых inference threads;
- свободное место primary storage и backup storage;
- объём diagnostic storage и число bundles, ожидающих 90-day deletion.

Рекомендуется рассчитывать p50/p95/p99 в PostgreSQL через `percentile_cont` за
выбранный период и добавлять разрезы по SPA, pipeline и query source только при
диагностической необходимости.

Не требуется отдельный Prometheus/Grafana stack для MVP.

**Почему принято:** PostgreSQL уже хранит события и способен вычислять
рекомендуемые перцентили. Богатые разрезы и отдельный monitoring stack
добавляются позже только при появлении эксплуатационной необходимости.

---

## 8. Что входит в MVP сервера и display

1. Один центральный сервер и одна pilot SPA.
2. Kubuntu 26.04 LTS с KDE Plasma.
3. Пользователь `facemoment` для SSH, `sudo` и Docker без autologin.
4. Непривилегированный пользователь `display` с autologin и Chromium sandbox.
5. Docker Engine с независимым автозапуском контейнеров через systemd.
6. PostgreSQL + pgvector.
7. MinIO/S3-compatible storage без внешней публикации.
8. Один `BackgroundPhotoWorker`.
9. Один `RealtimeFaceService`.
10. Один `SpaPromoClient` на локальном HDMI или отдельном remote client после
    выбора pilot-площадки.
11. Постоянный локальный видеопоток и автоматическая sensor-triggered
    reference-серия для участников pilot.
12. Простой `spa_client_token -> spa_id` mapping.
13. Только HTTPS и key-only SSH снаружи; PostgreSQL, MinIO и Docker API закрыты.
14. Best-effort group search без tracking и гарантии полного покрытия.
15. Chromium на весь экран, реклама между результатами, четыре low-quality
    preview без watermark и QR continuation.
16. Независимые display, cooldown, QR и browser idle timers.
17. Diagnostic storage с retention 90 дней.
18. Acceptance `<10 s` от `reference_series_ready_at` до fully visible QR для
    минимум 19 из 20 попыток.
19. Автоматическое восстановление Chromium/display после сбоя.
20. Отдельное backup storage для коммерческих originals и PostgreSQL.

### 8.1 Рекомендуется после базового запуска

- reference profile с двумя P-core и их Hyper-Thread для realtime;
- непересекающиеся realtime/background CPU sets;
- Docker `cpuset` для всех контейнеров;
- thread limits OpenCV, ONNX Runtime, OpenVINO, OpenMP и BLAS;
- отдельная `CPUAffinity` Chromium;
- p50/p95/p99 по расширенным разрезам, отображение CPU sets и thread limits.

Эти настройки применяются по результатам benchmark и не являются условиями
готовности базового MVP.

---

## 9. Что осознанно не входит в MVP сервера и display

- публичный rollout на обычных посетителях;
- deployment сразу на 10–15 SPA;
- payment, receipt, refund и actual original download;
- tracking и дедупликация физических людей между frames;
- гарантия полного group coverage;
- watermarking preview;
- Docker Desktop;
- Kubernetes;
- distributed scheduler;
- Redis как coordination layer;
- Celery/RQ/Arq workers;
- несколько priority queues;
- pause/resume background processing;
- `reference_mode` и `ResourceManager`;
- динамическая приоритизация CPU;
- отдельный inference-сервер в каждом SPA;
- GPU-инфраструктура;
- полноценный kiosk mode;
- оплата и скачивание на promo display;
- дополнительные системные пользователи кроме `facemoment` и `display`;
- mTLS, VLAN и сложный RBAC;
- headless-топология центрального сервера;
- SSE или WebSocket для доставки результатов promo search;
- полная изоляция всей KDE-сессии через cgroup partitions;
- обязательный Prometheus/Grafana stack в MVP.

**Почему принято:** ни один из этих механизмов пока не решает подтверждённый
bottleneck. Их добавление увеличит стоимость разработки, тестирования и
эксплуатации.

---

## 10. Условия пересмотра инфраструктуры

| Текущее решение | Когда разрешено пересмотреть | Следующий минимальный шаг |
|---|---|---|
| Один realtime instance, CPU profile подбирается benchmark-ом | queue wait p95 > 2 s, регулярный search deadline exhaustion или bounded queue rejection | скорректировать CPU sets; затем рассмотреть второй instance |
| Один background worker | растёт oldest pending job или ingest-to-searchable p95 | рекомендовать второй PostgreSQL consumer с `SKIP LOCKED` |
| PostgreSQL jobs | PostgreSQL polling/locking подтверждённо ограничивает throughput | рассмотреть простой broker |
| Один центральный сервер | доступность одного узла не соответствует требуемому SLA | добавить standby/репликацию |
| CPU-only inference | CPU не выполняет SLA после настройки thread pools и масштабирования | исследовать GPU |
| PostgreSQL percentiles без Grafana | эксплуатация требует алертов, dashboard history и внешнего наблюдения | добавить monitoring stack |

**Почему принято:** таблица задаёт измеримые границы. Агенты не должны предлагать
следующий уровень сложности до выполнения соответствующего условия.

---

## 11. Основные инфраструктурные риски

### 11.1 Один центральный сервер

Отказ сервера влияет на все SPA. Обязательны мониторинг диска,
автоматический restart процессов и документированный recovery procedure.

### 11.2 Локальная графическая сессия

Обновление Plasma, Chromium или видеодрайвера может нарушить показ на локальном
HDMI-мониторе, но не должно останавливать Docker-сервисы. Display-сеанс должен
проверяться после системных обновлений.

### 11.3 Задержка загрузки коммерческих фотографий

Если фотографии загружаются в конце дня, promo display не сможет показать
релевантные результаты при выходе клиента. Нужно согласовать workflow фотографа
и измерять `ingest_to_searchable`.

### 11.4 Качество камеры и зоны захвата

Плохой свет, motion blur, pose и несколько людей могут влиять сильнее, чем выбор
между SFace и Buffalo M. Камера, освещение и зона захвата должны тестироваться
вместе с моделями.

### 11.5 Storage exhaustion

Центральный сервер хранит данные всех SPA. Необходимо контролировать свободное
место primary storage, backup storage, diagnostic bundles, БД, временных файлов
и логов.

### 11.6 Best-effort group selection

Один человек может занять несколько detection slots, а другой — не попасть в
search. Это принято для pilot, но требует явного UX, ручной annotation и не даёт
права обещать полное покрытие группы.

---

## 12. Финальная инфраструктурная формула

~~~text
один central server + одна pilot SPA
+
Kubuntu 26.04 LTS и два пользователя: facemoment + display
+
независимый автозапуск Docker Engine
+
PostgreSQL + pgvector
+
MinIO/S3-compatible storage
+
отдельное backup storage
+
один BackgroundPhotoWorker
+
один RealtimeFaceService
+
один локальный или remote SpaPromoClient
+
синхронный HTTPS request/response с простым spa_client_token
+
automatic sensor capture + best-effort group search
+
четыре low-quality preview без watermark + QR continuation
+
90-day diagnostic storage
+
независимые display/cooldown/QR/browser timers
+
<10 секунд от reference_series_ready_at до fully visible QR
+
PostgreSQL и MinIO только во внутренней сети; снаружи HTTPS и key-only SSH
+
Chromium display с рекламой, preview и QR
+
штатный Chromium sandbox без --no-sandbox
+
точная CPU topology, cpuset, thread limits, Chromium CPUAffinity и богатые
percentiles остаются рекомендациями
+
никаких Redis/Celery/priority/pause/Kubernetes/GPU на старте
~~~

10–15 SPA остаются target capacity после успешного pilot и не являются его
acceptance gate.

Главный принцип:

> Сначала простая измеримая система. Новая инфраструктурная сложность добавляется
> только после того, как текущий bottleneck подтверждён реальными метриками.
