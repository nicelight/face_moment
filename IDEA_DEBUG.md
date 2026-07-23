# Face Moment: отладка и подбор параметров

Обновлено: 2026-07-23

## 1. Назначение

Я хочу, чтобы в Face Moment был встроенный контур отладки, полный интерфейс и
protected content которого доступны только разработчику приложения. Контур должен
связывать
browser-side и server-side logs с конкретной попыткой Promo/QR, помогать находить
источник ошибки или задержки и давать понятные рекомендации по face-match
threshold и качеству входного лица. Это не отдельная monitoring или test-management
система, а часть backend/admin application, создаваемого в этом проекте.

Главной единицей расследования является core Attempt с client-generated
`attempt_id/correlation_id`. Он создаётся до inference и является единственной
обязательной correlation record: отдельный пустой diagnostic anchor не нужен.
Разработчик должен найти Attempt по времени или идентификатору и увидеть её
исход, stage timeline, применённую конфигурацию и все фактически собранные
browser/server events, face-search decisions и protected artifacts. Отсутствие
подробных evidence не скрывает terminal Attempt, а отображается как
`incomplete`.

## 2. Attempts

Страница `Attempts` показывает список попыток с фильтрами по времени, status,
release, pipeline, latency и issue tags. Из списка разработчик открывает одну
attempt и получает общий timeline browser и server.

Оператор может видеть только sanitized outcome, stage timeline, latency и
issue tags. Protected images/crops, имена, annotations, detailed logs и
Calibration доступны только разработчику. Фотограф не имеет доступа к
diagnostic pages.

Timeline должен показывать capture, отправку request, network delay, queue wait,
inference, vector search, формирование response, получение результата браузером,
отрисовку Promo и момент полной видимости QR. Если attempt не уложилась в десять
секунд, разработчик должен сразу видеть, какой этап создал задержку, и иметь
возможность перейти к относящимся к этапу logs.

В detail attempt должны быть видны release, serving pipeline revision,
фактически применённый face threshold, quality values и другие параметры,
которые влияли на результат. Там же показываются выбранные reference
detections, повторные detections одного человека, candidate pools, выбранные
teaser-фотографии и итоговый `N`. Это должно позволять понять, почему group flow
нашёл одних участников, пропустил других или повторно обработал одного человека.

Detailed evidence сохраняются best-effort и не блокируют capture, search, Promo
и QR. Diagnostic images не помещаются в log records; они хранятся как protected
artifacts и открываются из Attempt detail по авторизованным ссылкам. Когда
evidence собраны, Attempt также показывает redacted reproducibility manifest с
версиями, параметрами, timestamps и ссылками на artifacts. Автоматический replay
runner не нужен. Текущий pilot не снимает selfie и не создаёт selfie artifact.

## 3. Ручная разметка

Разработчик вручную размечает результаты на уровне человека и detection. Для
каждого detection можно вписать настоящее имя участника и отметить результат
как `correct`, `wrong/false` или `missed`. Имена тестировщиков разрешено хранить в
diagnostic annotations.

Отдельный реестр участников, pseudonymous IDs, dataset catalog и сложное
управление тестовыми наборами не нужны. Для pilot достаточно простой формы
разметки внутри attempt. Разметка должна использоваться и при анализе group
result, и при расчёте рекомендаций по threshold и quality gates.

## 4. Log Explorer

Страница `Log Explorer` предназначена для глобального поиска по structured
browser/server logs. Разработчик должен фильтровать записи по времени, source,
component, severity, release, message и correlation fields, а из найденной
записи переходить к связанной attempt. Поиск работает через backend,
создаваемый в этом проекте, и не открывает PostgreSQL непосредственно
браузеру.

Searchable logs хранятся в PostgreSQL проекта. Для первой версии не нужны
Grafana Faro/Loki, SigNoz, ClickStack, OpenSearch или другой отдельный
observability datastore. 

Browser logging и server logging должны использовать структурированные записи,
но не должны замедлять или блокировать capture, search, Promo и QR. В logs нельзя
сохранять images, embeddings, auth headers, cookies, tokens, request bodies или
session replay.

Technical browser/server logs хранятся 30 дней. Core Attempts и ordinary
diagnostic evidence хранятся 90 дней. Вручную promoted Calibration case
может храниться до явного удаления, но только как curated subset: выбранные
frames/crops, нужные versions/parameters, scores, annotations и имя участника.
Остальная reference series, Promo screenshot и technical logs удаляются по
обычным срокам.

## 5. Calibration

Страница `Calibration` использует размеченные attempts для сравнения SFace и
Buffalo M и для подбора face-match threshold. Система работает в
рекомендательном режиме: она рассчитывает варианты, объясняет их влияние, но
никогда не меняет serving settings автоматически. Выбранное значение применяет
разработчик вручную.

Для face-match threshold одновременно показываются три рекомендации.
«Лучшее совпадение лица» минимизирует false matches и при равенстве предпочитает
вариант с большим числом correct matches. «Баланс» ищет компромисс между
correct, false и missed results. «Минимум пропусков лиц» минимизирует missed
results и при равенстве предпочитает вариант с меньшим числом false matches.
Точная формула «Баланс» остаётся решением SDD.

Каждая рекомендация показывает предлагаемое числовое значение threshold,
количество `correct`, `false` и `missed`, precision, recall и размер размеченной
выборки. Разработчик должен видеть исходные cases, на которых рассчитан
результат, и иметь возможность перейти от агрегата к конкретной attempt.

Quality gates анализируются отдельно друг от друга, без совместной многомерной
оптимизации. Для face size и detection confidence предлагается minimum cutoff,
для brightness — допустимый range, для pose — maximum absolute yaw, pitch и
roll. Направление blur cutoff определяется фактической семантикой используемого
blur score. Для каждого quality gate показываются текущее и предлагаемое
значение, размер выборки, число kept/rejected detections и ожидаемое изменение
`correct`, `false` и `missed`. Применение также остаётся ручным.

Calibration должна позволять сравнить результаты до и после release либо
изменения parameter/config set. Для этого достаточно уже сохранённых versions,
parameters, outcomes и annotations; отдельная experimentation platform не
нужна.

Calibration запускается только разработчиком во время отладки и может занять
общий `BackgroundPhotoWorker`, временно задержав обработку фотографий. Если worker
перезапущен, Calibration run становится `failed` или `interrupted`, photo processing
возобновляется, а разработчик при необходимости запускает Calibration заново вручную.
Preemption, priority scheduler, automatic reclaim и отдельный Calibration worker не нужны.

## 6. Граница первой версии

Первая версия анализирует face-match threshold, различия SFace/Buffalo M и
quality gates по face size, detection confidence, blur, brightness и pose. Она
не подбирает capture window, frame interval, group-selection parameters,
CPU/thread settings или UI/QR timings. Group-selection решения должны быть
видимы для расследования, но их автоматическая оптимизация не входит в scope.

Мне нужен простой путь от проблемной attempt к ответу: что произошло, где
потрачено время, какое лицо и какие фотографии выбрал алгоритм, почему возникли
false или missed results и как изменится результат при другом threshold или
quality gate. Всё остальное добавляется только после появления измеримой
необходимости.
