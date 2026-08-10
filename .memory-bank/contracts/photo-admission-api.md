---
description: Exact authenticated staff-browser API and UI contract for independent Photo admission.
status: active
last_updated: 2026-08-08
source_of_truth:
  - .memory-bank/contracts/photo-admission-api.md
---
# Photo Admission API

## Scope And Ownership

This contract specializes the staff-browser upload boundary in the
[boundary map](boundary-map.md). `inventory` owns the independent Photo-
admission outcome and calls `serving_control` plus `processing` through their
application boundaries. `platform/auth` supplies the staff principal. HTTP/UI
handlers, generic utilities and the composition root MUST NOT own this business
orchestration or directly write capability state.

## Staff Session Endpoints

- `GET /staff/login` serves the same-origin login page.
- `POST /api/staff/sessions` accepts exactly `username` and `password` as JSON.
  Success returns `204` and the cookies defined by
  [Staff Access](../domains/staff-access.md). Invalid credentials return a
  generic `401`; configured login limiting returns `429`.
- `GET /api/staff/session` returns exactly `staff_user_id`, `username` and
  `role` for the current session.
- `DELETE /api/staff/session` requires CSRF, revokes the current session,
  clears both cookies and returns `204`. Repeating with no valid session returns
  `401`.

No self-registration, browser password reset, session listing or custom error
envelope is part of FT-001.

## Upload Context And Page

### Authenticated Ingest Target Context

- `GET /api/inventory/ingest-targets` requires the same role and returns
  `{"schema_version":1,"spas":[...]}`. Each active one-СПА pilot entry
  contains exactly `spa_id`, `name` and IANA `timezone`; the photographer still
  selects and submits authoritative `visit_date`.

### Independent Uploader Page

- `GET /staff/photo-upload` requires an active `photographer` session and
  renders the same-origin uploader.
- The page lets the photographer select one returned СПА, one `visit_date` and
  multiple local files. It sends one independent request per file, keeps one
  visible row per file and never adds Batch, manifest or confirmation state.
  Completion order MUST NOT change another file's result.

## Photo Upload Endpoint

- Method and path: `POST /api/inventory/photos`.
- Content type: `multipart/form-data` with exactly one UUID `spa_id`, one ISO
  `YYYY-MM-DD` `visit_date` and one `photo` part declared `image/jpeg`.
- Authentication: the staff-session cookie; authorization: active
  `photographer`; CSRF: matching `fm_staff_csrf` cookie and `X-CSRF-Token`.
- The request is rate-limited by authenticated principal/session plus IP using
  deployment-configured positive limits. The single-backend pilot requires no
  distributed limiter.
- Each request crosses the `inventory` application boundary once. The handler
  MUST NOT issue direct Photo, pipeline-state, Spa or MinIO repository writes.

An accepted upload returns `201` with exactly:

```json
{
  "schema_version": 1,
  "outcome": "accepted",
  "photo": {
    "photo_id": "6d30bb17-2af0-4bb4-afcb-9f90af8b03ce",
    "spa_id": "19d33739-989f-4e02-8c0f-56ce0141fa0f",
    "visit_date": "2026-08-03",
    "accepted_at": "2026-08-03T08:12:13.456Z",
    "captured_at": "2026-08-03T07:58:01.000Z",
    "processing_status": "pending"
  },
  "warnings": []
}
```

A same-СПА/date checksum duplicate returns `200` with exactly
`schema_version: 1`, `outcome: "duplicate"` and `warnings`. It does not expose
the existing Photo or object identity. `warnings` may contain only
`exif_visit_date_mismatch`; this warning never rewrites or rejects the selected
scope.

## Rejection And Failure Contract

The endpoint uses standard HTTP failures and no project-wide error framework:

| Status | Contract |
|---|---|
| `401` | Staff session is missing, invalid, expired or revoked. |
| `403` | Role or CSRF authorization fails. |
| `413` | The compressed candidate exceeds the configured upload-byte limit. |
| `422` | Multipart fields, selected target, media type, configured decoded bounds or JPEG decode/EXIF validation fails. |
| `429` | The configured uploader rate limit is exceeded. |
| `5xx` | A technical database/object-storage failure occurs. No success outcome is emitted. |

The UI maps `413`/`422` to a visible per-file `rejected` result and keeps other
completed file rows unchanged. It maps `200 duplicate` and `201 accepted`
directly. It MUST NOT infer control behavior from `5xx` prose.

PostgreSQL, MinIO and internal role ports remain private. The browser receives
neither object keys nor storage credentials and uses no presigned/direct-MinIO,
external ingest, resumable upload or aggregate confirmation path.

## Verification Targets

- Contract tests cover exact paths, methods, fields, response shapes, cookie,
  role and CSRF requirements plus representative `401/403/413/422/429/5xx`
  mappings.
- A same-origin application-boundary flow logs in, selects one СПА/date and
  independently submits valid, invalid, undecodable, mixed-EXIF and duplicate
  files; every visible/API result and persisted authoritative date matches.
- A concurrent duplicate fixture returns one `accepted` and one `duplicate`
  while the [Photo Admission](../domains/photo-admission.md) data counts remain
  unchanged beyond the winner.
- Topology and redaction probes confirm that only the HTTPS edge is browser-
  reachable and no password, session/CSRF token, authorization header, object
  key or storage credential appears in URL or application logs.
