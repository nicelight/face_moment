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
identity metadata, or invent the first SPA/serving revision. Do not run
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

The first use additionally needs an intentional initial SPA, a compatible
eligible serving pipeline revision, a staff account and a display-client token.
If preflight shows that those records do not exist, there is no approved
production seed command for this state: stop after runtime deployment and
arrange an explicit, reviewed initializer rather than copying smoke fixtures
or editing tables by hand.

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

3. Build the selected source, then apply migrations once and start the roles:

   ```bash
   docker compose build
   docker compose up -d postgres minio
   docker compose run --rm migrate
   docker compose up -d --wait backend background-worker realtime edge
   docker compose ps
   ```

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

For ordinary later restart or kiosk recovery, use
[Display and central restart recovery](display-and-central-restart.md), not
this release procedure.
