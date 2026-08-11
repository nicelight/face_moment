# Technical-debt review — wave W6

## Checked scope

`TASK-013-T2-FT-001-W6` and `TASK-014-T2-FT-001-W6` only: PostgreSQL-backed
duplicate arbitration with request-owned loser cleanup, and the isolated
pre-commit crash/re-upload proof. The surface was resolved through the two
indexed task records, their durable execute/independent-verify evidence,
task-owned probes, and the actual inventory source plus focused tests. This is
not a repository-wide review.

## Evidence checked

- `.memory-bank/tasks/TASK-013-T2-FT-001-W6.task.json`: completed T2 scope,
  database-winner, redacted-outcome and loser-only cleanup constraints.
- `.tasks/TASK-013-T2-FT-001-W6/TASK-013-T2-FT-001-W6-S-EXECUTE-final-report-code-01.md`
  and `TASK-013-T2-FT-001-W6-S-VERIFY-final-report-docs-01.md`: a fresh
  packaged-image proof of sequential/concurrent one-winner arbitration,
  named-constraint filtering, loser-only idempotent cleanup and zero residue.
- `src/face_moment/inventory/admission.py:41-111`: the narrow admission branch
  catches only the named Photo uniqueness constraint after rollback, cleans the
  supplied candidate only, returns a redacted duplicate result, and leaves
  other integrity failures to propagate.
- `tests/inventory/test_duplicate_admission.py:114-213` and
  `.tasks/TASK-013-T2-FT-001-W6/TASK-013-T2-FT-001-W6-S-VERIFY-verifier-probe-code-01.py`:
  disposable sequential/concurrent projections, winner/pending/object counts,
  repeated cleanup and fixture cleanup.
- `.memory-bank/tasks/TASK-014-T2-FT-001-W6.task.json`: completed T2 scope
  limited to pre-commit failure, private non-authoritative orphan and ordinary
  re-upload; recovery machinery is explicitly excluded.
- `.tasks/TASK-014-T2-FT-001-W6/TASK-014-T2-FT-001-W6-S-EXECUTE-final-report-code-01.md`
  and `TASK-014-T2-FT-001-W6-S-VERIFY-final-report-docs-01.md`: fresh
  packaged-image proof of zero committed rows after injection, a private
  orphan, one ordinary complete re-upload and zero task-owned residue.
- `src/face_moment/inventory/admission.py:50-81,105-106` and
  `tests/inventory/test_crash_recovery.py:23-166`: one pre-commit test seam,
  isolated fault injection, database/object assertions, a fresh request-owned
  re-upload and owned cleanup.
- `.tasks/TASK-014-T2-FT-001-W6/TASK-014-T2-FT-001-W6-S-VERIFY-probe-code-01.py`:
  verifier-owned disposable PostgreSQL/MinIO topology and no media-route
  observation.

## Confirmed material findings

None.

## Assessment and uncertainty

The completed W6 change remains within two deliberately separate, small
mechanisms: an inventory admission wrapper for the exact PostgreSQL duplicate
constraint, and a test-only pre-commit fault seam. The evidence shows neither
cross-slice recovery machinery nor a new lifecycle, lock, queue, distributed
transaction, public identity disclosure, or non-owned object cleanup. The
focused tests and fresh verification probes cover the material coupling and
reliability risks on this surface.

This advisory review did not independently rerun packaged-image gates; it
relied on the durable fresh Reviewer evidence and reproducible task probes. No
contrary evidence was found, so that limitation does not admit a debt finding.

## Smallest remediation direction

None; no material finding was admitted.
