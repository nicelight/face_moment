---
description: Resolved exhausted-retry history for TASK-090 realtime event emission.
status: archived
last_updated: 2026-09-02
source_of_truth:
  - .memory-bank/bugs/task-090-realtime-event-post-commit-sql.md
---
# TASK-090 Realtime Event Post-Commit SQL

## Failure

`TASK-090-T3-FT-009-W1` exhausted its initial attempt plus two retries while
proving `FT-009-AC-002`. The final independent verifier reproduced a material
participant-path violation: realtime admission commits the owner
`PromoAttempt`, then event assembly reads the commit-expired ORM row and waits
on an implicit PostgreSQL refresh before the exact event can enqueue.

The QR Attempt-3 correction is preserved evidence: its immutable pre-commit
snapshot completed and enqueued without post-commit SQL, produced no duplicate
on repeated scan, emitted nothing after commit failure, and preserved the exact
expired outcome and correlation pair. Any repair must retain those passing
constraints.

## Evidence

- [Canonical verification](../../.protocols/TASK-090-T3-FT-009-W1/verification.md)
- [Final realtime PostgreSQL latch](../../.tasks/TASK-090-T3-FT-009-W1/TASK-090-T3-FT-009-W1-S-VERIFY-targeted-probe-03.md)
- [Final verification report](../../.tasks/TASK-090-T3-FT-009-W1/TASK-090-T3-FT-009-W1-S-VERIFY-final-report-docs-03.md)
- [Authoritative failed task](../tasks/TASK-090-T3-FT-009-W1.task.json)

## Resolution

The failed task identity remains immutable. Its unfinished acceptance result was
replanned as `TASK-094-T3-FT-009-W1`, which removed the implicit realtime ORM
refresh and hidden QR event state without imposing a global SQL prohibition.

- [Replacement task](../tasks/TASK-094-T3-FT-009-W1.task.json)
- [Functional PASS](../../.protocols/TASK-094-T3-FT-009-W1/verification.md)
- [Semantic pass](../../.protocols/TASK-094-T3-FT-009-W1/red-verification.md)

The accepted resolution uses pre-commit primitives for realtime and one
explicit bounded Promo-owned QR correlation query after commit. TASK-090 stays
`failed` as historical evidence and is not a current blocker.
