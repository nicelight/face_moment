#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service_file="${project_root}/deploy/kiosk/spa-promo-client.service"
expected_origin="${FACE_MOMENT_ORIGIN:-https://localhost:8443}"
require_live="${KIOSK_REQUIRE_LIVE:-0}"

if [[ ! -f "${service_file}" ]]; then
  echo "FAIL source_service_missing=${service_file}" >&2
  exit 1
fi

export KIOSK_SERVICE_FILE="${service_file}"
export KIOSK_EXPECTED_ORIGIN="${expected_origin}"
export KIOSK_REQUIRE_LIVE="${require_live}"

python3 - <<'PY'
import os
import pwd
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


service_path = Path(os.environ["KIOSK_SERVICE_FILE"])
expected_origin = os.environ["KIOSK_EXPECTED_ORIGIN"]
require_live = os.environ["KIOSK_REQUIRE_LIVE"] == "1"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL {message}")


def exact_origin(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.path in ("", "/")
        and not parsed.query
        and not parsed.fragment
        and not any(marker in value for marker in ("*", "[", "]", "?"))
    )


if not exact_origin(expected_origin):
    fail("expected_origin_is_not_an_exact_https_origin")
expected_target = expected_origin.rstrip("/") + "/"

raw = service_path.read_text(encoding="utf-8")
lowered = raw.lower()
for forbidden in (
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-namespace-sandbox",
    "--disable-seccomp-filter-sandbox",
    "--disable-gpu-sandbox",
    "--disable-web-security",
    "--allow-running-insecure-content",
    "--ignore-certificate-errors",
    "--remote-debugging-port",
):
    if forbidden in lowered:
        fail(f"unsafe_browser_flag_present={forbidden}")
if any(marker in lowered for marker in ("token", "secret", "password", "bearer")):
    fail("service_contains_credential_marker")


def setting(name: str) -> list[str]:
    prefix = name + "="
    return [line[len(prefix):].strip() for line in raw.splitlines() if line.startswith(prefix)]


def require_one(name: str, expected: str) -> None:
    values = setting(name)
    if values != [expected]:
        fail(f"{name}_unexpected")


require_one("User", "display")
require_one("Group", "display")
require_one("NoNewPrivileges", "yes")
require_one("Restart", "always")
if setting("RestartSec"):
    fail("restart_timing_override_present")
if setting("EnvironmentFile") or setting("ExecStartPre") or setting("ExecStartPost"):
    fail("unapproved_service_hook_present")

exec_values = setting("ExecStart")
if len(exec_values) != 1:
    fail("execstart_missing_or_duplicated")
try:
    argv = shlex.split(exec_values[0])
except ValueError as exc:
    fail(f"execstart_not_parseable={type(exc).__name__}")

expected_profile = "/home/display/.config/face-moment/kiosk-profile"
expected_argv = [
    "/usr/bin/chromium",
    "--kiosk",
    "--no-first-run",
    "--no-default-browser-check",
    f"--user-data-dir={expected_profile}",
    expected_target,
]
if argv != expected_argv:
    fail("execstart_is_not_the_allow_listed_real_origin_command")
if any(argument.startswith("$") for argument in argv):
    fail("execstart_has_environment_or_argument_passthrough")

print("source_service=PASS path=deploy/kiosk/spa-promo-client.service")
print("service_identity=PASS user=display group=display")
print("sandbox_bypass_flags=PASS absent")
print("browser_flags=PASS allow_listed")
print(f"real_origin_target=PASS origin={expected_origin}")
print("restart_control=PASS automatic_browser_replacement_enabled")
print("deployment_secret_surface=PASS no_environment_file_or_credential_hook")


def run_capture(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


try:
    display_pw = pwd.getpwnam("display")
except KeyError:
    print("display_privilege_probe=NOT_AVAILABLE user=display_missing")
    display_available = False
else:
    display_available = True
    groups_result = run_capture(["id", "-Gn", "display"])
    if groups_result.returncode != 0:
        print("display_privilege_probe=NOT_AVAILABLE groups_unreadable")
    else:
        groups = groups_result.stdout.split()
        forbidden_groups = {"sudo", "docker", "wheel"}.intersection(groups)
        if forbidden_groups:
            fail("display_has_privileged_group")
        print(
            "display_privilege_probe=PASS "
            f"uid={display_pw.pw_uid} forbidden_groups=absent"
        )

    sudo_bin = shutil.which("sudo")
    if sudo_bin is None:
        print("display_sudo_probe=NOT_AVAILABLE sudo_command_missing")
    else:
        sudo_result = run_capture([sudo_bin, "-n", "-l", "-U", "display"])
        if sudo_result.returncode == 0:
            fail("display_sudo_policy_allows_listing")
        print("display_sudo_probe=PASS nonzero_without_policy_output")


ps_result = run_capture(["ps", "-eo", "pid=,user=,args="])
if ps_result.returncode != 0:
    print("runtime_process_probe=NOT_AVAILABLE ps_unreadable")
    process_state = "unavailable"
else:
    candidates: list[tuple[str, str, str]] = []
    for line in ps_result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        pid, user, args = parts
        if "chromium" in Path(args.split(None, 1)[0]).name.lower() and expected_target in args:
            candidates.append((pid, user, args))

    if not candidates:
        print("runtime_process_probe=NOT_AVAILABLE no_managed_chromium_process")
        process_state = "unavailable"
    elif any(user != "display" for _, user, _ in candidates):
        fail("real_origin_chromium_process_is_not_display")
    elif len(candidates) > 1:
        fail("multiple_real_origin_chromium_processes_present")
    else:
        pid, _, args = candidates[0]
        if any(flag in args for flag in (
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-namespace-sandbox",
            "--disable-seccomp-filter-sandbox",
            "--disable-gpu-sandbox",
        )):
            fail("runtime_sandbox_bypass_flag_present")
        status_path = Path(f"/proc/{pid}/status")
        no_new_privs = "unavailable"
        if status_path.is_file():
            status = status_path.read_text(encoding="utf-8", errors="replace")
            match = re.search(r"^NoNewPrivs:\s+(\d+)$", status, flags=re.MULTILINE)
            if match:
                no_new_privs = match.group(1)
        print(
            "runtime_process_probe=PASS "
            f"pid={pid} user=display origin={expected_origin} "
            f"sandbox_bypass_flags=absent no_new_privs={no_new_privs}"
        )
        process_state = "available"


curl = shutil.which("curl")
if curl is None:
    print("real_origin_probe=NOT_AVAILABLE curl_missing")
    origin_state = "unavailable"
else:
    origin_result = subprocess.run(
        [curl, "--insecure", "--silent", "--show-error", "--fail", "--head", "--max-time", "5", expected_target],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if origin_result.returncode == 0:
        print(f"real_origin_probe=PASS origin={expected_origin}")
        origin_state = "available"
    else:
        print(f"real_origin_probe=NOT_AVAILABLE origin={expected_origin}")
        origin_state = "unavailable"

if require_live and (not display_available or process_state != "available" or origin_state != "available"):
    fail("live_kiosk_probe_required_but_unavailable")

print("check=PASS read_only_no_profile_or_credential_contents_read")
PY
