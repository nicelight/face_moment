# Technical-debt review — wave W1

## Checked scope

Completed W1 work only: `TASK-003-T3-FT-001-W1`,
`TASK-006-T2-FT-001-W1`, `TASK-010-T2-FT-001-W1`, and
`TASK-011-T3-FT-001-W1`. This covers staff-principal provisioning, immutable
processing revisions, JPEG/time validation, and request-owned private candidate
staging. It does not assess subsequent waves or unrelated concurrent worktree
changes.

## Evidence checked

- Authoritative task records: `.memory-bank/tasks/TASK-003-T3-FT-001-W1.task.json`,
  `.memory-bank/tasks/TASK-006-T2-FT-001-W1.task.json`,
  `.memory-bank/tasks/TASK-010-T2-FT-001-W1.task.json`, and
  `.memory-bank/tasks/TASK-011-T3-FT-001-W1.task.json` (all `done`).
- Functional and semantic handoffs under `.tasks/TASK-003-T3-FT-001-W1/`,
  `.tasks/TASK-006-T2-FT-001-W1/`, `.tasks/TASK-010-T2-FT-001-W1/`, and
  `.tasks/TASK-011-T3-FT-001-W1/`; the relevant focused tests, type checks,
  migration probes, and T3 semantic reviews passed with no admitted findings.
- Actual change surface: `src/face_moment/platform/auth/principals.py`,
  `src/face_moment/platform/auth/cli.py`,
  `src/face_moment/processing/revisions.py:15-115`,
  `src/face_moment/inventory/validation.py:68-185`,
  `src/face_moment/inventory/candidate_staging.py:8-59`,
  `src/face_moment/infrastructure/object_store.py:36-76`, and migrations
  `0002_staff_users.py` and `0003_pipeline_revisions.py`.
- `git diff --check` over that surface completed with exit `0` and no output.
- Repository search confirms `PrivateObjectStore.list_keys` is presently used
  only by the task-scoped staging test; its one-page implementation is not a
  production enumeration path.

## Confirmed findings

None. The observed boundaries are small and owner-aligned: inventory depends on
the minimal object-store protocol, processing exposes an eligibility projection,
and the migrations retain a linear ownership-preserving schema path. No
observable debt mechanism with material repeated-change, coupling, reliability,
or regression impact was confirmed in the completed W1 surface.

## Correctness impact on closed-task claims

None found. The checked evidence and direct source inspection do not contradict
any closed W1 task claim.

## Uncertainty

This advisory review did not execute a repository-wide audit or judge future
consumer integrations; those are outside the explicit completed-W1 boundary.
