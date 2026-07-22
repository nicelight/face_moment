# Face Moment — дополнительные идеи к рассмотрению

Этот advisory-документ содержит только полезные идеи из прежней версии `arch_impr1.md`, которые отсутствуют или недостаточно явно отражены в текущем `arch_vision.md`. Они рекомендуются к отдельному рассмотрению и не меняют принятые пять slices, KISS reliability target или отменённые решения.

## 1. pHash как ranking-only сигнал

Рекомендуется явно закрепить `pHash` за slice `processing` и использовать его только для ranking/diversity среди уже threshold-valid фотографий. `pHash` не рекомендуется применять как дополнительный eligibility gate или способ расширения match set.

Почему рекомендуется: pHash относится к derived/search данным, а не к immutable ingest. Ranking-only семантика сохраняет face threshold единственным источником match eligibility и снижает риск ложного добавления визуально похожих фотографий.

## 2. Stale-response guard через активный `attempt_id`

Рекомендуется принимать realtime response только тогда, когда его `(spa_id, attempt_id)` всё ещё соответствует активной попытке SpaPromoClient. Ответ завершённой, отменённой или уже заменённой попытки рекомендуется молча отбрасывать без Promo rendering и cooldown.

Почему рекомендуется: timeout или network delay могут вернуть корректный, но уже устаревший результат. Проверка активного `attempt_id` предотвращает показ результата предыдущему участнику без отдельного `capture_id`.

## 3. Key-only SSH и sandboxed Chromium

Рекомендуется оставить только key-based SSH administration и запускать Chromium под непривилегированным OS user с включённой browser sandbox.

Почему рекомендуется: это дешёвые штатные controls для пилотного сервера и публичного display. Они сокращают последствия компрометации без IAM, bastion platform или отдельного device-management слоя.

## 4. Минимальный realtime request payload

Рекомендуется явно определить в realtime contract:

- одну простую `contract_version`;
- client-generated `attempt_id`;
- момент готовности reference series на client monotonic timeline;
- ordered frames;
- относительный capture timestamp каждого frame;
- минимальную camera/capture metadata, реально используемую диагностикой или обработкой.

Почему рекомендуется: порядок и относительное время кадров позволяют воспроизвести pre/post-trigger series без синхронизации часов клиента и сервера. Одна версия contract даёт дешёвое обнаружение несовместимого client/server release без protocol-negotiation framework.

Прежний отдельный `capture_id` и server-created `attempt_id` не рекомендуются: единый client-generated `attempt_id` уже покрывает correlation, idempotency и stale-response isolation.

## 5. Ручной retry terminal `failed` photo

Рекомендуется предоставить авторизованному operator/developer простой manual action, возвращающий выбранную terminal `failed` photo-processing запись в `pending`. Повтор рекомендуется начинать с нуля и проводить через тот же bounded retry/final-publication flow.

Почему рекомендуется: автоматический retry limit останавливает poison-file loop, но временная ошибка или исправленная конфигурация не должны требовать ручного SQL. Один explicit retry command дешевле automatic lease recovery, scheduler или workflow engine.

## 6. Стандартные HTTP statuses для технических ошибок

Рекомендуется выражать authentication, authorization, validation, payload-limit, rate-limit и unexpected server errors обычными HTTP statuses, например `401`, `403`, `413`, `422`, `429` и `5xx`. Небольшой domain outcome enum рекомендуется оставить только для результатов capture/search, таких как `busy`, `deadline`, unacceptable query или insufficient results.

Почему рекомендуется: стандартное разделение transport errors и business outcomes упрощает client logic, логи и тесты. Собственный error framework или protocol-negotiation layer не дают сопоставимой пользы для одного backend.

## 7. Одна PostgreSQL schema и один metadata registry

Рекомендуется физически оставить одну PostgreSQL schema и один SQLAlchemy metadata/migration stream для всего modular monolith. Capability slices остаются code-level владельцами данных; отдельные DB users, schemas и ACL per slice не рекомендуются.

Почему рекомендуется: slices нужны для semantic/write ownership, а не для имитации микросервисов внутри одной БД. Физическое дробление усложнило бы migrations, joins, shared transactions и локальную разработку без isolation benefit для одного deployable.

## 8. Один дешёвый import-boundary test

После появления реальных imports рекомендуется один небольшой architecture test, проверяющий только устойчивые правила, например отсутствие прямого импорта foreign write repositories и запрещённых обратных зависимостей между slices. Полный architecture validator или per-file ownership registry не рекомендуется.

Почему рекомендуется: один механический тест дешево предотвращает постепенное размывание пяти slices. Он полезнее подробной документации imports, которая быстро расходится с кодом.

## 9. Простые liveness endpoints

Рекомендуется иметь простой liveness signal для backend и BackgroundPhotoWorker, а для RealtimeFaceService — отдельный readiness signal после загрузки и warmup активной model revision. Edge может возвращать обычный `502/503`, пока upstream недоступен.

Почему рекомендуется: минимальные endpoints позволяют Compose и operator отличить работающий процесс от упавшего или неготового. Более сложная readiness matrix, route admission orchestration и автоматический healing остаются неоправданными для stop-the-world one-server deployment.
