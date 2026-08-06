---
description: Promo-owned core Attempt, realtime result assembly and result-session persistence specification.
status: active
last_updated: 2026-08-06
source_of_truth:
  - .memory-bank/domains/promo-attempt.md
---
# Promo Attempt

## Scope And Owner

`promo` owns the core Attempt, its immutable admission snapshot, processing
outcome, result assembly, result session and display status. `processing`
returns selected-detection match sets through its application boundary;
`diagnostics` may attach best-effort detail but neither capability may directly
write the core Attempt or result-session tables.

## PostgreSQL Shape

The runtime persistence path is `face_moment.promo_attempts`, accessed only
through the `promo` repository. One sequential Alembic revision introduces the
table with:

| Field | Contract |
|---|---|
| `id` | Server-generated UUID primary key. |
| `spa_id` | Authoritative UUID from the authenticated display-client principal. |
| `client_attempt_id` | Required client UUID; unique together with `spa_id`. |
| `trigger_source` | `sensor \| test`. |
| `client_release`, `detector_id`, `model_version`, `jpeg_quality`, `camera_device_id` | Immutable admitted client/proposal context. |
| `reference_series_ready_at` | Client wall-clock correlation timestamp. |
| `local_detection_completed_ms`, `request_started_ms` | Non-negative client monotonic offsets. |
| `proposal_count` | Integer `0..20`. |
| `settings_revision`, `visit_date`, `pipeline_revision_id`, `pipeline_code`, `query_source`, `release_id` | Immutable serving snapshot copied before inference; `query_source` is `reference`. |
| `threshold`, `quality_settings`, `calibration_id` | Immutable applied search inputs; `calibration_id` is nullable. |
| `deadline_ms` | Positive immutable server deadline configured for this admitted Attempt. |
| `slot_decided_at`, `search_started_at`, `search_finished_at` | Nullable server stage timestamps sufficient to distinguish busy, active search and terminal search timing. |
| `processing_status` | `accepted \| searching \| result_issued \| no_success \| interrupted \| deadline \| internal_failure`. |
| `domain_outcome` | Nullable `result \| no_proposals \| busy \| deadline \| unacceptable_query \| insufficient_results \| interrupted`. |
| `display_status` | `not_applicable \| pending \| confirmed \| failed`; `unconfirmed` is derived on read and is not stored as scheduler work. |
| `created_at`, `updated_at` | Server timestamps. |

The migration MUST use the project-wide `face_moment` schema, shared
`Base/MetaData` and current linear Alembic stream. No database cascade may
delete the core Attempt with a Photo or diagnostic record.

## Admission And Transitions

- Transport/auth/validation/readiness rejection creates no row.
- The first admitted `(spa_id, client_attempt_id)` creates exactly one row with
  the immutable client and serving snapshot before inference or singleton-slot
  acquisition.
- `accepted -> searching` occurs only when the singleton slot is acquired.
- Terminal processing transitions are:
  `result_issued | no_success | interrupted | deadline | internal_failure`.
- `no_proposals`, `busy`, `unacceptable_query` and `insufficient_results` map to
  `no_success`; `result` maps to `result_issued`; `deadline` and `interrupted`
  map to the like-named processing states.
- A `result_issued` Attempt starts with `display_status=pending`; every other
  terminal processing outcome uses `not_applicable`. Display confirmation and
  later derived `unconfirmed` remain governed by the
  [lifecycle map](../states/lifecycle-map.md).
- Repeating a key reads the existing row/result. It MUST NOT overwrite the
  immutable snapshot, create another row or start inference twice.
- Realtime startup changes stale `accepted|searching` rows to `interrupted` and
  does not replay proposal bytes or search.

The core table does not require crop/media persistence, detailed evidence or a
reliable client-offline outbox. If later diagnostic work stores capture-derived
media, `diagnostics` owns that storage and retention.

## Singleton Runtime Orchestration

After the immutable core Attempt is committed, `promo` tries once to acquire
one process-local non-blocking realtime slot protecting the `processing`
reference-search boundary:

- failure records `slot_decided_at`, terminal `no_success`/`busy`, calls no
  inference/search and returns immediately without enqueueing a waiter;
- success records `slot_decided_at`, transitions `accepted -> searching`, sets
  `search_started_at` and owns the slot until its one processing call finishes
  or fails;
- one positive deployment-configured deadline starts at server admission. It is
  checked before and after every processing step. Once expired, `promo` records
  `deadline`, publishes no result/session and discards any late return;
- slot release occurs in owner cleanup after every terminal path. Only a fresh
  admitted request may acquire it later; a previous `busy` Attempt is never
  resumed.

Realtime startup first transitions every persisted `accepted|searching`
Attempt to `interrupted`, sets its terminal/search-finished timestamp and proves
that no result session exists, then opens readiness with a fresh empty runtime
slot. Proposal bytes and query work are not durable or replayed. The singleton
is not a database lock, waiter queue, lease, fencing token, scheduler or second
runtime lifecycle.

## Result Assembly

Assembly consumes the ordered selected-detection match sets from
[Realtime Reference Search](realtime-search.md). Before candidate reservation,
`promo` forms `session_result_photo_ids` as the complete unique union of every
threshold-valid `photo_id` returned for every processed selected detection.
One Photo matching several detections contributes once. This union is never
reduced by teaser diversity and its cardinality is issued as `N`.

For each selected detection in order:

1. exclude `photo_id` values already present in either global pool;
2. order its remaining valid matches by descending similarity and ascending
   `photo_id`;
3. choose the best match as the first diverse candidate;
4. repeatedly choose the Photo maximizing its minimum pHash Hamming distance
   to that detection's already selected diverse candidates, with descending
   similarity and ascending `photo_id` as deterministic ties, stopping at four
   or when the maximum distance is zero;
5. add those Photos to the global diverse pool, then add the best remaining
   similarity-ranked matches to the global fallback pool until that detection
   contributed at most four total pool entries.

After all detections, fallback fills a global diverse pool smaller than four.
If more than four are available, final farthest-first selection starts from the
highest-similarity Photo and uses the same distance/similarity/`photo_id`
tie-breaks. pHash only ranks threshold-valid Photos. The four teasers are
unique and are a subset of `session_result_photo_ids`.

Fewer than four unique valid Photos returns `insufficient_results` and creates
no result session. No tracking, identity clustering, group-coverage guarantee,
weak-match admission, replacement selection or `N` truncation is introduced.

## Result Session Shape

One successful Attempt creates one `face_moment.promo_sessions` row owned by
`promo`:

| Field | Contract |
|---|---|
| `id` | Server-generated UUID primary key and response `session_id`. |
| `attempt_id` | Required unique reference to the owning core Attempt; owner-local cascade is allowed. |
| `spa_id`, `visit_date` | Immutable values copied from the Attempt snapshot. |
| `session_result_photo_ids` | Ordered unique UUID array containing the complete valid union. |
| `teaser_photo_ids` | Ordered UUID array of exactly four unique union members. |
| `n` | Integer equal to the union cardinality and at least four. |
| `qr_ticket_hash_sha256` | Required unique digest of the opaque QR ticket; plaintext is not stored. |
| `qr_issued_at`, `qr_first_open_expires_at` | Server timestamps separated by the accepted 30-minute first-open interval. |
| `created_at` | Server timestamp. |

Photo IDs are durable historical references rather than ownership-crossing
foreign keys. Photo soft delete does not alter the row; later hard purge may
make media unavailable without changing the arrays or `N`.

The opaque ticket is deterministically regenerated for an idempotent terminal
response as URL-safe HMAC-SHA-256 over the persisted session identity and issue
time using one deployment QR-ticket secret; only its SHA-256 digest is stored.
The secret and ticket MUST NOT enter logs. Rotation/recovery machinery is not
part of FT-004. FT-006 owns ticket exchange, shared browser-access state,
participant reads and expiry enforcement.

Publishing a result inserts this row and transitions its Attempt to
`processing_status=result_issued`, `domain_outcome=result` and
`display_status=pending` in one `promo` transaction. Any failure publishes
neither half. A terminal idempotent repeat reconstructs the exact accepted API
response from persisted session data without rerunning search.

## Edge Cases And Errors

- Failure to obtain a complete serving snapshot prevents inference and produces
  the applicable admitted non-success or pre-admission readiness response from
  the API contract; it MUST NOT silently use client СПА/date/configuration.
- A technical failure after row creation records `internal_failure` before the
  endpoint returns `5xx` when the transaction can still complete safely.
- A failed write prevents downstream inference. Detailed evidence failure does
  not roll back an already valid core Attempt outcome.
- A deadline, restart or fewer-than-four result creates no session and cannot
  publish a late result after the Attempt is terminal.
- Migration downgrade removes only this feature revision in an isolated test;
  it MUST NOT introduce another migration stream or cross-owner cascade.

## Verification Targets

- Migration upgrade/downgrade and repository integration prove the table,
  unique key, allowed states, immutable snapshot and persistence across
  database restart.
- Concurrent duplicate admission proves one row and at most one inference
  call; terminal repeat returns the stored response and non-terminal repeat
  reports `in_progress`.
- Failure-path tests prove no row for pre-admission rejection, correct domain
  outcome/state mapping and `internal_failure` for admitted technical failure.
- Ownership tests prove `promo` is the only writer and Photo deletion cannot
  cascade into core Attempts.
- Candidate-pool fixtures prove deterministic pHash ranking, four unique
  threshold-valid teasers and `N` equal to the complete union without group
  coverage or weak-match expansion.
- Result publication and idempotent-repeat tests prove one Attempt/session
  transaction, exact response reconstruction, digest-only QR ticket storage and
  no result/session after insufficient, deadline, interrupted or failed work.
