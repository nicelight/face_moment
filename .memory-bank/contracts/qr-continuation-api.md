---
description: Exact public QR ticket exchange, session-wide browser access, protected phone read and expiry contract.
status: active
last_updated: 2026-08-06
source_of_truth:
  - .memory-bank/contracts/qr-continuation-api.md
---
# QR Continuation API

## Scope And Ownership

This contract specializes the public `phone browser -> backend` continuation
boundary for one issued Promo/search session. `promo` owns ticket validation,
the shared browser-access state, personalized response assembly, activity and
expiry. `serving_control` supplies only the accepted СПА-name projection;
`inventory` and `processing` supply only the accepted referenced-preview
projection. HTTP handlers, infrastructure, generic helpers and the composition
root MUST NOT own this flow or write capability state directly.

The contract reuses the exact opaque `ticket` already issued in the
[Realtime Attempt API](realtime-attempt-api.md#response-version-1) and stored
only as `qr_ticket_hash_sha256` by
[Promo Attempt](../domains/promo-attempt.md#result-session-shape). It adds no
participant account, per-device grant, parallel access token, session table or
public object-storage route.

The configured main Face Moment purchase/selfie-search target MUST be one
server-owned absolute HTTPS URL. Requests cannot override it, and redirects or
CTA navigation MUST NOT append a session identifier, ticket, teaser, `N` or
other personalized parameter. Missing or invalid target configuration returns
`503` before personalized content is rendered.

## Ticket Exchange

- Method and path: `GET /q?ticket=<opaque-ticket>`.
- The request accepts exactly one non-empty `ticket` query value. The backend
  hashes it and resolves the owning Promo session without storing or logging
  plaintext.
- A first scan succeeds only when server time is strictly before
  `qr_first_open_expires_at`. It atomically sets the session's nullable
  `browser_first_opened_at` and `browser_last_seen_at` to that server time.
- A later scan before the same first-open deadline reuses the existing shared
  state and advances its one `browser_last_seen_at`; it creates no device row or
  independent idle deadline.
- Success sets the existing opaque ticket as the value of one session cookie
  named `fm_promo_access`, with `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`,
  no `Domain` and no persistent `Expires`/`Max-Age`, then returns `303` to
  `/phone`.
- Missing, malformed, unknown or late tickets all return the same `303` to the
  configured main Face Moment target without setting an access cookie or
  revealing which condition occurred.

The `/q` query string MUST be omitted from access logs. Every exchange response
uses `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.

## Phone Shell And Session Read

`GET /phone` validates but does not advance the shared state; the preceding QR
exchange is the explicit navigation that already advanced it. A valid active
`fm_promo_access` cookie returns `200 text/html`; missing or expired access
deletes the cookie and returns `303` to the configured main Face Moment target.
The successful HTML is a shell: personalized fields are loaded only through
the protected session read below. It MUST clear rendered personal state before
local expiry redirect, use `location.replace` for that redirect and retain no
personalized state in durable browser storage.

`GET /api/phone/session` validates the same cookie but is a passive read and
MUST NOT advance `browser_last_seen_at`. Success is `200 application/json`
with exactly:

```json
{
  "schema_version": 1,
  "session_id": "aa39236f-17e3-41eb-9c22-75a49ef21f93",
  "spa_name": "Pilot SPA",
  "visit_date": "2026-08-06",
  "teaser": {
    "photo_id": "2b22eb29-f8a3-4083-bc57-6776295effcb",
    "media_url": "/api/phone/media/opaque-reference"
  },
  "n": 12,
  "purchase_url": "https://example.invalid/purchase",
  "idle_expires_at": "2026-08-06T13:34:56.000Z",
  "idle_expires_in_ms": 3599123
}
```

`schema_version` is integer `1`; `session_id`, СПА, authoritative
`visit_date` and `n` come from the issued session and accepted owner
projections. `n` never changes after issuance. `idle_expires_at` is exactly 60
minutes after the current shared `browser_last_seen_at`, and
`idle_expires_in_ms` is the non-negative remaining duration calculated from the
same server observation so the phone can use a local monotonic timer without
subtracting client/server clocks.

`teaser` is either the first currently loadable entry in original
`teaser_photo_ids` order or JSON `null` when none remains. A soft-deleted Photo
remains loadable for this issued session. A hard-purged/unavailable item is
skipped; this does not select a replacement from the wider result union,
invalidate or rebuild the session, or recalculate `n`. A media item that
disappears after the read returns `404`; the client may repeat the passive
session read to obtain the next still-loadable issued teaser or `null`.

## Activity And Media

Explicit activity uses `POST /api/phone/activity` with
`Content-Type: application/json` and exactly:

```json
{"schema_version": 1}
```

The phone sends this request only for an explicit participant navigation or
action in the open page. Background polling, timers, page visibility changes
and media/asset loads MUST NOT send it. A valid still-active context atomically
advances the same shared `browser_last_seen_at` and returns `200` with exactly
`schema_version`, `idle_expires_at` and `idle_expires_in_ms`. Unknown fields or
another schema version return `422` without an activity update. The endpoint is
same-origin only; a present non-matching `Origin` returns `403`, and no CORS
permission is exposed.

Each `media_url` resolves through:

- method and path: `GET /api/phone/media/{media_ref}`;
- authentication: the active `fm_promo_access` cookie;
- success: `200 image/jpeg` containing one low-quality no-watermark preview
  referenced by that same issued session;
- response headers: `Cache-Control: no-store` and
  `Referrer-Policy: no-referrer`.

`media_ref` is opaque. Unknown, foreign-session or unavailable references
return non-disclosing `404` without raw MinIO keys, participant-facing presigned
URLs, replacement selection or session mutation. Media reads are passive and
never extend idle access.

## Shared Expiry

The first-open window and browser idle window are independent derived checks:

- a scan is admitted only while `server_now < qr_first_open_expires_at`;
- after first open, personalized access is active only while
  `server_now < browser_last_seen_at + 60 minutes`;
- at either exact boundary the corresponding operation is expired;
- an expired shared context cannot be revived by a stale cookie, passive read,
  media load or activity request.

`GET /phone` redirects expired access as above. Protected API calls with a
missing, invalid or expired cookie return `401` with no personalized response
body and delete the cookie. The phone clears any rendered teaser, СПА/date,
`N` and session identifier before replacing its location with the configured
main target. A passive session read may update the local monotonic expiry timer
when another phone has extended the shared state, but does not itself extend
that state.

Result-display duration and successful-capture cooldown remain entirely
independent. Display expiry, display acknowledgement and browser access MUST
NOT call one another's invalidation path or mutate QR issue/first-open values.
No expiry scheduler, stored expired status or cleanup job is introduced.

## Failures And Security

- Every route crosses the public HTTPS boundary and uses configured public
  request rate limiting; excess receives `429`.
- Invalid activity JSON returns `422`; unavailable configuration returns
  `503`; technical failures return `5xx`. The safe top-level redirects and
  protected API `401`/media `404` behavior above remain exact.
- Ticket/cookie plaintext, cookie headers, ticket digests, personalized
  payloads and raw storage identities MUST NOT enter logs. The accepted opaque
  ticket query is the only personalized credential allowed in a URL.
- Phone HTML, JSON, media and redirects are `no-store` and use
  `Referrer-Policy: no-referrer`; the CTA uses no-referrer navigation.
- PostgreSQL, MinIO and internal service ports stay private. Commercial media
  is backend-proxied and authorized; public MinIO/presigned participant URLs
  remain outside the pilot.
- No custom error envelope, participant login, refresh token, per-device grant,
  access-state table, session framework, redirect allow-list service, media
  cache or expiry scheduler is added.

## Verification Targets

- Exact-path tests cover ticket exchange, cookie attributes, shell/session/
  activity/media shapes, safe top-level redirects, strict validation, standard
  statuses and all cache/referrer headers.
- Controlled concurrent-clock tests cover first open, repeated scans from
  multiple phones, one shared state cardinality, explicit cross-phone activity,
  passive non-extension and exact 30-/60-minute boundaries without revival.
- Content tests reconcile session/phone identity, СПА, date, ordered available
  teaser, historical `N` and CTA; soft delete remains readable and each
  hard-purged/unavailable combination skips only missing issued media.
- Isolation tests prove expired HTML/API/media paths disclose no prior teaser,
  `N`, session or referrer/query data and clear both cookie and rendered state
  before redirect.
- Security tests cover forged/foreign/replayed tickets and cookies, rate
  limiting, log/URL/artifact redaction, no-store private media delivery and
  private PostgreSQL/MinIO/internal topology.
- The physical join scans the exact QR retained by the FT-005 display-expiry
  artifact after the display has returned to advertising and proves the same
  still-active session can be read on a representative phone without changing
  display or session truth.
