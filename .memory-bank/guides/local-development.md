---
description: Local-first Python development with uv and containerized PostgreSQL/MinIO.
status: active
last_updated: 2026-09-09
source_of_truth:
  - .memory-bank/guides/local-development.md
---
# Local development

## Shape

Daily development runs the changing Python code directly from the working tree:

- `backend`, `background-worker`, `realtime`, migrations, mypy and pytest run
  through `uv` on Python 3.11;
- PostgreSQL/pgvector and MinIO stay in Docker;
- Caddy and the Python image are reserved for the packaged runtime smoke.

This does not change the release topology in `compose.yaml`.

## First start

Install `uv` once, then from the repository root:

```bash
test -e .env.local || cp .env.example .env.local
uv sync --python 3.11
docker compose -f compose.yaml -f compose.local.yaml up -d postgres minio
docker compose -f compose.yaml -f compose.local.yaml exec -T postgres sh -ceu 'psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '\''face_moment_local'\''" | grep -q 1 || createdb -U "$POSTGRES_USER" face_moment_local'
uv run --locked --env-file .env.local face-moment-migrate
```

`.env.local` is ignored by Git. Keep `.env.example` as the safe local template;
do not reuse or source the repository `.env`, which may contain unrelated
operator settings.

## Daily commands

```bash
# Start only infrastructure.
docker compose -f compose.yaml -f compose.local.yaml up -d postgres minio

# Current-source checks.
uv run --locked python -m mypy src/face_moment
uv run --locked --env-file .env.local python -m pytest

# Run one role directly from the editable source.
uv run --locked --env-file .env.local face-moment-backend
uv run --locked --env-file .env.local face-moment-background-worker
uv run --locked --env-file .env.local face-moment-realtime
```

The backend is available at `http://127.0.0.1:8000`. Worker and realtime use
ports `8001` and `8002`. Run them in separate terminals. The two model-consuming
roles intentionally refuse startup until the local database contains a
committed compatible pipeline revision for the files under `models/`.

The local capacity paths are `.` because the host process cannot see Docker
volume mountpoints. Their readings are only a developer approximation; the
packaged smoke remains authoritative for actual volume-capacity wiring.

Canonical Promo and staff URLs are proxied to the backend through
`deploy/Caddyfile`. Run the [live edge regression](../../tests/promo/test_public_edge_routes.py)
with pinned Caddy `2.10.0-alpine` using loopback-only temporary TLS and
disposable PostgreSQL/DB fixtures:

```bash
uv run --locked --env-file .env.local python -m pytest tests/promo/test_public_edge_routes.py tests/client/test_central_shell.py
```

This isolated route proof does not replace the full packaged runtime smoke for
finding #10.

## Packaged proof

Before deployment or after changes to packaging/startup, run the packaged smoke
from the repository root. It requires Docker with Compose, Python 3 and existing
`models/opencv_sface/{yunet,sface}.onnx` files:

```bash
bash scripts/smoke-runtime.sh
```

The [script](../../scripts/smoke-runtime.sh) builds current source using
[Dockerfile](../../Dockerfile) and [compose.yaml](../../compose.yaml). It uses
a unique project, private subnet, loopback HTTPS port and disposable volumes;
`--env-file /dev/null` excludes the repository `.env`. Models are mounted read-only.

It checks migrations, a minimal committed SFace/SPA/display-token seed, native
model binding, all three roles, HTTPS routes and authentication, then storage
persistence and readiness after dependency/application restarts. It creates no
Photo or Promo session. This verifies the packaged SFace path; it does not
establish Buffalo end-to-end readiness, complete other tasks or deploy the server.

The seed now contains two active venues sharing one revision. The smoke proves
model startup/restart does not depend on having exactly one venue.

The exit trap removes the run's containers, networks, volumes and owned image
tag. Logs and redacted `compose-topology.json` stay in `EVIDENCE_DIR` (default:
`.tasks/ASTRA-findings/10-packaged-smoke/runtime-<run-id>/`). Success requires
`runtime_smoke=ok`, `owned_cleanup_status=0`, `owned_image_cleanup_status=0`.
`SMOKE_PREBUILT_IMAGE` may name an explicitly built current-source local image;
this tests runtime packaging/restarts but not a fresh dependency build.
Never reuse smoke credentials or fixture version labels in production.

## Общая модель нескольких площадок — 2026-09-16

Все активные площадки используют одну eligible serving revision. Параметры
модели и assets задаются на уровне приложения; площадки сохраняют свои даты,
часовые пояса, пороги, токены и данные. Создание через repository принимает
только общую активную revision; UI создания остаётся отдельной задачей.

`switch_serving_revision(spa_id=..., target_pipeline_revision_id=...)` теперь
переключает все площадки атомарно; `spa_id` лишь указывает инициирующую площадку.
Pending/processing работа любой площадки блокирует смену по прежнему exact-A
guard. Выполняйте переключение в maintenance, затем перезапустите realtime и
worker с соответствующими assets/settings. Hot reload модели не добавлен.
Локальная `scripts/apply-local-photo-preprocessing.py` поддерживает snapshot
нескольких площадок и сохраняет прежние embeddings/исходники; это отдельная
явная операция, включение мультиплощадочности её не запускает.

При конфликтующих активных revisions startup выдаёт явную ошибку конфигурации.
Не исправляйте её выбором первой площадки: поддерживаемые команды не создают
такой конфигурации, а историческое/direct-SQL расхождение требует явного
согласования общей revision. Неактивная legacy Calibration UI остаётся 410;
её старый одноплощадочный helper не участвует в startup или worker.

[Проверки AC-27](../testing/index.md#functional-multi-venue-operation-ac-27):
реальные изолированные данные и границы сделанных выводов.

Локально применено: перезапущены backend/realtime/background-worker с имеющимся
source overlay; все healthy, HTTPS и существующий display token работают.
Миграция не требовалась (БД уже на `0026_advertising_playlists`). Хеши прежних
42 Photos, настроек/токенов, 54 Attempts, 26 sessions и 270 объектов сохранились.
Рабочая БД по-прежнему содержит одну площадку; две проверены только изолированно.
[Отчёт](../../.protocols/multi-venue-report.md): результаты и ограничение сборки.

For server deployment, rebuild from source and consult
[server parameters](../../SERVER/serverparams.md). The saved topology has
redacted environment values; it is evidence, not deployable configuration.
Do not reuse smoke credentials or `smoke-local-v1` fixture version labels as
production settings. The smoke still verifies the actual model weights SHA-256.

Last full smoke passed on 2026-09-07:
[log](../../.tasks/ASTRA-findings/10-packaged-smoke/runtime-20260907T043355Z-858117/smoke.log).
Automatic image cleanup was added afterwards and syntax-checked; the test image
was removed manually. Detailed historical checks remain in the
[evidence report](../../.tasks/ASTRA-findings/10-packaged-smoke/implementation-report.md).

## Persistent local testing stand — 2026-09-08

The operator requested a running application on this workstation. The current
source was rebuilt as `face-moment:dev` and started with:

```bash
docker compose --env-file .env.testing up -d --wait --wait-timeout 120
```

This uses the existing `face-moment` PostgreSQL/MinIO volumes. Migration
`0022_inventory_hard_purge_run` completed. All three application roles became
healthy. The local HTTPS origin is `https://localhost:8443` with Caddy's internal
certificate; a fresh browser may require accepting the local certificate.
Services use Compose `restart: unless-stopped` and remain running after the
agent session ends.

Initial empty-database setup created `Local testing` (Asia/Dushanbe), a display
client, and a committed SFace revision bound to the actual model hashes.
`local-testing-v1` is a local asset identity, not an upstream release claim.
Search date was initialized to 2026-09-08. Test-only search settings reuse the
integration fixture values: similarity 0.6, minimum query quality 0.5, quality
settings version 1. These are uncalibrated. Promo display is 20 seconds and
success cooldown 3 seconds. Change the visit date in operator search settings
when testing another day.

Access files are ignored by Git and have mode 600:

- `.protocols/local-testing/operator-credentials.txt`: operator account for
  search date, display settings, inventory and processing health.
- `.protocols/local-testing/photographer-credentials.txt`: photographer account
  for photo upload.
- `.protocols/local-testing/credentials.txt`: developer account `tester` for
  diagnostics.
- `.protocols/local-testing/display-token.txt`: token to paste into the kiosk
  configuration at `/#configuration`.
- `.env.testing`: persistent Compose model/timing settings and QR secret.

Entry points: `/staff/login`, `/staff/photo-upload`, `/staff/search-settings`,
`/staff/display-clients`, `/staff/attempts`, and `/` for the display.
Roles are separate, not hierarchical; developer is not a photo uploader.

Evidence: `.protocols/local-testing/http-check.log` records successful HTTPS
health, client assets, staff login and role-appropriate page checks.
`.protocols/local-testing/check-http.py` repeats these HTTP checks.
The one-time `start.sh`/`seed.py` bootstrap must not be rerun against the seeded
database; use the Compose command above for ordinary startup.
No photos were uploaded and no camera/sensor/phone end-to-end test was performed.
The loopback-only endpoint is not reachable from a phone on the LAN.


The Motion Atlas review now uses a source-mounted backend overlay. See
[motion-presentation.md](motion-presentation.md#local-review-and-evidence) for
its restart command and the `/site`, `/staff`, `/display` review routes.

## Full-resolution JPEG uploads

The upload results panel now offers «История загрузок». The browser retains
the latest 300 upload records in localStorage, scoped to the authenticated
photographer UUID. Records store names, selected date/SPA, result and accepted
Photo ID, not image bytes or credentials. Loading history refreshes accepted
Photo processing statuses through the existing authenticated endpoint.
Previously lost page-only results cannot be recovered by this local history;
uploads interrupted before an acceptance response remain explicitly unknown.

Operator decision, 2026-09-13: the default upload rate limit is 60 files per
60 seconds per authenticated photographer and client IP. This permits the
observed 38-file upload selection within the ordinary limit. The setting is
`PHOTO_UPLOAD_RATE_LIMIT`; the window remains `PHOTO_UPLOAD_RATE_WINDOW_SECONDS`.
The source-mounted backend must restart to load a changed default.

Operator decision, 2026-09-08: remove the need to manually shrink ordinary
camera JPEGs before upload. Defaults now admit up to 100 MiB compressed,
200,000,000 decoded pixels and 20,000 pixels on either side. All three limits
apply together. Settings live in `src/face_moment/infrastructure/settings.py`,
`.env.example` and `compose.yaml`. `deploy/Caddyfile` permits 101 MiB multipart
requests including form overhead; align both edge caps when changing the byte
limit. Originals remain unchanged. These admission limits do not establish
processing latency or concurrent-upload capacity at maximum resolution.

The operator fixture `IMG_20230523_185218.jpg` (4608×3456, 6,363,178 bytes)
previously failed with `decoded_side_exceeded` at 4096 px. Its EXIF orientation
3 is valid and unrelated to that rejection.

Validation: 20 JPEG-validation/uploader tests and mypy (95 source files)
passed; Caddy configuration validated and reloaded. The local backend was
recreated with the source overlay and became healthy. The unchanged operator
JPEG now passes the actual running backend validator (4608×3456). Full
200 MP processing and the 100 MiB upload boundary were not benchmarked.

Upload rejection UI now displays the safe per-file validation message from the
backend (size, pixel bounds, JPEG decode/format or EXIF orientation) and a size
explanation for an unstructured proxy 413. Refresh an already-open uploader to
load the updated inline script. See the
[upload contract](../contracts/photo-admission-api.md#upload-rejection-explanation).
Validation for rejection explanations: 26 focused tests passed, mypy passed
for 95 source files, and the actual uploader JS passed structured-422,
empty-proxy-413 and generic-422 checks in Node. Backend restart completed and
HTTPS health returned 200. The database-backed upload suite could not run:
local PostgreSQL port 55432 refused connection; a direct container-IP retry
was stopped while connecting, before any tests ran.

Operator-requested test inventory reset: hard-purge run
`44fdd8ea-5966-423e-b505-510e6782fffc` completed all four pre-existing photos
at 2026-09-08 12:22:40 UTC through authenticated visibility/purge APIs.
A new upload `82c14178-2eba-45b7-9cb6-85f7c8d465a3` arrived at 12:22:42 UTC,
after completion, and was preserved. Source files in `/tmp/!datasets/` were
not modified. The inventory therefore is no longer empty after the reset.

## YuNet portrait scale diagnosis

Manual calibration preparation exposed five `no_faces` outcomes among six
uploaded close-up portraits; only the 200×200 `_logo.jpg` was searchable.
`SFacePhotoAdapter.process_photo` feeds full-resolution images to YuNet.
A read-only experiment inside the actual background-worker loaded the six
persisted originals and reduced the detection working image to at most 640 px
on its longest side (INTER_AREA, no upscaling). The same detector and threshold
found one face in each, including both versions of IMG_20230523_185218.
This isolates scale as a sufficient explanation for this sample; it is not
an SFace identity-match threshold failure. EXIF-aware decode was preserved.
The exploratory local scale matrix is in
`.protocols/model-debug/yunet-scale.log` with its reproducer beside it.
Production preprocessing, existing Photo results and pipeline revisions were
not changed by this diagnosis. A fix must preserve original-coordinate boxes,
landmarks and revision compatibility; 640 px is sample evidence, not yet a
validated universal setting for distant or group faces.


## Versioned local Photo reprocessing

С 2026-09-09 локально активна `opencv-photo-640-v2`, revision
`50e488ac-842e-404f-ba32-7d8390832152`; шесть Photos готовы, старые revision и
оригиналы сохранены. Контракт: [Photo preprocessing](../domains/photo-processing.md#versioned-photographer-preprocessing).

`scripts/apply-local-photo-preprocessing.py` выполняется так: `snapshot` сохраняет
IDs/хэши, `apply` делает guarded switch и создаёт только отсутствующие pending,
затем штатный worker обрабатывает новую revision, а `check` проверяет terminals,
search и сохранность снимка. Повторный apply не сбрасывает готовые состояния.
Rollback и failure tests — только через явные guarded/disposable процедуры.
[TASK-118 evidence](../../.protocols/TASK-118-T3-FT-002-W8/verification.md).

## Camera search diagnosis — 2026-09-09

Две первые реальные попытки дали: deadline 3371 мс и `insufficient_results` за
2448 мс при пороге 0.6. Старые попытки не содержали лучшего отклонённого score.
Для новых поисков developer detail теперь сохраняет pre-threshold similarity и
число совместимых Photos; поведение matching не менялось.

```bash
docker compose --env-file .env.testing -f compose.yaml -f .protocols/local-testing/compose-source.yaml up -d --no-deps realtime
docker compose --env-file .env.testing -f compose.yaml -f .protocols/local-testing/compose-source.yaml restart backend
```

Текущая source-overlay проверка: 12 focused tests и mypy прошли. Для повторной
проверки фиксировать date/threshold/photos и смотреть новую Attempt; старые scores
не backfill-ятся. Две следующие попытки выдали результаты за 2055/2083 мс с best
scores 0.6670/0.6743.

## Issued preview revision repair and SFace threshold 0.4

Причина `media_failure`: media reader брал admission revision, где preview не
было; теперь display и phone используют immutable revision issuing Attempt.
Локальный SFace threshold был изменён на 0.4. `#debug` получил bounded log и
безопасные error codes. 48 API-тестов, 52 client-теста и mypy прошли; browser
доказательство сохранено в `.protocols/model-debug/display-qa.md`.

## Manual threshold in Calibration

`/staff/calibrations` получил ручной threshold без запуска Calibration; сохраняется
только threshold, stale revision отклоняется. Девять HTTP-тестов и mypy прошли;
Chromium подтвердил сохранение 0.4. [Evidence](../../.protocols/model-debug/manual-threshold-qa.md).

## Native browser fetch failure after preview repair

Browser `configuration_failure` оказался `Illegal invocation`: native
`Window.fetch` был передан без receiver. Binding исправлен; 53 client-теста и
полный UI smoke прошли. [Evidence](../../.protocols/model-debug/display-full-flow-qa.md).

## Live camera/display confirmation — 2026-09-10

Attempt `472e284a-569d-426a-832d-dc189533e56e` (09-09 23:36:48 Asia/Dushanbe):
реальный показ подтверждён (`confirmed`), evidence полные. Найдено 6 фото,
показано 4; поиск 1870 мс, QR виден через 2434 мс от готовности серии.
Порог попытки и текущий — 0.38; similarity максимум 0.5923, минимум среди
совпадений 0.3833. Открытие по QR ещё не записано; стенд доступен только локально.

Карточки малы: заметка `PAPERCUTS/gpt-6 __ 09-10-2026 01.20.md`.

## No server connection notice — 2026-09-10

Operator Network evidence confirmed `net::ERR_CERT_AUTHORITY_INVALID` on the
Attempt fetch: Chrome rejected TLS before HTTP. Earlier `curl -k` health checks
did not test certificate trust; the token/origin explanation was unproven.
After accepting the local certificate, Attempt
`0aa5b559-1bb0-4d60-b310-fa5eed792eff` at 2026-09-10 08:09:52 UTC returned
`no_proposals` with zero occurrences; client timing was received. No Promo is
expected for that outcome. This does not explain why the detector found no face.
Empty `/healthz` content is normal. Durable local CA trust/persistence remains
follow-up work; browser JavaScript cannot bypass a certificate trust failure.

## USB recovery and reload diagnostics — 2026-09-10

Physical follow-up: automatic reconnection now produces a stream, but the
operator reports magenta imagery until selecting another camera and returning.
Recovery is therefore not yet physically accepted. Host kernel messages around
14:02:58–14:03:00 Asia/Dushanbe show descriptor/address errors `-71` and failed
enumeration; the UVC device is discovered again at 14:03:07 and 14:03:23.
These prove USB initialization trouble, not the cause of color corruption.
At 14:04 the camera reports YUYV 640x480, 30 fps, automatic white balance on;
the operator's visual state at that read is not yet confirmed. Both manual
and automatic paths use the same exact-device getUserMedia constraints.
Early reopening is a hypothesis pending a controlled before/after comparison;
do not treat an automatic second reopen or a color filter as a verified fix.
The operator subsequently explicitly held the magenta state for inspection:
same YUYV 640x480 at 30 fps, automatic white balance enabled, inactive manual
white-balance-temperature readback 0, gain 22, exposure 305. No capture settings
were changed by the inspection. A normal-color comparison is still pending;
the inactive temperature value alone is not a diagnosis.

Read-only follow-up around 14:15 Asia/Dushanbe found the same device and
YUYV 640x480/30 fps format, automatic white balance on and inactive temperature
readback 0; gain was 20 and exposure 405. The operator has not yet identified
the visible color state for this sample, so it is not a normal-color baseline.
No further reconnect entries appeared after 14:03:25 in the inspected kernel
log. Next evidence needed: identify the current preview color, then compare
controls after the manual camera-switch recovery under the same lighting.

At 14:18 Asia/Dushanbe the operator confirmed a stable magenta preview with
a screenshot. A fresh read-only sample showed YUYV 640x480/30 fps, automatic
white balance on, inactive temperature 0, gain 22 and exposure 405. Brightness
128, contrast 32 and saturation 32 were at device defaults. This is the
confirmed faulty-state baseline; comparison after manual switching remains
pending. No controls or stream settings were changed for this sample.

At 14:19 the operator switched to the built-in camera and back to UVC without
USB removal; the screenshot confirmed normal color. The subsequent read
retained YUYV 640x480/30 fps and automatic white balance on, but inactive
white-balance-temperature readback changed from 0 to 3900. Gain changed from
22 to 20 and exposure from 405 to 505; other listed controls were unchanged.
This associates recovery with a changed camera white-balance readback, but does
not prove that this inactive control caused the tint. Stream format did not
change. Next controlled check: reproduce the tint on USB reconnect and test
page reload while keeping UVC selected, to determine whether reopening alone
is sufficient without selecting the built-in camera.

Operator decision after that comparison: allow initialization time before
reopening; the operator reports white-balance availability after roughly 1.5 s.
Automatic same-device recovery now waits 2 s before getUserMedia. Explicit
selection and ordinary page startup retain their existing timing. A newer
selection, another disconnect or controller destruction invalidates the pending
open. All 54 client unit checks passed, including delay and cancellation
checks. Physical color recovery with this delay is still pending; the earlier
reload experiment is superseded by this operator-directed change.

Subsequent operator test: camera recovery after automatic disconnection still
did not restore normal operation. The operator explicitly deferred this defect
as non-blocking for further testing; the two-second delay is not an accepted
physical fix. Other requested manual scenarios were reported working. This
is operator-reported evidence, not an independently observed physical pass.

2026-09-11 yellow-preview check: automatic white balance is enabled; inactive
temperature readback is 10000 (previous normal-color sample: 3900). Client code
and camera change history contain no white-balance writes or color filters;
the recovery change is exact-device reopening after a 2-second delay. This
inspection changed no camera controls; the cause of the yellow tint is unproven.

Read-only polls at 11:14:30/40/50 on 2026-09-11 all returned auto=1,
temperature=10000. Chrome 151.0.7922.71 calls `ResetUserAndCameraControlsToDefault`
when starting V4L2 capture: auto white balance off, controls reset, auto restored.
[Source](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.71/media/capture/video/linux/v4l2_capture_delegate.cc).
Its involvement in this camera's failure needs a reconnect-time ioctl trace;
polling alone does not change image color.

Reconnect trace at 11:27 on 2026-09-11: Chrome successfully toggled AWB off/on,
but all four default-reset `VIDIOC_S_EXT_CTRLS` batches returned `EINVAL`;
YUYV 640x480 capture started successfully. Operator screenshot was magenta;
readback was auto=1, temperature=0. This does not establish the cause without
a successful-start comparison. Operator deferred investigation and fixes;
trace stopped, application and camera controls unchanged by the investigation.

Controlled comparison at 11:40 on 2026-09-11: operator screenshots confirm
normal → magenta after USB reconnect → normal after selecting another camera
and returning. The captured Logitech startup writes, format and return codes
are identical in the failed and recovered runs; EINVAL occurs in both.
The recovered run initially reads temperature=10000, versus 0 in the failed
run, so 10000 alone is not a reliable failure detector. Manual switching adds
a successful STREAMOFF on the connected Logitech before reopening; physical
removal yields ENODEV. This narrows the next experiment to stop/reopen of the
same device, but does not prove its sufficiency or establish a root cause.
Comparison trace: `/tmp/face-moment-camera-comparison.trace`; tracing stopped.

Operator decision, 2026-09-11: camera configuration offers automatic/manual
white balance and a temperature slider using the track capability range.
Manual defaults to 4500 K; mode and temperature are saved per device in local
browser storage and reapplied on every open, including USB recovery. Camera
readings of 0/10000 do not override the saved manual value. Unsupported controls
are disabled; rejected/unconfirmed settings show an error without stopping
preview. This controls the camera, not a display color filter. Physical camera
confirmation remains separate from unit coverage in `test_camera.mjs`.

The next manual no-face test also passed per operator report: camera pointed
at an empty wall, old frames allowed to leave the buffer, test trigger followed
by normal return to advertising without an automatic stale-photo display.

Operator reproduced USB disappearance/return with the same camera still selected
but unavailable; switching away and back restored preview. `devicechange`
previously refreshed enumeration without reopening the stream. The client now
reopens the exact selected deviceId when it returns while awaiting reselection.
Changed identities still require explicit selection; no label-based fallback.
This refines FR-CAP-11 per operator request. Physical USB verification remains
necessary; simulated lifecycle tests cover the implementation.

The last 20 safe client diagnostic events now use sessionStorage and survive
reload in the same tab. Blocked/full storage falls back to in-memory operation.
HTTP status and camera transitions are recorded; tokens/images remain excluded.
Older in-memory history lost to a prior reload cannot be recovered.

Validation: 54 client unit tests and all 17 existing Chromium browser tests
passed. Separate isolated browser checks confirmed sessionStorage round-trip
and retained event rendering in the actual app's `#debug` after reload;
API responses were mocked and no new real Attempt was created. TLS trust was
ignored only by the QA browser, so this does not establish a certificate fix.

## Названия площадок в админке

«Библиотека» и «Обработка» показывают выпадающий список сохранённых названий.
Чтобы переименовать площадку, войдите как оператор или администратор, откройте «Площадки»
и сохраните новое название в карточке нужной площадки. После открытия других
разделов список показывает новое имя. Новые площадки, создаваемые через
`IngestTargetRepository.configure_spa` без `name`, получают «Площадка 1»,
«Площадка 2» и далее по первому свободному номеру. Существующие имена сохраняются.
[Контракт](../contracts/boundary-map.md#staff-площадка-names).

## Server timezone and staff date/time controls

Operator update 2026-09-11: server services default to `Asia/Novosibirsk`
(UTC+7). `Dockerfile` and the shared Compose application environment set `TZ`;
PostgreSQL starts with explicit `timezone` and `log_timezone` in that zone,
including existing databases. Local `uv --env-file .env.local` launches use
`TZ=Asia/Novosibirsk`; `.env.example` carries the same default. This does not
change the developer workstation's timezone or reinterpret stored instants.
The central host is already documented as UTC+7 in
[server parameters](../../SERVER/serverparams.md).

«События сервера», «История поиска» and «Обработка» use a calendar on the left
and a clock on the right, in UTC+7 independently of browser timezone. Both
bounds initially show today/current time. «Применять период» enables the range;
edits enable it automatically. A saved URL restores the selected interval.
The browser converts the selection to UTC for existing API queries. Date-only
upload/search-settings forms use native calendars, defaulting to today in
UTC+7 where no saved date exists.

[Event filter contract](../contracts/server-event-api.md#staff-filter-controls-operator-update-2026-09-11):
exact `all`/Severity/Component choices and validation.

### Fixed date display format

Operator correction: all staff date selectors display `dd.mm.yyyy` regardless
of browser locale. A validated text field sits beside a native calendar
trigger; picking a date updates the text and typing updates the calendar.
The uploader and search-settings serialize `YYYY-MM-DD`; period filters still
convert UTC+7 to UTC. Implementation lives in
[staff date controls](../../src/face_moment/platform/staff_datetime.py) and
[date synchronization](../../client/staff-datetime.js).

### Fixed 24-hour time selection

All staff time selectors use one compact `HH:mm:ss` text field with a clock
icon, independent of browser locale. `HH:mm` input normalizes to `HH:mm:00` on
blur. Arrow Up/Down adjusts the hour/minute/second segment under the caret.
Strict 24-hour validation rejects impossible values; UTC+7 interpretation and
UTC query serialization are preserved. No additional UI dependency is needed.

### Displayed timestamps

Staff-facing timestamps display `dd.mm.yyyy HH:mm:ss` in UTC+7, without
fractional seconds or a trailing timezone suffix. The shared staff footer
identifies UTC+7. Processing/statistics use the browser formatter; event,
Attempt, Calibration and retention pages use the matching Python formatter.
Persisted values, query serialization and API responses keep exact UTC instants.

Переименование площадок доступно оператору и администратору (`developer`)
в разделе «Площадки» (`/staff/spas`). «Настройки поиска» доступны обеим ролям.
Страница создания новых площадок пока не реализована.

### Пустая страница площадок: HTTPS routing

`/staff/spas` and `/api/serving/spas/*/name` must be listed in
`deploy/Caddyfile`'s `@backend_canonical` matcher. Adding only a FastAPI route
leaves Caddy returning an empty `200` for an unmatched request. After changes,
validate/reload Caddy and check authenticated HTML plus the rename API through
`https://localhost:8443`, not only the direct backend. The regression is in
`tests/promo/test_public_edge_routes.py::test_live_caddy_serves_spa_page_and_name_mutation`.


## Venue media and search-range rollout — 2026-09-12

Library (`/staff/photo-inventory`, alias `/staff/library`) now links each active
venue to `/staff/venue-media?spa_id=...`. Select upload dates (both days included,
UTC+7) to view thumbnails, added/capture timestamps, dimensions/size and status.
Click a thumbnail for the private native original; the final action reuses
soft deletion. Admission-state no_faces photos are excluded. Operator/developer
see venue uploads; photographers see their own.

The operator explicitly authorized deploying both concurrent changes. Built the
shared current-source image, verified seven media/search/migration files match
the workspace, applied `0023_search_date_ranges` from live0022, recreated backend,
realtime and background-worker, and validated/reloaded Caddy. All three roles
are healthy. HTTPS media/original and `/api/serving/spas/{id}/search-dates` were
checked as operator and developer without modifying live Photos. Counts stayed
6 Photos,17 Attempts,12 sessions. The existing manual date2026-09-08 was retained
for both range bounds; migration enabled search_today and advanced revision7→8.

Rollout evidence: `.tasks/staff-media-release/` (build, migration, service health,
Caddy validation/reload, image ID and live-check logs). Functional/semantic media
proof: `.protocols/TASK-119-T3-FT-012-W3/`. The task-owned isolated
staff-media-test Compose resources were removed after verification.

## Local stand refresh — 2026-09-15

Operator update: серверный лимит realtime обработки повышен с 3000 до 7000 мс
через default `REALTIME_DEADLINE_MS` в `compose.yaml` и Python settings.
Source-mounted realtime пересоздан; healthy, effective Settings = 7000 мс.
Изменение действует для новых Attempts; исторические deadline_ms сохранены.
Четыре unit-проверки orchestration прошли; две DB-backed проверки не стартовали
в host-запуске без DATABASE_URL. Это изменение лимита не исправляет отклонение
reference crops серверным детектором.

Restarted the existing Compose services to load current source. The old
`migrate` container could not resolve database revision `0023_search_date_ranges`.
Ran the existing migration service with the workspace `migrations/` mounted
read-only at `/app/migrations`; upgrade to `0024_spa_detector_thresholds`
completed. Restarted backend, realtime and background-worker afterwards.
Until the migration container is updated, plain Compose restart also restarts
that stale one-shot container; use current migration files when applying upgrades.

## Capture identity и порог сходства — локальное применение

Оператор уточнил: новые изменения должны сразу работать в локальных контейнерах.
Образ `face-moment:dev` пересобран, БД обновлена до `0025_capture_identity_labels`;
backend/realtime/worker healthy. Исходники подключены read-only через
`.protocols/local-testing/compose-source.yaml`, включая worker. Caddy перечитан.
Старый migration container заменён актуальным; проблема неизвестной revision выше
устранена. Существующие фотографии, Attempts и значения порогов не сбрасывались.

«Площадки → Настройки площадки → Порог сходства» читает текущую serving revision
конкретной площадки и существующие `reference_search_settings`. PUT проверяет
конечность/диапазон `[-1, 1]`, session/CSRF, права operator/developer и обе
переданные версии: settings revision и pipeline revision. Сохраняет только
ручной порог, оставляя quality settings; live calibration provenance очищается,
как и в прежнем ручном сохранении. Исторические результаты не меняются.
Без модели/настроек форма недоступна, значения по умолчанию не выдумываются.
API: `/api/serving/spas/{spa_id}/similarity-threshold` (GET/PUT).
Уточнение UI: порог сходства использует тот же переключатель разрешения
редактирования и расположение input/button, что пороги детекторов. Выключение
переключателя отменяет черновик; успешное сохранение снова блокирует поля.
Пояснение вынесено в tooltip переключателя с указанным оператором default 0.38;
это текст подсказки, не сброс сохранённых значений.

Calibration удалена из меню, все прежние `/staff/calibrations` и дочерние
маршруты отвечают `410`. Worker больше не получает callbacks выбора, исполнения
и startup interruption Calibration. Старые файлы, таблицы, миграции и записи
сохранены; cleanup не расширялся и вручную не запускался. Новый capture identity
не зависит от Calibration. Для переноса порога новой миграции нет.

Для повторного применения изменений исходников на этом локальном стенде:

```bash
docker compose --env-file .env.testing -f compose.yaml -f .protocols/local-testing/compose-source.yaml up -d --no-deps --wait --wait-timeout 120 background-worker
docker compose --env-file .env.testing -f compose.yaml -f .protocols/local-testing/compose-source.yaml restart backend realtime background-worker
docker compose --env-file .env.testing exec -T edge caddy reload --config /etc/caddy/Caddyfile
```

Открыть `https://localhost:8443/staff/spas` и обновить страницу. Для обычного
запуска без source overlay сначала пересобрать образ. User timer
`face-moment-retention-cleanup.timer` включён; локальный override использует
`.env.testing`, source overlay и `DOCKER_CONTEXT=desktop-linux`. Crops имеют
обычный срок хранения Attempt (по умолчанию 90 суток).

Проверки: отдельные PostgreSQL/MinIO и настоящий Caddy для API/HTTPS;
`test_similarity_threshold.py` проверяет save/reopen, разделение площадок,
неверную revision, finite/range, права/CSRF, `410` и сохранность requested/running
Calibration при работе default worker. `test_background_worker_runtime.py`
проверяет реальную БД/MinIO и цикл обработки с тестовым face adapter, не native
распознавание. Native YuNet/SFace отдельно покрыт `test_capture_identity.py`.
JS controls проверяются DOM fixtures, не полноценной камерной сессией браузера.
Известный прежний тест переименования площадки ожидает удалённый селектор
`recent-statistics-spa-id`; отмечен в PAPERCUTS, медиатека здесь не менялась.
Финальный focused набор: 20 Python checks passed, 7 JS checks passed,
mypy — 104 source files без ошибок; read-only HTTPS smoke локального стенда
успешен. Временные PostgreSQL/MinIO контейнеры проверки удалены, данные
локального приложения не удалялись.
