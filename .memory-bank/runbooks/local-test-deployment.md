---
description: Local test deployment procedures for the editable development stack and disposable packaged smoke.
status: active
last_updated: 2026-09-16
source_of_truth:
  - .memory-bank/runbooks/local-test-deployment.md
---
# Local Test Deployment

## Choose the smallest mode

Use the editable stack for ordinary code/test work. Use the packaged smoke
before server deployment or after changing Docker, Compose, Caddy, startup or
model packaging. Neither mode is the central server deployment; that procedure
is [Server deployment](server-deployment.md).

## Editable local stack

From the repository root, create a local-only environment once, start only
PostgreSQL and MinIO, then migrate the local database:

```bash
test -e .env.local || cp .env.example .env.local
uv sync --python 3.11
docker compose -f compose.yaml -f compose.local.yaml up -d postgres minio
docker compose -f compose.yaml -f compose.local.yaml exec -T postgres sh -ceu 'psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '\''face_moment_local'\''" | grep -q 1 || createdb -U "$POSTGRES_USER" face_moment_local'
uv run --locked --env-file .env.local face-moment-migrate
uv run --locked --env-file .env.local face-moment-initialize-venue
```

`.env.local` is ignored by Git. Begin from `.env.example`; do not import a
central-server `.env` or production credentials. Before initialization, fill
the `SFACE_*` metadata described in [server deployment](server-deployment.md)
using the local model artifacts, with host paths to the files. Initialization
creates **СПА Сибирь 1** only on an empty venue database; existing venues are
untouched. The local host processes use
the editable source and connect to Docker on `127.0.0.1`. Run roles separately
when needed:

```bash
uv run --locked --env-file .env.local face-moment-backend
uv run --locked --env-file .env.local face-moment-background-worker
uv run --locked --env-file .env.local face-moment-realtime
```

The three role ports are `8000`, `8001` and `8002`. Worker/realtime correctly
refuse to start until the local database has an eligible compatible pipeline
revision for the assets in `models/`; do not work around this by disabling model
admission. Normal tests and type checking use the same environment:

```bash
uv run --locked python -m mypy src/face_moment
uv run --locked --env-file .env.local python -m pytest
```

The local infrastructure may contain useful developer data. Do not run
`docker compose down -v` unless you intentionally want to remove those named
volumes.

## Existing browser test stand

The workstation also has a persistent Compose stand configured by the ignored
`.env.testing`. To start its existing containers and open the app locally:

```bash
docker compose --env-file .env.testing up -d --wait --wait-timeout 120
```

Its edge is `https://localhost:8443` with an internal Caddy certificate.
Operator/photographer/developer credentials and the display token live in the
ignored, mode-600 files under `.protocols/local-testing/`. Do not print or
copy them to the server. This stand has existing data; do not rerun its old
`start.sh`/`seed.py` bootstrap. The optional
`.protocols/local-testing/compose-source.yaml` overlay mounts current source;
after Python changes recreate only the affected role with that overlay.
For navigation and app usage see [the Russian app guide](app_guide_ru.md).

## Packaged smoke

The smoke builds current source, starts a separately named Compose project with
disposable volumes and a loopback-only HTTPS edge, then cleans up only its own
containers, network, volumes and image. It is the authoritative local proof
for deployment packaging.

It requires Docker with Compose, Python 3, and these SFace files:

```text
models/opencv_sface/yunet.onnx
models/opencv_sface/sface.onnx
```

Run it from the repository root:

```bash
bash scripts/smoke-runtime.sh
```

The script deliberately ignores the repository `.env`, generates temporary
credentials and saves redacted evidence below
`.tasks/ASTRA-findings/10-packaged-smoke/`. It verifies migrations, a disposable
first-venue initializer and its no-op retry, addition of a second venue,
native model binding, all roles, internal HTTPS, auth and
restart/persistence behavior. Its fixture credentials and `smoke-local-v1`
labels must never be copied to the central server.

For a route-only Caddy regression run:

```bash
uv run --locked --env-file .env.local python -m pytest tests/promo/test_public_edge_routes.py tests/client/test_central_shell.py
```

This requires the local PostgreSQL from the editable stack and does not
replace the packaged smoke.
