---
description: FT-012 verification contract for role visibility, rolling counters and resumable ownership-safe hard purge.
status: active
last_updated: 2026-09-04
source_of_truth:
  - .memory-bank/testing/photo-inventory.md
---
# Photo Inventory Verification

## Test State And Isolation

All destructive proof uses a uniquely named disposable PostgreSQL database and
private test object prefix through the existing local infrastructure. Fixtures
record their initial rows/objects, support safe rerun and remove only their own
state. No production worker, operator/default database, bucket contents or
external backup is an authorized probe target.

Use one fixed server clock, three staff roles, Photos covering all
`captured_at` fallbacks, each admission-lineage processing status, one issued
Promo session and linked core Attempt/diagnostic evidence. Seed a second
pipeline state only to prove it neither duplicates counters nor replaces the
admission state.

## Role And Visibility Matrix

For list, soft-delete and restore, cover photographer-owned, another
photographer's and operator/developer-accessible Photos across matching and
non-matching СПА/date/half-open capture ranges. Compare the exact API results,
Photo row, media, faces, pipeline state, compatible search, recent counters and
issued-session read before delete, while inactive and after restore.

Decisive success requires only `is_active` to change: new search and counters
exclude the inactive Photo, issued media remains loadable, and restore exposes
the original preserved state/timestamps without a new upload or processing
claim.

## Recent-Counter Oracle

For one shared `observed_at`, independently calculate every 1/5/60-minute
`new`, `unprocessed`, `processed` and `failed` result. Include exact lower and
upper timestamps, just-outside values, soft-deleted and restored Photos, every
status, and a later non-admission revision row. Compare the full response and
repeat after the UI's five-second poll interval.

The proof fails if one Photo contributes twice, a deleted Photo contributes,
restore changes a timestamp, windows use different clocks, or implementation
adds stored counters, a materialized metric store, WebSocket or SSE.

## Processing Cleanup Boundary

For one inactive Photo with multiple processing states, faces, preview and
thumbnail objects, call only the processing public cleanup boundary. Assert all
processing-owned rows/objects disappear, repeated cleanup succeeds, and the
inventory Photo/original, Promo session/result, core Attempt and diagnostic
evidence remain unchanged. Inject failure before database commit and prove the
same call converges on rerun.

## Fixed Snapshot, Restart And Retention Matrix

Confirm a snapshot with two inactive Photos, then soft-delete a third. Prove
individual restore and restore-all reject/exclude only the first two while the
third restores normally. Run once from idle and once while Photo processing or
Calibration occupies the shared worker; inspect the exact waiting message,
non-preemption, snapshot immutability and completed/total progress.

Interrupt after object cleanup but before the first target commit, then after a
later committed target. Restart backend/worker and require the same `run_id`,
target array and next prefix to finish. Concurrent upload is allowed to commit
ordinary pending work but is never added to the snapshot or interrupted.

After completion, assert every snapshot Photo, original, preview, thumbnail,
face and pipeline row is absent. The issued Promo session/result, core Attempt,
diagnostic evidence and late soft-delete remain; phone/session reads skip only
missing media and preserve session identity and issued `N`.

## Acceptance Evidence Map

| Feature criterion | Required proof |
|---|---|
| `FT-012-AC-001` | Role/range matrix covers all capture-time sources and ownership/СПА authorization. |
| `FT-012-AC-002` | Before/deleted/restored matrix proves preserved state, new-search/counter exclusion and issued-session continuity. |
| `FT-012-AC-003` | Fixed snapshot plus late soft delete proves individual/global restore exclusion only until completion. |
| `FT-012-AC-004` | Idle/busy worker scenarios prove confirmation, waiting copy, no preemption and exact progress replacement. |
| `FT-012-AC-005` | Two crash points plus restart prove idempotent convergence, complete owned deletion and foreign-state retention. |
| `FT-012-AC-006` | Independent three-window SQL oracle proves exact categories, boundaries, visibility and polling; schema/runtime inspection proves no stored or realtime counter mechanism. |
| `FT-012-AC-007` | Schema/runtime inspection proves one worker and singleton run with no jobs or per-photo purge state. |

Project-native typecheck, focused tests, task `/verify` and T3 `/red-verify`
remain governed by [Testing & Verification](index.md) and tier policy.
