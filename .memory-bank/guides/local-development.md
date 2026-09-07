---
description: Local-first Python development with uv and containerized PostgreSQL/MinIO.
status: active
last_updated: 2026-09-07
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
