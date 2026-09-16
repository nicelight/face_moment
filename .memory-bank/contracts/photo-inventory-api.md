---
description: Exact authenticated staff API and UI contract for Photo selection, visibility, recent counters, restore-all and global hard purge.
status: active
last_updated: 2026-09-04
source_of_truth:
  - .memory-bank/contracts/photo-inventory-api.md
---
# Photo Inventory API

## Scope And Ownership

This contract specializes the authenticated staff-browser boundary for
FT-012. `inventory` owns Photo selection, visibility transitions, recent
counter assembly, restore-all and the user-visible global hard-purge outcome.
`staff_access` supplies the authenticated principal; `processing` supplies its
read projection and owner-only purge cleanup boundary.

HTTP/UI handlers and the composition root only adapt transport. They MUST NOT
authorize inventory actions, mutate Photo or processing rows directly, run
purge work, or disclose object keys, credentials or embeddings. Commercial
media is delivered only by the authorized staff media boundary below or the
existing Promo/QR boundaries. The pilot adds no Batch endpoint, jobs API, WebSocket or SSE stream.

## Staff Inventory Page And Selection

- Page: `GET /staff/photo-inventory`.
- The площадка selector is a dropdown of saved active площадка names. UUIDs
  remain option values and API parameters. Select the first available площадка
  by default, preserve a valid `spa_id` URL selection, and refresh on change.
  An empty list shows «Нет доступных площадок» and sends no scoped request.
  Names are edited by operator/developer in `/staff/spas`; see
  [Staff площадка names](boundary-map.md#staff-площадка-names).
- Authentication: active staff session. Every accepted staff role may open the
  page; controls and API results remain role-scoped below.
- Selection API: `GET /api/inventory/photos` with required UUID `spa_id`, ISO
  `visit_date`, timezone-aware `captured_from` and `captured_before`.
- The interval is half-open `[captured_from, captured_before)` and requires
  `captured_from < captured_before`; missing, naive or invalid bounds return
  `422`.
- A photographer receives only Photos whose immutable `uploader_id` is that
  principal. An operator or developer receives matching Photos in the
  accessible one-СПА pilot scope. Unknown or inaccessible СПА returns `404` or
  `403` respectively.

Success returns `200` with exactly:

```json
{
  "schema_version": 1,
  "spa_id": "19d33739-989f-4e02-8c0f-56ce0141fa0f",
  "visit_date": "2026-09-04",
  "captured_from": "2026-09-04T09:00:00.000+05:00",
  "captured_before": "2026-09-04T12:00:00.000+05:00",
  "photos": [
    {
      "photo_id": "6d30bb17-2af0-4bb4-afcb-9f90af8b03ce",
      "captured_at": "2026-09-04T10:15:00.000+05:00",
      "accepted_at": "2026-09-04T05:16:00.000Z",
      "active": true
    }
  ]
}
```

Rows are ordered by `captured_at`, then `photo_id`. The route returns only the
small projection needed for selection and adds no pagination, saved filter,
bulk-selection state or alternate timestamp calculation. `captured_at` is the
persisted effective value established by Photo admission.

## Per-Photo Visibility

- Method and path: `PUT /api/inventory/photos/{photo_id}/visibility`.
- Body: exactly `{"schema_version":1,"active":true}` or the same shape with
  `false`.
- Mutations require the matching `fm_staff_csrf` cookie and `X-CSRF-Token`.
- A photographer may change only their own Photo. An operator/developer may
  change a Photo in the accessible one-СПА scope.
- Repeating the already-current value is an idempotent `200`.
- Restoring a member of a confirmed non-terminal purge snapshot returns `409`
  and changes nothing. Soft-deleting after confirmation never adds that Photo
  to the existing snapshot.

Success returns exactly `schema_version`, `photo_id` and `active`. The command
changes only `Photo.is_active`; it does not rewrite acceptance/capture times,
processing state, media, faces, Promo/session, Attempt or diagnostic evidence.

## Recent Statistics

- Method and path: `GET /api/inventory/recent-statistics?spa_id=<uuid>`.
- Authentication/authorization: active `operator` or `developer`; a
  photographer receives `403`.
- One server `observed_at` anchors all windows. Each window includes persisted
  timestamps from `observed_at - minutes` through `observed_at`, inclusive.
- The processing row is the Photo's immutable admission-revision state. A
  later revision row MUST NOT duplicate or replace that Photo in these counts.
- Every counter excludes `is_active=false`; a restored Photo re-enters only
  according to its preserved acceptance/state timestamps.

Success returns `200` with exactly:

```json
{
  "schema_version": 1,
  "spa_id": "19d33739-989f-4e02-8c0f-56ce0141fa0f",
  "observed_at": "2026-09-04T07:00:00.000Z",
  "windows": [
    {"minutes": 1, "new": 0, "unprocessed": 0, "processed": 0, "failed": 0},
    {"minutes": 5, "new": 2, "unprocessed": 1, "processed": 1, "failed": 0},
    {"minutes": 60, "new": 12, "unprocessed": 2, "processed": 8, "failed": 2}
  ]
}
```

The array always contains minutes `1`, `5`, `60` in that order and all counts
are non-negative integers. The page polls this route every five seconds.
Direct PostgreSQL aggregation is the whole mechanism.

## Restore-All And Hard-Purge Surfaces

All routes in this section require active `operator` or `developer` plus
matching CSRF on mutation. They are project-wide administrative actions.

### Restore all

`POST /api/inventory/restore-all` accepts exactly `{"schema_version":1}`.
Success returns `200` with exactly `schema_version`, non-negative
`restored_count` and non-negative `excluded_snapshot_count`. It restores every
currently inactive Photo except members of the current confirmed non-terminal
purge snapshot. Repeating it is safe.

### Purge read and confirmation

- `GET /api/inventory/hard-purge` returns the current run projection.
- `POST /api/inventory/hard-purge` accepts exactly
  `{"schema_version":1,"confirmed":true}` and atomically fixes the sorted UUID
  snapshot of every currently inactive Photo.
- A second confirmation while a run is non-terminal returns `409` and does not
  replace or enlarge the snapshot. A completed prior run may be replaced by a
  newly confirmed run. An empty snapshot completes immediately with zero
  progress.

The read and successful confirmation return exactly:

```json
{
  "schema_version": 1,
  "run": {
    "run_id": "f60b986b-b0f1-4296-82d4-d023d6510d27",
    "state": "confirmed_waiting",
    "completed": 0,
    "total": 10,
    "waiting_for": "Обработка фото",
    "confirmed_at": "2026-09-04T07:10:00.000Z",
    "started_at": null,
    "completed_at": null
  }
}
```

Before any run, `run` is `null`. State is exactly `confirmed_waiting`,
`running` or `completed`. `waiting_for` is nullable and present only while
waiting; it is derived from the worker's current operation through this fixed
mapping:

| Worker operation | `waiting_for` |
|---|---|
| `photo_processing` | `Обработка фото` |
| `calibration` | `Калибровка` |
| `retention_cleanup` | `Очистка диагностических данных` |

When `waiting_for` is non-null, the page displays
`Начну удаление, как только закончится процесс {waiting_for}`. An idle worker
may briefly leave it null until the next worker tick starts the purge. While
the run is non-terminal, its progress view replaces the destructive controls
and polls the read route every five seconds.

## Failure, Security And Verification

| Status | Contract |
|---|---|
| `401` | Staff session is missing, invalid, expired or revoked. |
| `403` | Role, Photo ownership, СПА access or CSRF authorization fails. |
| `404` | The requested Photo or СПА does not exist. |
| `409` | Restore conflicts with a non-terminal snapshot or a purge is already active. |
| `422` | Query/body validation fails. |
| `5xx` | The owner-backed operation fails; no false-success projection is emitted. |

Every response is `Cache-Control: no-store`. Contract and browser tests cover
exact paths/shapes, roles, CSRF, interval bounds, idempotency, `401/403/404/409/
422/5xx`, five-second polling, waiting/progress replacement and absence of raw
storage or protected diagnostic detail. Purge execution and restart proof are
owned by [Photo Inventory](../domains/photo-inventory.md) and
[Photo Inventory Verification](../testing/photo-inventory.md).

## Staff Venue Media

Operator request 2026-09-11: the Library provides a «Медиа» link for each
площадка. It opens a venue-specific page with inclusive From/To date filters
and a table: thumbnail, date/time added, useful persisted photo information,
and a final per-photo delete action. Clicking a thumbnail opens the original
JPEG at its native resolution. Staff media remains authenticated and private;
no bucket keys or public object URLs are exposed.

The page uses the existing inventory role scope: photographers see their own
uploads; operator/developer see venue uploads. Every list and media request
rechecks the active staff session and Photo ownership. The date basis is an
implementation default of acceptance/upload date (`accepted_at`), pending an
optional operator preference; it does not change authoritative `visit_date`
or search scope. Both calendar days are included in server UTC+7. Default:
today. Additional columns use existing capture time, dimensions/byte size,
and processing status; no invented metadata is required.

Inventory owns selection and authorization, reads its original object reference
and obtains thumbnail availability through a processing-owned read boundary.
Reuse persisted admission-revision thumbnails (default maximum edge 320 px).
Do not create thumbnails on HTTP reads or download originals to populate the
table. Missing/pending thumbnails have an explicit placeholder; original access
remains possible for an authorized existing Photo. Use existing soft-delete
visibility mutation with CSRF. No new per-photo hard-delete operation is added.
Operator clarification 2026-09-11: exclude Photos whose admission processing
status is `no_faces` from the table. Pending/processing/failed or missing state
has no confirmed no-face outcome and may appear with a placeholder.
All other selected active photos are reachable; avoid an unannounced result limit.
Exact routes and serialization are defined below.

Verification covers venue/date bounds including UTC+7 day edges, ownership,
revoked/missing sessions, missing derivatives, native original bytes, escaped
metadata, soft-delete/CSRF, browser table navigation and actual HTTPS edge
routing. Use disposable fixtures for delete proof; retain live uploaded photos.

### Venue media transport

- Page: `GET /staff/venue-media?spa_id=<uuid>`; Library links preserve the venue
  UUID. The page shows the venue name, uses the existing staff shell/date picker
  (`dd.mm.yyyy`) and server UTC+7 display helpers, and initially selects today.
- List: `GET /api/inventory/venue-media?spa_id=<uuid>&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`.
  Both ISO dates are required. Select active Photos except admission-state
  `no_faces`, by `accepted_at` from
  `date_from` 00:00 UTC+7 inclusive to the day after `date_to` 00:00 UTC+7
  exclusive; reversed or invalid dates and malformed UUIDs return `422`.
  No `visit_date` or capture-time filter is imposed on this separate view.
- Success `200` JSON contains exactly `schema_version: 1`, `spa_id`,
  `date_from`, `date_to`, and `photos`. Each row contains exactly `photo_id`,
  `accepted_at`, `captured_at` (timezone-aware ISO timestamps), `width`, `height`,
  `original_byte_size` (persisted integers), `processing_status` (the existing
  status enum, or null when the admission state is absent), `thumbnail_url`
  (same-origin route below, or null), and `original_url` (same-origin route
  below). Sort by `accepted_at` descending, then `photo_id` ascending. Return
  all matching rows; no silent cap, saved query or new pagination contract.
- Thumbnail: `GET /api/inventory/venue-media/{photo_id}/thumbnail`.
  Original: `GET /api/inventory/venue-media/{photo_id}/original`.
  Both independently authorize the Photo's venue and immutable uploader under
  the current session, including direct requests. Existing soft-deleted Photos
  remain readable by the same authorized staff until hard purge; they are
  absent from the active table. Unknown/purged Photo or unavailable object
  returns `404`. A missing derivative reference also returns `404`.
- Successful media replies return private `image/jpeg` bytes with
  `Cache-Control: no-store`; original bytes MUST equal the stored JPEG without
  resizing or re-encoding. Open the original in a separate browser tab; the
  image retains its native dimensions and browser zoom. Do not redirect to
  object-store URLs. Missing thumbnails render a placeholder with original
  access, including a reference whose object disappeared after listing.
- Missing/expired/revoked sessions return `401`; denied role/venue/uploader
  access returns `403`; unknown venue returns `404`. Storage/database failures
  other than missing objects return `5xx`, with no false empty/success result.
  All page/API/media responses, including failures, use `no-store`.
- Escape venue names and metadata. The final row action calls the existing
  visibility endpoint with `active:false` and CSRF; remove the row only after
  successful mutation and show a failed action without pretending deletion.
  Empty result, loading and failed list states are explicit.
- The checked-in HTTPS edge MUST route `/staff/venue-media` to the backend;
  existing `/api/inventory/*` delivery remains the media transport.

### Candidate original cleanup

At the bottom of «Медиа площадки», operator/developer may launch project-wide
cleanup of MinIO `candidates/` originals with no `Photo` reference. The button
shows a confirmation dialog with the operator's 30-minute warning and exact
`ДА!` / `Отмена` choices. Photographer has no control. Confirmation calls
`POST /api/inventory/orphan-originals/cleanup` with the active staff session and
CSRF header/cookie. Success returns `schema_version: 1`, `scanned` and `deleted`
counts. The page shows the result or failure without claiming success early.

The server waits for active admissions, excludes new candidate staging during
the scan, pages through the private bucket and checks each page against
committed `Photo.original_object_key` values before deleting unmatched keys.
Only `candidates/` is in scope; accepted Photos and other MinIO namespaces are
untouched. New uploads during cleanup return retryable `503`; duplicate cleanup
requests return `409`. Missing/invalid staff session returns `401`, invalid CSRF
or role returns `403`, and storage/database failures return `500`. No database
migration or persistent job state is added. A dropped browser connection may
leave the outcome unknown to that browser; another run is safe.
