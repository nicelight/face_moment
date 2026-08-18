#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

origin="${FACE_MOMENT_ORIGIN:-https://localhost:8443}"
marker="task-051-$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}"
fixture_spec=""
browser_pid=""
browser_profile=""

run_probe() {
  local action="$1"
  shift
  local -a compose_exec=(docker compose exec -T)
  if [[ -n "${TASK051_STAFF_PASSWORD:-}" ]]; then
    compose_exec+=( -e "TASK051_STAFF_PASSWORD=${TASK051_STAFF_PASSWORD}" )
  fi
  "${compose_exec[@]}" backend python - "$action" "$@" <<'PY'
from __future__ import annotations

import json
import http.client
import os
import secrets
import socket
import sys
import time
import uuid
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import ssl

import cv2
import numpy as np
from sqlalchemy import delete, select, create_engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.admission import AdmissionCandidate, AtomicPhotoAdmission
from face_moment.inventory.candidate_staging import CandidateStager
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import (
    JpegValidationLimits,
    validate_jpeg_candidate,
)
from face_moment.platform.auth.principals import (
    StaffRole,
    StaffUser,
    provision_staff_user,
)
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace
from face_moment.processing.revisions import PipelineCode, PipelineRevision
from face_moment.promo.attempt import PromoAttempt
from face_moment.serving_control.display_client_access import (
    DisplayClient,
    DisplayClientRepository,
)
from face_moment.serving_control.ingest_target import Spa, IngestTargetRepository
from face_moment.serving_control.realtime_context import (
    QuerySource,
    ReferenceSearchSettings,
)
from face_moment.platform.auth.sessions import StaffSession


def fail(reason: str) -> None:
    raise SystemExit(f"FAIL {reason}")


def settings_and_engine():
    settings = Settings.from_env()
    return settings, create_engine(settings.database_url, pool_pre_ping=True)


def active_runtime(session: Session):
    spas = list(
        session.scalars(select(Spa).where(Spa.active.is_(True)).order_by(Spa.id))
    )
    if len(spas) != 1:
        fail("active_spa_count_not_one")
    spa = spas[0]
    revision = session.get(PipelineRevision, spa.serving_pipeline_revision_id)
    if revision is None or revision.validated_at is None:
        fail("active_revision_not_eligible")
    if revision.pipeline_code is not PipelineCode.OPENCV_SFACE:
        fail("active_revision_is_not_sface")
    context = session.scalar(
        select(ReferenceSearchSettings).where(
            ReferenceSearchSettings.spa_id == spa.id,
            ReferenceSearchSettings.pipeline_code == PipelineCode.OPENCV_SFACE.value,
            ReferenceSearchSettings.query_source == QuerySource.REFERENCE.value,
        )
    )
    if context is None or spa.active_visit_date is None:
        fail("active_realtime_context_missing")
    return spa, revision


def http_call(url: str, *, method: str = "GET", data: bytes | None = None,
              headers: dict[str, str] | None = None) -> tuple[int, bytes, object]:
    parsed = urlsplit(url)
    if parsed.hostname == "edge" and parsed.port == 8443:
        class EdgeConnection(http.client.HTTPSConnection):
            def connect(self) -> None:
                self.sock = socket.create_connection(
                    (self.host, self.port), self.timeout
                )
                self.sock = self._context.wrap_socket(
                    self.sock, server_hostname="localhost"
                )

        connection = EdgeConnection(
            "edge", 8443, timeout=8, context=ssl._create_unverified_context()
        )
        try:
            path = parsed.path or "/"
            if parsed.query:
                path += f"?{parsed.query}"
            connection.request(method, path, body=data, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read(), response.headers
        except (OSError, TimeoutError) as error:
            fail(f"http_unavailable_edge_{type(error).__name__}")
        finally:
            connection.close()
    request = Request(url, data=data, method=method, headers=headers or {})
    context = ssl._create_unverified_context() if url.startswith("https://") else None
    try:
        with urlopen(request, timeout=8, context=context) as response:
            return response.status, response.read(), response.headers
    except HTTPError as error:
        return error.code, error.read(), error.headers
    except (URLError, TimeoutError) as error:
        fail(f"http_unavailable_{type(error).__name__}")


def health(url: str, *, host: str | None = None) -> tuple[int, bool | None]:
    headers = {"Host": host} if host else {}
    status, body, _ = http_call(url, headers=headers)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    ready = payload.get("ready") if isinstance(payload, dict) else None
    return status, ready


def readiness() -> None:
    checks = {
        "backend": ("http://127.0.0.1:8000/healthz", None),
        "background_worker": ("http://background-worker:8001/healthz", None),
        "realtime": ("http://realtime:8002/healthz", None),
        "edge": ("https://edge:8443/healthz", "localhost:8443"),
    }
    observed: dict[str, str] = {}
    for name, (url, host) in checks.items():
        status, ready = health(url, host=host)
        if status != 200:
            fail(f"{name}_health_status_{status}")
        if name != "edge" and ready is not True:
            fail(f"{name}_not_ready")
        observed[name] = "ready" if name != "edge" else "200"
    print(
        "central_readiness=PASS "
        + " ".join(f"{name}={value}" for name, value in observed.items())
    )


def make_jpeg() -> bytes:
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[:, :, 0] = 23
    image[:, :, 1] = 47
    image[:, :, 2] = 71
    encoded, output = cv2.imencode(
        ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 85]
    )
    if not encoded:
        fail("disposable_jpeg_encode_failed")
    return bytes(output)


def setup(marker: str) -> None:
    settings, engine = settings_and_engine()
    username = f"task-051-{marker}".casefold()
    password = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    try:
        with Session(engine) as session:
            spa, revision = active_runtime(session)
            principal = provision_staff_user(
                session,
                username=username,
                password=password,
                role=StaffRole.DEVELOPER,
            )
            staff_id = principal.staff_user_id

        with Session(engine) as session:
            spa, revision = active_runtime(session)
            spa_id = spa.id
            spa_timezone = spa.timezone
            visit_date = spa.active_visit_date
            client = DisplayClientRepository(session).provision(
                spa_id=spa_id,
                name=f"task-051-display-{marker}",
                now=now,
            )
            session.commit()

        payload = make_jpeg()
        with Session(engine) as session:
            target = IngestTargetRepository(session).resolve_ingest_target(spa_id)
        validated = validate_jpeg_candidate(
            payload,
            visit_date=visit_date,
            spa_timezone=spa_timezone,
            upload_started_at=now,
            limits=JpegValidationLimits(
                max_compressed_bytes=10 * 1024 * 1024,
                max_decoded_side_length=4096,
                max_decoded_pixels=16 * 1024 * 1024,
            ),
        )
        stager = CandidateStager(
            PrivateObjectStore(settings), key_prefix=f"task-051/{marker}"
        )
        staged = stager.stage(payload)
        with Session(engine) as session:
            photo = AtomicPhotoAdmission(session).publish(
                ingest_target=target,
                uploader_id=staff_id,
                candidate=AdmissionCandidate(
                    staged_candidate=staged,
                    validated_jpeg=validated,
                ),
            )
            photo_id = photo.id
        print(f"{username}\t{password}")
    finally:
        engine.dispose()


def backend_probe(marker: str, username: str, password: str) -> None:
    settings, engine = settings_and_engine()
    try:
        with Session(engine) as session:
            spa, _ = active_runtime(session)
            spa_id = str(spa.id)

        login_body = json.dumps(
            {"username": username, "password": password},
            separators=(",", ":"),
        ).encode("utf-8")
        status, _, headers = http_call(
            "http://127.0.0.1:8000/api/staff/sessions",
            method="POST",
            data=login_body,
            headers={"Content-Type": "application/json"},
        )
        if status != 204:
            fail(f"backend_login_status_{status}")
        cookies = SimpleCookie()
        for set_cookie in headers.get_all("Set-Cookie", []):
            cookies.load(set_cookie)
        cookie_header = "; ".join(
            f"{key}={morsel.value}" for key, morsel in cookies.items()
        )
        if not cookie_header:
            fail("backend_session_cookie_missing")
        query = urlencode({"spa_id": spa_id})
        status, _, _ = http_call(
            f"http://127.0.0.1:8000/api/inventory/processing-health?{query}",
            headers={"Cookie": cookie_header},
        )
        if status != 200:
            fail(f"authenticated_backend_probe_status_{status}")
        print("authenticated_backend_probe=PASS status=200")
    finally:
        engine.dispose()


def wait_photo(marker: str) -> None:
    _, engine = settings_and_engine()
    try:
        deadline = time.monotonic() + 35
        last_status = "missing"
        while time.monotonic() < deadline:
            with Session(engine) as session:
                state = session.scalar(
                    select(PhotoPipelineState)
                    .join(Photo, Photo.id == PhotoPipelineState.photo_id)
                    .where(Photo.original_object_key.like(f"task-051/{marker}/%"))
                )
                if state is not None:
                    last_status = state.status
                    if state.status in {"ready", "no_faces"}:
                        print(f"photo_transition=PASS terminal={state.status}")
                        return
                    if state.status == "failed":
                        fail("photo_transition_failed")
            time.sleep(0.5)
        fail(f"photo_transition_timeout_last={last_status}")
    finally:
        engine.dispose()


def realtime_probe(marker: str) -> None:
    _, engine = settings_and_engine()
    try:
        with Session(engine) as session:
            spa, revision = active_runtime(session)
            client = session.scalar(
                select(DisplayClient).where(
                    DisplayClient.name == f"task-051-display-{marker}",
                    DisplayClient.active.is_(True),
                )
            )
            if client is None:
                fail("task_display_client_missing")
            token = client.token_value
        attempt_id = uuid.uuid4()
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        manifest = {
            "schema_version": 1,
            "attempt_id": str(attempt_id),
            "trigger_source": "test",
            "client_release": f"task-051-{marker}",
            "detector_id": "mediapipe_blazeface_full_range",
            "model_version": "task-051-disposable",
            "jpeg_quality": 0.85,
            "camera_device_id": "task-051-disposable",
            "timing": {
                "reference_series_ready_at": timestamp,
                "local_detection_completed_ms": 1,
                "request_started_ms": 2,
            },
            "occurrences": [],
        }
        boundary = f"task051{secrets.token_hex(8)}"
        body = (
            f"--{boundary}\r\n"
            "Content-Disposition: form-data; name=\"manifest\"\r\n"
            "Content-Type: application/json; charset=utf-8\r\n\r\n"
            + json.dumps(manifest, separators=(",", ":"))
            + f"\r\n--{boundary}--\r\n"
        ).encode("utf-8")
        status, response_body, _ = http_call(
            "https://edge:8443/api/realtime/attempts",
            method="POST",
            data=body,
            headers={
                "Host": "localhost:8443",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {token}",
                "Content-Length": str(len(body)),
            },
        )
        if status != 200:
            fail(f"realtime_probe_status_{status}")
        try:
            response = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            fail("realtime_probe_response_not_json")
        if response.get("outcome") != "no_proposals":
            fail("realtime_probe_outcome_not_no_proposals")
        with Session(engine) as session:
            attempt = session.scalar(
                select(PromoAttempt).where(
                    PromoAttempt.spa_id == spa.id,
                    PromoAttempt.client_attempt_id == attempt_id,
                )
            )
            if attempt is None or attempt.domain_outcome != "no_proposals":
                fail("realtime_attempt_not_persisted")
        print("realtime_admission=PASS outcome=no_proposals")
    finally:
        engine.dispose()


def cleanup(marker: str) -> None:
    settings, engine = settings_and_engine()
    store = PrivateObjectStore(settings)
    username = f"task-051-{marker}".casefold()
    client_name = f"task-051-display-{marker}"
    derivative_prefixes: list[str] = []
    try:
        with Session(engine) as session:
            staff_ids = list(
                session.scalars(
                    select(StaffUser.id).where(StaffUser.username == username)
                )
            )
            photo_rows = list(
                session.scalars(
                    select(Photo).where(
                        Photo.original_object_key.like(f"task-051/{marker}/%")
                    )
                )
            )
            photo_ids = [photo.id for photo in photo_rows]
            keys = set(store.list_keys(prefix=f"task-051/{marker}/"))
            for photo_id in photo_ids:
                derivative_prefix = f"private/derivatives/{photo_id}/"
                derivative_prefixes.append(derivative_prefix)
                keys.update(store.list_keys(prefix=derivative_prefix))
            for key in sorted(keys):
                store.delete(key=key)
            if photo_ids:
                session.execute(
                    delete(PhotoFace).where(PhotoFace.photo_id.in_(photo_ids))
                )
                session.execute(
                    delete(PhotoPipelineState).where(
                        PhotoPipelineState.photo_id.in_(photo_ids)
                    )
                )
                session.execute(delete(Photo).where(Photo.id.in_(photo_ids)))
            session.execute(
                delete(PromoAttempt).where(
                    PromoAttempt.client_release == f"task-051-{marker}"
                )
            )
            session.execute(
                delete(DisplayClient).where(DisplayClient.name == client_name)
            )
            if staff_ids:
                session.execute(
                    delete(StaffSession).where(StaffSession.staff_user_id.in_(staff_ids))
                )
                session.execute(
                    delete(StaffUser).where(StaffUser.id.in_(staff_ids))
                )
            session.commit()
        remaining_objects = store.list_keys(prefix=f"task-051/{marker}/")
        remaining_derivatives = {
            key
            for prefix in derivative_prefixes
            for key in store.list_keys(prefix=prefix)
        }
        if remaining_objects or remaining_derivatives:
            fail("cleanup_task_objects_remaining")
        with Session(engine) as session:
            remaining = {
                "photos": session.scalar(
                    select(Photo.id).where(
                        Photo.original_object_key.like(f"task-051/{marker}/%")
                    )
                ),
                "attempts": session.scalar(
                    select(PromoAttempt.id).where(
                        PromoAttempt.client_release == f"task-051-{marker}"
                    )
                ),
                "clients": session.scalar(
                    select(DisplayClient.id).where(DisplayClient.name == client_name)
                ),
                "staff": session.scalar(
                    select(StaffUser.id).where(StaffUser.username == username)
                ),
            }
        if any(value is not None for value in remaining.values()):
            fail("cleanup_rows_remaining")
        print("cleanup=PASS task_owned_rows=0 task_owned_objects=0")
    finally:
        engine.dispose()


def main() -> None:
    if len(sys.argv) < 2:
        fail("action_missing")
    action = sys.argv[1]
    if action == "readiness":
        readiness()
    elif action == "setup":
        setup(sys.argv[2])
    elif action == "backend-probe":
        backend_probe(sys.argv[2], sys.argv[3], os.environ["TASK051_STAFF_PASSWORD"])
    elif action == "wait-photo":
        wait_photo(sys.argv[2])
    elif action == "realtime-probe":
        realtime_probe(sys.argv[2])
    elif action == "cleanup":
        cleanup(sys.argv[2])
    else:
        fail("unknown_action")


try:
    main()
except SystemExit:
    raise
except Exception as error:
    raise SystemExit(f"FAIL probe_error={type(error).__name__}") from None
PY
}

cleanup() {
  local main_status=$?
  local cleanup_status=0
  trap - EXIT
  set +e
  if [[ -n "${browser_pid}" ]]; then
    if ! kill -- "-${browser_pid}" 2>/dev/null && ! kill "${browser_pid}" 2>/dev/null; then
      if kill -0 "${browser_pid}" 2>/dev/null; then
        cleanup_status=1
      fi
    fi
    wait "${browser_pid}" 2>/dev/null || true
    if kill -0 "${browser_pid}" 2>/dev/null; then
      cleanup_status=1
    fi
    browser_pid=""
  fi
  if [[ -n "${browser_profile}" && "${browser_profile}" == /tmp/face-moment-task-051.* ]]; then
    if ! rm -rf -- "${browser_profile}"; then
      cleanup_status=1
    fi
    browser_profile=""
  fi
  if [[ -n "${marker}" ]]; then
    local cleanup_output
    cleanup_output="$(run_probe cleanup "${marker}" 2>/dev/null)"
    local cleanup_probe_status=$?
    if [[ "${cleanup_probe_status}" -eq 0 ]]; then
      printf '%s\n' "${cleanup_output}"
    else
      echo "cleanup=FAIL"
      cleanup_status=1
    fi
  fi
  if [[ "${cleanup_status}" -ne 0 ]]; then
    echo "cleanup=FAIL"
    if [[ "${main_status}" -eq 0 ]]; then
      main_status=1
    fi
  fi
  exit "${main_status}"
}
trap cleanup EXIT

assert_no_display_baseline() {
  if ! command -v loginctl >/dev/null 2>&1; then
    echo "STOP no_display_baseline_unavailable=loginctl"
    return 1
  fi
  if ! command -v ps >/dev/null 2>&1; then
    echo "STOP no_display_baseline_unavailable=ps"
    return 1
  fi

  local sessions
  if ! sessions="$(loginctl list-sessions --no-legend 2>/dev/null)"; then
    echo "STOP no_display_baseline_unavailable=session_list"
    return 1
  fi
  while read -r session_id _; do
    [[ -n "${session_id}" ]] || continue
    local session_props session_type session_class session_state session_remote session_active
    if ! session_props="$(loginctl show-session "${session_id}" \
      -p Type -p Class -p State -p Remote -p Active 2>/dev/null)"; then
      echo "STOP no_display_baseline_unavailable=session_probe"
      return 1
    fi
    session_type="$(awk -F= '$1 == "Type" {print $2; exit}' <<< "${session_props}")"
    session_class="$(awk -F= '$1 == "Class" {print $2; exit}' <<< "${session_props}")"
    session_state="$(awk -F= '$1 == "State" {print $2; exit}' <<< "${session_props}")"
    session_remote="$(awk -F= '$1 == "Remote" {print $2; exit}' <<< "${session_props}")"
    session_active="$(awk -F= '$1 == "Active" {print $2; exit}' <<< "${session_props}")"
    if [[ "${session_class}" == "user" && "${session_state}" == "active" \
      && "${session_remote}" == "no" && "${session_active}" == "yes" \
      && ("${session_type}" == "wayland" || "${session_type}" == "x11") ]]; then
      echo "STOP display_login_present=graphical_session"
      return 1
    fi
  done <<< "${sessions}"

  local pid process_user process_name process_args
  while read -r pid process_user process_name process_args; do
    case "${process_name}" in
      chrome|chromium|google-chrome|chromium-browser)
        echo "STOP display_browser_present=chromium_process"
        return 1
        ;;
    esac
  done < <(ps -eo pid=,user=,comm=,args=)

  echo "no_display_baseline=PASS"
}

assert_no_display_baseline

run_probe readiness

fixture_spec="$(run_probe setup "${marker}")"
IFS=$'\t' read -r task_username task_password <<< "${fixture_spec}"
if [[ -z "${task_username}" || -z "${task_password}" ]]; then
  echo "FAIL disposable_fixture_setup_output"
  exit 1
fi

export TASK051_STAFF_PASSWORD="${task_password}"
run_probe backend-probe "${marker}" "${task_username}" \
  2>/dev/null
unset TASK051_STAFF_PASSWORD

run_probe wait-photo "${marker}"
run_probe realtime-probe "${marker}"

browser_bin="${TASK051_BROWSER_BIN:-}"
if [[ -z "${browser_bin}" ]]; then
  for candidate in /opt/google/chrome/chrome /usr/bin/google-chrome /usr/bin/chromium /usr/bin/chromium-browser; do
    if [[ -x "${candidate}" ]]; then
      browser_bin="${candidate}"
      break
    fi
  done
fi
if [[ -z "${browser_bin}" ]]; then
  echo "STOP disposable_display_session_browser_missing"
  exit 1
fi

browser_profile="$(mktemp -d -t face-moment-task-051.XXXXXX)"
setsid "${browser_bin}" \
  --headless=new \
  --disable-gpu \
  --no-first-run \
  --no-default-browser-check \
  "--user-data-dir=${browser_profile}" \
  "${origin}/" >/dev/null 2>&1 &
browser_pid=$!
sleep 3
if ! kill -0 "${browser_pid}" 2>/dev/null; then
  echo "STOP disposable_display_session_start_failed"
  exit 1
fi
echo "display_session=PASS started=disposable_local_browser"
run_probe readiness

kill -- "-${browser_pid}" 2>/dev/null || kill "${browser_pid}" 2>/dev/null || true
wait "${browser_pid}" 2>/dev/null || true
browser_pid=""
echo "display_session=PASS stopped=disposable_local_browser"
run_probe readiness
echo "recovery_check=PASS"
