---
description: Serving-control data, Admin settings and authentication rules for SpaPromoClient identity and token lifecycle.
status: active
last_updated: 2026-08-16
source_of_truth:
  - .memory-bank/domains/display-client-access.md
---
# Display Client Access

## Scope And Owner

`serving_control` owns central `SpaPromoClient` identity, СПА binding, current
token value and token lifecycle. `platform/auth` supplies the existing staff
principal and may supply a narrow client-authentication adapter, but `promo`,
HTTP handlers, firmware and the browser MUST NOT create, reset, deactivate or
directly mutate display-client credentials.

This specification covers the central application token only. The distinct
ESP32 sensor secret follows the
[Sensor Passage API](../contracts/sensor-passage-api.md) and never enters the
central display-client table.

## PostgreSQL Shape

The runtime persistence path is the `face_moment.display_clients` table owned
by the `serving_control` repository. It contains:

| Field | Contract |
|---|---|
| `id` | Server-generated UUID primary key. |
| `spa_id` | Required UUID returned in the authenticated principal; client input cannot override it. |
| `name` | Required operator-readable device name. |
| `token_hash_sha256` | Required unique 32-byte SHA-256 digest of the current high-entropy opaque token, used for client authentication. |
| `token_value` | Required current retrievable token shown only in authenticated Admin settings so an Admin can manually transfer it to the named kiosk. |
| `active` | Required boolean; inactive credentials authenticate as invalid. |
| `created_at` | Server timestamp. |
| `rotated_at` | Nullable server timestamp updated by explicit reset. |
| `deactivated_at` | Nullable server timestamp set by explicit deactivation. |

The token MUST contain at least 32 random bytes before URL-safe encoding.
Provision and reset atomically persist `token_value` and its matching digest;
the two values MUST NOT diverge. `token_value` is intentionally retrievable:
one-time display and hash-only storage are not the accepted pilot contract.
Reset replaces both values and invalidates the old token. Automatic rotation
and a separate credential scheduler are outside the pilot.

## Admin Settings Token Read

`Admin` in this contract means an authenticated active `operator` or
`developer` staff principal using the existing same-origin staff session. It
does not introduce a fourth staff role. A photographer or an unauthenticated,
expired, revoked or inactive staff principal MUST NOT receive a display-client
token.

The server Admin settings surface MUST list every configured kiosk with its
display-client `id`, `name`, authoritative `spa_id`, active state and full
current `token_value` at `GET /staff/display-clients`. The page requires the
existing staff-session cookie and returns `403` to an authenticated
photographer; invalid staff authentication returns `401`. The current token
remains visible on every authorized settings read, including after page reload
and database restart; the Admin does not reset or regenerate it merely to see
it. The response is `Cache-Control: no-store`, and the token MUST NOT enter a
URL, application/proxy log, analytics event or command-history artifact.

Provision/reset administration records only the changed kiosk identity and
lifecycle result in command output; it does not create a one-time secret
display. The full current value is read from the Admin settings page before
each manual kiosk transfer.

## Manual Kiosk Profile Handoff

The handoff is deliberately manual:

1. The Admin opens the authenticated server settings and reads the named
   kiosk's current token.
2. The Admin copies that value into the central-token field of the client
   configuration UI on the intended kiosk.
3. The client stores it in that managed kiosk browser profile and reuses it
   after page reload or Chromium restart only as the display-client Bearer
   credential.

The server does not push or inject the token into the kiosk, and the pilot adds
no pairing, enrollment link, deployment-policy secret injection or automatic
rotation. After reset, the Admin repeats the same manual transfer with the new
current token; until then the old kiosk value authenticates as invalid. Normal
advertising remains usable while the client reports the missing/invalid central
credential as an operator-recoverable configuration failure.

## Authentication Contract

- The public realtime request supplies exactly one
  `Authorization: Bearer <spa-client-token>` header.
- The server hashes the candidate token, resolves one active row and constructs
  a principal containing only the display-client `id` and authoritative
  `spa_id` needed by the target application boundary.
- Missing, malformed, unknown, reset or inactive tokens return `401` without
  revealing which condition failed.
- Manifest/body `spa_id`, token values or attempts to select another СПА are
  rejected and never override the principal.
- Redacted logging may include display-client `id`; it MUST NOT include the
  credential, Authorization header or token digest.
- Simple per-token and IP rate limits are deployment-configured positive
  values and return `429`. Tests use explicit deterministic limits; no rate
  limiter queue or distributed store is introduced.

## Lifecycle And Recovery

```text
provisioned(active) -> reset(active, old token invalid)
provisioned(active) -> deactivated(inactive)
```

Provision, reset and deactivation are explicit authorized administration
actions. Repeating deactivation is safe. A database restart preserves the
current retrievable token, matching digest and active state. Deactivation does
not create another credential or erase the Admin-visible current value; it
makes that value authenticate as invalid until an explicit lifecycle action.

## Verification Targets

- Repository/migration proof runs its upgrade/downgrade round-trip in a
  task-owned disposable PostgreSQL database, creates one row, preserves the
  current retrievable token plus matching digest across a database restart,
  authenticates the current value and rejects wrong/inactive/old-reset tokens,
  then drops the probe database without touching operator/default rows.
- Admin-settings proof shows the same current value on repeated authorized
  reads, returns `403` to a photographer, returns no credential to invalid
  staff sessions and proves `no-store` plus URL/log/analytics redaction.
- Real-browser handoff proof manually copies the server-visible value into the
  intended kiosk profile, authenticates a real request after reload and
  Chromium restart, and proves reset requires manual replacement without a
  push, pairing or deployment-secret path.
- Boundary proof derives `spa_id` from the authenticated principal and rejects
  a client-supplied override.
- Redaction and rate-limit tests prove that credentials/digests do not enter
  URLs or logs and that configured per-token/IP limits return `429`.
- Authorization review confirms only `serving_control` commands mutate the
  table and no cross-slice direct write exists.
