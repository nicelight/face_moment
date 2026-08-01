---
description: Promo-owned core Attempt persistence, transitions and idempotency data specification.
status: active
last_updated: 2026-08-01
source_of_truth:
  - .memory-bank/domains/promo-attempt.md
---
# Promo Attempt

## Scope And Owner

`promo` owns the core Attempt, its immutable admission snapshot, processing
outcome and display status. `processing` returns search results through its
application boundary; `diagnostics` may attach best-effort detail but neither
capability may directly write the core Attempt table.

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

## Edge Cases And Errors

- Failure to obtain a complete serving snapshot prevents inference and produces
  the applicable admitted non-success or pre-admission readiness response from
  the API contract; it MUST NOT silently use client СПА/date/configuration.
- A technical failure after row creation records `internal_failure` before the
  endpoint returns `5xx` when the transaction can still complete safely.
- A failed write prevents downstream inference. Detailed evidence failure does
  not roll back an already valid core Attempt outcome.
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
