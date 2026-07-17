# Face Moment: поступление фотографий

Обновлено: 2026-07-17

## 0. Статус и граница первого pilot

Документ описывает как обязательный ingest первого pilot, так и
post-pilot направления. Для первого pilot действует более позднее решение:

- одна SPA и тестировщики;
- только authenticated direct web upload фотографом;
- только готовые JPEG;
- Яндекс Диск и другие external channels не являются pilot/MVP gate.

Термин `batch` ниже относится к коммерческим фотографиям фотографа и не означает
`reference_series`, которую `SpaPromoClient` снимает для поиска.

## 1. Основная идея

В первом pilot фотографии поступают только через authenticated web uploader
Face Moment. Импорт публичных папок Яндекс Диска сохраняется как post-pilot
направление.

Pilot использует минимальную сущность batch:

~~~text
batch_id
spa_id
visit_date
timezone
confirmed_at
~~~

`source_type=direct_upload` можно считать фиксированным значением и не выводить в
pilot UI. `public_url` добавляется только вместе с post-pilot Yandex flow.

Один batch содержит подтверждённый manifest готовых коммерческих JPEG одного SPA
и одной рабочей даты после законченной съёмочной серии. В один день разрешено
несколько batches.

Подтверждённый `visit_date` является authoritative business date для дневного
search scope. EXIF `captured_at`, имя файла и время upload используются для
сортировки, диагностики и предупреждений, но не могут самостоятельно изменить
`visit_date`.

## 2. Канал первого pilot

1. Фотограф проходит authentication.
2. После законченной съёмочной серии создаёт batch.
3. Выбирает SPA и подтверждает `visit_date`.
4. Загружает готовые JPEG по HTTPS.
5. Сервер проверяет формат и декодирование, вычисляет checksum и показывает
   принятые и отклонённые файлы.
6. Фотограф подтверждает batch.
7. Система фиксирует неизменяемый manifest и `confirmed_at`.
8. Originals сохраняются в MinIO.
9. Идемпотентно создаются `photos` и jobs для serving pipeline.
10. UI показывает processing/searchable status и явные failures.

Повторная отправка одного файла не создаёт новую фотографию, если checksum и
контекст batch совпадают.

## 3. Рабочая дата и EXIF

Для будущего folder-based ingest можно рекомендовать единый формат имени:

~~~text
FM__<SPA_CODE>__<YYYY-MM-DD>__<BATCH_NO>
~~~

Например:

~~~text
FM__DA__2026-07-08__01
~~~

Название полезно для навигации и проверки, но окончательные `spa_id` и
`visit_date` всегда берутся из подтверждённой формы.

Полезно разделять:

- `visit_date` — подтверждённую рабочую дату SPA;
- `captured_at` — время съёмки из EXIF, если оно доступно.

При нескольких EXIF-датах pilot uploader показывает warning, но не меняет
подтверждённую рабочую дату. EXIF summary не является readiness gate. Ручное или
автоматическое разделение mixed-date folders на несколько batches остаётся
post-pilot возможностью: часы камеры могут быть настроены неверно, а съёмка может
продолжаться после полуночи.

## 4. Post-pilot candidate: импорт публичной папки Яндекс Диска

Этот flow не входит в первый pilot, не влияет на его готовность и не должен
добавлять `public_url`, Yandex API или folder snapshotting в pilot
implementation.

Фотографы смогут продолжать использовать собственные аккаунты:

1. Создать отдельную папку для одного SPA и одной рабочей даты.
2. Загрузить готовые фотографии и дождаться синхронизации.
3. Создать публичную ссылку с разрешённым скачиванием.
4. Вставить ссылку в Face Moment, выбрать SPA и рабочую дату.
5. Проверить состав и EXIF-сводку и подтвердить импорт.

Публичные папки можно читать через Yandex Disk REST API без доступа к аккаунту
фотографа:

~~~text
GET /v1/disk/public/resources
GET /v1/disk/public/resources/download
~~~

Рекомендуемая последовательность:

1. Получить полный список файлов с учётом pagination.
2. Показать количество, общий размер, типы файлов и EXIF-даты.
3. После подтверждения зафиксировать список `resource_id`, путей, размеров и
   доступных checksum.
4. Скачать каждый файл отдельно и потоково сохранить в MinIO.
5. Повторно вычислить SHA-256 и проверить декодирование изображения.
6. Создать фотографии и processing jobs.

Фиксация списка помогает не смешивать подтверждённый batch с файлами,
добавленными позднее. Повторный import можно сделать идемпотентным по
`resource_id` и checksum.

Для первой версии этого post-pilot канала проще ориентироваться на готовые к
продаже JPEG. RAW и прочие типы можно показывать в сводке как неподдерживаемые и
не передавать в face-processing.

## 5. Наблюдения по реальным папкам

Проверка публичных папок 2026-07-11 показала:

- [«Да 0707»](https://disk.yandex.ru/d/lIiZOWw-YFnAYA): 367 файлов, среди них
  365 JPEG и 2 CR2; EXIF всех файлов указывает на 2026-07-07;
- [«Да 0709»](https://disk.yandex.ru/d/pquPDBkHJnGZ8g): 453 JPEG; 438 файлов
  имеют EXIF-даты 2026-07-08, 14 — 2026-07-09, один файл не содержит даты.

Пример подтверждает полезность будущего Yandex flow, но не задаёт требований
первого pilot. Название папки и cloud timestamps помогают ориентироваться, а
рабочую дату всё равно подтверждает фотограф.

## 6. MVP первого pilot

- authenticated photographer web uploader;
- direct multi-file upload готовых JPEG;
- обязательный выбор SPA и authoritative `visit_date`;
- validation и явный список повреждённых или неподдерживаемых файлов;
- подтверждение и фиксация manifest batch;
- checksum и идемпотентная повторная отправка;
- originals в MinIO;
- идемпотентное создание `photos` и serving processing jobs;
- UI-статусы `pending | processing | searchable | no_faces | failed`, где
  `searchable` соответствует `photo_pipeline_states.status = ready`;
- измерение `ingest_to_searchable`.

Яндекс Диск, другие external channels, RAW processing, OAuth, Telegram bot и
EXIF-based auto-split являются post-pilot направлениями.

## 7. Семантика `ingest_to_searchable`

Population метрики — все уникальные JPEG из manifest подтверждённых pilot
batches. Rejected до подтверждения файлы и checksum-дубликаты в population не
входят.

~~~text
start = batch.confirmed_at
success = preview готов
          AND photo_pipeline_states.status = ready
          для serving_pipeline_revision
duration = searchable_at - batch.confirmed_at
target = не менее 95% принятых JPEG становятся searchable < 15 минут
~~~

`pending`, `processing`, `failed` и `no_faces` через 15 минут остаются в
denominator как SLO breach, а не исключаются молча. Backfill, benchmark и
non-serving pipeline jobs в метрику не входят. Задержка фотографа
`captured_at → batch.confirmed_at` измеряется отдельно.
