---
description: Exact realtime proposal-attempt multipart API, validation, outcome and idempotency contract.
status: active
last_updated: 2026-08-01
source_of_truth:
  - .memory-bank/contracts/realtime-attempt-api.md
---
# Realtime Attempt API

## Scope And Ownership

This contract specializes the `SpaPromoClient -> realtime` boundary in the
[boundary map](boundary-map.md). `promo` owns admission, the core Attempt and
the synchronous participant-attempt outcome. `processing` owns inference,
server-side selection and search through its application boundary. HTTP/UI
handlers, the composition root and generic helpers MUST NOT own this
orchestration or write foreign capability state.

## Endpoint And Authentication

- Method and path: `POST /api/realtime/attempts`.
- Request content type: `multipart/form-data`.
- Authentication: `Authorization: Bearer <spa-client-token>`; the server hashes
  the token, resolves its active display-client record and derives `spa_id`.
- The manifest MUST NOT supply `spa_id`, the client token or another secret.
- A total request body of at most `20,971,520` bytes may proceed to multipart
  validation. A body larger than that returns `413` before parsing/domain
  admission and creates no core Attempt or domain outcome.

The edge/realtime transport MUST enforce the total-body bound before domain
admission. No aggregate-pixel, per-JPEG-byte or manifest-size limit and no
client ranking/truncation path is added.

## Multipart Serialization

Parts are ordered as follows:

1. exactly one `manifest` part first, with
   `Content-Type: application/json; charset=utf-8` and strict UTF-8 JSON;
2. zero to twenty JPEG crop parts in ascending occurrence order.

For occurrence index `i`, the form-field name MUST be `crop_NNN`, where `NNN`
is the zero-padded three-digit index (`crop_000` through `crop_019`). Its
filename MUST be the same name plus `.jpg`, and its content type MUST be
`image/jpeg`. `occurrences[i].crop_part` MUST equal that form-field name.
Duplicate, unknown, missing or out-of-order parts are invalid. A zero-proposal
request contains only `manifest`.

## Manifest Version 1

The top-level object contains exactly these fields:

```json
{
  "schema_version": 1,
  "attempt_id": "d7938b68-31e8-44ce-bdaa-32755a64b067",
  "trigger_source": "sensor",
  "client_release": "2026.08.1",
  "detector_id": "mediapipe_blazeface_full_range",
  "model_version": "blazeface-full-range-1",
  "jpeg_quality": 0.85,
  "camera_device_id": "browser-device-id",
  "timing": {
    "reference_series_ready_at": "2026-08-01T08:12:13.456Z",
    "local_detection_completed_ms": 241,
    "request_started_ms": 278
  },
  "occurrences": [
    {
      "occurrence_index": 0,
      "frame_index": 0,
      "frame_offset_ms": 0,
      "detector_confidence": 0.93,
      "crop_part": "crop_000"
    }
  ]
}
```

Rules:

- `schema_version` MUST be integer `1`; `attempt_id` MUST be a UUID.
- `trigger_source` MUST be `sensor` or `test`.
- `client_release`, `model_version` and `camera_device_id` MUST be non-empty;
  `detector_id` MUST be `mediapipe_blazeface_full_range`.
- `jpeg_quality` MUST be one of `0.7`, `0.75`, `0.8`, `0.85`, `0.9`, `0.95`.
- `reference_series_ready_at` MUST be an RFC 3339 wall-clock correlation
  timestamp. It is never subtracted from a server clock.
- Both monotonic offsets MUST be non-negative integer milliseconds and
  `local_detection_completed_ms <= request_started_ms`.
- `occurrences` MUST contain at most 20 items. `occurrence_index` is contiguous
  and zero-based; `frame_index` and `frame_offset_ms` are non-negative and
  chronological; `detector_confidence` is within `[0, 1]`.
- Each JPEG MUST decode, have positive dimensions with neither side above 512
  pixels and contain no EXIF/source metadata. The client crop-geometry and
  no-upscale rules remain fixture-verified because the omitted source bbox/frame
  data cannot be reconstructed by the server.
- Unknown fields at every manifest level are invalid. The explicit omissions
  in the [boundary map](boundary-map.md) remain
  forbidden.

Malformed multipart, JSON, fields, relationships, JPEGs or structural bounds
return `422` before domain admission and create no core Attempt.

## Response Version 1

Every admitted request returns `200` with exactly
`schema_version`, `attempt_id`, `outcome` and, only for `result`, `result`.
Compact outcome names are:

- `result`;
- `no_proposals`;
- `busy`;
- `deadline`;
- `unacceptable_query`;
- `insufficient_results`;
- `interrupted`;
- `in_progress`, only when the same idempotency key is already non-terminal.

Non-`result` responses omit `result`. A `result` response contains exactly:

```json
{
  "session_id": "aa39236f-17e3-41eb-9c22-75a49ef21f93",
  "teasers": [
    {
      "photo_id": "2b22eb29-f8a3-4083-bc57-6776295effcb",
      "media_url": "/api/promo/media/opaque-reference-1"
    },
    {
      "photo_id": "095965bd-e2b7-4133-b6c1-830dd13a93cf",
      "media_url": "/api/promo/media/opaque-reference-2"
    },
    {
      "photo_id": "4e37e349-947c-41d7-b7e8-7c4c16a0918d",
      "media_url": "/api/promo/media/opaque-reference-3"
    },
    {
      "photo_id": "b731c61f-af11-476b-805e-dd847a749f1d",
      "media_url": "/api/promo/media/opaque-reference-4"
    }
  ],
  "n": 12,
  "qr_url": "/q?ticket=opaque-ticket",
  "qr_first_open_expires_at": "2026-08-01T08:42:15.000Z"
}
```

`teasers` MUST contain exactly four unique `photo_id` values, `n` MUST be an
integer at least four, and URLs MUST be same-origin application paths. This is
the smallest synchronous handoff needed by later Promo presentation and QR
features; it does not transfer result selection or session ownership to
FT-003.

## Admission, Idempotency And Failures

- `(spa_id, attempt_id)` is unique. The first admitted request persists its core
  Attempt before inference or singleton-slot acquisition.
- Repeating a terminal key returns its persisted terminal response without new
  inference. Repeating a non-terminal key returns `in_progress` without a
  second Attempt or inference execution.
- A valid request that cannot acquire the singleton slot returns admitted
  `busy`. Zero occurrences return admitted `no_proposals`.
- `result`, `no_proposals`, `busy`, `deadline`, `unacceptable_query`,
  `insufficient_results` and `interrupted` are domain outcomes, not transport
  errors. The client branches on `outcome`, never prose.
- Missing/invalid authentication returns `401`; payload rejection `413` or
  `422`; configured rate limiting `429`; closed serving readiness/maintenance
  `503` before admission; technical internal/upstream failure `5xx`.
- A `5xx` after admission may mark the core Attempt `internal_failure`, but the
  response remains a technical failure and adds no domain outcome.

## Verification Targets

- Contract tests cover the exact path, part names/order/content types, strict
  manifest allow-list, explicit omissions and all relational validation.
- Boundary tests at `20,971,520` and `20,971,521` bytes prove admission versus
  pre-admission `413`, with no core Attempt for the latter.
- Zero-proposal, slot-busy, deadline, unacceptable-query, insufficient-result,
  result and idempotent-repeat fixtures prove compact typed outcomes and the
  core Attempt relationship.
- Auth, validation, rate-limit, readiness and technical failures prove the
  standard status mapping without a custom error envelope.
