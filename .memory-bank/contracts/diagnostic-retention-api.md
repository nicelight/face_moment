---
description: Owner-ordered diagnostic retention command and latest-result staff contract.
status: active
last_updated: 2026-09-01
source_of_truth:
  - .memory-bank/contracts/diagnostic-retention-api.md
---
# Diagnostic Retention API

## Scope And Ownership

`promo` owns one project-wide latest retention result and the cleanup command.
It calls `diagnostics` through
[Boundary Map — Retention cleanup](boundary-map.md#retention-cleanup), then
deletes only promo-owned eligible Attempts/sessions. Each provider deletes only
its own rows/objects. No cross-owner cascade, cleanup history, generic jobs
table or reliable queue is introduced.

The fixed policy cutoffs are 30 days for structured server events and 90 days
for ordinary Attempts/evidence, evaluated in UTC. FT-007 supplies the ordinary
Attempt/evidence command and result; FT-009 extends the same diagnostics owner
boundary with server-event deletion without changing the public result shape.

## Idempotent Cleanup Command

The project-native entrypoint is:

```text
python -m face_moment.entrypoints.retention_cleanup
```

One invocation first acquires one project-scoped non-blocking PostgreSQL
advisory lock and holds it through terminal result recording. It then:

1. after acquiring the lock, converts any orphaned prior `running` result to
   `interrupted`; an active run cannot be orphaned while it holds the same lock;
2. atomically records the promo-owned latest result as `running`, with fixed
   cutoffs and a new run UUID;
3. asks diagnostics to delete its structured server events strictly before the
   30-day cutoff, including uncorrelated rows;
4. selects promo-owned core Attempts strictly before the 90-day cutoff and
   passes those UUIDs to diagnostics;
5. asks diagnostics to expire its owned Attempt evidence and confirm each
   supplied UUID, including an explicit no-op confirmation when no evidence row
   exists;
6. deletes only the confirmed promo-owned Attempts and owner-local expired
   sessions;
7. records `succeeded` with confirmed counts, or a sanitized `failed` result.

If another invocation cannot acquire the advisory lock, it exits with code `2`
and leaves the active run and latest-result row unchanged. A completed cleanup
exits `0`; a cleanup that records `failed` exits `1`. The lock is released when
the database session ends, so a process crash cannot leave a false active lock.

The one latest-result row is observable state, not cleanup history or a job
lifecycle. The command is safe for the source-managed external daily timer in
[Diagnostic Retention Runbook](../runbooks/diagnostic-retention.md). It adds no
internal scheduler, priority, preemption or production credential-management
path.

## Latest Result Persistence

`promo` stores one singleton row in `face_moment.retention_cleanup_latest`:

| Field | Contract |
|---|---|
| `singleton_key` | Fixed primary key ensuring one latest result and no history. |
| `run_id` | UUID of the latest invocation. |
| `status` | `running \| succeeded \| failed \| interrupted`. |
| `started_at`, `finished_at` | UTC server timestamps; finish is null only while running. |
| `technical_logs_before`, `attempts_and_evidence_before` | Fixed applied UTC cutoffs. |
| deletion/preservation counts | Non-negative confirmed counts for core Attempts, ordinary evidence, technical logs, private artifacts and promoted subsets. |
| `error` | Nullable bounded sanitized failure text; never a credential, payload or traceback. |

The next-linear migration follows every earlier planned migration dependency.
All stateful proof uses a disposable database and private object prefix with
known initial state, safe rerun and owned cleanup.

## Staff Read Contract

- HTML: `GET /staff/diagnostics-retention`.
- JSON: `GET /api/diagnostics/retention`.
- Authentication: the existing staff session.
- Authorization: active `operator` and `developer`; photographer receives
  `403`, missing/invalid session receives `401`.
- Both responses use `Cache-Control: no-store`.

Before the first command, JSON returns:

```json
{
  "schema_version": 1,
  "status": "never_run",
  "result": null
}
```

After an invocation it returns `status: "available"` and exactly one result
with this shape:

```json
{
  "schema_version": 1,
  "status": "available",
  "result": {
    "run_id": "cleanup-run-uuid",
    "state": "succeeded",
    "started_at": "2026-08-25T00:00:00Z",
    "finished_at": "2026-08-25T00:00:01Z",
    "cutoffs": {
      "technical_logs_before": "2026-07-26T00:00:00Z",
      "attempts_and_evidence_before": "2026-05-27T00:00:00Z"
    },
    "counts": {
      "core_attempts_deleted": 3,
      "ordinary_evidence_expired": 3,
      "technical_logs_deleted": 0,
      "private_artifacts_deleted": 0,
      "promoted_subsets_preserved": 1
    },
    "error": null
  }
}
```

`state` is `running|succeeded|failed|interrupted`; counts are non-negative
integers. While running, `finished_at` is null. `error` is non-null only for
`failed|interrupted`. `technical_logs_deleted` is the diagnostics-confirmed
count of structured server events newly deleted by that successful invocation;
zero remains valid when no row crossed the cutoff or a prior partial run already
converged. The HTML page renders the same fields and never exposes raw object
identities, participant data or an execution trigger.

## Structured Server-Event Extension

The cleanup command supplies `technical_logs_before` to the diagnostics owner
independently of the 90-day Attempt candidate UUIDs. Diagnostics deletes
`face_moment.server_events` rows with `occurred_at` strictly before that cutoff,
including rows without Attempt/correlation identity, and returns the newly
deleted count. Equal-cutoff and newer rows remain.

This extension follows the
[Structured Server Events retention boundary](../domains/structured-server-events.md#retention-boundary).
It adds no new command, timer, result field, cleanup history, event tombstone or
cross-owner delete. An owner failure is sanitized and the command records
`failed`; a rerun converges without restoring events or fabricating counts.

## Failure And Rerun Rules

- A diagnostics failure prevents promo deletion for UUIDs not confirmed
  eligible and leaves a visible `failed` result.
- A supplied UUID with no diagnostics row is confirmed as an owner-local no-op
  and may be deleted by promo; absence MUST NOT retain the old core Attempt.
- A concurrent invocation that observes the advisory lock exits `2` without
  replacing the active run identity, cutoffs, timestamps or counts.
- Interruption never fabricates success counts. Rerun reuses owner idempotency
  and may finish already-expired work without restoring it.
- A promoted subset is counted as preserved and is never deleted by ordinary
  cleanup.
- Structured server-event deletion is diagnostics-owned, applies independently
  of Attempt candidates and includes uncorrelated rows; promo records only the
  confirmed count and never deletes those rows directly.
- Missing private objects are an idempotent success only after their owning
  database state is already inaccessible.
- Staff reads never start cleanup; no CSRF-protected mutation endpoint is part
  of this contract.

## Verification Targets

- Disposable database/object fixtures prove both fixed cutoffs, owner order,
  correlated and uncorrelated server-event deletion, successful deletion of an
  old Attempt with no evidence row, promoted preservation, failure isolation,
  orphaned-running interruption, overlapping-invocation exit `2`, safe rerun
  and exactly one latest-result row.
- Before/after reads prove operator/developer visibility, photographer and
  unauthenticated denial, `no-store` responses and sanitized errors.
- Ownership tracing proves promo never writes diagnostics rows, diagnostics
  never deletes promo rows, and Photo hard purge cannot cascade into either.
- Source/runtime scans prove one callable command, one external daily timer and
  no internal scheduler, cleanup history, jobs subsystem, production credential
  mutation or raw identifier leakage.
