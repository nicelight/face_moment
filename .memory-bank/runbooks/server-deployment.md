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
search with no historical date range. Staff accounts and display-client tokens
are still provisioned separately through their existing authorized procedures.

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

After backend is healthy, create the first application operator from an
interactive SSH terminal. This is an application account, not the Linux user:

```bash
docker compose exec backend face-moment-provision-staff --username operator --role operator
```

The CLI prompts for a hidden password; do not pass it on the command line.
Existing usernames are rejected rather than overwritten. An intentional reset
uses the same CLI with `--username operator --reset-password` and revokes that
account's sessions. Create a separate `developer` only if its diagnostic access
is needed. No default staff login is created by migrations or venue initialization.

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
