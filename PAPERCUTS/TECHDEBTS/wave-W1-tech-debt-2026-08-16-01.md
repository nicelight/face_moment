# Technical-debt review — wave W1

## Result

No material technical debt was confirmed in the checked TASK-064/TASK-065
change surface. This advisory report does not change queue state or the
environment blockers recorded by the scheduler.

## Checked scope

- TASK-064 managed key-only SSH source policy and read-only checker:
  `deploy/ssh/sshd_config.d/50-facemoment-key-only.conf` and
  `scripts/check-ssh-policy.sh`;
- TASK-065 source-managed private topology checker:
  `scripts/check-private-topology.sh`, `compose.yaml`, and
  `deploy/Caddyfile`;
- the indexed task records, execution handoffs, independent verification
  reports, and current W1 Memory Bank reconciliation.

TASK-064's missing host `sshd`, TASK-065's pre-existing native PostgreSQL
listener, and the missing outside observer are environment/ownership evidence
blockers, not admitted source technical debt. No internal port was published,
no SSH daemon/account/key was changed, and no credentials were inspected.

## Evidence checked

- `.memory-bank/tasks/TASK-064-T3-FT-003-W1.task.json` and
  `.memory-bank/tasks/TASK-065-T3-FT-003-W1.task.json`.
- TASK-064 independent verification:
  `.tasks/TASK-064-T3-FT-003-W1/TASK-064-T3-FT-003-W1-S-VERIFY-final-report-docs-01.md`.
- TASK-065 independent verification:
  `.tasks/TASK-065-T3-FT-003-W1/TASK-065-T3-FT-003-W1-S-VERIFY-final-report-docs-01.md`.
- `node scripts/mb-lint.mjs`, `node scripts/mb-doctor.mjs --strict`, and
  `git diff --check` all pass; doctor reports only existing advisory warnings
  plus the declared blocked dependency.

## Confirmed findings

## Smallest remediation direction

None; no material finding was admitted. The exact remediation is environmental:
provide a pilot-host-capable SSH/runtime context and authorized outside
observer, then resume the two blocked tasks through their recorded routes.

## Uncertainty

This review did not install `sshd`, mutate the native PostgreSQL service,
publish internal ports, or perform a repository-wide architecture audit. It
does not decide ownership of the pre-existing host listener or authorize
changes to it.
