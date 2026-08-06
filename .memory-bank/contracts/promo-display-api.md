---
description: Exact authenticated Promo display configuration, teaser-media and post-render acknowledgement API contract.
status: active
last_updated: 2026-08-06
source_of_truth:
  - .memory-bank/contracts/promo-display-api.md
---
# Promo Display API

## Scope And Ownership

This contract specializes the central-origin `SpaPromoClient -> backend`
display boundary after a successful
[Realtime Attempt API](realtime-attempt-api.md) result. `promo` owns display
configuration projection, authorized teaser delivery, acknowledgement
orchestration and core Attempt display state. `inventory` and `processing`
supply only their accepted Photo/preview projections. HTTP handlers,
infrastructure, generic helpers and the composition root MUST NOT own this
flow or write capability state directly.

Every endpoint below reuses the active central display-client Bearer principal
from [Display Client Access](../domains/display-client-access.md). The server
derives authoritative `spa_id` from the stored token hash; a session or media
reference from another СПА is not disclosed.

## Display Configuration

- Method and path: `GET /api/promo/display/config`.
- Authentication: `Authorization: Bearer <spa-client-token>`.
- Success: `200 application/json` with exactly:

  ```json
  {
    "schema_version": 1,
    "result_display_ms": 15000,
    "success_cooldown_ms": 30000
  }
  ```

Both durations MUST be positive integers and come from two independent
deployment settings. The values above are examples, not product defaults. A
missing or invalid value returns `503`; it MUST NOT silently reuse the other
duration or create a settings framework. The same `result_display_ms` value is
used when `promo` fixes
`display_expires_at = qr_issued_at + result_display_ms` for a newly issued
result.

## Teaser Media

Each `media_url` in Realtime Attempt API Response Version 1 resolves through:

- method and path: `GET /api/promo/media/{media_ref}`;
- authentication: the same display-client Bearer principal;
- success: `200 image/jpeg` containing the low-quality no-watermark preview
  for exactly one of that session's four teaser Photos;
- response headers: `Cache-Control: no-store`.

`media_ref` is an opaque same-origin application reference. It MUST resolve
through the `promo` session plus accepted inventory/processing projections and
MUST NOT expose a raw MinIO key or produce a participant-facing presigned URL.
Unknown, unavailable, hard-purged or foreign-СПА references return `404`
without replacement selection or session/`N` mutation. The display treats any
missing or undecodable teaser as render failure and never presents a partial
Promo.

## Display Acknowledgement

- Method and path:
  `PUT /api/promo/sessions/{session_id}/display`.
- Authentication: the same display-client Bearer principal.
- Content type: `application/json`.
- A confirmed request contains exactly:

  ```json
  {
    "schema_version": 1,
    "status": "confirmed",
    "qr_fully_visible_elapsed_ms": 8421
  }
  ```

- A render-failure request contains exactly:

  ```json
  {
    "schema_version": 1,
    "status": "failed"
  }
  ```

`schema_version` MUST be integer `1`. `status` MUST be `confirmed` or
`failed`. `qr_fully_visible_elapsed_ms` is required only for `confirmed`, MUST
be a non-negative integer monotonic offset from that Attempt's
`reference_series_ready` zero and MUST be absent for `failed`. Unknown fields
or invalid relationships return `422`.

The client sends `confirmed` only after all four teaser JPEGs have decoded and
the locally generated QR is fully visible. The first accepted report before
`display_expires_at` atomically records the terminal stored display status,
server receipt time and, for `confirmed`, the client monotonic elapsed value.
Repeating the same terminal status is idempotent and returns the originally
stored result without changing its elapsed value or timestamps. A conflicting
terminal status or any first report after the pending window has derived
terminal `unconfirmed` returns `409` and changes nothing. A late report never
reopens `unconfirmed`.

A successful response is `200 application/json` with exactly
`schema_version`, `session_id`, `status`, `display_expires_at` and, only for
`confirmed`, the persisted `qr_fully_visible_elapsed_ms`. The acknowledgement
does not change the Promo session, QR ticket, `qr_issued_at`, first-open expiry,
teaser IDs, union or `N`.

## Client Outcome Rules

- A compact realtime `result` is eligible for rendering only when its exact
  four-teaser/result shape validates. The client fetches and decodes all four
  authorized media responses and generates the QR locally from `qr_url`.
- Final Promo, optional Chime and success cooldown begin only after the four
  teasers and fully visible QR have formed one complete display result.
- Any non-result outcome, invalid/partial result, media/decode/QR/render error,
  stale response, camera/sensor/network/processing failure or missing display
  configuration leaves or returns the client to usable local advertising and
  starts no success cooldown. A best-effort `failed` report is allowed only
  for a server-issued result.
- Result-display expiry changes only local presentation. It returns to
  advertising and MUST NOT call a session-expiry/invalidation path. Result
  display and success cooldown use their independent configured durations.
- Missing optional audio/animation is silent and non-blocking. A server-
  communication failure keeps the accepted replaceable 5–10-second
  timestamped notice.

## Failures And Security

- Missing, invalid, reset or inactive display authentication returns `401`.
- A valid principal requesting a foreign or unknown session/media reference
  receives `404` without resource disclosure.
- Invalid JSON/fields return `422`; applicable rate limiting returns `429`;
  unavailable configuration/readiness returns `503`; technical failure returns
  `5xx`.
- Authorization headers, token plaintext/digests, personalized result payloads
  and raw storage identities MUST NOT enter URLs or logs. Media and JSON
  responses are `no-store`; PostgreSQL, MinIO and internal ports remain private.
- No custom error envelope, acknowledgement outbox, scheduler, reliable retry
  queue, media cache, replacement selection or parallel session owner is added.

## Verification Targets

- Contract tests cover the exact three paths, strict JSON shapes, authenticated
  principal scope, standard statuses, `no-store` delivery and absence of raw
  storage/credential material.
- Media fixtures prove four authorized low-quality no-watermark previews,
  foreign/missing/hard-purged `404` and zero partial/replacement result.
- State tests prove pending `-> confirmed|failed`, duplicate idempotency,
  conflicting/late rejection, derived terminal `unconfirmed` and unchanged
  session/ticket/expiry/teaser/union/`N` values.
- Client fixtures prove acknowledgement only after four decodes plus full QR
  visibility, independent display/cooldown timers, advertising fallback,
  optional-asset silence and no success cooldown on every named failure.
- The controlled 20-attempt artifact joins stable `attempt_id` values to the
  FT-004 server-correctness rows and records one-clock fully-visible elapsed,
  target-display rendering and representative-phone scan results without
  excluding timeout or no-match.
