#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_policy="${project_root}/deploy/chromium/policies/managed/facemoment.json"
origin="${FACE_MOMENT_ORIGIN:-https://localhost:8443}"
effective_policy="${CHROME_EFFECTIVE_POLICY_FILE:-}"

if [[ ! -f "${source_policy}" ]]; then
  echo "FAIL source_policy_missing=${source_policy}" >&2
  exit 1
fi

if [[ -z "${effective_policy}" ]]; then
  for candidate in \
    /etc/opt/google/chrome/policies/managed/facemoment.json \
    /etc/opt/chrome/policies/managed/facemoment.json \
    /etc/chromium/policies/managed/facemoment.json; do
    if [[ -f "${candidate}" ]]; then
      effective_policy="${candidate}"
      break
    fi
  done
fi

export SOURCE_POLICY="${source_policy}"
export EFFECTIVE_POLICY="${effective_policy}"
export EXPECTED_ORIGIN="${origin}"

python3 - <<'PY'
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

source = Path(os.environ["SOURCE_POLICY"])
effective_name = os.environ["EFFECTIVE_POLICY"]
expected = os.environ["EXPECTED_ORIGIN"]


def read_policy(path: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8")
    lowered = raw.lower()
    for forbidden in ("token", "secret", "password", "bearer"):
        if forbidden in lowered:
            raise SystemExit(f"FAIL policy_contains_credential_marker={forbidden}")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise SystemExit(f"FAIL policy_not_object={path}")
    return value


def validate(label: str, path: Path) -> None:
    policy = read_policy(path)
    if set(policy) != {"LocalNetworkAccessAllowedForUrls"}:
        raise SystemExit(
            f"FAIL {label}_unexpected_policy_keys={sorted(policy)!r}"
        )
    values = policy.get("LocalNetworkAccessAllowedForUrls")
    if values != [expected]:
        raise SystemExit(
            f"FAIL {label}_allowlist={values!r} expected={[expected]!r}"
        )
    parsed = urlsplit(expected)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or any(marker in expected for marker in ("*", "[", "]", "?"))
    ):
        raise SystemExit("FAIL expected_origin_is_not_an_exact_https_origin")
    if any(value != expected for value in values):
        raise SystemExit(f"FAIL {label}_unrelated_origin_present")
    print(f"{label}=PASS origin={expected}")


validate("source_policy", source)
validate("source_policy_restart_reparse", source)

unlisted = "https://unlisted.invalid"
if unlisted == expected:
    raise SystemExit("FAIL unlisted_probe_collides_with_expected_origin")
print(f"listed_origin_probe=PASS origin={expected}")
print(f"unlisted_origin_probe=PASS origin={unlisted}")

if effective_name:
    effective = Path(effective_name)
    if not effective.is_file():
        raise SystemExit(f"FAIL effective_policy_missing={effective}")
    validate("effective_policy", effective)
else:
    print("effective_policy=NOT_PROVIDED use CHROME_EFFECTIVE_POLICY_FILE for chrome://policy export")

print("credential_scan=PASS")
PY
