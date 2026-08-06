---
description: Implementation plan for bounded sensor-triggered browser capture and realtime admission in FT-003.
status: active
last_updated: 2026-08-06
---
# IMPL-FT-003 — Sensor-Triggered Capture And Admission

## Goal

Deliver one central-origin `SpaPromoClient` path in which a physical or test
trigger creates a fresh bounded reference series, submits the first at most 20
chronological BlazeFace occurrences through the exact authenticated multipart
boundary, keeps local advertising safe through failure, and recovers the
managed browser and intact-volume central runtime through a verified operator
procedure.

## Normative Basis

- [FT-003](../../features/FT-003.md): exact `FT-003-AC-001..013` closure.
- [Requirements](../../requirements.md): `REQ-CAP-001..002`, `REQ-UX-004`,
  `REQ-PERF-001`, `REQ-DIAG-001`, `REQ-REL-001`, `REQ-REL-003`,
  `REQ-SEC-001..002` and `REQ-ARCH-001`.
- [System architecture](../../architecture/system-architecture.md): AD-001,
  AD-002, AD-006, AD-007, AD-009 and AD-010 plus Deployment And Recovery.
- [Boundary map](../../contracts/boundary-map.md): `Participant Promo`,
  external/runtime, authentication/delivery, shared PostgreSQL and HTTP failure
  contracts.
- [Sensor Passage API](../../contracts/sensor-passage-api.md): exact ESP32
  long-poll, event, CORS, authentication and failure contract.
- [Realtime Attempt API](../../contracts/realtime-attempt-api.md): exact
  multipart, admission, validation, idempotency and typed outcome contract.
- [Display Client Access](../../domains/display-client-access.md): central
  display-token persistence and authentication lifecycle.
- [Promo Attempt](../../domains/promo-attempt.md): core Attempt persistence,
  immutable admission snapshot and task-applicable transitions.
- [Lifecycle map](../../states/lifecycle-map.md): automatic attempt/display and
  client restart behavior.
- [Client realtime verification](../../testing/client-realtime.md):
  deterministic browser, boundary, timing and recovery evidence.
- [Recovery runbook](../../runbooks/display-and-central-restart.md): exact
  operator preconditions, limits, steps and success checks.

## Constitution Constraints

- Preserve one browser-native Chromium route, one ESP32 long-poll, one
  synchronous realtime request and the existing one-release server runtime.
- Do not introduce a bridge, local server, WebSocket, discovery/pairing,
  detector abstraction, second detector, reliable client outbox, waiter queue
  or additional deployment service.
- `SpaPromoClient` owns local capture/proposal/display state. On the server,
  `promo` owns admission and core Attempt; `serving_control` owns display-token
  state; transport/composition code owns neither business flow nor foreign
  writes.
- T2/T3 tasks use full protocol and independent verification. Every T3 task
  also requires per-task semantic verification; after all tier obligations
  pass, the explicit lifecycle owner records the closure decision.

## Scope

### In Scope

- Central-origin browser bundle, local advertising state, camera list/preview/
  selection, ring buffer, trigger lock, fresh retry and failure notice.
- BlazeFace Full-range browser runtime and separate versioned model asset;
  chronological first-20 traversal, accepted crop/JPEG rules, exact quality
  configuration, multipart serialization, request-manifest timing fields and
  the distinct client-local ready-series/request-send/response-receipt moments.
- ESP32 firmware/protocol fixture for the exact authenticated mDNS long-poll,
  strict event shape, CORS/OPTIONS and secret redaction; managed Chromium Local
  Network Access policy and browser integration.
- `serving_control` display-client token hash/lifecycle and `promo` core Attempt
  persistence on the current linear migration stream.
- Exact realtime authentication, body limit, multipart validation,
  pre-admission failures, admitted zero-proposal/idempotent outcomes and typed
  downstream adapter response without implementing FT-004 search/result logic.
- Sandboxed non-privileged Chromium service, key-only administrative SSH,
  private port topology, automatic reachable-origin browser recovery, central
  role independence and the documented intact-volume recovery procedure.

### Non-goals

- Server-side proposal selection, inference-slot/search/deadline orchestration,
  candidate pools, thresholding, four-teaser result assembly or restart
  interruption owned by FT-004.
- Promo render/acknowledgement/final copy/cooldown owned by FT-005, and QR/
  phone/session behavior owned by FT-006.
- FT-007 diagnostic UI/evidence management, reliable client outbox, detailed
  retention, Calibration, inventory operations or production deployment.
- Full/downscaled reference-frame upload, local ranking/top-5/quality gate,
  tracking/clustering/deduplication, YuNet implementation, TensorFlow.js,
  generic detector/runtime abstraction, model OTA or dynamic sensor discovery.

## Architecture And Ownership

`SpaPromoClient` is the accepted external/runtime party, with expected project
source root `clients/spa_promo_client/`. It owns browser-local state and calls
only the canonical ESP32 and realtime boundaries. `firmware/passage_sensor/`
owns the matching ESP32 endpoint. These repository placements do not add a
server capability or graph edge.

For server admission, the primary owning slice is `promo` at
`src/face_moment/promo/`. It authenticates through the public
`serving_control` display-client boundary, persists the core Attempt and invokes
a typed `processing` application port. The actual FT-004 query/search
implementation remains absent. FastAPI handlers and
`src/face_moment/entrypoints/` adapt and compose only; they do not write
display-client or Attempt repositories directly.

## Cohesive Strategy

1. Build the browser-local capture/proposal state machine behind deterministic
   camera, detector, sensor and realtime adapters; prove crop/order/request and
   degraded-advertising behavior without credentials or physical deployment.
2. Implement the exact ESP32 firmware boundary and connect it to the browser
   through managed Local Network Access and a disposable sensor secret.
3. Add display-client/core-Attempt persistence and the exact realtime admission
   adapter on the existing server substrate, using fake downstream processing
   so no FT-004 behavior is pulled forward.
4. Compose the central-origin client and host controls, then prove runtime
   independence, automatic Chromium recovery and the canonical runbook from
   isolated and authorized physical/test state.

## Task Graph

| Task | Tier | Initial status | Depends on | Cohesive outcome |
|---|---|---|---|---|
| [TASK-007-T2-FT-003-W1](../TASK-007-T2-FT-003-W1.task.json) | T2 | planned | TASK-002-T2-FT-000-W0 | Build and prove bounded browser capture, proposal preparation, multipart construction and safe client state. |
| [TASK-008-T3-FT-003-W2](../TASK-008-T3-FT-003-W2.task.json) | T3 | planned | TASK-007-T2-FT-003-W1 | Deliver the authenticated ESP32 long-poll and managed-browser LAN integration without a bridge or secret leakage. |
| [TASK-009-T3-FT-003-W2](../TASK-009-T3-FT-003-W2.task.json) | T3 | planned | TASK-003-T2-FT-001-W1 | Deliver central display-client authentication, core Attempt persistence and exact bounded realtime admission without FT-004 search. |
| [TASK-010-T3-FT-003-W3](../TASK-010-T3-FT-003-W3.task.json) | T3 | planned | TASK-004-T3-FT-001-W2, TASK-005-T2-FT-002-W2, TASK-008-T3-FT-003-W2, TASK-009-T3-FT-003-W2 | Compose and prove the central-origin kiosk, server/display independence, automatic Chromium recovery and intact-volume runbook. |

The Foundation final gate is direct for TASK-007 and transitive for all later
tasks. TASK-009 waits for FT-001's owner-backed serving/database seam; TASK-010
waits for the authenticated backend and durable Photo transition needed by
`FT-003-AC-011`. No task depends on FT-004..FT-006, avoiding a feature cycle.

## Acceptance Closure

| Feature AC | Owning task(s) | Planned proof |
|---|---|---|
| `FT-003-AC-001` | TASK-007 + TASK-008 + TASK-010 | Deterministic and integrated physical/test trigger matrix proves one shared path, distinct source, fresh series and overlap lock. |
| `FT-003-AC-002` | TASK-007 + TASK-010 | Browser/device fixtures and site UAT prove list/preview/explicit selection, reconnect/reselection, advertising and pre-buffer downscale. |
| `FT-003-AC-003` | TASK-008 + TASK-010 | Firmware/browser contract probes prove the exact route; final integration repeats distinguishable endpoint, continuous-poll, event, LNA, CORS/OPTIONS/Bearer, redaction and forbidden-topology results. |
| `FT-003-AC-004` | TASK-007 | More-than-20/repeated-person fixtures and dependency scan prove BlazeFace order/stop and forbidden local authority/abstractions. |
| `FT-003-AC-005` | TASK-007 | Geometry/JPEG/metadata and quality persistence/apply-next fixtures cover every accepted value and boundary. |
| `FT-003-AC-006` | TASK-007 + TASK-009 + TASK-010 | Client serialization and server admission probes prove the contract; final integration repeats distinguishable multipart structure, manifest-only zero admission, exact `20 MiB` boundary and core Attempt relationship results. |
| `FT-003-AC-007` | TASK-007 + TASK-010 | Timeout/network/late-response and fresh-retry integration prove state order and no success cooldown. |
| `FT-003-AC-008` | TASK-007 + TASK-008 + TASK-010 | Named dependency failures keep advertising usable, expose recoverable feedback, time/replace the communication notice and keep best-effort client-only offline metadata non-blocking. |
| `FT-003-AC-009` | TASK-009 + TASK-010 | Rate/private-boundary proof plus effective host process/SSH/port topology proves the kiosk/admin controls. |
| `FT-003-AC-010` | TASK-007 + TASK-009 + TASK-010 | Client evidence distinguishes ready-series processing start, request-send start and response receipt on one monotonic clock; server evidence separately persists the three accepted request-manifest timing fields, and integration correlates both without implementing the later diagnostic UI or joint 20-attempt result. |
| `FT-003-AC-011` | TASK-010 | No-display central start/operation proves role readiness, authenticated backend, queued Photo transition and fresh realtime admission. |
| `FT-003-AC-012` | TASK-010 | Forced Chromium termination in advertising and active/result state proves automatic reachable-origin replacement, reload, advertising and state discard. |
| `FT-003-AC-013` | TASK-010 | Operator follows only the canonical runbook for both named failures and retains its checks and accepted limits. |

Every governing REQ maps to at least one task. Direct canonical links are scoped
to the claims each card changes; linking a subject spec does not pull FT-004+
claims into this queue.

## Advisory Expected Change Surface

### TASK-007 browser capture/proposal core

- `clients/spa_promo_client/` for the central-origin browser source, versioned
  BlazeFace asset and deterministic browser tests;
- `pyproject.toml` and/or one client-local package/build manifest only for the
  minimum compatible browser build/test tooling;
- `tests/` and `scripts/verify-client-realtime.sh` for deterministic fixtures.

### TASK-008 ESP32 and browser LAN boundary

- `firmware/passage_sensor/` for one configured ESP32 firmware target;
- `clients/spa_promo_client/` for the sensor adapter/configuration UI;
- `deploy/chromium/policies/` for the managed central-origin LNA policy;
- `tests/` and `scripts/verify-sensor-passage.sh` for firmware/protocol/browser
  evidence with disposable secrets.

### TASK-009 central admission

- `migrations/versions/` for one revision from the then-current linear head;
- `src/face_moment/serving_control/` for display-client identity/token lifecycle;
- `src/face_moment/promo/` for core Attempt and admission orchestration;
- `src/face_moment/entrypoints/realtime.py` and infrastructure settings for
  composition/configuration only;
- `deploy/Caddyfile`, `tests/` and `scripts/verify-realtime-admission.sh` for
  exact pre-admission/body/auth/idempotency evidence.

### TASK-010 host and recovery integration

- `clients/spa_promo_client/` and the backend static-delivery adapter required
  to load it from the central HTTPS origin;
- `deploy/systemd/user/spa-promo-client.service`,
  `deploy/chromium/policies/` and `deploy/ssh/sshd_config.d/` for source-managed
  host controls;
- `compose.yaml`, `deploy/Caddyfile`, `tests/`,
  `scripts/check-ft003-recovery.sh` and `scripts/verify-client-recovery.sh` for
  isolated/runtime/site proof;
- the canonical recovery runbook only where verified command names/checks need
  reconciliation.

These paths are advisory and non-exhaustive. Exact owner-local filenames and
the smallest browser/firmware tooling compatible with the accepted runtimes
remain executor discretion; the roots, public contracts and deployment
identities do not.

## Gates And UAT

Applicable project gates are:

- `docker compose config --quiet`
- `docker compose build`
- `docker compose run --rm --no-deps backend python -m mypy src/face_moment`
- `docker compose run --rm --no-deps backend python -m pytest tests/test_foundation.py tests/unit`
- `bash scripts/verify-client-realtime.sh`
- `bash scripts/verify-sensor-passage.sh`
- `bash scripts/verify-realtime-admission.sh`
- `bash scripts/verify-client-recovery.sh`

Each task emits only the gate it creates or extends. Verification uses unique
disposable Compose/browser profiles, test tokens, firmware/protocol fixtures,
owned ports/object prefixes and cleanup. Physical UAT uses a dedicated test
ESP32/camera and the managed display host; it never flashes or changes an
unapproved production device or deletes primary data.

## Invariants And Stop Conditions

- The browser never ranks, recognizes, quality-gates, tracks, clusters,
  deduplicates or searches proposals and never silently activates YuNet.
- Transport/auth/validation/readiness rejection creates no core Attempt;
  admitted zero-proposal creates one. Client `spa_id` and secrets never enter
  the manifest, URL or logs.
- `promo` and `serving_control` remain the only server writers of their owned
  state; result selection/session/search stays outside FT-003.
- Browser failure cannot stop central roles. Recovery discards personalized
  result/frame/QR/session/Attempt state without resetting managed display or
  sensor credentials; it never disables Chromium sandbox, broadens the
  `display` user's privilege, deletes volumes, promises offline start or claims
  sole-primary-loss recovery.
- Any need to change the endpoint/manifest/outcome, component ownership,
  security model, accepted runtime topology, task dependencies or FT-004+
  boundary stops and routes back to `/feature-to-tasks FT-003` or
  `/spec-design` for a shared/global change.

## Definition Of Done And Handoff

- All four tasks satisfy their tier gates and independent verification; each
  T3 card additionally has semantic-pass, after which the explicit lifecycle
  owner records the closure decision.
- Every `FT-003-AC-001..013` and governing REQ has distinguishable claim-linked
  evidence, including runbook execution and recovery limits.
- Reconcile task/feature/RTM state at the W3/feature boundary through
  `/mb-sync`.
