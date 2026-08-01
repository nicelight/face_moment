---
description: Exact browser-to-ESP32 passage-event API, authentication, CORS and delivery contract.
status: active
last_updated: 2026-08-01
source_of_truth:
  - .memory-bank/contracts/sensor-passage-api.md
---
# Sensor Passage API

## Scope And Ownership

This contract specializes the `SpaPromoClient -> ESP32` boundary in the
[boundary map](boundary-map.md). The browser client owns request continuation
and in-memory duplicate suppression. ESP32 owns authenticated delivery of a
passage event; it owns no capture, Attempt, search or durable queue state.

## Endpoint

- Method and path: `GET /api/v1/passage-events/next` on the configured fixed
  mDNS host, for example `http://fm-sensor1.local`.
- Authentication: `Authorization: Bearer <sensor-secret>`.
- Origin: the managed Chromium request carries the central Face Moment HTTPS
  origin. ESP32 allows exactly that configured origin, never `*`.
- Hold behavior: ESP32 holds the request for at most 10 seconds. One passage
  event returns `200`; an ordinary hold timeout returns `204` with no body.
- While active, `SpaPromoClient` MUST keep exactly one request outstanding and
  MUST open the next request immediately after `200` or `204`.

The sensor secret MUST NOT appear in the host, path, query, response, browser
or firmware log. The fixed mDNS host is deployment configuration; the client
MUST NOT discover or select another sensor dynamically.

## Event Shape

A `200` response uses `Content-Type: application/json` and exactly this shape:

```json
{
  "schema_version": 1,
  "sensor_id": "fm-sensor1",
  "boot_id": "48cf0a18-2c87-46b6-bb26-c46e81606535",
  "sequence": 17,
  "type": "passage"
}
```

- `schema_version` MUST equal integer `1`.
- `sensor_id` MUST be the configured non-empty stable sensor identifier.
- `boot_id` MUST be a UUID generated for the current firmware boot.
- `sequence` MUST be a non-negative integer that increases within one boot.
- `type` MUST equal `passage`.
- Unknown or missing fields are invalid.

The client may suppress a repeated transport delivery only by the pair
`(boot_id, sequence)` and keeps that memory only until browser restart. It MUST
NOT treat this as person, trigger-window or Attempt deduplication.

## CORS And Failure Semantics

- `OPTIONS /api/v1/passage-events/next` MUST return `204` for the configured
  origin and advertise `GET, OPTIONS` plus the `Authorization` request header.
- Successful preflight and `GET` responses MUST return the exact configured
  `Access-Control-Allow-Origin` and `Vary: Origin`.
- Missing or invalid Bearer authentication returns `401`; a disallowed origin
  returns `403`; sensor technical failure uses `5xx`.
- A malformed `200` body or any transport failure is not a passage event. The
  client stays in local advertising, exposes recoverable operator feedback and
  keeps recovery state in memory without a bridge, fallback transport or
  durable sensor queue.

## Verification Targets

- A contract fixture proves `200` event and `204` timeout behavior, strict
  versioned decoding and in-memory `(boot_id, sequence)` duplicate suppression.
- Browser integration proves exactly one outstanding 10-second request and
  immediate continuation after event or timeout.
- Preflight/authentication tests prove exact-origin CORS, Authorization header
  support, rejection of a wrong origin/secret and absence of the secret from
  URLs and redacted logs.
- Firmware build and an ESP32 or protocol-equivalent test fixture prove the
  endpoint without introducing discovery, pairing, WebSocket or a local bridge.
