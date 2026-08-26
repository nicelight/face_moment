---
description: Pilot-host activation and observation of the daily diagnostic retention command.
status: active
last_updated: 2026-08-25
source_of_truth:
  - .memory-bank/runbooks/diagnostic-retention.md
---
# Diagnostic Retention Runbook

## Scope And Owner

The pilot-host operator owns installation and activation of the external daily
timer after the FT-007 cleanup command is deployed. Application cleanup and
latest-result semantics remain owned by the
[Diagnostic Retention API](../contracts/diagnostic-retention-api.md); this
runbook adds no internal scheduler, jobs table, cleanup history or credential
store.

Source-managed units live at:

- `deploy/systemd/system/face-moment-retention-cleanup.service`;
- `deploy/systemd/system/face-moment-retention-cleanup.timer`.

The host supplies the deployed Compose project directory through the
root-readable `/etc/face-moment/retention-cleanup.env` using exactly:

```text
FACE_MOMENT_PROJECT_DIR=/absolute/path/to/deployed/face-moment
```

The service MUST invoke exactly:

```text
/usr/bin/docker compose --project-directory ${FACE_MOMENT_PROJECT_DIR} run --rm backend python -m face_moment.entrypoints.retention_cleanup
```

It MUST NOT embed database/object-store credentials.

## Installation And Activation

1. Confirm the deployed image contains the reviewed FT-007 command and the
   database is at the required migration revision.
2. Install the two source-managed units without editing their command.
3. Create the root-readable environment file containing only the absolute
   Compose project path required by the unit.
4. run `systemd-analyze verify` for both installed units;
5. enable and start `face-moment-retention-cleanup.timer`.

The timer MUST use `OnCalendar=daily` and `Persistent=true`, so a missed daily
run is invoked after the host becomes available. It MUST NOT run more than one
cleanup concurrently; the command's PostgreSQL advisory lock is the final
overlap guard.

## Verification And Recovery

- Record redacted `systemctl is-enabled`, `systemctl is-active` and
  `systemctl list-timers` evidence showing the daily next trigger.
- Trigger the one-shot service once after installation and confirm exit `0`
  plus a matching authorized latest-result read. Use task-owned disposable
  records for pre-production proof; production activation requires explicit
  pilot-host authorization and must not manufacture participant data.
- Exit `2` means another cleanup is active: do not restart or overwrite it;
  observe the unchanged latest result and wait for the next timer invocation.
- Exit `1` means the command recorded `failed`: inspect only the sanitized
  latest result, correct the external dependency, then invoke the same one-shot
  command again. Do not edit cleanup rows manually.
- After a host/process interruption, the next lock-owning invocation marks the
  orphaned prior result `interrupted` and safely starts a fresh run.

## Success Conditions

- the installed units match the source-managed definitions;
- the timer is enabled and active with a daily schedule and persistent catch-up;
- the service invokes only the accepted cleanup entrypoint through the deployed
  Compose project;
- one authorized latest result becomes observable without exposing credentials,
  raw object identities, participant payloads or tracebacks.
