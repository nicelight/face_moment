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
purge work, or disclose object keys, credentials, embeddings or commercial
media. The pilot adds no Batch endpoint, jobs API, WebSocket or SSE stream.

## Staff Inventory Page And Selection

- Page: `GET /staff/photo-inventory`.
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
