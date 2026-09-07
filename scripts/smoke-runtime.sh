#!/usr/bin/env bash
set -Eeuo pipefail
# Credentials are ephemeral, but must not enter evidence through shell tracing.
set +x
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
EVIDENCE_DIR="${EVIDENCE_DIR:-${ROOT_DIR}/.tasks/ASTRA-findings/10-packaged-smoke/runtime-${RUN_ID}}"
PROJECT_NAME="face-moment-smoke-${RUN_ID,,}"
PROBE_ID="probe-${RUN_ID,,}"
CONFIG_JSON="$(mktemp)"
RESOURCES_STARTED=0
IMAGE_BUILT=0
mkdir -p "${EVIDENCE_DIR}"
exec > >(tee "${EVIDENCE_DIR}/smoke.log") 2>&1

export FACE_MOMENT_IMAGE="face-moment-smoke:${RUN_ID,,}"
export FACE_MOMENT_MODEL_DIR="${ROOT_DIR}/models"
export POSTGRES_DB="smoke_$$" POSTGRES_USER="smoke_$$"
export POSTGRES_PASSWORD MINIO_ROOT_PASSWORD PROMO_QR_TICKET_SECRET
POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
MINIO_ROOT_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
PROMO_QR_TICKET_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export MINIO_ROOT_USER="smoke$$" S3_BUCKET="smoke-${RUN_ID,,}"
export REALTIME_RESULT_DISPLAY_MS=5000 REALTIME_SUCCESS_COOLDOWN_MS=1000
export SFACE_DETECTOR_PATH=/run/face-moment/models/opencv_sface/yunet.onnx
export SFACE_RECOGNIZER_PATH=/run/face-moment/models/opencv_sface/sface.onnx
# Fixture identity labels do not claim an unverified upstream release version.
export SFACE_DETECTOR_ID=yunet SFACE_DETECTOR_VERSION=smoke-local-v1
export SFACE_RECOGNIZER_ID=sface SFACE_RECOGNIZER_VERSION=smoke-local-v1
export SFACE_PREPROCESSING_VERSION=opencv-bgr-v1 SFACE_ALIGNMENT_VERSION=opencv-aligncrop-v1
export SFACE_NORMALIZATION_VERSION=l2-v1 SFACE_EMBEDDING_DIMENSION=128

dc() {
  docker compose --project-directory "${ROOT_DIR}" --env-file /dev/null \
    -f "${ROOT_DIR}/compose.yaml" -p "${PROJECT_NAME}" "$@"
}

cleanup() {
  local command_status=$? cleanup_status=0 remaining
  trap - EXIT
  if [[ ${RESOURCES_STARTED} == 1 ]]; then
    dc down --volumes --remove-orphans --timeout 20 || cleanup_status=1
    if remaining="$(docker ps -aq --filter "label=com.docker.compose.project=${PROJECT_NAME}")"; then
      [[ -z "${remaining}" ]] || cleanup_status=1
    else
      cleanup_status=1
    fi
    if remaining="$(docker volume ls -q --filter "label=com.docker.compose.project=${PROJECT_NAME}")"; then
      [[ -z "${remaining}" ]] || cleanup_status=1
    else
      cleanup_status=1
    fi
    echo "owned_cleanup_status=${cleanup_status}"
  fi
  if [[ ${IMAGE_BUILT} == 1 ]]; then
    docker image rm "${FACE_MOMENT_IMAGE}" || cleanup_status=1
    echo "owned_image_cleanup_status=${cleanup_status}"
  fi
  rm -f "${CONFIG_JSON}"
  [[ ${command_status} == 0 ]] || exit "${command_status}"
  exit "${cleanup_status}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cd "${ROOT_DIR}"
echo "smoke_project=${PROJECT_NAME}"
echo "evidence_dir=${EVIDENCE_DIR}"
test -s "${FACE_MOMENT_MODEL_DIR}/opencv_sface/yunet.onnx"
test -s "${FACE_MOMENT_MODEL_DIR}/opencv_sface/sface.onnx"

# Inspect network subnets only; never dump container environments.
NETWORK_CHOICE="$(python3 - <<'PY'
import ipaddress, json, socket, subprocess
ids = subprocess.check_output(['docker', 'network', 'ls', '-q'], text=True).split()
networks = json.loads(subprocess.check_output(['docker', 'network', 'inspect', *ids])) if ids else []
used = [ipaddress.ip_network(c['Subnet']) for n in networks for c in (n.get('IPAM', {}).get('Config') or []) if c.get('Subnet')]
for subnet in ipaddress.ip_network('10.0.0.0/8').subnets(new_prefix=24):
    if not any(subnet.overlaps(n) for n in used):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            print(subnet, next(subnet.subnets(new_prefix=25)), subnet[-2], sock.getsockname()[1])
        break
else:
    raise SystemExit('no free smoke subnet')
PY
)"
read -r FACE_MOMENT_PRIVATE_SUBNET FACE_MOMENT_PRIVATE_DYNAMIC_RANGE FACE_MOMENT_TRUSTED_PROXY_IP FACE_MOMENT_EDGE_PORT <<< "${NETWORK_CHOICE}"
export FACE_MOMENT_PRIVATE_SUBNET FACE_MOMENT_PRIVATE_DYNAMIC_RANGE FACE_MOMENT_TRUSTED_PROXY_IP FACE_MOMENT_EDGE_PORT

dc config --format json > "${CONFIG_JSON}"
python3 - "${CONFIG_JSON}" "${PROJECT_NAME}" "${EVIDENCE_DIR}/compose-topology.json" <<'PY' | tee "${EVIDENCE_DIR}/topology-summary.txt"
import ipaddress, json, os, pathlib, sys
config = json.loads(pathlib.Path(sys.argv[1]).read_text())
project = sys.argv[2]
assert config['name'] == project
services = config['services']
assert sorted(n for n, s in services.items() if s.get('ports')) == ['edge']
assert all(p['host_ip'] == '127.0.0.1' for p in services['edge']['ports'])
assert {services[n]['image'] for n in ('backend', 'background-worker', 'realtime', 'migrate')} == {os.environ['FACE_MOMENT_IMAGE']}
assert sorted(n for n, s in services.items() if 'edge' in s.get('networks', {})) == ['edge']
private = config['networks']['private']
assert private['internal'] is True
subnet = ipaddress.ip_network(private['ipam']['config'][0]['subnet'])
dynamic = ipaddress.ip_network(private['ipam']['config'][0]['ip_range'])
proxy = ipaddress.ip_address(services['edge']['networks']['private']['ipv4_address'])
assert str(subnet) == os.environ['FACE_MOMENT_PRIVATE_SUBNET']
assert dynamic.subnet_of(subnet) and proxy in subnet and proxy not in dynamic
for name, volume in config['volumes'].items():
    assert not volume.get('external') and volume['name'] == f'{project}_{name}'
for name, service in services.items():
    for mount in service.get('volumes', []):
        assert 'docker.sock' not in str(mount)
        if mount['type'] == 'volume':
            assert mount['source'] in config['volumes']
for name in ('background-worker', 'realtime'):
    mounts = [v for v in services[name]['volumes'] if v['target'] == '/run/face-moment/models']
    assert len(mounts) == 1 and mounts[0]['read_only'] is True
    assert mounts[0]['source'] == os.environ['FACE_MOMENT_MODEL_DIR']
# Keep reusable topology evidence without retaining runtime credentials.
for service in services.values():
    service['environment'] = {key: '<redacted>' for key in service.get('environment', {})}
pathlib.Path(sys.argv[3]).write_text(json.dumps(config, indent=2) + '\n')
print(f'isolated_topology=ok project={project} private_subnet={subnet}')
print('host_published_services=edge loopback=true model_mount=read-only shared_image=true')
PY

dc build backend
IMAGE_BUILT=1
RESOURCES_STARTED=1
dc up -d --wait --wait-timeout 180 postgres minio
dc run --rm -T --no-deps migrate | tee "${EVIDENCE_DIR}/migration.log"
dc run --rm -T --no-deps backend python - <<'PY' | tee "${EVIDENCE_DIR}/schema.txt"
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from face_moment.infrastructure.settings import Settings
engine = create_engine(Settings.from_env().database_url)
heads = ScriptDirectory.from_config(Config('alembic.ini')).get_heads()
with engine.connect() as c:
    actual = list(c.execute(text('SELECT version_num FROM alembic_version')).scalars())
    assert len(heads) == 1 and actual == heads
    assert c.scalar(text("SELECT to_regclass('face_moment.pipeline_revisions')"))
    assert c.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname='face_moment'")) > 0
    assert c.scalar(text("SELECT count(*) FROM pg_extension WHERE extname='vector'")) == 1
engine.dispose()
print(f'migrated_product_schema=ok alembic_head={heads[0]} pgvector=ok')
PY

# Capture only the generated token; do not log it or pass it in command arguments.
DISPLAY_TOKEN="$(dc run --rm -T --no-deps background-worker python - <<'PY'
import os
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from face_moment.infrastructure.settings import Settings
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.processing.sface_adapter import SFaceModelAssets
from face_moment.serving_control.ingest_target import IngestTargetRepository
from face_moment.serving_control.display_client_access import DisplayClientRepository
assets = SFaceModelAssets(**{
    key: Path(os.environ['SFACE_' + key.upper()]) if key.endswith('_path') else os.environ['SFACE_' + key.upper()]
    for key in ('detector_path', 'detector_id', 'detector_version', 'recognizer_path', 'recognizer_id', 'recognizer_version', 'preprocessing_version', 'alignment_version', 'normalization_version')
})
engine = create_engine(Settings.from_env().database_url)
try:
    with Session(engine) as session, session.begin():
        revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE, validated_at=datetime.now(timezone.utc),
            weights_sha256=assets.weights_sha256(), embedding_dimension=128,
            **{k: getattr(assets, k) for k in ('detector_id', 'detector_version', 'recognizer_id', 'recognizer_version', 'preprocessing_version', 'alignment_version', 'normalization_version')})
        spa = IngestTargetRepository(session).configure_spa(name='packaged-smoke', timezone='UTC', serving_pipeline_revision_id=revision.id)
        client = DisplayClientRepository(session).provision(spa_id=spa.spa_id, name='smoke-display')
        token = client.token_value
    print(token)
except Exception as error:
    # SQL exceptions can contain the token in bound parameters.
    raise SystemExit('seed_failed=' + type(error).__name__) from None
finally:
    engine.dispose()
PY
)"
export DISPLAY_TOKEN
echo 'serving_model_seed=committed'
dc run --rm -T --no-deps background-worker python - <<'PY' | tee "${EVIDENCE_DIR}/model-binding.txt"
from face_moment.entrypoints.model_consumers import bind_model_consumer
from face_moment.infrastructure.settings import Settings
binding = bind_model_consumer(Settings.from_env())
try:
    assert binding.adapter.ready
    print('real_sface_binding=ok revision=' + str(binding.adapter.pipeline_revision_id))
finally:
    binding.close()
PY

dc up -d --wait --wait-timeout 180
# Check the created network, not only its intended Compose definition.
docker network inspect "${PROJECT_NAME}_private" --format '{{.Internal}} {{range .IPAM.Config}}{{.Subnet}}{{end}}' \
  | tee "${EVIDENCE_DIR}/private-network.txt"
[[ "$(cat "${EVIDENCE_DIR}/private-network.txt")" == "true ${FACE_MOMENT_PRIVATE_SUBNET}" ]]
backend_image="$(docker inspect -f '{{.Image}}' "$(dc ps -q backend)")"
for role in backend background-worker realtime; do
  role_image="$(docker inspect -f '{{.Image}}' "$(dc ps -q "${role}")")"
  [[ "${role_image}" == "${backend_image}" ]]
  echo "${role}_image=${role_image}"
done | tee "${EVIDENCE_DIR}/image-identities.txt"

check_readiness() {
  dc exec -T backend python - <<'PY'
import json, urllib.request
for host, port, role in [('backend', 8000, 'backend'), ('background-worker', 8001, 'BackgroundPhotoWorker'), ('realtime', 8002, 'RealtimeFaceService')]:
    with urllib.request.urlopen(f'http://{host}:{port}/healthz', timeout=5) as response:
        payload = json.load(response)
    assert payload['ready'] is True and payload['role'] == role
    if host != 'backend':
        assert payload['production_model_loaded'] is True and payload['recovery_completed'] is True
    print(json.dumps(payload, sort_keys=True))
PY
}
check_readiness | tee "${EVIDENCE_DIR}/role-readiness.jsonl"
check_edge() {
python3 - <<'PY'
import json, os, ssl, time, urllib.error, urllib.request, uuid
base = 'https://localhost:' + os.environ['FACE_MOMENT_EDGE_PORT']
context = ssl._create_unverified_context()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
def probe(path, expected, *, authenticated=False, body=None):
    headers = {'Authorization': 'Bearer ' + os.environ['DISPLAY_TOKEN']} if authenticated else {}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(base + path, headers=headers, data=None if body is None else json.dumps(body).encode(), method='GET' if body is None else 'PUT')
    try:
        response = opener.open(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        status, payload = response.code, response.read()
    assert status == expected, f'{path}: expected {expected}, got {status}'
    print(f'{request.method} {path} authenticated={authenticated} status={status}')
    return payload
for attempt in range(30):
    try:
        health = json.loads(probe('/realtime/healthz', 200))
        assert health['ready'] and health['production_model_loaded'] and health['recovery_completed']
        break
    except (OSError, AssertionError):
        if attempt == 29:
            raise
        time.sleep(1)
probe('/staff/login', 200)
probe('/staff/photo-inventory', 401)
probe('/api/promo/display/config', 401)
config = json.loads(probe('/api/promo/display/config', 200, authenticated=True))
assert config == {'schema_version': 1, 'result_display_ms': 5000, 'success_cooldown_ms': 1000}
probe('/api/promo/media/' + 'A' * 43, 404, authenticated=True)
probe('/api/promo/sessions/' + str(uuid.uuid4()) + '/display', 404, authenticated=True, body={'schema_version': 1, 'status': 'failed'})
PY
}
check_edge | tee "${EVIDENCE_DIR}/edge-routes.txt"

dc exec -T backend python scripts/runtime-storage-probe.py write --probe-id "${PROBE_ID}" \
  | tee "${EVIDENCE_DIR}/storage-write.txt"
dc stop backend background-worker realtime
dc restart postgres minio
dc up -d --wait --wait-timeout 180 postgres minio
dc up -d --wait --wait-timeout 180
check_readiness | tee "${EVIDENCE_DIR}/role-readiness-after-restart.jsonl"
check_edge | tee "${EVIDENCE_DIR}/edge-routes-after-restart.txt"
unset DISPLAY_TOKEN
dc exec -T backend python scripts/runtime-storage-probe.py read --probe-id "${PROBE_ID}" \
  | tee "${EVIDENCE_DIR}/storage-read-after-restart.txt"
dc exec -T backend python scripts/runtime-storage-probe.py delete --probe-id "${PROBE_ID}" \
  | tee "${EVIDENCE_DIR}/storage-delete.txt"
dc exec -T postgres psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
  'SELECT count(*) FROM face_moment.promo_sessions;' | tee "${EVIDENCE_DIR}/promo-session-count.txt"
[[ "$(tr -d '[:space:]' < "${EVIDENCE_DIR}/promo-session-count.txt")" == 0 ]]
dc ps --format json > "${EVIDENCE_DIR}/service-state.json"
echo 'runtime_smoke=ok'
