#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_ID="${TASK_ID:-TASK-001-T3-FT-000-W0}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
EVIDENCE_DIR="${EVIDENCE_DIR:-${ROOT_DIR}/.tasks/${TASK_ID}/runtime-smoke-${RUN_ID}}"
PROJECT_NAME="face-moment-smoke-${RUN_ID,,}"
PROBE_ID="probe-${RUN_ID,,}"
CONFIG_JSON="$(mktemp)"

mkdir -p "${EVIDENCE_DIR}"
exec > >(tee "${EVIDENCE_DIR}/smoke.log") 2>&1

export COMPOSE_PROJECT_NAME="${PROJECT_NAME}"
export FACE_MOMENT_IMAGE="face-moment-smoke:${RUN_ID,,}"
export FACE_MOMENT_EDGE_PORT
FACE_MOMENT_EDGE_PORT="$(
  python3 - <<'PY'
import socket

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"
export POSTGRES_DB="face_moment"
export POSTGRES_USER="foundation_$$"
export POSTGRES_PASSWORD="test-only-${RUN_ID}"
export MINIO_ROOT_USER="foundation$$"
export MINIO_ROOT_PASSWORD="test-only-minio-${RUN_ID}"
export S3_BUCKET="foundation-${RUN_ID,,}"

dc() {
  docker compose --project-directory "${ROOT_DIR}" "$@"
}

cleanup() {
  local command_status=$?
  local cleanup_status=0
  trap - EXIT

  if dc ps --status running --services 2>/dev/null | grep -qx backend; then
    dc exec -T backend python scripts/runtime-storage-probe.py delete \
      --probe-id "${PROBE_ID}" || cleanup_status=$?
  fi
  dc down --volumes --remove-orphans --timeout 20 || cleanup_status=$?
  rm -f "${CONFIG_JSON}"

  if dc ps -a --services 2>/dev/null | grep -q .; then
    echo "owned_cleanup=failed"
    cleanup_status=1
  else
    echo "owned_cleanup=ok"
  fi

  if [[ ${command_status} -ne 0 ]]; then
    exit "${command_status}"
  fi
  exit "${cleanup_status}"
}
trap cleanup EXIT

cd "${ROOT_DIR}"

echo "smoke_project=${PROJECT_NAME}"
echo "evidence_dir=${EVIDENCE_DIR}"

dc config --quiet
dc config --format json > "${CONFIG_JSON}"
python3 - "${CONFIG_JSON}" "${EVIDENCE_DIR}/topology-summary.txt" <<'PY'
import json
import pathlib
import sys

config = json.loads(pathlib.Path(sys.argv[1]).read_text())
services = config["services"]
published = sorted(name for name, service in services.items() if service.get("ports"))
if published != ["edge"]:
    raise SystemExit(f"unexpected host-published services: {published}")

app_roles = ["backend", "background-worker", "realtime"]
images = {services[name]["image"] for name in app_roles}
if len(images) != 1:
    raise SystemExit(f"application roles do not share one image: {images}")

for name, service in services.items():
    for volume in service.get("volumes", []):
        source = str(volume.get("source", ""))
        target = str(volume.get("target", ""))
        if "docker.sock" in source or "docker.sock" in target:
            raise SystemExit(f"Docker socket mounted by {name}")

edge_network_members = sorted(
    name for name, service in services.items() if "edge" in service.get("networks", {})
)
if edge_network_members != ["edge"]:
    raise SystemExit(f"unexpected edge network members: {edge_network_members}")

summary = (
    "host_published_services=edge\n"
    f"application_image={next(iter(images))}\n"
    "application_roles=backend,BackgroundPhotoWorker,RealtimeFaceService\n"
    "docker_socket_mount=absent\n"
    "private_network_internal=true\n"
    "edge_network_members=edge\n"
)
pathlib.Path(sys.argv[2]).write_text(summary)
print(summary, end="")
PY

dc build
dc run --rm --no-deps backend python - <<'PY'
import cv2
import insightface

print(f"opencv_import=ok version={cv2.__version__}")
print(f"insightface_import=ok version={insightface.__version__}")
PY

dc up -d --wait --wait-timeout 180

dc exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
  "SELECT extname FROM pg_extension WHERE extname = 'vector';" \
  | tee "${EVIDENCE_DIR}/pgvector.txt"

dc exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
  "SELECT count(*) FROM pg_tables WHERE schemaname = 'face_moment';" \
  | tee "${EVIDENCE_DIR}/application-table-count.txt"
if [[ "$(tr -d '[:space:]' < "${EVIDENCE_DIR}/application-table-count.txt")" != "0" ]]; then
  echo "empty_application_schema=failed"
  exit 1
fi

dc run --rm --no-deps backend python - <<'PY' \
  | tee "${EVIDENCE_DIR}/metadata.txt"
from face_moment.infrastructure.database import APP_SCHEMA, Base

assert APP_SCHEMA == "face_moment"
assert Base.metadata.schema == APP_SCHEMA
assert len(Base.metadata.tables) == 0
print("single_base_metadata=ok")
print("product_table_count=0")
PY

dc run --rm --no-deps backend alembic heads \
  | tee "${EVIDENCE_DIR}/alembic-heads.txt"
if [[ "$(wc -l < "${EVIDENCE_DIR}/alembic-heads.txt")" -ne 1 ]]; then
  echo "single_alembic_head=failed"
  exit 1
fi

backend_image="$(docker inspect -f '{{.Image}}' "$(dc ps -q backend)")"
worker_image="$(docker inspect -f '{{.Image}}' "$(dc ps -q background-worker)")"
realtime_image="$(docker inspect -f '{{.Image}}' "$(dc ps -q realtime)")"
{
  echo "backend_image=${backend_image}"
  echo "background_worker_image=${worker_image}"
  echo "realtime_image=${realtime_image}"
} | tee "${EVIDENCE_DIR}/image-identities.txt"
if [[ "${backend_image}" != "${worker_image}" || "${backend_image}" != "${realtime_image}" ]]; then
  echo "one_application_image=failed"
  exit 1
fi

python3 - "${FACE_MOMENT_EDGE_PORT}" <<'PY' \
  | tee "${EVIDENCE_DIR}/https-readiness.json"
import ssl
import sys
import time
import urllib.request

context = ssl._create_unverified_context()
url = f"https://localhost:{sys.argv[1]}/realtime/healthz"
last_error = None
for _ in range(60):
    try:
        with urllib.request.urlopen(url, context=context, timeout=2) as response:
            payload = response.read().decode()
            if response.status != 200:
                raise RuntimeError(f"unexpected HTTPS status: {response.status}")
            if '"engine":"fake"' not in payload or '"engine_ready":true' not in payload:
                raise RuntimeError(f"fake engine readiness missing: {payload}")
            print(payload)
            break
    except Exception as error:
        last_error = error
        time.sleep(0.5)
else:
    raise RuntimeError("HTTPS realtime readiness did not converge") from last_error
PY

dc exec -T background-worker python - <<'PY' \
  | tee "${EVIDENCE_DIR}/background-worker-readiness.json"
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8001/healthz", timeout=5) as response:
    print(response.read().decode())
PY

dc exec -T backend python scripts/runtime-storage-probe.py write \
  --probe-id "${PROBE_ID}" | tee "${EVIDENCE_DIR}/storage-write.txt"

dc restart postgres minio backend background-worker realtime
dc up -d --wait --wait-timeout 180

python3 - "${FACE_MOMENT_EDGE_PORT}" <<'PY' \
  | tee "${EVIDENCE_DIR}/https-readiness-after-restart.json"
import ssl
import sys
import time
import urllib.request

context = ssl._create_unverified_context()
url = f"https://localhost:{sys.argv[1]}/backend/healthz"
last_error = None
for _ in range(60):
    try:
        with urllib.request.urlopen(url, context=context, timeout=2) as response:
            payload = response.read().decode()
            if response.status != 200 or '"ready":true' not in payload:
                raise RuntimeError(f"backend not ready after restart: {payload}")
            print(payload)
            break
    except Exception as error:
        last_error = error
        time.sleep(0.5)
else:
    raise RuntimeError("HTTPS backend readiness did not converge") from last_error
PY

dc exec -T backend python scripts/runtime-storage-probe.py read \
  --probe-id "${PROBE_ID}" | tee "${EVIDENCE_DIR}/storage-read-after-restart.txt"
dc exec -T backend python scripts/runtime-storage-probe.py delete \
  --probe-id "${PROBE_ID}" | tee "${EVIDENCE_DIR}/storage-delete.txt"

dc ps --format json > "${EVIDENCE_DIR}/service-state.json"
echo "runtime_smoke=ok"
