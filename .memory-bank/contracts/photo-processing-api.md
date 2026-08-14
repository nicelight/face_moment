---
description: Exact authenticated staff API and UI contract for Photo processing status, SLO and primary-storage health.
status: active
last_updated: 2026-08-14
source_of_truth:
  - .memory-bank/contracts/photo-processing-api.md
---
# Photo Processing API

## Scope And Ownership

This contract specializes the authenticated staff-browser boundary for
FT-002. `inventory` owns the user-visible Photo/status and operational-health
outcome. It reads the `processing` projection defined by
[Photo Processing](../domains/photo-processing.md), its own Photo/visibility
state, the current serving target and two infrastructure capacity probes.
`platform/auth` supplies the principal but does not authorize this business
read.

HTTP/UI handlers and the composition root only adapt transport. They MUST NOT
query or mutate processing repositories directly, claim work, calculate a
parallel lifecycle, or disclose object keys, model paths, storage paths or
credentials.

The private-store topology and protected-data redaction on this surface are
the FT-002 application of `REQ-SEC-001`; this traceability does not broaden the
accepted staff roles or add a separate security mechanism.

## Per-Photo Processing Status

- Method and path: `GET /api/inventory/photos/{photo_id}/processing`.
- Authentication: active staff session.
- Authorization: a `photographer` may read only a Photo whose immutable
  `uploader_id` is that principal; `operator` and `developer` may read the
  one-СПА pilot's Photos. Unauthorized ownership/role returns `403` and an
  unknown Photo returns `404`.
- The existing photographer upload page polls this endpoint only for accepted
  `photo_id` values. No Batch, manifest or cross-file state is introduced.

### Admission-lineage selector

The response represents the one state whose `pipeline_revision_id` equals the
Photo's immutable `admission_pipeline_revision_id`. `inventory` MUST pass that
revision explicitly to the `processing` read boundary; current serving
selection, another revision row, status/timestamp ordering and attempt count
MUST NOT select or replace the response state.

`pipeline_revision_id`, `pipeline_code`, `processing_status`, `attempt_count`,
`status_changed_at`, `searchable_at` and `failure_reason` all describe that
admission state. `searchable` applies the existing complete active/current-
serving compatibility rule to that same selected state. Therefore an
A-admitted Photo remains an A response after serving changes to B, and its A
state is not searchable while B serves. A later B state, including complete
`ready`, neither replaces the A fields nor causes a multiple-row failure.

| Persisted state | Current serving | Exact response |
|---|---|---|
| Admission A only | A | A fields; `searchable` follows A completeness and Photo activity. |
| Admission A only | B | A fields; `searchable=false`. |
| Admission A plus any B state | A | A fields; `searchable` follows A completeness and Photo activity; B is ignored by this endpoint. |
| Admission A plus any B state | B | A fields; `searchable=false`; B is ignored by this endpoint. |

The required admission state missing is an owner-backed read failure and maps
to `5xx`. Multiple later revision rows are valid data and MUST still return the
single admission response with `200`; the schema is unchanged.

Success returns `200` with exactly:

```json
{
  "schema_version": 1,
  "photo_id": "6d30bb17-2af0-4bb4-afcb-9f90af8b03ce",
  "pipeline_revision_id": "fe36f0c5-8424-4ccd-83fa-cf14dd6c9513",
  "pipeline_code": "opencv_sface",
  "processing_status": "ready",
  "searchable": true,
  "attempt_count": 1,
  "status_changed_at": "2026-08-06T08:12:13.456Z",
  "searchable_at": "2026-08-06T08:12:13.456Z",
  "failure_reason": null
}
```

`processing_status` is the persisted value `pending`, `processing`, `ready`,
`no_faces` or `failed`. The page renders `ready` as the photographer-facing
`searchable` state only when the separate `searchable` value is true under the
complete active/compatible rule; an incompatible or inactive `ready` remains
explicitly not searchable. `failure_reason` is non-null only for `failed` and
remains bounded/operator-safe. No object key, embedding, landmark, model path
or traceback is returned.

## Processing Health And SLO

- Page: `GET /staff/processing-health`.
- API: `GET /api/inventory/processing-health` with required UUID `spa_id` and
  optional paired ISO timestamps `accepted_from` and `accepted_before` for a
  half-open controlled SLO interval `[accepted_from, accepted_before)`.
  Supplying only one bound, equal bounds or another invalid/reversed interval
  returns `422`.
- Authentication/authorization: active `operator` or `developer`; a
  photographer receives `403`.
- The page polls every five seconds. WebSocket, SSE, materialized metrics and a
  second observability store are absent.

Success returns `200` with exactly these top-level fields:

```json
{
  "schema_version": 1,
  "spa_id": "19d33739-989f-4e02-8c0f-56ce0141fa0f",
  "observed_at": "2026-08-06T08:15:00.000Z",
  "queue": {},
  "ingest_to_searchable": null,
  "storage": {}
}
```

`queue` contains exactly `pending`, `processing`, `ready`, `no_faces`,
`failed`, nullable `oldest_pending_accepted_at`, `current_operation`, nullable
`operation_started_at`, nullable `worker_started_at`, nullable
`last_recovery_at` and
`last_recovered_count`. Counts cover the current serving revision for the
selected СПА. Inventory visibility does not rewrite processing state and is not
used to hide processing failures from this operational view.

When both interval bounds are present, `ingest_to_searchable` contains exactly
`accepted_from`, `accepted_before`, `population`, `success_under_15_minutes`,
`breach`, `open`, nullable `success_ratio` and nullable `meets_95_percent`. The
lower bound is inclusive and the upper bound is exclusive. When no Photo is in
that interval, all four counts are zero and both nullable values are `null`.
The classification and nullable verdict otherwise follow
[Photo Processing](../domains/photo-processing.md#searchable-truth-and-slo-projection).
Without the interval, this field is `null` rather than an implicit or misleading
population.

`storage` contains exactly `postgresql` and `minio`. Each contains `status`
(`ok|low|unavailable`), nullable non-negative `available_bytes`, positive
`low_threshold_bytes`, `observed_at` and nullable bounded `error`. One store's
failure MUST NOT erase or reuse the other store's result.

## Failure And Privacy Contract

| Status | Contract |
|---|---|
| `401` | Staff session is missing, invalid, expired or revoked. |
| `403` | Role or Photo ownership authorization fails. |
| `404` | The Photo or СПА does not exist. |
| `422` | Path/query validation fails. |
| `5xx` | The owner-backed database read fails; no partial success envelope is emitted. |

A capacity-probe failure is a successful current observation with that store's
`status=unavailable`; it is not a `5xx` when the owner-backed state read still
succeeds. Responses and logs MUST NOT expose credentials, authentication state,
database/object-store paths, MinIO object keys, embeddings or commercial media.
No custom project-wide error envelope is introduced.

## Verification Targets

- Contract tests cover exact paths, query rules, response fields and
  `401/403/404/422/5xx`, including photographer ownership and operator/developer
  health access.
- The per-Photo A+B matrix proves that an A-admitted Photo retains its exact A
  fields with either serving selection; A completeness governs `searchable`
  only while A serves, and any B state is ignored. With B serving the response
  is `searchable=false`, never a multiple-row failure, and causes no processing
  mutation.
- A same-origin photographer flow polls each independently accepted Photo and
  observes persisted `pending -> processing -> ready|no_faces|failed` plus the
  truthful derived searchable label without changing another upload row.
- An operator/developer controlled-interval flow reconciles every SLO count and
  the nullable ratio/95% verdict to persisted Photo/state timestamps, including
  both half-open boundaries and the exact empty-population result.
- Normal, configured-low and unavailable probes produce distinct current
  PostgreSQL and MinIO results while the other store remains truthful.
- Static/integration tracing locates outcome assembly and authorization in
  `inventory`, processing state publication in `processing`, and no business
  orchestration or foreign repository write in transport, infrastructure,
  generic helpers or the composition root.
