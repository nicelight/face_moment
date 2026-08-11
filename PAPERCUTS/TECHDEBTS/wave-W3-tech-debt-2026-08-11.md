# Technical-debt review — wave W3

## Checked scope

- `TASK-005-T3-FT-001-W3` — password-reset/deactivation session revocation.
- `TASK-008-T2-FT-001-W3` — inventory-owned Photo identity persistence.
- `TASK-015-T3-FT-001-W3` — authenticated ingest-target context endpoint.

The surface was resolved from the three indexed task records, their execution
and independent verification evidence, and the actual changed source,
migration, deployment and test files. It is not a repository-wide review.

## Evidence checked

- `TASK-005`: `.memory-bank/tasks/TASK-005-T3-FT-001-W3.task.json`; execution
  attempt 2 and semantic reassessment reports; implementation at
  `src/face_moment/platform/auth/{cli,principals,sessions}.py`; regression
  probe at `tests/staff_access/test_credential_lifecycle.py`.
- `TASK-008`: `.memory-bank/tasks/TASK-008-T2-FT-001-W3.task.json`; execution
  and verification reports; `src/face_moment/inventory/photo_persistence.py`,
  `migrations/versions/0006_photo_identity_persistence.py`,
  `migrations/env.py`, and `tests/inventory/test_photo_persistence.py`.
- `TASK-015`: `.memory-bank/tasks/TASK-015-T3-FT-001-W3.task.json`; both
  verification attempts and semantic-pass report; implementation at
  `src/face_moment/{serving_control/ingest_target.py,inventory/ingest_targets.py,inventory/http.py,entrypoints/backend.py}`;
  edge configuration `deploy/Caddyfile`; packaging input `Dockerfile`; and
  `tests/inventory/test_ingest_targets_api.py`.
- All three task records contain a terminal closure supported by fresh
  packaged-image functional evidence; the T3 records additionally contain
  `semantic-pass` reassessments.

## Confirmed material findings

None.

## Assessment and uncertainty

No inspected item demonstrates a material repeated change cost, coupling,
regression risk, reliability issue, or maintenance burden that remains after
the accepted W3 corrections.

TASK-015 verification attempt 1 established a real packaged-test-input defect:
the API test reads `deploy/Caddyfile` while the backend image did not contain
it. The current `Dockerfile` copies that versioned file and verification
attempt 2 proved matching host/image hashes and a passing exact packaged gate.
The Compose edge still mounts the same versioned source file. This review found
no divergent configuration source or remaining failure mechanism, so it is not
admitted as technical debt.

`IngestTargetRepository.list_active_eligible_ingest_targets()` validates each
active target through the owner repository. The evidence contains neither
target-volume requirements nor a measured latency, failure, or operational
cost. That implementation shape alone is insufficient to establish material
debt.

## Smallest remediation direction

None; no material finding was admitted.
