# Face Moment: отладка и подбор параметров

Обновлено: 2026-07-18

## 1. Назначение

Я хочу, чтобы в Face Moment был встроенный developer-only контур отладки. Его
главный пользователь — разработчик приложения. Контур должен связывать
browser-side и server-side logs с конкретной попыткой Promo/QR, помогать быстро
находить источник ошибки или задержки и давать понятные рекомендации по
face-match threshold и качеству входного лица. Это не отдельная monitoring или
test-management система, а небольшая часть существующей админки.

Главной единицей расследования является attempt с единым
`diagnostic_session_id/correlation_id`. Разработчик должен найти attempt по
времени или идентификатору и увидеть всю её историю: browser events, server
processing, фактически применённую конфигурацию, результаты face search,
решения group algorithm и связанные diagnostic artifacts. Логи без связи с
attempt не должны быть единственным способом расследования.

## 2. Attempts

Страница `Attempts` показывает список попыток с фильтрами по времени, status,
release, pipeline, latency и issue tags. Из списка разработчик открывает одну
attempt и получает общий timeline browser и server.

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

Diagnostic images не помещаются в log records. Они остаются в существующем
diagnostic bundle и открываются из attempt detail по разрешённым ссылкам. Для
воспроизведения сложного case attempt также показывает manifest с версиями,
параметрами, timestamps и ссылками на связанные artifacts. Автоматический
replay runner для этого не нужен.

## 3. Ручная разметка

Разработчик вручную размечает результаты на уровне человека и detection. Для
каждого detection можно вписать настоящее имя участника и отметить результат
как `correct`, `wrong` или `missed`. Имена тестировщиков разрешено хранить в
diagnostic annotations.

Отдельный реестр участников, pseudonymous IDs, dataset catalog и сложное
управление тестовыми наборами не нужны. Для pilot достаточно простой формы
разметки внутри attempt. Разметка должна использоваться и при анализе group
result, и при расчёте рекомендаций по threshold и quality gates.

## 4. Log Explorer

Страница `Log Explorer` предназначена для глобального поиска по structured
browser/server logs. Разработчик должен фильтровать записи по времени, source,
component, severity, release, message и correlation fields, а из найденной
записи переходить к связанной attempt. Поиск работает через существующий backend
и не открывает PostgreSQL непосредственно браузеру.

Searchable logs хранятся в существующем PostgreSQL. Для первой версии не нужны
Grafana Faro/Loki, SigNoz, ClickStack, OpenSearch или другой отдельный
observability datastore. 

Browser logging и server logging должны использовать структурированные записи,
но не должны замедлять или блокировать capture, search, Promo и QR. В logs нельзя
сохранять изображения, embeddings, auth headers, cookies, tokens или другие крупные и чувствительные payloads. Session
replay не нужен.

Technical browser/server logs хранятся 30 дней. Attempts и diagnostic bundles
хранятся 90 дней. Отдельные полезные cases, вручную выбранные для calibration,
вместе с их разметкой хранятся до явного удаления.

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
