# Контекст проекта: SPA Photo Recognition

Обновлено: 2026-07-09

## 1. Суть проекта

В SPA-центрах ежедневно делают фотографии посетителей.

После посещения клиент должен иметь возможность:

1. Перейти на единый публичный сайт.
2. Выбрать дату посещения или открыть ссылку с уже заданным SPA/визитом.
3. Загрузить селфи или сделать live-selfie с телефона.
4. Получить список фотографий, где он присутствует.
5. Выбрать понравившиеся фото.
6. Оплатить.
7. Скачать купленные фотографии.

Фотографии в основном портретные. Лица обычно видны чётко.

Ожидаемый объём:

* 150–200 фото в день на один SPA;
* хранение истории минимум 1 месяц;
* проект работает в РФ;
* inference должен выполняться локально или на сервере в РФ, без облачных API распознавания лиц.

Главная продуктовая идея:

> Фотографии заранее обрабатываются, лица превращаются в embeddings, а клиент находит свои фото по селфи или через промо-экран на выходе.

### 1.1 Статус требований и рекомендаций

В этом документе важно различать:

```text
продуктовые требования
- что пользователь и админ должны уметь делать;
- какое поведение системы критично для UX и безопасности.

рекомендуемая архитектура
- один из хороших способов реализовать это поведение;
- может быть заменена другой архитектурой, если сохраняются SLA, безопасность и управляемость нагрузки.
```

К продуктовым требованиям в текущей версии относятся:

* выбор pipeline распознавания через веб-интерфейс админки: `SFace` или `Buffalo M`;
* обработка search/reference-фото тем же pipeline, по которому есть embeddings в базе;
* запрет смешивания embeddings разных моделей;
* высокий приоритет reference-фото с выхода над фоновой batch-обработкой;
* временная пауза CPU-heavy фоновых задач при reference-триггере;
* сохранение приватности: preview с watermark, короткоживущие QR/search sessions, ограничение поиска по SPA/дате/визиту.

К рекомендуемой архитектуре относятся:

* `FaceEngine` adapter layer;
* отдельные очереди `reference.realtime`, `search.interactive`, `photo.background`, `reprocess.low`;
* Redis-флаг `reference_mode` с TTL;
* `ResourceManager`;
* pause-aware background workers;
* раздельные таблицы/индексы embeddings для разных моделей.

Эти архитектурные элементы не являются единственно возможным обязательным требованием. Они рекомендуются как наиболее простой и управляемый вариант для MVP/пилота.

---

## 2. Промо-экран на выходе из SPA

На выходе из SPA устанавливается промо-экран с камерой.

Сценарий:

1. Клиент выходит из SPA.
2. Камера делает 3–5 кадров.
3. Система выбирает лучший кадр.
4. Распознаёт одно или несколько лиц.
5. Ищет совпадения среди уже обработанной базы фотографий.
6. На промо-экране показывает:

   * что фото найдены;
   * несколько лучших preview;
   * QR-код / единую ссылку на сайт.
7. Клиент открывает сайт на своём телефоне.
8. Дальше выбор, оплата и скачивание происходят на телефоне.

Полноценный `kiosk mode` не нужен.

Не нужно:

* сенсорное управление на киоске;
* оплата на киоске;
* скачивание на киоске;
* блокировка ОС в kiosk mode.

Нужен только `display mode`:

* камера;
* экран;
* отображение найденных preview;
* QR/ссылка для перехода на телефон.

Промо-экран не должен раскрывать слишком много приватной информации. Preview должны быть маленькими, с watermark, а QR-сессия должна быть короткоживущей.

---

## 3. Пользовательский workflow

### Поиск фото через сайт

1. Клиент заходит на единую публичную ссылку.
2. Выбирает SPA и дату посещения или открывает ссылку с уже заданным SPA/визитом.
3. Загружает селфи или делает live-selfie.
4. Система проверяет качество селфи.
5. Система создаёт embedding через активный face recognition pipeline.
6. Система ищет совпадения только среди embeddings той же модели.
7. Клиент видит найденные фотографии в виде preview.
8. Клиент выбирает нужные фото.
9. Оплачивает.
10. Получает доступ к скачиванию оригиналов.

### Завлечение через промо-экран

1. Клиент выходит из SPA.
2. Камера на выходе делает несколько кадров.
3. Система выбирает лучший кадр.
4. Выполняется локальный inference через активный pipeline для данного SPA.
5. Если найдено совпадение, на экране показываются несколько preview с этим человеком.
6. На экране отображается QR-код / ссылка.
7. Клиент открывает сайт на телефоне и завершает покупку там.

---

## 4. Приватность и безопасность

Главный риск проекта — доступ к чужим фото.

Нельзя делать так, чтобы любой человек мог загрузить чужое селфи и получить чужие фотографии.

Минимально безопасный сценарий:

* единая ссылка;
* выбор SPA и даты;
* загрузка селфи;
* поиск только по выбранному SPA и дате;
* показ только preview;
* watermark на preview;
* оригиналы доступны только после оплаты.

Лучше:

* добавить код визита / QR / номер браслета / номер чека;
* искать не по всей базе, а внутри конкретного визита или сессии;
* использовать селфи как второй фактор, а не как единственный ключ доступа.

Оптимальный сценарий доступа:

```text
QR / код визита / номер браслета / чек
+
селфи / live-selfie
+
ограничение по spa_id + visit_date + time_window
```

Для РФ важно учесть:

* 152-ФЗ;
* обработку персональных данных;
* обработку биометрических данных;
* хранение данных в РФ;
* отдельное согласие на обработку фото/лица;
* сроки хранения и удаления данных;
* журнал согласий;
* механизм удаления фото, селфи и embeddings по запросу.

Селфи клиента желательно не хранить постоянно. После завершения search session его нужно удалять или хранить временно с коротким TTL.

---

## 5. Pipeline

### 5.1 Общий pipeline обработки фото

Рекомендуется обрабатывать базу фотографий заранее.

Рекомендуемая схема:

```text
фотограф загрузил фото
↓
сервер заранее создал original / preview / thumbnail
↓
сервер нашёл лица
↓
создал face embeddings выбранной моделью
↓
сохранил embeddings в БД с model_name и model_version
↓
клиент выходит из SPA
↓
камера делает 3–5 кадров
↓
система выбирает лучший кадр
↓
распознаёт лицо через активный pipeline
↓
сравнивает embedding только с embeddings той же модели
↓
показывает найденные preview на промо-экране
↓
клиент переходит на сайт по QR/ссылке
↓
выбирает, оплачивает и скачивает фото
```

### 5.2 Выбор face recognition pipeline через админку

В админке требуется реализовать возможность выбора активного pipeline распознавания лиц.

Для MVP требуется предусмотреть минимум два варианта:

1. `OpenCV YuNet + SFace`
2. `InsightFace Python + buffalo_m`

Рекомендуется сделать выбор доступным на уровне SPA:

```text
Admin → SPA settings → Face Recognition Pipeline
```

Поля в админке:

```text
active_pipeline:
- opencv_sface
- insightface_buffalo_m

processing_mode:
- active_only
- dual_benchmark

search_pipeline:
- same_as_active
- opencv_sface
- insightface_buffalo_m

promo_pipeline:
- same_as_active
- opencv_sface
- insightface_buffalo_m

threshold_cosine:
- значение по умолчанию для выбранной модели
- возможность ручной настройки

min_face_quality:
- минимальное качество лица для поиска

min_top1_top2_margin:
- минимальный отрыв первого результата от второго

model_status:
- installed
- missing
- warming_up
- ready
- error

reprocess_status:
- not_required
- required
- queued
- running
- completed
- failed
```

Главный принцип:

```text
Админ выбирает pipeline.
Новые фото обрабатываются выбранным pipeline.
Поиск клиента выполняется тем же pipeline.
Embeddings разных pipeline не смешиваются.
```

### 5.3 Режимы работы pipeline

#### active_only

Основной production-режим.

```text
загруженное фото
↓
обработка только активным pipeline
↓
сохранение одного embedding на лицо
```

Плюсы:

* проще;
* быстрее;
* меньше нагрузка;
* меньше размер базы.

Минусы:

* нельзя честно сравнивать SFace и Buffalo M на одних и тех же фото без переобработки.

#### dual_benchmark

Режим для тестов и пилота.

```text
загруженное фото
↓
SFace embedding
+
Buffalo M embedding
↓
сохранение двух embeddings на одно лицо
↓
сравнение качества в админке
```

Плюсы:

* можно сравнить модели на реальных SPA-фото;
* можно посмотреть false positives / false negatives;
* можно выбрать production-модель по фактическим данным.

Минусы:

* больше нагрузка на CPU;
* больше RAM во время обработки;
* больше места в БД;
* сложнее отладка.

Для MVP рекомендуется:

```text
pilot / benchmark period: dual_benchmark
production: active_only
```

### 5.4 Переключение pipeline в админке

При смене pipeline админке рекомендуется явно показывать последствия:

```text
Вы переключаете active_pipeline с opencv_sface на insightface_buffalo_m.
Для поиска через Buffalo M нужны Buffalo M embeddings.
Для уже загруженных фото требуется переобработка.
```

После переключения возможны варианты:

1. Использовать новый pipeline только для новых фото.
2. Поставить переобработку старых фото в очередь.
3. Временно оставить search_pipeline на старой модели, пока новая модель не пересчитала embeddings.
4. Включить `dual_benchmark` на тестовый период.

Рекомендуемые кнопки админки:

```text
Reprocess missing embeddings for selected pipeline
Reprocess all photos for selected pipeline
Compare SFace vs Buffalo M on selected date
Show photos without embeddings for active pipeline
Show failed processing jobs
```

### 5.5 Почему нельзя смешивать embeddings разных моделей

Embeddings от разных моделей находятся в разных embedding spaces.

```text
SFace embedding ≠ Buffalo M embedding
```

Даже если оба embedding описывают одно и то же лицо, их нельзя сравнивать напрямую.

Нельзя делать так:

```text
селфи обработано через SFace
↓
поиск среди Buffalo M embeddings
```

Нужно делать так:

```text
селфи обработано через SFace
↓
поиск только среди SFace embeddings
```

или так:

```text
селфи обработано через Buffalo M
↓
поиск только среди Buffalo M embeddings
```

Поэтому в базе обязательно нужно хранить:

```text
model_name
model_version
embedding_dim
preprocessing_version
```

### 5.6 Рекомендуемая FaceEngine abstraction

Рекомендуется сделать общий интерфейс для всех моделей.

Пример:

```python
class FaceEngine:
    name: str
    version: str
    embedding_dim: int

    def detect(self, image) -> list[FaceDetection]:
        ...

    def embed(self, image, face: FaceDetection) -> FaceEmbedding:
        ...

    def process_image(self, image) -> list[FaceResult]:
        ...
```

Реализации:

```text
OpenCvSFaceEngine
- detector: YuNet
- recognizer: SFace
- preprocessing: OpenCV alignCrop
- embedding: SFace feature vector

InsightFaceBuffaloMEngine
- detector: SCRFD из buffalo_m pack
- recognizer: buffalo_m recognition model
- preprocessing: internal InsightFace alignment
- embedding: normed_embedding
```

Рекомендуется, чтобы остальной продукт работал не с конкретной моделью, а с `FaceEngine`.

```text
upload photo
↓
get active FaceEngine
↓
process image
↓
save detected faces + embeddings
↓
search with same FaceEngine
```


### 5.7 Reference-фото на выходе: рекомендуемый realtime pipeline

Reference-фото — это кадры, которые делает камера на выходе из SPA для быстрого поиска человека по уже обработанной базе.

Важно различать два типа фотографий:

```text
общие фотографии фотографа
- коммерческие фото, которые продаются клиенту;
- обрабатываются заранее;
- могут обрабатываться batch-очередью.

reference-фото с выхода
- временные query-фото для поиска человека;
- не продаются клиенту;
- должны обрабатываться максимально быстро;
- должны иметь короткий TTL и удаляться после завершения search session.
```

Reference pipeline относится к realtime-задачам. Целевое поведение: если сработал триггер камеры на выходе, система временно освобождает CPU под быстрое распознавание reference-фото и поиск по базе.

Целевой SLA:

```text
идеально: 1–3 секунды
нормально: 3–5 секунд
максимум: до 10 секунд
```

### 5.8 Brainstorm: как приоритезировать reference-фото

Варианты механизма приоритезации:

| Вариант | Суть | Плюсы | Минусы | Вердикт |
|---|---|---|---|---|
| Простая priority queue | Reference jobs получают высокий priority | Легко реализовать | Не помогает, если CPU уже занят тяжёлыми workers | Недостаточно |
| Отдельная realtime-очередь | `reference.realtime` обслуживается отдельным worker-ом | Предсказуемее | Нужно контролировать фоновые workers | Рекомендуется |
| Cooperative pause | Фоновые workers видят флаг `reference_mode=active` и не берут новые jobs | Просто и безопасно | Текущий model inference нельзя остановить мгновенно | Рекомендуемый MVP-вариант |
| Hard preemption / kill workers | Убивать batch jobs при reference-триггере | Быстро освобождает CPU | Риск битых состояний, retry-штормов, потери прогресса | Не использовать как основной путь |
| Reserved CPU cores | Фоновые workers используют не все ядра, оставляя запас под reference | Стабильно | Немного снижает batch throughput | Рекомендуется |
| OS-level priority | `nice`, `ionice`, `cgroups`, `systemd slices` | Реально защищает realtime-контур | Требует аккуратной настройки Linux | Желательно для production |
| Отдельное устройство для промо | Reference pipeline на отдельном mini PC / edge node | Лучшее разделение ресурсов | Дороже, сложнее обслуживание | Хорошо позже |
| Предрасчёт clusters/cache | Поиск идёт по дневным cluster centroids, не по всем лицам | Ускоряет поиск и снижает шум | Нужно реализовать кластеризацию | Желательно |

Рекомендуемый подход:

```text
priority queue
+
отдельный realtime reference worker
+
cooperative pause фоновых workers
+
резерв CPU под realtime-задачи
+
короткий TTL на reference mode
+
OS-level понижение приоритета batch workers
```

То есть не нужно пытаться мгновенно убивать все процессы. Лучше сделать управляемую паузу фоновых задач и не давать им начинать новые тяжёлые операции, пока reference-фото обрабатывается.

### 5.9 Рекомендуемая архитектура очередей

Это не обязательная единственная архитектура, а рекомендуемый вариант для MVP/пилота. Его можно упростить или заменить, если выбранный queue-framework уже даёт похожие гарантии приоритета и паузы.

Рекомендуемые очереди:

```text
reference.realtime
- самый высокий приоритет;
- кадры с камеры на выходе;
- распознавание reference-фото;
- создание promo_search_session и QR.

search.interactive
- высокий приоритет;
- поиск по live-selfie / селфи на сайте;
- пользователь ждёт результат на телефоне.

photo.background
- обычный приоритет;
- импорт общих фото фотографа;
- preview / thumbnail;
- face detection;
- embeddings активной модели.

reprocess.low
- низкий приоритет;
- переобработка старых фото;
- пересчёт embeddings после смены модели;
- dual_benchmark jobs.

maintenance.low
- самый низкий приоритет;
- cleanup;
- удаление TTL-файлов;
- housekeeping.
```

Приоритеты jobs:

```text
reference.realtime: 1000
search.interactive: 800
photo.background: 100
reprocess.low: 20
maintenance.low: 5
```

Reference jobs должны иметь более высокий приоритет, чем фоновые jobs.

### 5.10 Рекомендуемый механизм паузы фоновой обработки

При срабатывании триггера камеры:

```text
reference trigger
↓
Redis SET reference_mode:{spa_id}=active EX 30
↓
новые background jobs временно не стартуют
↓
текущие background jobs доходят до ближайшей safe pause point
↓
reference.realtime worker получает CPU
↓
делает detect → quality → embedding → search
↓
создаёт promo_search_session + QR
↓
reference_mode снимается или истекает по TTL
↓
background jobs продолжаются
```

Рекомендуется, чтобы фоновые workers проверяли `reference_mode` перед тяжёлыми этапами:

```text
перед face detection
перед embedding extraction
перед запуском второй модели в dual_benchmark
перед reprocess batch
перед обработкой следующего фото
```

Если `reference_mode=active`, worker рекомендуется:

```text
не брать новые jobs;
не запускать новый model inference;
сохранить checkpoint, если job длинный;
перейти в paused/suspended;
периодически проверять, можно ли продолжить.
```

Текущий короткий inference можно не прерывать насильно. Достаточно запретить старт новых тяжёлых операций.

### 5.11 Почему hard preemption лучше не делать основным механизмом

Нельзя строить основной механизм на убийстве процессов:

```text
kill worker
↓
job оборвался посередине
↓
непонятный статус
↓
повторная обработка
↓
риск дубликатов / битых preview / retry storm
```

Hard preemption допустим только как аварийный fallback, если worker завис и не отдаёт CPU дольше лимита.

Основной механизм:

```text
cooperative pause
+
короткие atomic steps
+
checkpoint между этапами
+
timeouts
+
retry с idempotency key
```

### 5.12 ResourceManager как рекомендуемый компонент

`ResourceManager` не является обязательным отдельным сервисом. Для MVP эту роль может выполнять backend, worker supervisor или небольшой модуль вокруг Redis/Celery/RQ. Рекомендуется выделить такую ответственность логически, чтобы централизованно управлять режимами нагрузки.

Рекомендуемые задачи:

```text
следить за reference triggers;
включать reference_mode с TTL;
останавливать выдачу новых background jobs;
контролировать число активных workers;
держать модель promo_pipeline прогретой;
снимать reference_mode после завершения;
не допускать вечной блокировки фоновой обработки.
```

Минимальная логика:

```python
def on_reference_trigger(spa_id: str):
    redis.set(f"reference_mode:{spa_id}", "active", ex=30)
    enqueue("reference.realtime", priority=1000, payload={"spa_id": spa_id})


def background_worker_loop():
    while True:
        if redis.exists("reference_mode:*"):
            sleep(0.5)
            continue
        job = take_next_background_job()
        process_job_with_safe_pause_points(job)
```

Лучше не использовать wildcard-проверку в production-цикле буквально. Практически лучше хранить глобальный счётчик или set активных `spa_id`:

```text
reference_mode_global = active / inactive
reference_mode_spas = set(spa_id)
```

### 5.13 Рекомендуемая CPU/RAM политика

Для сервера без GPU рекомендуется такая политика:

```text
reference worker:
- отдельный процесс;
- concurrency: 1;
- модель promo_pipeline загружена заранее;
- приоритет OS выше обычного;
- работает только с лучшими 1–2 лицами.

background workers:
- concurrency ограничен;
- не занимают все ядра CPU;
- используют низкий OS priority;
- pause-aware;
- batch size ограничен.
```

Рекомендация для i5/i7:

```text
CPU cores total: N
background CPU workers: max(N - 2, 1)
reference worker: 1 dedicated process
interactive search worker: 1 process
```

Для Linux production желательно:

```text
background workers:
- nice 10..15
- ionice idle/best-effort low
- systemd slice с CPUQuota

reference worker:
- normal или elevated priority
- без лишней конкуренции за CPU
- отдельный process pool
```

### 5.14 Рекомендуемый Reference trigger flow

Рекомендуемый flow:

```text
1. Камера / motion / button / presence sensor создаёт trigger.
2. ReferenceCaptureService делает 3–5 кадров.
3. Быстрый quality scorer выбирает лучший кадр.
4. Если лиц несколько, выбираются 1–2 самых крупных и качественных.
5. Reference job уходит в reference.realtime queue.
6. ResourceManager включает reference_mode.
7. FaceEngine создаёт embedding через promo_pipeline.
8. Поиск идёт только по embeddings той же модели.
9. Сначала ищем по cluster centroids текущего дня/окна времени.
10. Потом уточняем по отдельным face embeddings.
11. Если threshold + margin проходят, создаётся promo_search_session.
12. Экран показывает preview + QR.
13. Reference кадры удаляются по TTL.
14. Background processing возобновляется.
```

Reference-фото не должны попадать в общую коммерческую галерею.

### 5.15 Защита от starvation

Если на выходе постоянный поток людей, background jobs могут почти не выполняться.

Рекомендуемые ограничения:

```text
reference_pause_ttl_seconds: 30
reference_max_processing_seconds: 10
reference_max_continuous_mode_seconds: 180
reference_trigger_debounce_seconds: 3–5
reference_trigger_coalesce_window_seconds: 5–10
```

Правила:

```text
если триггеров много, объединять близкие triggers;
не запускать параллельно много reference jobs;
если reference worker занят, новые triggers ставить в короткую очередь;
устаревшие reference jobs удалять;
после max_continuous_mode_seconds дать background workers короткое окно для прогресса;
не держать reference_mode бесконечно без активного job.
```

### 5.16 Админские настройки для приоритезации

Рекомендуемые настройки в админке:

```text
reference_priority_enabled: true / false
pause_background_on_reference: true / false
reference_pause_ttl_seconds: 30
reference_max_processing_seconds: 10
reference_trigger_debounce_seconds: 5
reference_max_faces_per_trigger: 1 или 2
background_worker_concurrency: N
reprocess_worker_concurrency: N
reserve_cpu_cores_for_reference: 1 или 2
reference_pipeline: same_as_active / opencv_sface / insightface_buffalo_m
reference_frame_ttl_minutes: 15–60
```

В админке также рекомендуется показывать:

```text
reference mode сейчас активен / неактивен;
последний trigger;
среднее время обработки reference-фото;
95-й перцентиль времени обработки;
количество отменённых / устаревших triggers;
сколько background jobs сейчас paused;
сколько photo.background jobs ожидают обработки;
```

### 5.17 Практический рекомендуемый MVP-вариант

Для MVP не рекомендуется строить сложный distributed scheduler.

Обычно достаточно:

```text
Redis
+
RQ / Celery / Arq
+
отдельные очереди по приоритету
+
отдельный reference worker
+
Redis flag reference_mode с TTL
+
pause-aware background workers
+
ограничение concurrency
```

Рекомендуемая минимальная архитектура:

```text
ReferenceWorker
- слушает reference.realtime
- всегда готов
- держит активную/promo модель прогретой
- обрабатывает reference-фото первым

InteractiveSearchWorker
- слушает search.interactive
- отвечает за поиск с сайта

BackgroundPhotoWorker
- слушает photo.background
- проверяет reference_mode перед тяжёлыми шагами

ReprocessWorker
- слушает reprocess.low
- всегда останавливается первым
```

Итоговое целевое поведение:

```text
Reference-фото с выхода имеют абсолютный приоритет над batch-обработкой.
При reference-триггере batch/reprocess не стартуют новые CPU-heavy этапы.
Сервер освобождает CPU под realtime-распознавание.
После завершения reference job background processing автоматически продолжается.
```

Конкретные названия очередей, workers и компонента ResourceManager являются рекомендуемой реализацией, а не жёстким обязательным дизайном.

---

## 6. Model-specific preprocessing

У каждой модели свой pipeline подготовки лица. Рекомендуется спрятать эту часть внутри adapter-слоя.

Общая подготовка изображения может быть одна:

```text
image upload
↓
EXIF orientation fix
↓
format validation
↓
RGB/BGR conversion as needed
↓
max image size limit
↓
blur / brightness / contrast checks
↓
pass image to selected FaceEngine
```

Модель-зависимую часть рекомендуется держать внутри конкретного adapter.

### 6.1 OpenCV YuNet + SFace

Pipeline:

```text
image
↓
YuNet face detection
↓
bbox + landmarks
↓
FaceRecognizerSF.alignCrop(...)
↓
SFace feature(...)
↓
embedding
↓
optional L2 normalization
↓
cosine similarity / L2 distance
```

Особенности:

* хорош для простого MVP;
* относительно лёгкий;
* хорошо подходит для CPU;
* проще юридически и инфраструктурно;
* качество нужно проверить на реальных SPA-фото;
* может быть слабее на промо-экране при плохом свете, смазе и ракурсах.

### 6.2 InsightFace buffalo_m

Pipeline:

```text
image
↓
InsightFace FaceAnalysis.get(image)
↓
SCRFD detection
↓
landmarks / alignment внутри InsightFace
↓
buffalo_m recognition model
↓
normed_embedding
↓
cosine similarity
```

Особенности:

* вероятно выше качество на сложных кадрах;
* лучше подходит для промо-экрана, где хуже свет, ракурс и движение;
* больше вес моделей;
* больше нагрузка на CPU/RAM;
* нужно отдельно проверить лицензию для коммерческого использования;
* preprocessing лучше не переписывать вручную, а использовать штатный InsightFace pipeline.

### 6.3 Правило реализации

Не рекомендуется делать один универсальный crop/alignment для всех моделей.

Правильно:

```text
общий код: загрузка, EXIF, проверка качества
модельный adapter: detection, landmarks, alignment, crop, normalization, embedding
```

---

## 7. Face embeddings

Face embedding — это числовой вектор лица.

Пример:

```text
лицо человека → модель → embedding
```

Эти числа используются для сравнения лиц.

Фотографии хранятся отдельно, а embeddings хранятся в базе.

Важно:

```text
одно detected_face может иметь несколько embeddings от разных моделей
```

Например:

```text
detected_face #123
├── opencv_sface embedding
└── insightface_buffalo_m embedding
```

Это нужно для:

* A/B-теста;
* перехода с одной модели на другую;
* переобработки старых фото;
* сравнения качества SFace и Buffalo M.

---

## 8. pgvector и структура базы

`pgvector` — расширение PostgreSQL для хранения и поиска векторов.

В проекте его рекомендуется использовать для поиска похожих лиц по embeddings.

Рекомендуемая структура:

```text
spas
- id
- name
- active_pipeline
- search_pipeline
- promo_pipeline
- threshold_cosine_sface
- threshold_cosine_buffalo_m
- min_face_quality
- min_top1_top2_margin
- created_at
- updated_at

photos
- id
- spa_id
- visit_date
- batch_id
- original_path
- preview_path
- thumbnail_path
- width
- height
- exif_taken_at
- created_at

detected_faces
- id
- photo_id
- bbox_x
- bbox_y
- bbox_w
- bbox_h
- landmarks_json
- detection_confidence
- quality_score
- blur_score
- brightness_score
- pose_yaw
- pose_pitch
- pose_roll
- created_at

face_embeddings
- id
- detected_face_id
- spa_id
- photo_id
- model_name
- model_version
- preprocessing_version
- embedding_dim
- embedding
- embedding_norm
- created_at

processing_jobs
- id
- spa_id
- photo_id
- job_type
- queue_name
- priority
- model_name
- status
- can_be_paused
- pause_requested_at
- suspended_at
- resumed_at
- idempotency_key
- error_message
- attempts
- created_at
- started_at
- finished_at

search_sessions
- id
- spa_id
- visit_date
- source
- pipeline
- query_face_quality
- top_score
- top1_top2_margin
- result_count
- expires_at
- created_at

reference_triggers
- id
- spa_id
- trigger_source
- status
- active_pipeline
- frame_count
- selected_frame_id
- detected_faces_count
- result_count
- processing_time_ms
- error_message
- created_at
- started_at
- finished_at
- expires_at

reference_frames
- id
- reference_trigger_id
- storage_path
- quality_score
- blur_score
- brightness_score
- face_count
- selected
- expires_at
- created_at

worker_runtime_state
- id
- worker_name
- queue_name
- current_job_id
- status
- last_heartbeat_at
- paused_by_reference_mode
- cpu_usage_percent
- memory_usage_mb
```

Логика поиска:

```text
селфи клиента
↓
активный search_pipeline
↓
embedding через эту же модель
↓
поиск nearest neighbors только по model_name + model_version
↓
фильтр spa_id + visit_date / visit_id / time_window
↓
проверка threshold + margin
↓
выдача preview
```

Для одного SPA и 200 фото/день нагрузка маленькая, но pgvector рекомендуется заложить сразу.

### 8.1 Вариант с разными размерностями embeddings

У разных моделей может быть разная размерность embedding.

В PostgreSQL/pgvector проще всего использовать отдельные таблицы или отдельные vector-колонки:

```text
face_embeddings_sface
- embedding vector(128 или другая размерность SFace)

face_embeddings_buffalo_m
- embedding vector(512 или другая размерность Buffalo M)
```

Альтернативный вариант:

```text
face_embeddings
- model_name
- embedding_dim
- embedding
```

Но индексы pgvector удобнее и надёжнее держать отдельно по моделям, если размерности отличаются.

Рекомендуемый вариант для MVP:

```text
detected_faces — общая таблица лиц
face_embeddings_sface — embeddings SFace
face_embeddings_buffalo_m — embeddings Buffalo M
```

---

## 9. ONNX-модели

ONNX-модель — это нейросеть в переносимом формате `.onnx`.

Плюсы ONNX:

* можно запускать на CPU;
* можно запускать через OpenVINO;
* можно позже перейти на другое железо без полной смены архитектуры;
* удобно использовать в production.

Для SFace/YuNet ONNX-подход хорошо подходит.

Для Buffalo M в MVP можно использовать Python-пакет InsightFace как adapter. Если позже понадобится более строгий production-контур, можно отдельно исследовать экспорт/запуск через ONNX Runtime или OpenVINO, но это не должно блокировать MVP.

---

## 10. Local inference

Local inference — это запуск AI-модели локально:

* на сервере SPA;
* на mini PC;
* на своём сервере в РФ;

а не через облачные API.

В проекте inference делает:

```text
фото → поиск лица → embedding → сравнение → результат
```

С учётом выбора pipeline:

```text
фото
↓
FaceEngine выбранный в админке
↓
модельный preprocessing
↓
embedding
↓
поиск в embeddings той же модели
```

---

## 11. Скорость распознавания на выходе

Условие:

* база фото уже обработана;
* на выходе делаем 3–5 кадров;
* выбираем лучший кадр;
* распознаём лица;
* ищем совпадения;
* максимум на всё — 10 секунд.

Оценка:

| Железо                   | 1 человек | 2 человека | 4 человека |
| ------------------------ | --------: | ---------: | ---------: |
| Intel N100/N305, CPU     |   3–7 сек |    4–9 сек |   6–12 сек |
| Core i5/i7, CPU/OpenVINO |   1–3 сек |    2–4 сек |    3–6 сек |
| RTX 3060/4060            | 0.5–2 сек |  1–2.5 сек |  1.5–4 сек |
| Jetson Orin Nano         |   1–3 сек |    2–5 сек |    3–7 сек |

10 секунд — достижимо с запасом.

Если людей несколько, не обязательно распознавать всех. Можно брать 1–2 самых крупных и чётких лица.

### Влияние выбора модели

Ожидание:

```text
SFace:
- быстрее;
- легче;
- проще для CPU;
- может давать больше промахов на сложных кадрах.

Buffalo M:
- тяжелее;
- потенциально точнее;
- лучше как quality baseline;
- может требовать больше RAM/CPU.
```

Для промо-экрана можно выбрать отдельный `promo_pipeline`, но для MVP лучше держать один активный pipeline для загрузки, сайта и промо.

---

## 12. Выбор лучшего кадра

Камера делает 3–5 кадров.

Система выбирает лучший по признакам:

* лицо крупнее;
* меньше смаз;
* лицо смотрит в камеру;
* глаза/лицо хорошо видны;
* нормальное освещение;
* меньше перекрытий;
* только одно явно доминирующее лицо, если это сценарий персонального поиска.

Распознавание лучше делать только на лучшем кадре, а не на всех 5 полностью.

В `dual_benchmark` режиме можно считать обе модели на лучшем кадре, но клиентский результат должен показываться только от одного выбранного pipeline.

---

## 13. Хранилище

Вводные:

```text
200 фото/день
30 дней
= 6000 фото/месяц
```

Примерный объём:

| Средний размер фото | 30 дней |
| ------------------: | ------: |
|                5 МБ |  ~30 ГБ |
|               10 МБ |  ~60 ГБ |
|               15 МБ |  ~90 ГБ |
|               25 МБ | ~150 ГБ |

Дополнительно:

* preview;
* thumbnails;
* embeddings;
* БД;
* логи;
* резервные копии;
* временные селфи search sessions;
* embeddings второй модели, если включён `dual_benchmark`.

Для одного SPA:

```text
Минимум: 200 ГБ
Нормально: 500 ГБ
Комфортно: 1 ТБ
```

В текущем hardware-варианте закладываем:

```text
2 TB NVMe
```

Этого достаточно для:

* хранения фото минимум за месяц;
* хранения preview;
* работы PostgreSQL;
* MinIO;
* локального кэша;
* запаса под рост данных;
* тестового хранения embeddings двух моделей.

Embeddings занимают мало места по сравнению с оригинальными фото. Рост хранилища из-за двух моделей будет заметен в БД и индексах, но не критичен относительно фотографий.

---

## 14. Hardware

### Целевая конфигурация

```text
Intel Core i5-13400 или Intel Core i7-13700
32 GB RAM
2 TB NVMe
Ubuntu 24.04
ONNX Runtime + OpenVINO
без GPU на старте
```

### Логика выбора

* CPU достаточно для текущего объёма;
* GPU на старте не нужен;
* OpenVINO ускоряет inference на Intel CPU;
* 32 GB RAM нужны, потому что всё крутится на одной машине;
* 2 TB NVMe дают запас под фото, БД, MinIO, preview и логи.

Если `dual_benchmark` будет постоянно включён, рекомендуется использовать i7 и ограничивать число параллельных workers, чтобы не перегружать машину.

---

## 15. RAM

На одной машине будут работать:

* PostgreSQL;
* MinIO/хранилище;
* backend;
* workers обработки фото;
* face models;
* браузер промо-экрана;
* Redis/очередь;
* Linux OS.

Примерная RAM:

| Компонент                       |        RAM |
| ------------------------------- | ---------: |
| Linux OS                        |   1.5–3 GB |
| PostgreSQL + pgvector           |     1–4 GB |
| MinIO                           |   0.5–2 GB |
| Backend API                     |   0.3–1 GB |
| Workers обработки фото          |     2–8 GB |
| SFace / YuNet runtime           |   0.5–2 GB |
| Buffalo M / InsightFace runtime |     1–4 GB |
| Браузер промо-экрана            |   0.8–2 GB |
| Redis / очередь                 | 0.2–0.5 GB |
| OS cache под файлы/превью       |     2–8 GB |

Так как всё крутится на одной машине, рекомендуемый целевой вариант — 32 GB RAM.

Если одновременно держать SFace и Buffalo M загруженными в память, RAM всё ещё должна быть достаточной, но нужно контролировать workers.

---

## 16. Рекомендуемый стек

Backend:

```text
Python + FastAPI
```

Database:

```text
PostgreSQL + pgvector
```

Storage:

```text
MinIO
```

Queue:

```text
Redis + RQ / Celery / Arq
отдельные priority queues:
- reference.realtime
- search.interactive
- photo.background
- reprocess.low
- maintenance.low
```

Face recognition:

```text
OpenCV YuNet + SFace
InsightFace Python + buffalo_m
```

Pipeline abstraction:

```text
FaceEngine interface
OpenCvSFaceEngine
InsightFaceBuffaloMEngine
```

Inference:

```text
ONNX Runtime + OpenVINO для ONNX-моделей
InsightFace runtime для buffalo_m
```

Frontend:

```text
Клиентский сайт
Админка
```

Admin features:

```text
загрузка фото
выбор active_pipeline
выбор processing_mode
настройка thresholds
переобработка фото под выбранную модель
просмотр ошибок обработки
сравнение качества SFace vs Buffalo M
настройка reference_priority_enabled
настройка pause_background_on_reference
мониторинг reference.realtime queue
мониторинг paused background jobs
```

Promo screen:

```text
браузер в display mode
камера
auto-refresh найденных preview и QR
короткоживущие promo search sessions
```

---

## 17. Админка

Админке рекомендуется включать не только загрузку фото, но и управление ML-пайплайном.

### 17.1 Загрузка фото

Функции:

* загрузка фото batch-ами;
* привязка к SPA;
* привязка к дате;
* создание preview и thumbnails;
* запуск обработки лиц;
* просмотр статуса обработки.

### 17.2 Настройки распознавания

Функции:

* выбрать `active_pipeline`:

```text
opencv_sface
insightface_buffalo_m
```

* выбрать режим обработки:

```text
active_only
dual_benchmark
```

* настроить thresholds:

```text
cosine_threshold_sface
cosine_threshold_buffalo_m
min_face_quality
min_top1_top2_margin
max_results
reference_priority_enabled
pause_background_on_reference
reference_pause_ttl_seconds
reference_max_processing_seconds
reference_max_faces_per_trigger
background_worker_concurrency
reserve_cpu_cores_for_reference
```

* включить/выключить pipeline для промо-экрана;
* посмотреть, сколько фото уже обработано каждой моделью;
* посмотреть, сколько embeddings отсутствует для выбранной модели.

### 17.3 Переобработка

Функции:

* пересчитать embeddings для выбранной даты;
* пересчитать embeddings для выбранного SPA;
* пересчитать только missing embeddings;
* пересчитать только failed jobs;
* остановить очередь переобработки;
* посмотреть ошибки по каждой модели.

### 17.4 Benchmark-экран

Для пилота желательно добавить экран сравнения моделей.

Показатели:

```text
model_name
processed_faces_count
failed_faces_count
average_processing_time
search_success_rate
manual_false_positive_count
manual_false_negative_count
average_top_score
average_top1_top2_margin
```

Цель benchmark-а:

```text
понять, хватает ли SFace для реального SPA-кейса
или стоит переходить на Buffalo M / коммерчески лицензированный аналог
```


### 17.5 Управление realtime-priority для reference-фото

Функции:

* включить/выключить приоритетную обработку reference-фото;
* включить/выключить паузу фоновой обработки при reference-триггере;
* задать TTL для `reference_mode`;
* задать лимит времени обработки одного reference-триггера;
* задать число CPU cores, которые рекомендуется резервировать под realtime-задачи;
* задать максимальное число лиц, обрабатываемых с одного trigger;
* увидеть активные reference jobs;
* увидеть paused background jobs;
* увидеть среднее и p95 время обработки reference-фото;
* вручную снять зависший `reference_mode`, если TTL/failsafe не сработал.

Минимальные статусы на экране:

```text
reference_mode: active / inactive
active_reference_jobs: N
paused_background_jobs: N
reference_avg_latency_ms: N
reference_p95_latency_ms: N
oldest_background_job_waiting_time: N
```

---

## 18. Что входит в MVP

Важно: MVP ниже разделён на функциональное ядро и рекомендуемую техническую реализацию.

Функциональное ядро — это продуктовые требования. Конкретная архитектура очередей, `ResourceManager`, `reference_mode` и названия workers — рекомендуемый способ реализации, а не единственно возможный обязательный дизайн.

### 18.1 Функциональное ядро MVP

MVP должен включать:

1. Админку для загрузки фото.
2. Выбор face recognition pipeline в веб-интерфейсе админки: `SFace` или `Buffalo M`.
3. Режим обработки `active_only`.
4. Желательно — режим `dual_benchmark` для пилота.
5. Автоматическую обработку фото.
6. Поиск лиц на фото.
7. Создание embeddings с сохранением `model_name` и `model_version`.
8. Хранение оригиналов и preview.
9. Клиентский сайт.
10. Загрузку селфи.
11. Поиск похожих лиц через тот же pipeline, которым обработана база.
12. Галерею найденных фото.
13. Preview с watermark.
14. Оплату.
15. Выдачу ссылок на скачивание.
16. Промо-экран на выходе.
17. Камеру на выходе.
18. Распознавание выходящего клиента через активный pipeline.
19. Показ нескольких найденных preview и QR-кода.
20. Очередь переобработки embeddings при смене pipeline.
21. Просмотр ошибок обработки по моделям.
22. Приоритет reference-фото над фоновой обработкой общих фотографий.
23. Временную паузу CPU-heavy фоновых задач при reference-триггере.
24. Мониторинг времени обработки reference-фото.

### 18.2 Рекомендуемая техническая реализация MVP

Рекомендуется реализовать:

1. Отдельную очередь `reference.realtime` для reference-фото с выхода.
2. Отдельную очередь `search.interactive` для поиска с сайта.
3. Очереди `photo.background` и `reprocess.low` для фоновой обработки и переобработки.
4. Механизм `reference_mode` с TTL для временной паузы фоновых CPU-heavy задач.
5. Pause-aware background workers.
6. Отдельный `ReferenceWorker`, который держит active/promo pipeline прогретым.
7. Ограничение concurrency фоновых workers.
8. Мониторинг reference latency и paused jobs в админке.
9. OS-level приоритеты через `nice`, `ionice`, `systemd slices` или `cgroups` для production.
10. Возможность заменить эту схему другой реализацией, если сохраняются приоритет reference-фото, пауза фоновой CPU-heavy обработки и целевой SLA.

---

## 19. Что не входит в MVP

Не входит:

* полноценный kiosk mode;
* оплата на киоске;
* скачивание на киоске;
* мобильное приложение;
* собственная обученная модель;
* обучение модели на своих данных;
* сложная CRM;
* ретушь фото;
* масштабирование на десятки SPA;
* GPU-инфраструктура;
* автоматическая юридическая система согласий без юриста;
* автоматическое решение коммерческой лицензии Buffalo M;
* сложный multi-model ensemble, где SFace и Buffalo M одновременно участвуют в клиентской выдаче;
* полноценный distributed scheduler для нескольких серверов;
* hard preemption / kill workers как основной механизм управления CPU.

---

## 20. Оценка разработки

Если делает один сильный fullstack-разработчик с AI-агентами:

```text
Прототип с одним pipeline: 3–5 недель
Прототип с SFace + Buffalo M через FaceEngine: 4–7 недель
MVP с выбором pipeline в админке, reference-priority поведением и рекомендуемой priority-очередью: 8–12 недель
Production: 4–6 месяцев
```

Почему оценка выросла:

* добавляются два adapter-а;
* embeddings разных моделей хранятся раздельно;
* добавляются настройки pipeline в админку;
* добавляется переобработка старых фото;
* thresholds калибруются отдельно для SFace и Buffalo M;
* false positives тестируются отдельно по каждой модели;
* добавляется приоритетная realtime-очередь для reference-фото;
* добавляется cooperative pause для фоновых workers;
* мониторится задержка reference pipeline.

---

## 21. Риски

### 21.1 Главный ML-риск

False positive хуже, чем false negative.

Лучше не найти фото клиента, чем показать ему чужие фото.

Поэтому критерии выдачи должны быть строгими:

```text
top_score > threshold
+
top1_top2_margin > margin
+
face_quality > min_quality
+
поиск ограничен spa_id + date / visit_id / time_window
```

### 21.2 Риск переключения pipeline

Если админ переключил модель, а старые фото ещё не переобработаны, поиск может временно находить меньше фото.

Админке рекомендуется явно показывать:

```text
для выбранного pipeline обработано 65% фото за эту дату
```

И предупреждать:

```text
Для полной выдачи нужно дождаться переобработки embeddings.
```

### 21.3 Риск лицензии Buffalo M

Перед коммерческим запуском нужно отдельно проверить лицензию и условия использования `InsightFace buffalo_m`.

Для прототипа и benchmark-а Buffalo M можно использовать как quality baseline, но production-решение должно учитывать юридический статус модели.

### 21.4 Риск промо-экрана

Промо-экран может работать хуже сайта, потому что кадр с камеры на выходе часто хуже селфи:

* движение;
* смаз;
* плохой свет;
* лицо не смотрит в камеру;
* несколько людей в кадре.

Для промо-экрана рекомендуется использовать более строгий threshold, чем для поиска на сайте.


### 21.5 Риск конкуренции за CPU

Если фоновая обработка общих фото, dual_benchmark или переобработка embeddings занимают весь CPU, reference-фото на выходе могут обрабатываться слишком долго.

Это критично, потому что клиент стоит у промо-экрана и ждёт быстрый результат.

Правило:

```text
reference.realtime важнее photo.background и reprocess.low
```

Рекомендуемые меры:

```text
выделить отдельный ReferenceWorker или аналогичный realtime executor;
держать promo_pipeline прогретым;
ограничить concurrency фоновых workers;
включать reference_mode с TTL;
ставить background/reprocess на cooperative pause;
использовать OS-level приоритеты для production;
не допускать вечной starvation фоновой очереди.
```

Главная опасность не в том, что reference job окажется в очереди первым, а в том, что CPU уже будет занят несколькими тяжёлыми inference-процессами. Поэтому одной priority queue часто недостаточно. Рекомендуется ResourceManager-логика и pause-aware workers, но это может быть реализовано как отдельный сервис, модуль backend-а или настройки выбранной queue-системы.

---

## 22. Текущая финальная концепция

Финальная концепция:

> SPA-фотосервис с локальным распознаванием лиц.
> Фотографии заранее загружаются и обрабатываются.
> В админке можно выбрать pipeline распознавания: `OpenCV YuNet + SFace` или `InsightFace buffalo_m`.
> Клиент может найти свои фото на сайте по дате/визиту и селфи, оплатить и скачать.
> На выходе из SPA стоит промо-экран с камерой: reference-фото получают realtime-приоритет, фоновая обработка временно освобождает CPU, система распознаёт выходящего клиента через активный pipeline, показывает несколько найденных preview и QR-код для перехода на сайт.
> Все покупки и скачивания происходят на телефоне клиента.

Главный принцип:

```text
Промо-экран завлекает.
Телефон продаёт и скачивает.
Сервер распознаёт и хранит.
Админка выбирает ML-pipeline.
Reference-фото имеют приоритет над batch-обработкой.
Embeddings разных моделей не смешиваются.
```

Рекомендуемая техническая формула:

```text
одна продуктовая система
+
общий FaceEngine interface
+
два сменных adapter-а: SFace и Buffalo M
+
раздельное хранение embeddings
+
выбор pipeline через админку
+
переобработка фото при смене модели
+
reference.realtime queue
+
cooperative pause фоновых workers при reference-триггере
+
возможность заменить эту архитектуру другим решением при сохранении того же поведения
```
