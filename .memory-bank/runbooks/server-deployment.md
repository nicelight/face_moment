---
description: Canonical non-destructive procedure for deploying Face Moment to facecentral and accepting the public origin.
status: active
last_updated: 2026-09-16
source_of_truth:
  - .memory-bank/runbooks/server-deployment.md
---
# Server Deployment

## Scope and boundaries

This is the single procedure for deploying current application source to the
central host `face-pc`. The public VPS edge is owned by the separate
[VPS Caddy and FRP runbook](vps-caddy.md). Local proof is owned by the
[local test deployment runbook](local-test-deployment.md).

The intended public origin is `https://face-moment.ru`; the VPS public IPv4 is
`46.8.200.99`. The legacy `face-time.moment-studio.ru` hostname is only the FRP
WSS control/management path and must remain in place during this migration.

This procedure does not restore lost data, rotate the FRP token, choose model
identity metadata. The approved initializer creates the first SPA from verified
configured SFace assets; it never imports smoke identities. Do not run
`docker compose down -v`, remove named volumes, reset display tokens or modify
PostgreSQL directly while following it.

## Topology and access

```text
Browser → face-moment.ru → VPS Caddy → VPS loopback :18443
        → FRP/WSS → face-pc loopback :8443 → Docker edge → application roles
```

The central server is behind NAT and makes the outbound FRP connection. Only
the VPS is public; PostgreSQL, MinIO, Docker and the application edge are not.

From the operator workstation:

```bash
ssh -l facemoment facecentral
cd /opt/face-moment
```

The `facecentral` alias reaches VPS loopback `127.0.0.1:10022` through
`ProxyJump igornskprod`. Its default user is the KDE/bootstrap account `face`;
`-l facemoment` is required for deployment. `facemoment` owns the deployment
directory and has Docker access. System changes, including FRP administration,
require an interactive sudo password. No passwordless sudo is configured.

The central checkout uses remote `origin` at
`https://github.com/nicelight/face_moment.git`. Treat its existing revision
and containers as unknown release state until the preflight records them.

## First checkout and host prerequisites

If `/opt/face-moment` does not exist, create it once; skip this block for an
existing checkout. Run as `facemoment` (sudo only creates the directory):

```bash
sudo install -d -m 755 -o facemoment -g facemoment /opt/face-moment
git clone https://github.com/nicelight/face_moment.git /opt/face-moment
cd /opt/face-moment
```

GitHub access must work from this account; never embed an access token in the
remote URL. Do not copy a workstation `.env.testing`, database or browser tokens.
Host prerequisites are Git, Docker Engine with Buildx and the Compose plugin;
Python/uv/Node on the host are not needed for the packaged deployment.
If Docker is absent, follow the
[official Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/)
for the installed OS; do not reinstall a working daemon.

```bash
id
docker version
docker compose version
docker buildx version
systemctl is-enabled docker
df -h /opt/face-moment /var/lib/docker
free -h
ip route
```

Docker must work without sudo for `facemoment`; reconnect after changing its
group membership. Check space for images, models and incoming photos. Confirm
the private subnet from [compose.yaml](../../compose.yaml) does not overlap
host/LAN/VPN routes. Do not change the Compose project name `face-moment`:
doing so selects different named volumes and can look like an empty database.

## Required inputs before changing either host

1. A reviewed target Git commit and a successful local packaged proof. See
   [local test deployment](local-test-deployment.md#packaged-smoke).
2. Public DNS: the REG.RU apex A record for `face-moment.ru` resolves to
   `46.8.200.99`; no stale public AAAA record points elsewhere.
3. Central `/opt/face-moment/.env`, owned by `facemoment` and mode `600`. It is
   not committed. For public deployment, unique values for `POSTGRES_PASSWORD`,
   `MINIO_ROOT_PASSWORD` and `PROMO_QR_TICKET_SECRET` are preferable, but not
   mandatory. If omitted, Compose uses known development fallbacks; record and
   accept that risk explicitly. Never place secret values in a shell history,
   Git diff or report.
4. The same file sets `FACE_MOMENT_PUBLIC_HOST=face-moment.ru`, an absolute
   `FACE_MOMENT_MODEL_DIR` if models are outside the checkout, and the selected
   model identity/version settings. The required assets are mounted read-only;
   their presence alone does not make realtime/worker ready.
5. Positive `REALTIME_RESULT_DISPLAY_MS` and `REALTIME_SUCCESS_COOLDOWN_MS`,
   plus any intended `PHONE_PURCHASE_URL`. These are explicit product settings,
   not values to infer during deployment.
6. The actual immediate FRP/Docker peer observed by inner Caddy, assigned to
   `FACE_MOMENT_FRP_PROXY_IP`. The placeholder `192.0.2.1` is deliberately
   fail-closed. How to measure it is in
   [VPS Caddy and FRP](vps-caddy.md#trusted-visitor-ip).

The first deployment runs the one-shot `initialize-venue` service after
migrations. It creates **СПА Сибирь 1** only when no SPA exists, using verified
`opencv_sface` assets and their configured metadata/digest. Defaults: timezone
`Etc/GMT-7` (GMT+7), photo YuNet `.7`, camera BlazeFace `.5`, similarity `.38`,
minimum query quality `.5`, quality settings `{"version": 1}`, current-day
search with no historical date range. Staff accounts may be bootstrapped by the
backend-only `.env` override described in [Staff Access](../domains/staff-access.md)
or provisioned separately through the existing authorized CLI procedure.

Required `SFACE_*` inputs: `DETECTOR_PATH`, `DETECTOR_ID`, `DETECTOR_VERSION`,
`RECOGNIZER_PATH`, `RECOGNIZER_ID`, `RECOGNIZER_VERSION`, `PREPROCESSING_VERSION`,
`ALIGNMENT_VERSION`, `NORMALIZATION_VERSION`, `EMBEDDING_DIMENSION`. Paths must
be absolute container paths below `/run/face-moment/models`, not host-relative
paths from the local example. Set identity/version metadata from the deployed
model artifacts; do not copy `local-testing-v1` or smoke-fixture labels.
The initializer computes SHA-256 from both files and runs native inference,
including actual embedding dimension verification; it does not download models.

Build the server `.env` from the inputs above and
[Compose variables](../../compose.yaml), not by copying [.env.example](../../.env.example).
That example targets host-local Python: notably its
`FACE_MOMENT_TRUSTED_PROXY_IP=127.0.0.1` and relative model paths are wrong
for this Compose deployment. Leave the Compose trusted-backend proxy default
unless the Docker subnet is deliberately changed. Keep `FACE_MOMENT_EDGE_PORT`
at `8443` to match FRP. Upload model files separately to `FACE_MOMENT_MODEL_DIR`
and make them readable by runtime UID `10001` (including parent-directory
traversal) before starting initialization. Do not change ownership of `/home`
or other shared parent directories to grant this access.

Keep existing secrets on updates. Changing `POSTGRES_PASSWORD` in `.env` does
not change the password inside an already initialized database; it can instead
break application login. Credential rotation is a separate operation.

Missing/invalid assets fail the initializer without partial revision, SPA or
search settings. Correct the configuration and rerun
`docker compose run --rm --no-deps initialize-venue`, then start the roles again.
Any existing SPA, including inactive ones, makes initialization a no-op. It
never resets names, dates, thresholds or serving selection. Ordinary role
restarts do not invoke it. Backend and edge can start independently of model
readiness, so the authenticated «Добавить площадку» flow also supports an empty
database; its operator/developer and CSRF requirements remain in force.

## Preflight

On the workstation, confirm the target source has no unreviewed work and run
the packaged smoke. On the central host, capture the existing state before any
release operation:

```bash
ssh -l facemoment facecentral
cd /opt/face-moment
git status --short
git rev-parse --short HEAD
docker compose ps -a
docker volume ls --format '{{.Name}}' | rg '^face-moment_'
```

If the checkout is dirty, a named volume is unexpected, or the source cannot
be moved to the reviewed commit without overwriting local work, stop and
resolve that ownership question first. Never use `git reset --hard` as a
deployment shortcut.

Confirm the VPS configuration and DNS before publishing a new application
release; use the VPS runbook through its certificate-readiness step. Caddy must
be able to receive public TCP `80` and `443` for ACME validation.

## Deploy the central application

1. Ensure the central checkout is exactly the reviewed commit. A clean checkout
   with access to `origin` may use `git fetch origin` followed by a non-forcing
   checkout of that commit. Record the resulting short commit ID; do not deploy
   an untracked local snapshot.
2. Review `/opt/face-moment/.env` without printing secrets. Confirm its owner
   and mode with `stat -c '%A %U:%G %n' .env`, then validate the resolved
   non-secret Compose shape:

   ```bash
   docker compose config --quiet
   ```

3. Build the selected source. For an update, agree on a maintenance window:
   stop the retention timer if active, wait for any running cleanup to finish,
   then stop application writers before migrating. Keep the old image ID and
   commit recorded; do not prune images during the release.

   ```bash
   docker compose build
   docker compose stop edge backend background-worker realtime
   docker compose up -d --wait --wait-timeout 120 postgres minio
   docker compose run --rm --no-deps migrate
   docker compose run --rm --no-deps initialize-venue
   docker compose up -d --no-deps --wait --wait-timeout 120 backend background-worker realtime edge
   docker compose ps
   ```

   Run each command only if the preceding one succeeded. Explicit one-shot
   commands followed by `--no-deps` avoid starting migrations/initialization
   again through the dependency graph. Record the old running image ID **before**
   build, for example `docker inspect --format '{{.Image}}' "$(docker compose ps -q backend)"`
   on an existing installation. Restore the previously active retention timer
   after successful acceptance.

   Migration changes durable state. If it fails, leave volumes intact, collect
   sanitized logs and stop; do not retry by deleting the database volume.

### Narrow route/static-only update path

The migration and initializer commands above remain mandatory for any release
that changes migrations, ORM/schema definitions, initialization inputs,
Compose/env settings, model bindings, storage behavior or other durable state.
They are not a blanket opt-out. A reviewed follow-up may use the narrower path
below only when a recorded `git diff BASE..TARGET` proves that the target is
limited to route/static/UX presentation and its tests/docs, with no migration,
initializer, Compose, env, model, database or storage changes.

For that proven schema-neutral case, capture the old running image IDs and
retention state, build the exact target checkout, then replace only the
application roles and inner edge:

```bash
docker compose build
docker compose stop edge backend background-worker realtime
docker compose up -d --no-deps --wait --wait-timeout 120 backend background-worker realtime edge
docker compose ps
```

Do not run `migrate` or `initialize-venue`, restart PostgreSQL/MinIO, alter
named volumes or change credentials/settings. An already-enabled retention
timer may remain active because this path does not mutate database schema;
record its unchanged state and next trigger. Validate the inner Caddy config,
the local `/healthz`, all role healthchecks and the public route/content matrix
before acceptance. If the diff classification is uncertain, use the full
deployment sequence above and its migration safeguards.

4. Check the central edge locally:

   ```bash
   curl -kfsS --max-time 5 https://localhost:8443/healthz
   docker compose logs --tail=100 backend realtime background-worker edge
   ```

   `-k` is correct only for this local probe because the inner Caddy uses its
   own `tls internal` certificate. `backend`, `realtime` and
   `background-worker` must be healthy; a model-consuming role that rejects an
   absent/incompatible serving target is a deployment blocker, not a reason to
   disable its validation.

## First staff login and operational setup

Before the first backend start, the owner may put the desired passwords in the
mode-600 server `.env` under `STAFF_PHOTOGRAPHER_PASSWORD`,
`STAFF_OPERATOR_PASSWORD` and `STAFF_DEVELOPER_PASSWORD`. Backend startup then
creates only the configured fixed accounts (`photographer`, `operator`,
`developer`) with their corresponding roles. A blank or unset value does not
create or change an account, so this override is optional and does not remove
manual provisioning.

If the operator was not supplied through the env override (or manual CLI
provisioning is preferred), create the application account from an interactive
SSH terminal. This is an application account, not the Linux user:

```bash
docker compose exec backend face-moment-provision-staff --username operator --role operator
```

The CLI prompts for a hidden password; do not pass it on the command line.
Existing usernames are rejected rather than overwritten. An intentional reset
uses the same CLI with `--username operator --reset-password` and revokes that
account's sessions. To apply a changed env password, edit the mode-600 server
`.env`, then recreate only the backend so it loads the new environment:

```bash
docker compose up -d --no-deps --force-recreate backend
```

The startup override preserves an existing inactive account and role; a role
mismatch fails backend startup with a generic configuration error. Same-value
restarts leave the password hash, `password_changed_at` and existing sessions
unchanged. Empty/unset keys leave existing accounts untouched.

Open `https://face-moment.ru/staff/login`, check the initialized venue, then
create an entry/token per kiosk in «Экраны». Configure the kiosk at the new
origin: browser settings, camera permission and token do not migrate from
`localhost` or the old domain. UI steps are in the
[application guide](app_guide_ru.md#сотрудники-площадки-и-экраны).

Activate the existing daily cleanup using the
[retention runbook](diagnostic-retention.md), with
`FACE_MOMENT_PROJECT_DIR=/opt/face-moment`. Compose alone does not install this
host timer. Its activation deletes expired diagnostic data according to the
existing retention policy, so it belongs to the approved deployment window.

## Public acceptance

### Verified central rollout — 2026-09-16

The central application was deployed from reviewed commit
`8c0467fbb6f1db0ae9f51c7021b6579a5e5798ab`. The built application image was
`sha256:bb91f3846fe08b51a7726accbefab08e839f8b2a82eaa26efb45f01e27cf36ec`.
The existing PostgreSQL and MinIO volumes were retained; no `down -v`, volume
removal, credential reset, or VPS mutation was performed.

The local packaged proof remained the authoritative precondition:
`scripts/smoke-runtime.sh` passed in evidence directory
`.tasks/ASTRA-findings/10-packaged-smoke/runtime-20260916T095642Z-2952493/`.
Central models matched the workstation assets (YuNet SHA-256
`ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0`, SFace
SHA-256 `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79`),
were made traversable by runtime UID `10001`, and passed native YuNet/SFace
validation with a 128-dimensional embedding. The configured production
metadata is `yunet/2023mar`, `sface/2021dec`, `opencv-photo-640-v2`,
`opencv-aligncrop-v1`, `l2-v1`.

Migration reached `0027_preview_phash`; initialization created the default
`СПА Сибирь 1` venue. The final database counts are one SPA, one pipeline
revision, one reference-settings row, and one active `operator` staff account.
The generated initial password was delivered separately in a local mode-600
credential file and is not recorded here. Backend,
background-worker, realtime, PostgreSQL and MinIO are running healthy; public
`GET /` and `/healthz` return successfully through `https://face-moment.ru`.
The measured immediate FRP/Docker peer is `172.19.0.1`, and this exact value
is set as `FACE_MOMENT_FRP_PROXY_IP`; the temporary measurement access log was
removed and the central Caddyfile matches the reviewed source.
The forged-XFF controlled probe and post-cleanup health check are recorded in
`.protocols/central-deployment-2026-09-16/xff-probe.md`.

The product timing decision is deployed as
`REALTIME_RESULT_DISPLAY_MS=12000` and `REALTIME_SUCCESS_COOLDOWN_MS=1`.
The success cooldown starts at `promo-rendered` while the display timer runs,
so the positive minimum leaves no additional pause after the 12-second result
display. Recognition is still blocked during that interval by the separate
`promoDisplayController.isVisible` guard in the trigger-request handler; the
short cooldown cannot bypass the display lock. The central `.env` remains mode
`600`; existing secret values were preserved and are not recorded here.

Remaining operational setup is intentional: the initial operator was
provisioned through the canonical CLI and its login was verified against the
public session endpoint. The host retention timer was installed by the
operator's root command and user-confirmed as `enabled` and `active`, with
next trigger `2026-09-17 00:00:00` in the server timezone. Its first cleanup
execution has not yet been observed. The authoritative product choice sets
`PHONE_PURCHASE_URL=https://face-moment.ru/` as the temporary self-owned
purchase target; the purchase mechanism itself remains a product TODO and was
not implemented. Public full photo-flow acceptance still requires an
authorized test photo, provisioned display client, and mobile continuation
check; these photo/kiosk/mobile E2E paths remain unverified.

### Verified route/static-only follow-up — 2026-09-16

The reviewed routing correction was deployed to `facecentral` from exact
commit `7924321af0cb1989b0084385e5f600b3f11fcff7`, from clean base
`8c0467fbb6f1db0ae9f51c7021b6579a5e5798ab`. The recorded delta contains only
the public/kiosk route split, static navigation links, tests and runbook docs;
it contains no migration, ORM/schema, Compose, env, model, database or storage
change. This satisfied the narrow route/static-only classification above, so
no migration or `initialize-venue` command was run.

The old application image was
`sha256:bb91f3846fe08b51a7726accbefab08e839f8b2a82eaa26efb45f01e27cf36ec`;
the rebuilt and running application image is
`sha256:46a67115211150ab1d9308bcb83f6b19eb9fb16b7b2428a9a4da1c82c8d2019a` for
`backend`, `background-worker` and `realtime`. The inner edge continues to use
the existing `caddy:2.10.0-alpine` image
`sha256:ae4458638da8e1a91aafffb231c5f8778e964bca650c8a8cb23a7e8ac557aa3c`.
The checkout is clean at the target commit and `docker compose config
--quiet` plus inner Caddy validation succeeded. PostgreSQL and MinIO stayed
running with named volumes `face-moment_postgres-data` and
`face-moment_minio-data`; no volume, secret, settings or VPS edge mutation was
performed. The enabled/active `face-moment-retention-cleanup.timer` remained
active with its next trigger at `2026-09-17 00:00 +07`.

Public acceptance through `https://face-moment.ru` recorded: `/` and `/site`
returned `200` with the public-site marker; `/client1` and `/display` returned
`200` with the `SpaPromoClient` kiosk marker; `/staff/login` returned `200`;
`/healthz` returned `200`; `/phone` without a ticket returned one `303` to
`https://face-moment.ru/`; anonymous `/api/phone/session` returned `401`; and
plain HTTP `/` returned `308` to HTTPS. The deployed scope is routing/static
correction only and explicitly excludes the separate selfie UI work in the
workstation tree.

### Verified public selfie UI follow-up — 2026-09-16

The reviewed public selfie interaction was deployed to `facecentral` from exact
commit `08d2467b7d090164001bfbbb131d31318b7ccbda`, from the already deployed
clean base `7924321af0cb1989b0084385e5f600b3f11fcff7`. The delta contains only
client HTML/CSS/JS, its focused Playwright test and runbook documentation; it
contains no migration, ORM/schema, Compose, env, model, database or storage
change. The narrow route/static-only path therefore applied again: no
migration or `initialize-venue` command was run, and credentials, data,
settings, volumes and the retention timer were preserved.

The old running application image was
`sha256:46a67115211150ab1d9308bcb83f6b19eb9fb16b7b2428a9a4da1c82c8d2019a`;
the rebuilt and running application image is
`sha256:97f22e9ed2aea5743ca0401ec00a0d58a7a26a58dcddfb1b6d198e1491e6b84c` for
`backend`, `background-worker` and `realtime`. The inner edge remains
`caddy:2.10.0-alpine`, image
`sha256:ae4458638da8e1a91aafffb231c5f8778e964bca650c8a8cb23a7e8ac557aa3c`.
All application roles are healthy; PostgreSQL and MinIO are healthy/running,
the named volumes remain intact, and the enabled/active retention timer was
left running. The exact remote checkout is clean at `08d2467` and Compose plus
inner Caddy validation succeeded.

Public content acceptance through `https://face-moment.ru` confirmed `GET /`
returns `200` with the public marker, without the old `Настроить Fluid`,
`.fm-selfie-copy` or `Всего один шаг навстречу воспоминаниям` content. The new
`Жмак меня` and `подбираем Ваши фото..` overlay strings and selfie
`toggleAttribute`/`captureSelfie` logic are present; `/client/site-selfie.js`
returns `200`. `/client1` and `/display` remain kiosk shells with `200` and
`SpaPromoClient`; `/site` remains the public alias with `200`; `/staff/login`
and `/healthz` return `200`; `/phone` without a ticket returns one `303` to
`https://face-moment.ru/`; anonymous `/api/phone/session` returns `401`.
The deployed scope is the public selfie UI follow-up only and excludes any
future uncommitted workstation changes.

After the VPS configuration has been applied, verify from outside the central
host:

```bash
curl -fsSI --max-time 10 https://face-moment.ru/
```

Confirm a browser shows a certificate for `face-moment.ru`, HTTPS redirects are
correct, the display can load its authenticated configuration, and the public
phone origin passes the intended same-origin check. Complete the targeted
proxy/IP checks in [VPS Caddy and FRP](vps-caddy.md#acceptance-checks) before
relying on public rate limits.

Health checks alone do not prove the photo flow. With an authorized test photo,
verify upload → completed processing → kiosk match → QR opened on a phone using
mobile data. Check the selected venue/date and phone media access. Do not count
an empty-database health check as successful end-to-end acceptance.

## Failed release and rollback limits

Stop at the first failed migration/initializer/health check; preserve volumes
and inspect the failed service's sanitized logs. A `--wait` timeout does not
undo the deployment. Do not resume writers against a schema of unknown state.

The pilot explicitly has no backup/snapshot recovery guarantee; see
[architecture](../architecture/system-architecture.md). An old image or Git
commit is **not** a database backup. Return to the previous application image
only after confirming its compatibility with the actual migrated schema and
model revision. Do not run automatic Alembic downgrades or restore an empty
database as a rollback. If incompatible, leave the application unavailable and
prepare a forward fix; loss of primary data cannot be recovered by this runbook.

For ordinary later restart or kiosk recovery, use
[Display and central restart recovery](display-and-central-restart.md), not
this release procedure.
