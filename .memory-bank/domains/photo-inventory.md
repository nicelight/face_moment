---
description: Canonical Photo visibility, recent-statistics and singleton fixed-snapshot hard-purge persistence specification.
status: active
last_updated: 2026-09-04
source_of_truth:
  - .memory-bank/domains/photo-inventory.md
---
# Photo Inventory

## Scope And Ownership

`inventory` owns Photo selection, `is_active`, recent-statistics assembly, the
single durable global purge run and purge orchestration. It reads processing
state through the accepted projection and commands processing-owned cleanup
through its public boundary. It MUST NOT directly mutate processing, Promo,
Attempt or diagnostics-owned state.

The exact staff transport is [Photo Inventory API](../contracts/photo-inventory-api.md).
The canonical lifecycle remains [Photo Inventory Visibility](../states/lifecycle-map.md#photo-inventory-visibility).

## Visibility And Selection

The existing required `Photo.is_active` boolean is the only visibility field.
`true` is active and `false` is soft-deleted. No deletion timestamp, reason,
actor history, tombstone or per-photo purge field is added.

Selection filters the persisted `spa_id`, authoritative `visit_date` and
effective `captured_at`. Photographer ownership uses immutable `uploader_id`;
operator/developer access uses the existing accessible one-СПА scope. A
visibility transition locks the Photo row, authorizes inside `inventory` and
changes only `is_active`. Restore is rejected when the Photo UUID belongs to
the current confirmed non-terminal purge snapshot.

Search, new result formation, worker claims and recent counters MUST read only
active Photos. Existing issued sessions retain their stored IDs and may read
soft-deleted media. Restore exposes preserved data and timestamps without new
processing work.

## Recent Statistics Projection

One database observation time anchors the `1`, `5` and `60` minute windows.
Each query joins an active Photo to exactly its immutable
`admission_pipeline_revision_id` state:

- `new`: `accepted_at` is inside the window;
- `unprocessed`: `accepted_at` is inside the window and current status is
  `pending|processing`;
- `processed`: status is `ready|no_faces` and `status_changed_at` is inside;
- `failed`: status is `failed` and `status_changed_at` is inside.

The query is a direct aggregate. It stores no counter, bucket, refresh time,
materialized view or metric event.

## Singleton Hard-Purge Persistence

One next-linear migration adds only `face_moment.inventory_hard_purge_run`, a
well-known singleton row that may be absent before first confirmation:

| Field | Contract |
|---|---|
| `singleton_id` | Integer primary key fixed to `1`. |
| `run_id` | UUID identifying the current or most recently completed run. |
| `state` | Exactly `confirmed_waiting`, `running` or `completed`. |
| `target_photo_ids` | Required UUID array, sorted once at confirmation and immutable for that run. |
| `completed_count` | Non-negative prefix length not greater than the target-array length. |
| `confirmed_at` | Required server timestamp. |
| `started_at` | Nullable until work starts. |
| `completed_at` | Set only with `completed`. |

This row is not a jobs table or history. A new confirmation may replace only a
completed row. It atomically snapshots every currently inactive Photo UUID;
later soft deletes are never appended. `total` is the array length and progress
is `completed_count/total`, so no duplicate total field is stored.

The next target is the UUID at the persisted completed prefix. A successful
step deletes all owner-approved media/rows for that target and increments the
prefix in the same database transaction that removes the Photo. Missing object
deletion is idempotent. A crash before the database commit leaves the same
target current; a crash after commit exposes the next prefix. No lease, target
row, retry counter, error history or generic scheduler is introduced.

## Purge Orchestration

The singleton `BackgroundPhotoWorker` checks the inventory purge boundary
before claiming ordinary Photo work. The flow is:

1. If no non-terminal run exists, continue ordinary worker behavior.
2. If another worker operation is active, leave the run
   `confirmed_waiting`; uploads may finish but no operation is preempted.
3. Once processing reports idle, ask its public boundary to enter
   `hard_purge`, transition the run to `running`, and process its fixed targets
   sequentially.
4. For one target, collect the owner-approved original and processing-owned
   derivative keys; idempotently delete private objects; in one short
   transaction call the processing cleanup boundary, delete the inventory
   Photo and advance `completed_count`.
5. At the final prefix, set the run `completed` and ask processing to return
   its runtime operation to `idle`.

On startup, stale worker operation state follows the existing recovery path.
The non-terminal inventory row remains authoritative, so the next worker tick
re-enters `hard_purge` and resumes the same target prefix. A confirmed run has
precedence over new ordinary Photo claims after the current operation ends; it
never interrupts an already running Photo or Calibration operation.

`inventory` orchestrates this user-visible outcome. The worker entrypoint only
invokes that application boundary; it owns no purge rules. Processing deletes
only its own rows/derivatives through
[Inventory Purge Cleanup Boundary](photo-processing.md#inventory-purge-cleanup-boundary).

## Retained Foreign State And Errors

Photo deletion uses no ownership-crossing cascade. Promo result/session arrays,
core Attempts, diagnostic evidence and promoted Calibration input remain
unchanged. Their reads treat missing hard-purged media as unavailable; issued
session identity and `N` stay historical.

An object-store or database failure leaves the run non-terminal and observable;
the same step is safely rerunnable. Execution MUST NOT skip a live target,
change the snapshot, mark false progress, delete foreign-owned state or return
the worker to ordinary claims before terminal completion.

## Migration And Verification Targets

- The migration uses the execution-time linear Alembic predecessor; isolated
  upgrade/downgrade/re-upgrade proves only this singleton shape and preserves
  existing Photo/processing/Promo/Attempt/evidence rows.
- Controlled database tests prove role selection, idempotent visibility,
  restore-all exclusion, immutable snapshots, late soft-delete exclusion and
  direct counter oracles at every window boundary.
- Disposable PostgreSQL/MinIO tests interrupt before and after a target commit,
  restart backend/worker and prove complete convergence with no duplicate
  progress or foreign deletion.
- Architecture inspection proves one inventory orchestration owner, the exact
  `inventory -> processing` edge, one existing worker, one singleton run row
  and absence of jobs/per-photo purge/realtime-statistics machinery.
