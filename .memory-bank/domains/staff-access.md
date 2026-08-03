---
description: Canonical staff identity, role, password, session and CSRF data contract.
status: active
last_updated: 2026-08-03
source_of_truth:
  - .memory-bank/domains/staff-access.md
---
# Staff Access

## Scope And Owner

`platform/auth` owns staff principals, password verification and server
sessions. It authenticates; the target capability still authorizes every
business action. FT-001 uses this boundary for the photographer uploader and
does not create a generic IAM/RBAC service.

## PostgreSQL Shape

### `face_moment.staff_users`

| Field | Contract |
|---|---|
| `id` | Server-generated UUID primary key. |
| `username` | Required case-normalized unique login name. |
| `password_hash` | Required Argon2id encoded hash; plaintext is never stored. |
| `role` | Exactly `photographer`, `operator` or `developer`. |
| `active` | Required boolean; inactive users cannot authenticate. |
| `created_at` | Server timestamp. |
| `password_changed_at` | Server timestamp updated by explicit reset. |
| `deactivated_at` | Nullable server timestamp set by explicit deactivation. |

### `face_moment.staff_sessions`

| Field | Contract |
|---|---|
| `id` | Server-generated UUID primary key. |
| `staff_user_id` | Required foreign key to `staff_users`; no cross-capability relation. |
| `token_hash_sha256` | Required unique 32-byte SHA-256 digest of the opaque session token. |
| `csrf_token_hash_sha256` | Required 32-byte SHA-256 digest of the synchronizer token. |
| `created_at`, `expires_at` | Server timestamps implementing one configured positive absolute TTL. |
| `revoked_at` | Nullable server timestamp; logout, reset and deactivation revoke sessions. |

Both plaintext tokens contain at least 32 random bytes before URL-safe
encoding and are returned only through secure browser cookies. They never enter
database rows, URLs or application logs.

## Browser Session Contract

- Successful login sets `fm_staff_session` as `Secure`, `HttpOnly`,
  `SameSite=Lax`, path `/`, and `fm_staff_csrf` as `Secure`,
  `SameSite=Lax`, path `/`. Both use the same absolute expiry; the CSRF cookie
  is readable only so the browser can echo it in `X-CSRF-Token`.
- Every unsafe authenticated request MUST present the session cookie, CSRF
  cookie and matching `X-CSRF-Token`; the server hashes and compares the CSRF
  token to the owning session row. Missing or mismatched CSRF returns `403`.
- Missing, malformed, expired, revoked, reset-owner or inactive-owner sessions
  return `401` without revealing the cause. Expiry is absolute and is not
  extended by requests.
- A principal contains only `staff_user_id`, `username` and `role`. FT-001
  authorizes Photo admission only for `photographer`; an authenticated wrong
  role receives `403`.
- Login is rate-limited by normalized username plus IP. Authenticated upload is
  rate-limited by session/principal plus IP under the API contract. Limits are
  deployment-configured positive values; deterministic tests set explicit
  values. The one-backend pilot uses no distributed limiter or queue.

## Provisioning And Lifecycle

An owner-backed CLI/application command supports provision, password reset and
deactivation. It accepts secrets without echoing or logging them, uses Argon2id,
and never exposes stored hashes. Reset and deactivation revoke all current
sessions for that user; repeated deactivation is safe. Reactivation, self-
registration, password recovery email, OAuth, MFA and automatic credential
rotation are outside the pilot.

## Verification Targets

- Migration/repository proof persists only Argon2id password hashes and SHA-256
  token digests, survives database restart, and never emits plaintext secrets.
- Boundary proof covers login success, generic login failure, absolute expiry,
  logout, reset/deactivation revocation, cookie attributes and CSRF rejection.
- Authorization proof derives the photographer principal from the session and
  returns `403` for an authenticated non-photographer without moving business
  authorization into `platform/auth`.
- Deterministic rate-limit and redaction probes prove `429` behavior and absence
  of passwords, cookies, headers, plaintext tokens and token digests in URLs or
  logs.

