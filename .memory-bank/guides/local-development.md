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
`50e488ac-842e-404f-ba32-7d8390832152`. Все шесть Photos от 2026-09-08 — ready,
по одному лицу; compatible search работает. Оригиналы, admission и результаты
старой revision `1fa46d01-f6aa-4a72-a47c-3770209d44ea` сохранены.
Контракт: [Photo preprocessing](../domains/photo-processing.md#versioned-photographer-preprocessing).

Процедура `scripts/apply-local-photo-preprocessing.py` запускается в локальной
Compose network с текущим source mount и каталогом evidence:

1. `snapshot --evidence <dir>`: сохранить IDs, original/history hashes и настройки.
   Ожидается шесть Photos; иной разрешённый объём задаётся `--expected-photos`.
2. После disposable tests собрать worker/realtime, дождаться окончания текущей работы
   и остановить model consumers. `apply --evidence <dir>` валидирует модель,
   сохраняет target.json, выполняет guarded switch и создаёт только missing pending.
3. Установить `SFACE_PREPROCESSING_VERSION` из target.json, перезапустить model consumers
   и backend с прежним source overlay. Обработку выполняет штатный worker.
4. `check --evidence <dir>`: проверить terminals/search и сохранность снимка.
   Повторный apply использует тот же target и сохраняет existing states.

Before snapshot не перезаписывать. Rollback — явный guarded switch со старыми
настройками и restart. Migration/failure tests — только disposable DB/objects.
Staff status/SLO сохраняют admission revision; результат новой обработки проверяется
через processing projections. Команды и доказательства:
[TASK-118 verification](../../.protocols/TASK-118-T3-FT-002-W8/verification.md).

## Camera search diagnosis — 2026-09-09

Read-only inspection found two real Attempts at 21:17:44 and 21:18:51 local
time. The first exceeded its 3000 ms deadline (3371 ms server search). The
second completed search in 2448 ms with `insufficient_results`: eight admitted
proposals, five selected observations passing quality, and zero matches at
threshold 0.6. Both used visit date 2026-09-08 and the new processing revision.
The current compatible inventory contains six ready Photos/faces; this is a
current read, not a historical inventory snapshot.

Developer `/staff/attempts/{attempt_id}` now shows a readable summary of this
existing evidence and expandable JSON. Backend source-overlay restart and
live HTTPS developer/operator projection checks passed for both Attempts.
Mypy passed for 96 files, render smoke passed, investigation tests: 15 passed,
one existing whole-document assertion rejected the shared navigation's hidden
Calibration link. No camera identity root cause is established.

The precise missing measurement is the best score before threshold filtering,
together with the compatible population size at search time. The current
repository applies the threshold before returning observations, and camera
crops/embeddings are not retained; old Attempts cannot recover those scores.
The follow-up now collects both values in the same exact-search SQL statement
and carries them into new ordinary evidence. Developer detail highlights the
best score and shows counts per selected detection. No threshold or matching
behavior changes. Deadline results remain discarded and may have no score.

The local source overlay now also mounts `src` into realtime. To load changes:

```bash
docker compose --env-file .env.testing -f compose.yaml -f .protocols/local-testing/compose-source.yaml up -d --no-deps realtime
docker compose --env-file .env.testing -f compose.yaml -f .protocols/local-testing/compose-source.yaml restart backend
```

Current-source tests must mount current `tests` too: the existing image contains
older tests. Twelve focused search/evidence/render checks passed with disposable
PostgreSQL databases and unique object prefixes; mypy passed. For the next probe,
keep date/threshold/photos fixed, use the normal camera and trigger twice a few
seconds apart, then inspect the newest developer Attempt detail. This obtains
actual camera measurements; old Attempts cannot be backfilled.

Rollout check: backend/realtime HTTPS health returned 200; realtime loaded both
new observation fields, and live developer/operator detail retained role
isolation. Older Attempt correctly displays no best-score measurement.
Read-only cross-comparison of the six active Photos in the selected revision
gave 15 Photo pairs: scores 0.5082–0.9246, with 14/15 reaching 0.6. This supports
consistency of most stored reference embeddings but does not establish camera
query correctness or an appropriate threshold. Awaiting operator's two fresh
camera triggers with unchanged settings.

Fresh operator triggers at 22:55:52 and 22:56:31 local time produced Attempts
`3b99687a-06b5-4afc-93f1-b7404bb71489` and
`a92240cf-e19b-4f0b-8127-673f116462b7`. Both issued a result containing four
Photos, with best scores 0.6669973 and 0.6743400 and search durations 2055/2083
ms. Every selected observation searched six Photos; date, pipeline revision,
settings revision 3 and threshold 0.6 match the earlier failed attempt.
This proves current camera-search success, not the cause of the earlier miss.
Both core display rows remain pending with no QR timing/ack evidence; actual
on-screen display and any changed capture conditions require operator feedback.

## Issued preview revision repair and SFace threshold 0.4

The operator confirmed that no photographs/QR appeared and the second capture
had worse lighting. Browser reproduction proved `media_failure`: all four
issued previews returned 404. The loader omitted revision and selected the
Photo's original admission state (`no_faces`, no preview); the issuing Attempt
used the new revision where the same Photos were `ready` with existing bytes.
This was not expiry. Display and phone preview reads now explicitly use the
issuing Attempt's immutable pipeline revision, preserving admission history
and previously issued results across future serving switches.

Per explicit operator instruction, updated local SFace threshold from 0.6 to
0.4 through `RealtimeContextRepository.update_reference_settings`; settings
revision is now 4. Local initial seed also uses 0.4. No Photo, historical
Attempt, quality gate, active date or model was changed.

The client `#debug` placeholder is replaced by a bounded 20-event in-memory
log: capture, server outcome, loading, card preparation, success or failure.
Failure includes a safe machine error code and available ACK HTTP status.
Only allowlisted scalar metadata is shown; no tokens, media URLs, images or
raw exceptions are retained. Reloading clears the log and loads updated JS.

Validation: 48 Promo/phone API tests, all 52 client unit tests and mypy passed;
the strengthened diagnostic error-code assertion passed its 14-test file.
Local backend restarted with the source overlay. The delegated browser proof
and any remaining end-to-end verification are recorded in
`.protocols/model-debug/display-qa.md`.

Post-fix Chromium verification loaded all four actual issued previews with
HTTP 200, decoded them, and rendered four cards plus QR. The retained old
session's ACK was mocked because its reporting window had expired; this does
not claim a new live ACK. Browser diagnostic failure/code visibility also
passed using a synthetic incomplete-config fixture. One fresh operator trigger
after hard reload remains the final camera-to-display/ACK check.

## Manual threshold in Calibration

Developer `/staff/calibrations` now has the operator-requested manual threshold
input and save button, with current threshold below it. It uses the active
model's existing serving settings; no Calibration run is required. The local
current value is 0.4. Save changes only threshold and clears recommendation
provenance; already admitted Attempts preserve their settings.

The owner serializes changes and checks the hidden settings revision. A stale
form asks for reload instead of overwriting newer settings. Role/CSRF, invalid
values, persisted readback, preserved quality and rollback checks passed in
the nine-test disposable Calibration HTTP suite; mypy passed.

Live Chromium developer check passed: numeric field displayed 0.4, one save of
that unchanged value returned 303, and reload showed persisted 0.4. No run or
recommendation was changed. Evidence:
`.protocols/model-debug/manual-threshold-qa.md`.

## Native browser fetch failure after preview repair

Three further operator Attempts (18:11:09, 18:11:32, 18:13:04 UTC) all issued
six-photo results at threshold 0.4; best scores were 0.6517/0.6524/0.6253.
The actual browser debug log then identified `configuration_failure` with
`promo_display_configuration_missing`. A native Chromium probe confirmed
`Illegal invocation`: PromoDisplayController stored Window.fetch unbound and
called it as a controller method. Both display configuration and display ACK
requests failed before HTTP. The preceding direct-controller preview QA used
an injected fetch wrapper and therefore did not cover this browser binding.

The controller now binds fetch to globalThis, matching the existing sensor
client pattern. Fifty-three client unit tests pass, including a default-fetch
receiver regression covering configuration and ACK. This complements the
earlier real preview-revision fix; neither defect was a matching-threshold
failure. Fresh full-app browser evidence is retained separately in
`.protocols/model-debug/display-full-flow-qa.md`.

Post-fix full UI browser check passed with a selected fake camera and the
actual Test button: native configuration GET 200, four actual preview GETs 200,
decoded cards and visible QR. Native fetch was neither injected nor wrapped.
Detector/search response used a retained-result fixture, and old-session ACK
was intercepted; the emitted confirmed request proves the browser path, not
durable live ACK or actual camera timing. No new Attempt was created. A hard
reload plus one operator camera trigger is still needed for live confirmation.
