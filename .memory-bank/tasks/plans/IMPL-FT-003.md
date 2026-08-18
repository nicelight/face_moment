---
description: Implementation plan for sensor-triggered reference capture and attempt control in FT-003.
status: active
last_updated: 2026-08-16
---
# IMPL-FT-003 — Sensor-Triggered Capture And Attempt Control

## Goal

Deliver the browser-native `SpaPromoClient` from the central HTTPS origin: an
Admin-visible current kiosk token with manual profile handoff, recoverable
camera and client configuration, one authenticated ESP32 long-poll route, a
fresh bounded reference series, chronological first-at-most-20 BlazeFace
occurrences, one exact multipart submission, server-side admission, safe
retry/degraded behavior, one-clock markers and bounded host/recovery controls.
The feature adds no local bridge, second origin, client-side selection/search or
mandatory offline-metadata delivery path.

## Normative Basis

- [FT-003](../../features/FT-003.md): `FT-003-AC-001..020` and its governing
  `REQ-*` set.
- [System Architecture](../../architecture/system-architecture.md): AD-001,
  AD-002, AD-006, AD-009, AD-010 and `Deployment And Recovery`.
- [Boundary Map](../../contracts/boundary-map.md): capability ownership,
  display-client administration, central-origin client delivery, runtime
  boundaries and HTTP failures.
- [Display Client Access](../../domains/display-client-access.md): current
  retrievable token persistence, Admin read, manual kiosk handoff,
  authentication, lifecycle and redaction.
- [Realtime Reference Search](../../domains/realtime-search.md): owner stores,
  immutable context resolution and closed-readiness behavior.
- [Promo Attempt](../../domains/promo-attempt.md),
  [Sensor Passage API](../../contracts/sensor-passage-api.md),
  [Realtime Attempt API](../../contracts/realtime-attempt-api.md),
  [Lifecycle Map](../../states/lifecycle-map.md),
  [Client Realtime Verification](../../testing/client-realtime.md) and
  [Display And Central Restart Recovery](../../runbooks/display-and-central-restart.md).

Global Backbone Planning Revision remains `4`; this plan neither changes the
Foundation decision nor rewrites completed Foundation/FT-001/FT-002 evidence.

## Scope And Non-Goals

In scope are the smallest owner-valid server stores/adapters/pages, the exact
realtime admission boundary, plain static client slices, the protocol-equivalent
ESP32 fixture, separate managed LNA/kiosk/SSH/port controls, automatic Chromium
recovery and operator recovery evidence. Admin token read and manual kiosk
profile handoff are separate execution units; the latter consumes the former.

FT-004 owns singleton inference, deadline orchestration, proposal selection,
search, result assembly and sessions. FT-005 owns Promo rendering and success
cooldown. FT-007 owns detailed diagnostic evidence. ESP32 firmware, production
deployment, automatic token handoff/rotation, reliable delivery queues and an
offline-metadata outbox are out of scope.

## Architecture And Ownership

The accepted module graph is unchanged. `serving_control` alone mutates
display-client credentials and active-search settings; `promo` alone writes the
core Attempt. `staff_access` supplies the existing staff principal but never
owns or projects the display token. The browser owns only its managed-profile
copy. Exact slice locators are reused from the subject specs; two headings were
refined without behavior change so persistence and resolution, and Admin read
and manual handoff, can be claimed independently.

The client bundle is delivered by the existing backend/edge. Client behavior is
then layered over that shell. Managed Local Network Access is a host-policy
prerequisite of the real central-origin sensor integration; a fixture alone
cannot satisfy that dependency. The optional PRD allowance for client-only
metadata creates no implementation or proof obligation in this queue.

## Execution-Cohesive Slicing And Unique Claims

The rejected sixteen-card queue is superseded by twenty-seven independently
completable outcomes. Existing IDs retain the dominant semantic subset; new
IDs `TASK-057..067` own the extracted outcomes. One feature AC or exact
canonical obligation has exactly one implementation owner.

| Task | Tier | Wave | Direct prerequisites | Exact owned claim | Outcome |
|---|---|---|---|---|---|
| TASK-041-T3-FT-003-W1 | T3 | W1 | TASK-002 | Display Client Access `PostgreSQL Shape`, `Lifecycle And Recovery` | Persist matching retrievable token/digest and explicit lifecycle. |
| TASK-042-T2-FT-003-W1 | T2 | W1 | TASK-002, TASK-040 | Realtime Search `Active-Search Context Persistence` | Persist owner settings and isolated provision/update path. |
| TASK-043-T2-FT-003-W1 | T2 | W1 | TASK-002 | Promo Attempt `PostgreSQL Shape` | Persist the promo-owned core Attempt. |
| TASK-044-T2-FT-003-W1 | T2 | W1 | TASK-002 | Boundary Map `Central-origin client delivery` | Serve the static shell and local-advertising baseline. |
| TASK-045-T3-FT-003-W3 | T3 | W3 | TASK-057, TASK-060, TASK-043, TASK-026 | `FT-003-AC-006` | Admit and reject bounded requests server-side. |
| TASK-046-T3-FT-003-W2 | T3 | W2 | TASK-044, TASK-063 | `FT-003-AC-003` | Integrate the real managed browser with ESP32 long-poll. |
| TASK-047-T2-FT-003-W2 | T2 | W2 | TASK-044 | `FT-003-AC-004` | Traverse BlazeFace occurrences chronologically. |
| TASK-048-T2-FT-003-W2 | T2 | W2 | TASK-044 | `FT-003-AC-005` | Crop/downscale/encode occurrences. |
| TASK-049-T3-FT-003-W2 | T3 | W2 | TASK-044 | `FT-003-AC-009` | Run Chromium sandboxed as the non-privileged display user. |
| TASK-050-T2-FT-003-W3 | T2 | W3 | TASK-061, TASK-046 | `FT-003-AC-001` | Form a fresh series through the shared trigger path. |
| TASK-051-T3-FT-003-W4 | T3 | W4 | TASK-045, TASK-044 | `FT-003-AC-011` | Prove central-runtime independence and supply its check. |
| TASK-052-T2-FT-003-W4 | T2 | W4 | TASK-050, TASK-047, TASK-048, TASK-062, TASK-045, TASK-059 | `FT-003-AC-015` | Form and send the exact browser multipart request. |
| TASK-053-T2-FT-003-W5 | T2 | W5 | TASK-052 | `FT-003-AC-007` | Branch outcomes, discard stale work and permit fresh retry. |
| TASK-054-T3-FT-003-W5 | T3 | W5 | TASK-049, TASK-052 | `FT-003-AC-012` | Restart Chromium and retain kiosk configuration only. |
| TASK-055-T2-FT-003-W7 | T2 | W7 | TASK-061, TASK-046, TASK-047, TASK-053, TASK-067 | `FT-003-AC-008` | Compose named dependency failures into safe advertising. |
| TASK-056-T3-FT-003-W6 | T3 | W6 | TASK-054, TASK-051, TASK-064 | `FT-003-AC-013` | Execute the bounded recovery procedure. |
| TASK-057-T3-FT-003-W2 | T3 | W2 | TASK-041 | Display Client Access `Authentication Contract` | Authenticate display Bearer credentials uniformly. |
| TASK-058-T3-FT-003-W2 | T3 | W2 | TASK-041, TASK-004 | Display Client Access `Admin Settings Token Read` | Show every current token to authorized Admin roles only. |
| TASK-059-T3-FT-003-W3 | T3 | W3 | TASK-058, TASK-044, TASK-057 | `FT-003-AC-020` | Manually copy and retain the token in the intended kiosk profile. |
| TASK-060-T2-FT-003-W2 | T2 | W2 | TASK-042 | Realtime Search `Immutable Active-Search Context` | Resolve one immutable context and close incomplete readiness. |
| TASK-061-T2-FT-003-W2 | T2 | W2 | TASK-044 | `FT-003-AC-002` | Select, preview and recover the camera. |
| TASK-062-T2-FT-003-W2 | T2 | W2 | TASK-044 | `FT-003-AC-014` | Persist/apply the six-value JPEG quality setting. |
| TASK-063-T3-FT-003-W1 | T3 | W1 | TASK-002 | `FT-003-AC-017` | Install and inspect exact-origin LNA policy. |
| TASK-064-T3-FT-003-W1 | T3 | W1 | TASK-002 | `FT-003-AC-018` | Enforce and inspect key-only SSH administration. |
| TASK-065-T3-FT-003-W1 | T3 | W1 | TASK-002 | `FT-003-AC-019` | Keep all internal service ports private. |
| TASK-066-T2-FT-003-W5 | T2 | W5 | TASK-052 | `FT-003-AC-010` | Record one-clock ready/request/response markers. |
| TASK-067-T2-FT-003-W6 | T2 | W6 | TASK-053 | `FT-003-AC-016` | Render and replace the timed communication notice. |

Feature claim ownership is therefore exact: `AC-001..013` are owned by
`TASK-050,061,046,047,048,045,053,055,049,066,051,054,056` respectively;
`AC-014..020` are owned by `TASK-062,052,067,063,064,065,059` respectively.
Dependency-consuming integration checks may exercise a prerequisite but do not
adopt its claim.

## Advisory Expected Change Surface

- `client/`, `tests/client/`
- `src/face_moment/serving_control/`, `tests/serving_control/`
- `src/face_moment/promo/`, `tests/promo/`
- `src/face_moment/entrypoints/backend.py`,
  `src/face_moment/entrypoints/realtime.py`
- `migrations/versions/`, `deploy/Caddyfile`
- `deploy/kiosk/`, `deploy/chromium/policies/managed/`,
  `deploy/ssh/`, `deploy/systemd/user/spa-promo-client.service`
- focused `scripts/check-*.sh` host/recovery checks

These paths remain advisory and non-exhaustive; each executor preflight resolves
the actual source-owned surface without crossing the task's hard forbidden
scope.

## Tests, Gates And UAT

- Python tasks run configured mypy and their focused project-native pytest;
  every task runs `node scripts/mb-lint.mjs`.
- Browser behavior uses installed `playwright cli` against the real central
  origin, with disposable browser profiles and protocol-equivalent fixtures.
- Credential proof separately covers persisted matching token/digest,
  authentication, Admin authorization/read/redaction and the real manual kiosk
  handoff/restart/reset sequence.
- Sensor integration consumes the completed exact-origin LNA policy and proves
  real-browser CORS/OPTIONS/Bearer/one-poll behavior.
- Multipart formation, server admission and monotonic-marker evidence remain
  separate; the integrated request may exercise all three without duplicating
  claim ownership.
- Host proof uses separate read-only checks for sandbox identity, LNA policy,
  SSH authentication and externally reachable ports.
- Under the 2026-08-18 local-development decision, real pilot-host/server
  evidence is deferred and is not a current queue gateway. The local queue
  uses source/static and runnable Linux Compose/browser checks; effective SSH,
  no-display-host, external-observer and operator-recovery evidence remains a
  later acceptance follow-up when the real server exists.
- `TASK-051` may create its own disposable credential, serving context, Attempt
  and Photo transition, then must clean them up; it never mutates or deletes
  operator/default state. This replaces the contradictory no-durable-state
  invariant.
- No task implements or must prove offline-metadata retention, expiry, replay or
  delivery.
- Tier-routed `/verify` applies to every task; each T3 additionally requires
  per-task `/red-verify`. Feature completion later requires
  `/red-verify --feature FT-003`.

## Constitution Constraints And Invariants

- Preserve the modular monolith, one schema/Base/Alembic stream, private
  PostgreSQL/MinIO topology and HTTPS-only public boundary.
- The server retains each current display token and matching digest; only the
  authorized `no-store` Admin read and the kiosk Authorization header reveal or
  carry the value. Provision/reset output is non-secret.
- `spa_id` derives from the authenticated display principal; no body override
  exists. Sensor and display credentials remain distinct.
- No local bridge/server/WebSocket, client ranking/search, durable sensor queue,
  automatic token handoff or reliable offline delivery mechanism is added.
- Stale work never replaces a newer state; retry uses a fresh series;
  non-success starts no success cooldown.
- Chromium remains sandboxed/non-privileged, SSH remains key-only and internal
  service ports remain private under separate owners.

## Definition Of Done

All twenty-seven indexed tasks independently satisfy their exact owned claims
and tier obligations, every `FT-003-AC-001..020` has one and only one task
owner, every root retains the completed Foundation gate directly or
transitively, the review-directed dependencies and disposable-probe semantics
hold, and a fresh `/review-tasks-plan FT-003` can evaluate the queue at Global
Backbone Planning Revision `4`.
