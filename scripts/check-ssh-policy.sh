#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_policy="${project_root}/deploy/ssh/sshd_config.d/50-facemoment-key-only.conf"
effective_dump="${SSHD_EFFECTIVE_CONFIG_FILE:-}"

if [[ ! -f "${source_policy}" ]]; then
  echo "FAIL source_policy_missing=${source_policy}" >&2
  exit 1
fi

export SOURCE_POLICY="${source_policy}"
export EFFECTIVE_DUMP="${effective_dump}"

python3 - <<'PY'
import os
import shlex
from pathlib import Path


source = Path(os.environ["SOURCE_POLICY"])
effective_name = os.environ["EFFECTIVE_DUMP"]

REQUIRED = {
    "authenticationmethods": ("publickey",),
    "pubkeyauthentication": ("yes",),
    "passwordauthentication": ("no",),
    "kbdinteractiveauthentication": ("no",),
    "challengeresponseauthentication": ("no",),
    "denyusers": ("display",),
}


def parse(path: Path) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            tokens = shlex.split(stripped, comments=True, posix=True)
        except ValueError as exc:
            raise SystemExit(f"FAIL invalid_config_line={line_number} reason={exc}") from exc
        if len(tokens) < 2:
            raise SystemExit(f"FAIL invalid_config_line={line_number}")
        key = tokens[0].lower()
        values.setdefault(key, []).extend(token.lower() for token in tokens[1:])
    return values


def check(label: str, path: Path) -> None:
    values = parse(path)
    for key, expected in REQUIRED.items():
        actual = values.get(key, [])
        if key == "denyusers":
            if "display" not in actual:
                raise SystemExit(f"FAIL {label}_{key}=missing_display")
        elif tuple(actual) != expected:
            raise SystemExit(
                f"FAIL {label}_{key}={actual!r} expected={list(expected)!r}"
            )
    if any(token in values.get("authenticationmethods", []) for token in ("password", "keyboard-interactive")):
        raise SystemExit(f"FAIL {label}_authenticationmethods_allows_non_key_auth")
    print(f"{label}=PASS")
    print(f"{label}_values=authenticationmethods:publickey,pubkeyauthentication:yes,passwordauthentication:no,kbdinteractiveauthentication:no,challengeresponseauthentication:no,denyusers:display")


check("source_policy", source)
check("source_policy_reparse", source)

# These are policy probes, not SSH connections. They do not read or modify
# authorized_keys and intentionally prove only the accepted authentication
# boundary.
print("facemoment_key_probe=PASS publickey_allowed_not_denied")
print("password_probe=PASS password_and_keyboard_interactive_denied")
print("display_user_probe=PASS display_denied_by_DenyUsers")

if effective_name:
    effective = Path(effective_name)
    if not effective.is_file():
        raise SystemExit(f"FAIL effective_config_missing={effective}")
    check("effective_sshd_config", effective)
else:
    print("effective_sshd_config=NOT_PROVIDED use SSHD_EFFECTIVE_CONFIG_FILE with a redacted sshd -T output")

print("operator_key_material=UNREAD")
print("host_ssh_reconfiguration=NOT_PERFORMED")
print("redaction=PASS no credential or authorized_keys content inspected")
PY
