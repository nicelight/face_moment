# ASTRA — findings и порядок исправления

Аудит от 2026-09-06, commit `0a46dc8`. Все 13 findings исправлены и приняты; № 10 прошёл isolated packaged smoke 2026-09-07. Исходная нумерация сохранена. Проверки выполнены локально; работающий deployment не проверялся. Пути и номера строк относятся к версии аудита.

## Очередь исправлений

| Порядок | Finding | Исполнитель | Серьёзность | Сложность /10 | Файлы /10 | Примерно файлов | Blast radius /10 |
|---|---|---|---|---:|---:|---:|---:|

Оценки приблизительные, включают реализацию и тесты:

- **Сложность:** 1 — простая локальная правка, 10 — системная переработка.
- **Файлы:** 1 = 1 файл; 2 = 2; 3 = 3–4; 4 = 5–6; 5 = 7–9; 6 = 10–14; 7 = 15–20; 8 = 21–30; 9 = 31–50; 10 = более 50.
- **Blast radius:** область возможной регрессии от исправления; 1 — изолированный компонент, 10 — весь проект.

**Luna работает под руководством Astra:** Astra задаёт план, границы и критерии проверки, затем проверяет результат. № 11 выполнен Astra и принят root; оставшиеся пункты назначены Luna.

Порядок учитывает зависимости: № 7 нужен для browser-проверок № 8–9; № 10 — до выкладки исправлений; решение по snapshot в № 11 — до № 12. Если Buffalo используется в serving, выполнять № 5 первым.

## Контекст для исполнителя

Перед исправлением конкретного пункта прочитать `AGENTS.md`, связанные с ним контракты и текущую реализацию. Сокращённые Python-пути ниже относительны к `src/face_moment/`; остальные пути — к корню репозитория. Имена функций надёжнее исторических номеров строк.

Этот файл содержит причины дефектов, доказательства и критерии исправления. Указанный способ исправления — направление; детали нужно проверить на текущем коде. Таблица задаёт исполнителя, но не заменяет конкретный план Astra для Luna. Для № 10 нужен serving/model fixture, для № 13 — владелец транзакции.

Начать с воспроизведения своего дефекта, затем проверить исправление тем же сценарием и связанными regression tests. Приложение содержит изолированные probes исходного аудита; при этой редактуре они не перезапускались. Некоторые repository/API tests создают disposable PostgreSQL через настройки окружения — прочитать fixture setup перед запуском.

## 3. Потерянные публичные routes

**Код:** `deploy/Caddyfile:19`, `src/face_moment/entrypoints/backend.py`, `src/face_moment/promo/http.py`.

Backend регистрирует маршруты, которые Caddy не пропускает:

- `/api/promo/*`;
- `/api/serving/spas/{spa_id}/active-visit-date`;
- `/api/diagnostics/retention`;
- `/staff/search-settings`, `/staff/photo-inventory`;
- `/staff/calibrations` и дочерние paths;
- `/staff/diagnostics-retention`.

Promo не может загрузить config/previews; перечисленные staff-сценарии недоступны через штатный edge. Подтверждено сопоставлением конфигурации с routes; настоящий Caddy не запускался.

**Исправление:** добавить маршруты, сохранив realtime upstream, auth boundary и body caps. Проверить config/media/ack и staff paths через edge.

**Контракт и тесты:** `.memory-bank/contracts/promo-display-api.md`; `tests/client/test_central_shell.py`, `tests/promo/test_promo_display_api.py`.

**Нюанс:** `compose.yaml` монтирует проверенный Caddyfile; `deploy/frp/vps/Caddyfile` сохраняет path. Наличие `/backend/*` не помогает клиенту, который обращается по canonical URL. Проверка нескольких строк Caddyfile или прямой вызов ASGI backend не доказывают работоспособность edge. Для закрытых routes проверить также сохранение отказа без credentials.

## 4. Нет рабочей страницы входа сотрудников

**Код:** `platform/auth/http.py:35`.

`GET /staff/login` возвращает только `<main><h1>Staff login</h1></main>`. Формы и обработчика нет; пользователь не может войти через штатный UI и начать загрузку фотографий.

**Доказательство:** настоящий backend ASGI route вернул 200 с этим HTML. Session API существует, тесты создают сессии прямыми запросами.

**Исправление:** форма username/password, вызов существующего session API, обработка отказа и переход после успеха. Проверить вход в браузере без готовых cookies.

**Контракт и тесты:** `.memory-bank/contracts/photo-admission-api.md#staff-session-endpoints`, `.memory-bank/domains/staff-access.md`; `tests/staff_access/test_sessions.py`.

**Нюанс:** `POST /api/staff/sessions` принимает JSON ровно с `username` и `password`, возвращает 204 и cookies; неверные credentials — 401, rate limit — 429. Реализовать форму поверх этого API, сохранив cookie/CSRF contract. Дополнить прямые API-тесты пользовательским путём: новый браузер → вход → доступ к staff-сценарию.

**Статус:** исправлен и проверен в текущем исходном коде. Clean-profile Playwright CLI proof подтвердил реальный `401`, `429`, `204` с canonical cookies, переход на `/staff/photo-inventory` (`200`), доступ фотографа к `/staff/photo-upload` (`200`) и восстановимую техническую ошибку Caddy `502`; `mypy`, staff-session pytest (`4 passed`) и `mb-lint` прошли. Redacted evidence: [.tasks/TASK-116-T3-FT-001-W9/playwright-cli-transcript.md](../../.tasks/TASK-116-T3-FT-001-W9/playwright-cli-transcript.md), [cleanup-record.md](../../.tasks/TASK-116-T3-FT-001-W9/cleanup-record.md).

## 5. Buffalo M падает при ready=True

**Код:** `processing/buffalo_adapter.py:133–166`, `processing/model_admission.py:48,71`.

Detector загружается без настройки input size; `detect(photo)` тоже не получает размер. `warmup()` проверяет только assets, `ready` всегда равен True. Ошибка блокирует Buffalo в Photo processing, realtime и Calibration.

**Доказательство:** production adapter с настоящим локальным `scrfd.onnx` имеет `input_size=None` и падает с `AssertionError` на изображении 320×320. Четыре unit tests с detector doubles проходят. Выбор Buffalo в работающем serving не проверялся.

**Исправление:** настроить native detector и проверять реальный inference перед ready. Добавить regression с dynamic-input ONNX; SFace менять не требуется.

**Контракт и тесты:** `.memory-bank/domains/photo-processing.md`; `tests/processing/test_buffalo_adapter.py`, `tests/processing/test_model_asset_admission.py`.

**Нюанс:** `from_configured_assets()` вызывает InsightFace `get_model()`; фактически загруженный detector — `RetinaFace` с ONNX input shape `[1,3,'?','?']`. Asset находится в `models/insightface_buffalo_m/scrfd.onnx`, recognizer — `w600k_r50.onnx` рядом. Revision должна соответствовать identity/checksums этих assets. Проверка лишь detector double снова пропустит ошибку; для ready нужен настоящий native вызов. Реальная загрузка воспроизводится отдельной командой в приложении.

## 6. Несогласованная EXIF orientation

**Код:** `inventory/validation.py:87–124`, `processing/photo_orchestration.py:110`, `processing/terminal_publication.py:221–227`.

Admission сохраняет размеры без EXIF-поворота, processing применяет поворот. Bbox сравнивается с размерами в другой системе координат, часть фотографий уходит в failed после повторных попыток.

**Доказательство:** JPEG 30×10 с orientation 6 принят как 30×10, декодирован как 10×30; корректный bbox `x=2,y=15,w=5,h=5` отвергнут с `face bounds must fit within the photo`.

**Исправление:** единая orientation/coordinate policy для admission, processing и derivatives; bbox validation сохранить. Отдельно определить, нужна ли коррекция размеров существующих Photo. Проверить orientation 6/8 сквозным тестом.

**Контракт и тесты:** `.memory-bank/domains/photo-admission.md`, `.memory-bank/domains/photo-processing.md`; `tests/inventory/test_jpeg_validation.py`, `tests/processing/test_photo_orchestration.py`, `test_terminal_publication.py`, `test_derivatives.py` в той же папке.

**Нюанс:** admission использует `IMREAD_IGNORE_ORIENTATION`, processing — `IMREAD_COLOR`. У orientation 5–8 размеры неквадратного изображения меняются местами; ошибка зависит от положения bbox. Повторная обработка тех же bytes не исправляет координаты. Согласовать размеры, bbox, landmarks и derivatives при сохранении оригинальных JPEG bytes. Проверить обычное изображение и повернутое; коррекцию уже сохранённых данных определить отдельно. Исходный probe — в приложении «EXIF и Calibration».

## 7. Невоспроизводимые browser recovery tests

**Код:** `tests/client/test_browser_recovery.spec.mjs:8,23`, `tests/client/test_degraded_advertising.spec.mjs:8`, `client/sensor-config.js:14–39`.

Specs импортируют `playwright/test`, но project-managed package/lock/runner отсутствует. Recovery fixture сохраняет `sensor_id`, production reader ожидает `sensorId`.

**Доказательство:** общий Node-прогон — 42 passed, 2 module-resolution failures до browser assertions. Фактическая browser regression этим не доказана.

**Исправление:** воспроизводимый runner и совместимая fixture. Проверять восстановление через production reader и поведение после restart.

**Контракт:** `.memory-bank/testing/client-realtime.md`. Проверять именно два spec-файла из поля «Код», а также production `client/sensor-config.js`.

**Нюанс:** установить зависимость глобально недостаточно — запуск должен воспроизводиться из репозитория. Проверка raw localStorage с неправильным `sensor_id` не проверяет восстановление конфигурации production reader. Критерий закрытия — specs выполняют browser assertions после restart и обычные Node-тесты остаются запускаемыми.

**Статус:** исправлен и принят root после source-read review. Независимый browser acceptance подтвердил `9 passed`, обычный Node unit acceptance — `42 passed`. [Browser QA transcript](../../.tasks/ASTRA-findings/07-browser-runner/browser-qa-transcript.log).

## 8. Неограниченное ожидание config/media

**Код:** `client/promo-display.js:403–419,462–471`, `client/app.js:392–430`, `client/realtime-attempt.js:232`.

Config/media fetch и decode не ограничены deadline. Таймер показа появляется после загрузки previews; зависшая загрузка удерживает attempt в busy и мешает следующим попыткам.

**Доказательство:** controlled pending fetch оставляет production `loadDisplayConfiguration()` незавершённым, AbortSignal отсутствует; другого освобождающего таймера в этой ветви нет.

**Исправление:** ограничить ожидание, завершать attempt через failure path, отменять transport и игнорировать поздние ответы. Проверить возврат к рекламе и возможность следующей попытки.

**Контракт и тесты:** `.memory-bank/contracts/promo-display-api.md`, `.memory-bank/testing/client-realtime.md`; `tests/client/test_promo_display.mjs`, `test_promo_display_timers.mjs`, `test_realtime_attempt.mjs` в той же папке.

**Нюанс:** `attempt-finished` не наступает до завершения показа; существующий timeout acknowledgement покрывает более позднюю стадию. Проверить по отдельности зависший config, один зависший preview, decode failure и позднее завершение после timeout. Старый ответ не должен менять новый показ. Учесть освобождение URL из № 9. Исходный pending-fetch probe — в приложении «Blob lifecycle и pending configuration».

**Статус:** исправлен и принят root после source-read review. Последние независимые gates подтвердили `47 passed` unit и `11 passed` browser; production capture-controller probe подтвердил переход `searching` → `advertising`, `nextAcceptTrigger: true`, следующий trigger `capturing` и отсутствие success-cooldown timers. Follow-up correction for the shared view container keeps the existing advertising card visible while a result's previews are loading and removes only an owned Promo card after failure or expiry; this is covered by the updated stalled-preview browser assertion. [Evidence](../../.tasks/ASTRA-findings/08-promo-deadline/independent-client-gate-transcript.log), [follow-up gate](../../.tasks/ASTRA-findings/09-blob-lifecycle/browser-gate.log).

## 9. Утечка Blob URL

**Код:** `client/promo-display.js:414,481–499`.

Каждый показ создаёт четыре Blob URL, но `revokeObjectURL` не вызывается. Удаление DOM не освобождает эти регистрации; память удерживается до выгрузки страницы.

**Доказательство:** 100 циклов production controller с DOM/URL doubles — 400 созданных URL, 0 освобождённых. RAM реального Chromium не измерялась.

**Исправление:** cleanup на expiry, failure, timeout и stale, включая поздние результаты `Promise.all`. Проверить повторные показы и отсутствие преждевременного revoke видимых previews.

**Контракт и тесты:** `.memory-bank/contracts/promo-display-api.md`; `tests/client/test_promo_display.mjs`, `test_promo_display_timers.mjs` в той же папке.

**Нюанс:** при отказе одного элемента `Promise.all` другие загрузки продолжаются и могут создать URL уже после общего cleanup. Отслеживать владельца каждого URL и обрабатывать позднее завершение; удаление DOM недостаточно. Regression должен считать созданные/освобождённые URL на успешном цикле и в ветвях отказа. Исходный 100-cycle probe — в приложении.

**Статус:** исправлен и принят root после source-read review и независимой проверки: 52 unit, 11 browser, 100 циклов с 400 созданными и 400 освобождёнными URL. Уточнение оператора о расходных данных сняло preservation blocker. Ошибочный запуск Python-тестов остаётся отдельным incident evidence; безопасность прошлого запуска не утверждается. [Independent review](../../.tasks/ASTRA-findings/09-blob-lifecycle/independent-review.md), [incident](../../.tasks/ASTRA-findings/09-blob-lifecycle/incident-review.md).

## 10. Устаревший packaged smoke

**Код:** `scripts/smoke-runtime.sh:121–185`, `.memory-bank/guides/local-development.md:64–72`.

Smoke запускает роли без обязательного serving/model seed, требует ноль application tables после migrations и ожидает устаревшее health-поле `engine=fake`. Рекомендуемая проверка deployability несовместима с текущим runtime.

**Доказательство:** assertions противоречат migrations и startup prerequisites. Docker/Compose smoke в аудите не запускался.

**Исправление:** Astra определяет изолированный serving/model setup; Luna обновляет seed, assertions и инструкцию. Проверить настоящий packaged runtime, включая routes из № 3.

**Контекст запуска:** `src/face_moment/entrypoints/model_consumers.py`, `src/face_moment/serving_control/ingest_target.py`, `src/face_moment/entrypoints/migrate.py`, migrations и `compose.yaml`.

**Нюанс:** без committed SPA/revision model-consuming роли не становятся healthy; `upgrade head` создаёт product tables; realtime публикует `production_model_loaded` вместо `engine=fake`. Это три независимые устаревшие предпосылки одного smoke. Исправить все три, сохранив изоляцию тестовой инфраструктуры. Успех — smoke проходит с текущими migrations и настоящими readiness prerequisites, а не после ослабления production startup.

**Текущее состояние № 10:** исправлен root по прямому поручению оператора. Реальный isolated packaged smoke прошёл: current migrations, SFace seed/binding, три healthy роли, HTTPS 200/401/404 до и после перезапуска, storage persistence и owned cleanup. Исправлена одна preflight-ошибка чтения null IPAM; первоначальный и успешный логи сохранены. [Handoff и evidence](../../.tasks/ASTRA-findings/10-packaged-smoke/implementation-report.md). Deployment не выполнялся.

## 11. Calibration запрещает сравнение других параметров

**Код:** `diagnostics/calibration_runs.py:167,269,308`, `tests/diagnostics/test_calibration_runs.py:295`.

`dataset_sha256` включает данные, pipeline revisions и настройки. Изменение параметров меняет hash даже на тех же Photo/Attempts; `compare_complete()` отклоняет сравнение.

**Доказательство:** production repository с in-memory Session double; изменены только serving threshold и settings revision — результат `DatasetMismatchError: dataset_mismatch`.

**Конфликт контрактов:** PRD `FR-DEV-09` и `.memory-bank/testing/calibration.md:104` требуют before/after разных параметров на одних данных; `.memory-bank/domains/calibration.md` определяет hash полного immutable input.

**Исправление:** согласовать dataset identity, отделяющую данные от сравниваемых параметров, и совместимость старых runs. Проверить: те же данные с другими параметрами сравниваются; изменённый датасет отклоняется.

**Контракт и тесты:** `.memory-bank/domains/calibration.md`, `.memory-bank/testing/calibration.md#beforeafter-and-manual-apply-proof`, PRD `FR-DEV-09`; `tests/diagnostics/test_calibration_runs.py`, `test_calibration_http.py` в той же папке.

**Нюанс:** snapshot содержит `photos`, `attempts`, `pipeline_revisions`, `serving_values`, `candidate_values`; `create_requested()` хэширует всё. Существующий тест специально ожидает mismatch при изменении `candidate_values`, поэтому зелёные тесты закрепляют проблему. Полностью одинаковые snapshots сравниваются. Не удалять mismatch-проверку целиком: нужно отделить данные от намеренно изменённых параметров и решить судьбу старых hashes. Исторические annotations как источник одной threshold-рекомендации — отдельное принятое ограничение, не часть этого finding.

**Статус:** исправлен и независимо проверен root. Сравнение complete runs вычисляет hash frozen data без ровно трёх верхнеуровневых evaluation fields; полные snapshots, persisted fingerprints и result bundles сохраняются. Те же данные с другими параметрами сравниваются, изменённые данные отклоняются. Правило работает для старых и новых runs без миграции, но не восстанавливает утраченные selected IDs/exclusions старых snapshots. Изолированные implementer и root gates — по `28 passed`, mypy и mb-lint прошли. [Evidence](../../.tasks/ASTRA-findings/11-calibration-identity/implementation-report.md).

## 12. Calibration теряет исходный selected sample

**Код:** `diagnostics/calibration_runs.py:754–798,899–900`.

`_frozen_attempts()` выбрасывает выбранные Attempts без annotations. Selected count рассчитывается уже по сокращённому snapshot; исходный выбор и exclusions теряются.

**Доказательство:** выбраны два Attempts, один annotated — reported selected/applicable = 1/1 вместо 2/1.

**Исправление:** сохранить исходные selected IDs и exclusions, считать applicable отдельно. Использовать согласованную в № 11 форму snapshot; проверить mixed annotated/unannotated выборку.

**Контракт и тесты:** `.memory-bank/domains/calibration.md#immutable-input-and-evaluation`; `tests/diagnostics/test_calibration_runs.py`, `test_calibration_http.py` в той же папке.

**Нюанс:** `_compose_balance_recommendation()` получает уже сокращённый snapshot, поэтому одной правкой отображения исходный выбор не восстановить. Сохранять exclusions, не создавать вымышленные annotations/outcomes для неразмеченных Attempts. Проверить смешанную и полностью неразмеченную выборки: исходные selected IDs/count доступны, applicable соответствует реальным annotations. Исходный probe — в приложении «EXIF и Calibration».

**Статус:** исправлен и принят root. Новые snapshots сохраняют полный `selected_attempt_ids` и `selection_exclusions`, а применимые annotated Attempts остаются отдельной frozen projection. Проверены смешанная выборка `2/1`, полностью неразмеченная `2/0` без recommendation, неизменность после поздней annotation, commit/reload fingerprint и UI rendering IDs/reasons. Legacy snapshots без selection metadata показывают selected count как unavailable; queued legacy execution не реконструирует selection и не создаёт свежую recommendation. Bounded root gate — `35 passed`, disposable UUID database/bucket удалены; mypy, mb-lint и `git diff --check` прошли. [Evidence](../../.tasks/ASTRA-findings/12-calibration-selection/implementation-report.md).

## 13. Revision switch конфликтует с открытой транзакцией

**Код:** `serving_control/ingest_target.py:124–132`.

`switch_serving_revision()` вызывает `Session.begin()`, хотя предварительное чтение уже запускает autobegin.

**Доказательство:** production method после `SELECT 1` в in-memory Session падает с `InvalidRequestError: A transaction is already begun on this Session`. Production caller отсутствует; дефект латентный.

**Исправление:** Astra определяет владельца транзакции; Luna приводит метод к этому contract и проверяет preread, commit и rollback. Исправить до подключения serving-switch caller.

**Тесты:** `tests/serving_control/test_serving_revision_switch.py`; implementation class — `IngestTargetRepository`.

**Нюанс:** обычный предварительный SELECT уже открывает транзакцию SQLAlchemy. Механическая замена на savepoint может скрыть конфликт, не обеспечив внешний commit. Выбрать владельца транзакции и проверить сохранение при успехе и rollback при отказе. Это переключение pipeline revision; отдельный Calibration apply меняет settings и к данному дефекту не относится. Исходный in-memory probe — в приложении «Transaction contract».


## Изолированное воспроизведение

Запускать из корня репозитория с установленными зависимостями. Эти команды сохраняют исходные probes до исправления: assertions и вывод показывают дефект. После правки преобразовать их в проверки ожидаемого поведения. DB/model doubles в них явно ограничивают область доказательства; проверки реальных моделей отмечены отдельно.

### Buffalo: настоящая загрузка модели — № 5

Использует локальные ONNX и согласованную временную revision без БД.
Исходный результат: `ready=True`, `input_size=None`, затем `AssertionError`.
Если assets отсутствуют, этот probe не проверяет finding; fake weights его
не заменяют.

```bash
NO_ALBUMENTATIONS_UPDATE=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY'
from pathlib import Path
import runpy
import numpy as np
from face_moment.processing.buffalo_adapter import BuffaloModelAssets, BuffaloPhotoAdapter

f = runpy.run_path('tests/processing/test_buffalo_adapter.py')
assets = BuffaloModelAssets(
    detector_path=Path('models/insightface_buffalo_m/scrfd.onnx'),
    recognizer_path=Path('models/insightface_buffalo_m/w600k_r50.onnx'),
    detector_id='scrfd', detector_version='probe',
    recognizer_id='w600k_r50', recognizer_version='probe',
    preprocessing_version='probe', alignment_version='probe',
    normalization_version='probe', embedding_dimension=512,
)
revision = f['_revision'](assets, embedding_dimension=512)
adapter = BuffaloPhotoAdapter.from_configured_assets(revision=revision, assets=assets)
adapter.warmup()
print('adapter.ready', adapter.ready, 'detector.input_size', adapter._detector.input_size)
try:
    print('faces', adapter.process_photo(np.zeros((320, 320, 3), dtype=np.uint8)))
except Exception as error:
    print('production process_photo:', type(error).__name__, str(error))
PY
```

### EXIF и Calibration — № 6 и 12

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY'
import runpy
from types import SimpleNamespace as NS
from uuid import uuid4
import cv2
import numpy as np
from face_moment.processing.terminal_publication import (
    TerminalFace, TerminalPublicationRepository,
)
from face_moment.diagnostics.calibration_runs import (
    _frozen_attempts, _compose_balance_recommendation,
)
from face_moment.processing.revisions import PipelineCode

f = runpy.run_path("tests/inventory/test_jpeg_validation.py")
jpeg = f["_jpeg"](width=30, height=10, orientation=6)
candidate = f["_validate"](jpeg)
image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
face = TerminalFace(
    face_index=0, bbox_x=2, bbox_y=15, bbox_w=5, bbox_h=5,
    landmarks_json=[[3,16]]*5, detection_confidence=.99, embedding=(1.,0.),
)
print("EXIF admitted", candidate.width, candidate.height,
      "decoded", image.shape[1], image.shape[0])
try:
    TerminalPublicationRepository._validate_faces(
        (face,), embedding_dimension=2,
        photo_width=candidate.width, photo_height=candidate.height,
    )
except ValueError as error:
    print(type(error).__name__, str(error))
else:
    raise AssertionError("Expected EXIF mismatch")

ids = [uuid4(), uuid4()]
revision = uuid4()
pipeline = PipelineCode.OPENCV_SFACE.value
class Session:
    def get(self, *args):
        return NS(threshold=.6, pipeline_revision_id=revision,
                  pipeline_code=pipeline)
class Provider:
    def calculation_snapshot(self, *, attempt_id):
        annotations = [] if attempt_id == ids[1] else [NS(
            annotation_id=uuid4(), attempt_id=attempt_id,
            target_kind="person", detection_occurrence_index=None,
            participant_name="A", outcome="correct",
        )]
        return NS(attempt_id=attempt_id, annotations=annotations)
frozen = _frozen_attempts(Session(), Provider(), ids)
snapshot = {
    "attempts": frozen,
    "pipeline_revisions": {"sface": str(revision), "buffalo_m": str(uuid4())},
    "serving_values": {
        "pipeline_code": pipeline, "pipeline_revision_id": str(revision),
        "quality_settings": {}, "min_query_face_quality": .5,
    },
}
profile, _ = _compose_balance_recommendation(snapshot)
print("Calibration actual selected", len(ids), "reported",
      profile.selected_attempt_count, profile.applicable_attempt_count)
assert (profile.selected_attempt_count, profile.applicable_attempt_count) == (1,1)
PY
```

### Blob lifecycle и pending configuration

```bash
node --input-type=module <<'JS'
import {createPromoDisplayController} from './client/promo-display.js';
globalThis.localStorage = {getItem: () => 'fixture-token'};
let created=0, revoked=0, expire;
const element = () => ({
  dataset:{}, classList:{add(){}}, append(){},
  replaceChildren(){}, setAttribute(){},
  getBoundingClientRect(){return {width:100,height:100}}
});
const c = createPromoDisplayController({
  container:element(),
  documentImpl:{createElement:element,createElementNS:element},
  fetchImpl:async()=>({ok:true,blob:async()=>new Blob(['jpeg'])}),
  imageFactory:()=>({decode:async()=>{}}),
  urlApi:{
    createObjectURL(){return 'blob:'+(++created)},
    revokeObjectURL(){revoked++}
  },
  setTimeoutImpl(fn){expire=fn;return 1},
  clearTimeoutImpl(){}, origin:'https://fm.test'
});
const result={
  session_id:'s',n:4,
  teasers:[0,1,2,3].map(i=>({
    photo_id:String(i),media_url:'/api/promo/media/'+i
  })),
  qr_url:'/q?ticket=t'
};
for(let i=0;i<100;i++){
  await c.showResult({
    attemptId:String(i),result,
    displayConfig:{
      schema_version:1,result_display_ms:100,success_cooldown_ms:100
    }
  });
  expire();
}
console.log({cycles:100,created,revoked,visible:c.isVisible});
let options;
c.fetchImpl=(_url,opts)=>{options=opts;return new Promise(()=>{})};
const pending=c.loadDisplayConfiguration();
const config=await Promise.race([
  pending.then(()=> 'resolved',()=> 'rejected'),
  new Promise(resolve=>setTimeout(()=>resolve('still pending'),25))
]);
console.log({config,signalPresent:'signal' in options});
JS
```

### Transaction contract

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY'
from uuid import uuid4
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import InvalidRequestError
from face_moment.serving_control.ingest_target import IngestTargetRepository
with Session(create_engine("sqlite:///:memory:")) as session:
    session.execute(text("SELECT 1"))
    try:
        IngestTargetRepository(session).switch_serving_revision(
            spa_id=uuid4(),target_pipeline_revision_id=uuid4())
    except InvalidRequestError as error:
        print(type(error).__name__,str(error))
    else:
        raise AssertionError("Expected transaction conflict")
PY
```


## Статус исправлений в текущей сессии

- № 5: исправлен Luna в рамках TASK-114-T3-FT-002-W6; root независимо проверил полный двухфайловый gate (26 passed) и native ONNX node без skip. Индексированный task lifecycle closure отдельно не заявляется. Историческое описание finding и исходный probe сохранены; подробности: .tasks/TASK-114-T3-FT-002-W6/final-gates.md.
- № 3 закрыт: TASK-115-T3-FT-005-W4; root independently проверил live Caddy и central-shell gate (7 passed), включая authenticated Promo/staff paths, CSRF/role rejection, realtime dispatch, body caps и private-route isolation. Caddy 2.10.0 validate прошёл; deployment не выполнялся.
- № 4 закрыт: TASK-116-T3-FT-001-W9; clean-profile Playwright CLI, current-source mypy, staff-session pytest (`4 passed`) и Memory Bank lint проверены. Redacted evidence: [.tasks/TASK-116-T3-FT-001-W9/playwright-cli-transcript.md](../../.tasks/TASK-116-T3-FT-001-W9/playwright-cli-transcript.md), [cleanup-record.md](../../.tasks/TASK-116-T3-FT-001-W9/cleanup-record.md).
- № 6 закрыт для новых загрузок: admission применяет ту же EXIF orientation, что processing и derivatives; original bytes/SHA-256 и bbox validation сохранены. Расширенный изолированный gate — 37 passed, независимый root gate — 29 проверок, mypy и mb-lint прошли. Существующие неверные Photo metadata и terminal failed не исправляются автоматически; duplicate re-upload также не исправляет metadata. [Evidence и ограничение первого неизолированного прогона](../../.tasks/ASTRA-findings/06-exif/implementation-report.md).
- № 11 закрыт: root принял разделение полного input fingerprint и вычисляемого hash данных для comparison; независимый изолированный gate — `28 passed`, временные БД и bucket удалены. Исторические snapshots не переписываются, утраченная selection не восстанавливается. [Evidence](../../.tasks/ASTRA-findings/11-calibration-identity/implementation-report.md).
- № 12 закрыт: root принял сохранение полного selected sample и явных exclusions, отдельную applicable projection, честные `2/1` и `2/0` counts и conservative legacy boundary; bounded gate — `35 passed`, временные БД и bucket удалены. [Evidence](../../.tasks/ASTRA-findings/12-calibration-selection/implementation-report.md).
- № 13 закрыт и принят root: owner transaction contract исправлен, root независимо подтвердил preread→commit, rejection preservation, post-flush rollback/retry, serving guard/concurrency и совместимость Calibration apply — `6 passed`; старый serving-switch matrix сохраняет собственную UUID БД, новые transaction tests и Calibration apply используют disposable PostgreSQL helper. Исторический finding и in-memory probe сохранены выше. [Evidence](../../.tasks/ASTRA-findings/13-revision-transaction/implementation-report.md).
- Deployment не выполнялся. Оставшиеся findings и probes выше описывают состояние до соответствующих исправлений.
