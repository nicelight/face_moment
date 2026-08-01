---
description: Serving-control data and authentication rules for SpaPromoClient identity and token lifecycle.
status: active
last_updated: 2026-08-01
source_of_truth:
  - .memory-bank/domains/display-client-access.md
---
# Display Client Access

## Scope And Owner

`serving_control` owns central `SpaPromoClient` identity, СПА binding and token
lifecycle. `platform/auth` may supply a narrow authentication adapter, but
`promo`, HTTP handlers, firmware and the browser MUST NOT create, reset,
deactivate or directly mutate display-client credentials.

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
| `token_hash_sha256` | Required unique 32-byte SHA-256 digest of a high-entropy opaque token. Plaintext is never stored. |
| `active` | Required boolean; inactive credentials authenticate as invalid. |
| `created_at` | Server timestamp. |
| `rotated_at` | Nullable server timestamp updated by explicit reset. |
| `deactivated_at` | Nullable server timestamp set by explicit deactivation. |

The token MUST contain at least 32 random bytes before URL-safe encoding. A
provision/reset command may display the plaintext once to the authorized
operator and MUST NOT write it to logs, command history artifacts or the
database. Reset replaces the digest; automatic rotation and a separate
credential scheduler are outside the pilot.

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
current digest and active state. Losing a plaintext token is recovered by
explicit reset, not by reading it back.

## Verification Targets

- Repository/migration proof creates one row, authenticates it after a database
  restart, rejects wrong/inactive/old-reset tokens and never stores plaintext.
- Boundary proof derives `spa_id` from the authenticated principal and rejects
  a client-supplied override.
- Redaction and rate-limit tests prove that credentials/digests do not enter
  URLs or logs and that configured per-token/IP limits return `429`.
- Authorization review confirms only `serving_control` commands mutate the
  table and no cross-slice direct write exists.
