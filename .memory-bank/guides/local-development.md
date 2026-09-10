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

The exit trap removes the run's containers, networks, volumes and test image.
Logs and redacted `compose-topology.json` remain under
`.tasks/ASTRA-findings/10-packaged-smoke/runtime-<run-id>/`; use `EVIDENCE_DIR`
to choose another evidence directory. Success requires exit 0 and
`runtime_smoke=ok`, `owned_cleanup_status=0`, `owned_image_cleanup_status=0`
in `smoke.log`. On failure, retain that directory for diagnosis.

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

Карточки малы: [заметка](../../PAPERCUTS/gpt-6%20__%2009-10-2026%2001.20.md).

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
