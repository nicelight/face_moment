---
description: Promo-owned core Attempt, realtime result assembly, result-session persistence and shared QR browser-access specification.
status: active
last_updated: 2026-08-25
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
| `local_detection_completed_ms`, `request_started_ms` | Non-negative client monotonic offsets admitted with the request. |
| `response_received_ms` | Nullable non-negative client monotonic offset reported best-effort after the synchronous response; it is never synthesized from server time. |
| `proposal_count` | Integer `0..20`. |
| `settings_revision`, `visit_date`, `pipeline_revision_id`, `pipeline_code`, `query_source`, `release_id` | Immutable serving snapshot copied before inference; `query_source` is `reference`. |
| `threshold`, `quality_settings`, `calibration_id` | Immutable applied search inputs; `calibration_id` is nullable. |
| `deadline_ms` | Positive immutable server deadline configured for this admitted Attempt. |
| `slot_decided_at`, `search_started_at`, `search_finished_at` | Nullable server stage timestamps sufficient to distinguish busy, active search and terminal search timing. |
| `processing_status` | `accepted \| searching \| result_issued \| no_success \| interrupted \| deadline \| internal_failure`. |
| `domain_outcome` | Nullable `result \| no_proposals \| busy \| deadline \| unacceptable_query \| insufficient_results \| interrupted`. |
| `display_status` | `not_applicable \| pending \| confirmed \| failed`; `unconfirmed` is derived on read and is not stored as scheduler work. |
| `display_expires_at`, `display_reported_at` | Nullable server timestamps. A result fixes a positive display window; the first accepted terminal report records its receipt time. |
| `qr_fully_visible_elapsed_ms` | Nullable non-negative client monotonic offset from `reference_series_ready`; present only for a confirmed display. |
| `created_at`, `updated_at` | Server timestamps. |

The migration MUST use the project-wide `face_moment` schema, shared
`Base/MetaData` and current linear Alembic stream. No database cascade may
delete the core Attempt with a Photo or diagnostic record.

Migration and repository proof uses a uniquely named task-owned disposable
database for upgrade/downgrade/re-upgrade and removes it after the probe; no
shared operator/default database is downgraded as test setup.

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
- A `result_issued` Attempt starts with `display_status=pending` and fixes
  `display_expires_at = qr_issued_at + result_display_ms` from the positive
  independent result-display setting; every other terminal processing outcome
  uses `not_applicable` with no display window. Display confirmation, failure and
  later derived `unconfirmed` remain governed by the
  [lifecycle map](../states/lifecycle-map.md) and exact
  [Promo Display API](../contracts/promo-display-api.md).
- Repeating a key reads the existing row/result. It MUST NOT overwrite the
  immutable snapshot, create another row or start inference twice.
- Realtime startup changes stale `accepted|searching` rows to `interrupted` and
  does not replay proposal bytes or search.

The core table does not require crop/media persistence, detailed evidence or a
reliable client-offline outbox. If later diagnostic work stores capture-derived
media, `diagnostics` owns that storage and retention.

## Client Response Timing

The exact [Client Diagnostic API](../contracts/client-diagnostic-api.md) is the
only client-to-server write for `response_received_ms`. `promo` authenticates
the display-client principal, resolves `(spa_id, client_attempt_id)` and stores
the first valid marker through its repository. Equal repeat is idempotent;
foreign, conflicting, non-terminal or out-of-order reports change nothing.

The marker belongs to the same browser monotonic origin as the admitted ready,
local-detection and request-start offsets. Server response time is not a
substitute. A missing best-effort report is projected as an explicit gap and
does not change the core outcome, create a new Attempt or trigger a retry
queue.

## Core Timeline Projection

The promo read projection exposes:

- client offsets `0` for ready-series start, then admitted
  `local_detection_completed_ms`, `request_started_ms` and nullable
  `response_received_ms`;
- server `created_at`, `slot_decided_at`, `search_started_at`,
  `search_finished_at` and terminal processing/outcome;
- display receipt/effective state and nullable
  `qr_fully_visible_elapsed_ms`.

It never subtracts client wall time from server time. Nullable stages carry a
machine gap rather than a fabricated timestamp. Base `issue_tags` are unique
lowercase machine values derived only from actual core truth:
`no_proposals`, `busy`, `deadline`, `unacceptable_query`,
`insufficient_results`, `interrupted`, `internal_failure`,
`response_receipt_missing`, `display_failed`, `display_unconfirmed` and
`latency_over_10s`. The latency tag is present only when a confirmed
`qr_fully_visible_elapsed_ms >= 10000`; no server duration substitutes for it.
The diagnostics read projection may add `evidence_incomplete` without writing
the core row.

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
| `browser_first_opened_at`, `browser_last_seen_at` | Nullable server timestamps for the one session-wide browser-access state; both are null before first open, otherwise both are present and `browser_last_seen_at >= browser_first_opened_at`. |
| `created_at` | Server timestamp. |

Photo IDs are durable historical references rather than ownership-crossing
foreign keys. Photo soft delete does not alter the row; later hard purge may
make media unavailable without changing the arrays or `N`.

The opaque ticket is deterministically regenerated for an idempotent terminal
response as URL-safe HMAC-SHA-256 over the persisted session identity and issue
time using one deployment QR-ticket secret; only its SHA-256 digest is stored.
The secret and ticket MUST NOT enter logs. Rotation/recovery machinery is not
part of FT-004. The nullable browser fields are added by the later FT-006
linear migration and remain null for every newly issued session until first
open; they do not change FT-004 publication or terminal-repeat behavior.

### Atomic result-session publication

Publishing a result inserts this row and transitions its Attempt to
`processing_status=result_issued`, `domain_outcome=result`,
`display_status=pending` and its fixed `display_expires_at` in one `promo`
transaction. Any failure publishes neither half. A terminal idempotent repeat
reconstructs the exact accepted API response from persisted session data
without rerunning search.

## QR Browser Access

### Shared Browser-Access Persistence

`promo` implements the exact
[QR Continuation API](../contracts/qr-continuation-api.md) against the existing
result-session row. The stored `qr_ticket_hash_sha256` validates both the QR
query and the shared `fm_promo_access` cookie; plaintext remains only in the
issued QR URL/browser cookie and is never persisted or logged.

First open atomically changes both nullable browser timestamps from null to the
same server time only while that time is strictly before
`qr_first_open_expires_at`. A valid repeated scan or explicit participant
activity advances the one `browser_last_seen_at` only while the derived shared
context is active. Concurrent phones update the same row; there is no
per-device identifier, grant row or independent deadline. Passive session
reads, asset/media loads, polling and local timers never write either field.

Active browser access is derived as
`server_now < browser_last_seen_at + 60 minutes`. Expiry is not stored and
cannot be reversed by a stale cookie or late activity; no scheduler or cleanup
row exists. The migration adds the two nullable columns and a constraint that
they are both null or both non-null with `last_seen >= first_opened`; existing
issued rows preserve their ticket, first-open deadline, teaser arrays, union
and `N` unchanged.

### Participant Response Assembly

Participant response assembly reads the immutable session plus accepted
СПА/media projections. Soft-deleted referenced media remains eligible for the
issued session. Hard-purged/unavailable teaser IDs are skipped in original
teaser order without choosing from the wider union, mutating arrays or
recalculating `N`. Access, media and redirect behavior never writes Photo,
processing or serving-control state.

## Display Outcome

The authenticated display report uses the exact
[Promo Display API](../contracts/promo-display-api.md) and is owned entirely by
`promo`:

- while effective state is `pending`, the first timely `confirmed` report
  atomically records `display_status=confirmed`, `display_reported_at` and the
  non-negative `qr_fully_visible_elapsed_ms` supplied on the same client
  monotonic timeline as `reference_series_ready`;
- the first timely `failed` report records `display_status=failed` and
  `display_reported_at` with no QR-visible elapsed value;
- repeating the same stored terminal status is idempotent and returns the
  original values; a conflicting terminal report changes nothing;
- when `pending` has reached `display_expires_at`, reads return effective
  `unconfirmed`; that terminal derivation is never replaced by a late report
  and adds no scheduler/update row;
- no display transition mutates the result session, QR ticket/issue/first-open
  times, teaser IDs, complete union or `N`.

The display setting and successful-capture cooldown remain independent positive
deployment values projected through the display API. No settings table,
acknowledgement outbox, background expiry job or reliable client-retry queue is
introduced.

The accepted baseline already creates `display_status`, `display_expires_at`,
`display_reported_at` and `qr_fully_visible_elapsed_ms` with the core Attempt,
and atomic result publication already fixes the positive display window. FT-005
therefore reuses those columns and adds no schema migration or historical
backfill. Existing session/ticket/result fields remain unchanged.

## Ordinary Attempt Retention

The exact [Diagnostic Retention API](../contracts/diagnostic-retention-api.md)
owns one latest cleanup result. Promo selects its own core Attempts whose
`created_at` is strictly before the fixed 90-day UTC cutoff, passes those UUIDs
to diagnostics and deletes them only after diagnostics confirms its portion
inaccessible or confirms that no evidence row exists. Owner-local result
sessions may be deleted with their expired Attempt; no Photo, processing,
serving-control or diagnostics row is cascaded.

`face_moment.retention_cleanup_latest` is one promo-owned singleton result, not
a history or generic jobs table. It records the latest run identity, fixed
cutoffs, `running|succeeded|failed|interrupted`, timestamps, confirmed owner
counts and a bounded sanitized error. A project-scoped PostgreSQL advisory lock
rejects a concurrent invocation without overwriting its active result; after
the lock becomes available, any orphaned `running` result becomes `interrupted`
before a fresh safe rerun. Ordinary cleanup never removes a diagnostics-owned
promoted subset.

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
- A missing/invalid display-duration setting prevents result publication with
  the applicable readiness/technical failure; it never silently copies the
  success-cooldown value.
- A foreign-СПА, conflicting or late display report changes no Attempt/session
  state. Missing or hard-purged teaser media never causes replacement selection
  or `N` recalculation.
- Display-outcome implementation MUST reuse the existing Attempt columns; it
  MUST NOT add another migration, storage owner or cross-owner cascade.

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
- Display tests prove authenticated principal scope, fixed positive expiry,
  timely confirmed/failed transitions, duplicate idempotency, conflicting/late
  rejection, derived `unconfirmed`, one-clock QR-visible persistence and no
  mutation of session/ticket/teaser/union/`N` truth.
- QR-access migration and repository tests prove nullable-pair constraints,
  preserved historical sessions, atomic first open, one shared monotonic
  `last_seen` across concurrent phones, passive-read non-extension, derived
  irreversible idle expiry and persistence across database restart without a
  grant table or expiry job.
- Phone assembly tests prove same-session СПА/date/available teaser/historical
  `N`, soft-delete continuity, ordered hard-purged-media skip, protected
  no-store delivery and zero foreign-owner writes or session reconstruction.
- Schema/repository proof confirms that the existing Attempt columns support
  timely terminal reports and derived `unconfirmed` without a stored terminal
  rewrite or historical backfill.
- Client timing proof confirms first-write/equal-repeat idempotency, monotonic
  ordering and explicit missing-report gaps with no reliable outbox or
  diagnostics direct write.
- Retention proof confirms diagnostics-before-promo owner order, the strict
  90-day cutoff, promoted-subset preservation, interruption/failure visibility,
  safe rerun and one latest result without a history table.
