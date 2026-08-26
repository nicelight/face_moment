---
description: Implementation plan for QR phone continuation and personalized-session expiry in FT-006.
status: active
---
# IMPL-FT-006 — QR Phone Continuation

## Goal

Allow a participant to continue the issued Promo result on a phone through the
same QR session, with one shared browser-access lifetime, ordered available
teaser delivery, explicit activity and strict expiry isolation.

## Normative basis

- [FT-006](../../features/FT-006.md): `FT-006-AC-001..005` and governing
  `REQ-UX-002`, `REQ-UX-003`, `REQ-SEC-001` and `REQ-ARCH-001`.
- [System Architecture](../../architecture/system-architecture.md):
  capability ownership, one write owner and session-wide private delivery.
- [Boundary Map](../../contracts/boundary-map.md): module inventory,
  Participant Promo, private provider projections, public delivery and HTTP
  failure rules.
- [QR Continuation API](../../contracts/qr-continuation-api.md): exact ticket,
  cookie, phone, media, activity, expiry and security contract.
- [Promo Attempt](../../domains/promo-attempt.md): result-session storage,
  QR browser-access state and historical Photo references.
- [Lifecycle Map](../../states/lifecycle-map.md): independent display, first-
  open and browser-idle lifetimes and hard-purge continuity.
- [Client Realtime Verification](../../testing/client-realtime.md): phone
  continuation, isolation, public-boundary and deferred physical-pilot proof.

Global Backbone Planning Revision remains `4`. Foundation final gate
`TASK-002-T2-FT-000-W0` is `done`; every FT-006 task retains it directly or
transitively.

## Scope and non-goals

In scope are the session-wide browser-access columns and repository rules,
public QR exchange, phone shell and protected session/media/activity reads,
local expiry cleanup, ordered hard-purged-media skip, public-route rate
limiting, purchase CTA navigation and deterministic real-browser continuation
proof. Physical-phone continuation and final HTTPS/private-topology/external-
CTA observations are post-deployment acceptance.

FT-004 retains result-session issuance and immutable result truth. FT-005
retains display rendering, display acknowledgement, display/cooldown timers
and display-expiry evidence production. The target purchase/selfie-search page
is only navigated to; it is not implemented. No participant account,
per-device grant, refresh token, access table, media cache, public MinIO route,
expiry scheduler, cleanup job or second client origin is added.

## Architecture and ownership

`promo` is the primary owner for all three outcomes under
`src/face_moment/promo/`. Backend HTTP wiring and the phone shell are adapters;
they do not own session state or foreign writes. The crossed accepted edges
are:

- `promo -> inventory|processing` through Boundary Map `Participant Promo` for
  session-scoped Photo availability and private preview bytes;
- `promo -> serving_control` only for the accepted СПА-name projection;
- public phone browser -> backend through the QR Continuation API.

The state task uses the existing `face_moment.promo_sessions` row and one
linear Alembic stream. The phone task reads immutable session arrays and
provider projections; soft deletion remains readable, hard-purged media is
skipped in issued order, and no provider state is written. The final task is a
read-only production/UAT decision with no application ownership.

## Execution-cohesive slicing and claims

| Task | Tier | Wave | Direct prerequisites | Exact owned claim | Outcome |
|---|---|---|---|---|---|
| `TASK-080-T3-FT-006-W1` | T3 | W1 | Foundation gate and FT-004 result-session seam | `promo-attempt.md#shared-browser-access-persistence` | One durable session-wide QR browser-access state with atomic first-open, repeated-scan/activity updates and irreversible derived idle expiry. |
| `TASK-081-T3-FT-006-W2` | T3 | W2 | `TASK-080`, FT-004 session and FT-005 preview/display-expiry seams | `FT-006-AC-001..004` | Same-session multi-phone continuation, configured public-route limiting, protected media/activity and deterministic browser isolation; physical join is deferred. |
| `TASK-082-T3-FT-006-W3` | T3 | W3 | `TASK-081` | `FT-006-AC-005` | Final deployed HTTPS/private-topology and external-CTA acceptance. |

The state task is independently proved through migration/repository and
concurrent-clock fixtures under its exact technical claim. Public transport,
rate limiting, phone rendering, browser isolation and physical continuation
remain one participant-visible result. The final production-only topology/CTA
checks remain one highest-wave task with no dependents.

## Advisory expected change surface

- `migrations/versions/0014_promo_browser_access.py` or the executor-selected
  next linear revision;
- `src/face_moment/promo/session.py`, `src/face_moment/promo/attempt.py`, and
  a minimal promo continuation/application adapter;
- `src/face_moment/inventory/promo_media_projection.py` and
  `src/face_moment/processing/preview_projection.py` only for accepted
  read-only provider projections;
- `src/face_moment/entrypoints/backend.py` and the existing public client
  binding;
- `src/face_moment/infrastructure/settings.py` for positive phone public-rate
  limit/window settings, reusing the existing single-backend limiter pattern;
- `client/phone.html`, `client/phone.js`, `client/styles.css` or equivalent
  existing client paths selected under the same phone-shell owner;
- focused `tests/promo/`, `tests/client/` and task-owned browser/UAT
  artifacts under `.tasks/TASK-081-T3-FT-006-W2/` plus final topology/CTA
  receipts under `.tasks/TASK-082-T3-FT-006-W3/`.

These paths are advisory and non-exhaustive. Exact filenames remain executor
discretion when ownership, public boundary and proof path stay unchanged.

## Tests, gates and UAT

- State implementation uses isolated disposable PostgreSQL fixtures, controlled
  server time, concurrent first-open/repeated-scan/activity attempts, restart
  persistence, null-pair constraints and safe cleanup.
- Phone implementation covers exact endpoint paths/shapes, cookie attributes,
  passive reads, explicit activity, ordered teaser availability, soft-delete
  continuity, every hard-purge combination, exact 30-/60-minute boundaries,
  no-store/no-referrer, redirection and rendered-state clearing.
- Security fixtures cover forged/foreign/late tickets and cookies, log/query
  redaction, positive rate-limit settings, client-IP separation and `429` on
  every phone route, plus request-overridable purchase targets.
- TASK-081 uses `playwright cli` on the central origin to retain the
  `/q -> /phone` cookie/read/activity/expiry flow, rendered-state clearing,
  `location.replace`, URL/referrer/cache isolation and post-expiry rejection
  with deterministic disposable session/API fixtures. It consumes the
  FT-005 display-expiry contract for the local join; scanning that exact QR on
  an authorized representative phone is deferred to post-deployment acceptance
  and compares the same session content when the pilot environment exists.
- Final UAT inspects only the deployed HTTPS/private-service topology and the
  configured external CTA target without implementing the target page or
  repeating same-session/expiry proof.
- Each implementation task runs focused pytest/Node tests, mypy and
  `node scripts/mb-lint.mjs`; final acceptance runs the focused regression
  checks plus redacted production/UAT evidence.

## Constitution constraints and invariants

- Keep the modular monolith, accepted capability graph, one owner per mutable
  invariant and KISS scope.
- Store only the QR ticket digest; plaintext ticket/cookie, personalized
  payloads and raw storage identities never enter logs or retained artifacts.
- First-open and idle expiry use strict server-time boundaries; a valid repeated
  scan and explicit activity each advance the one shared last-seen timestamp,
  while passive reads, media loads and timers never extend access; expired
  access cannot be revived.
- One shared browser state row serves all phones; no per-device grants,
  scheduler or stored expired state exists.
- Session identity, authoritative date, ordered issued teaser IDs and `N` are
  immutable. Soft delete remains readable; hard purge skips unavailable issued
  media without replacement, rebuild or `N` recalculation.
- Display expiry, cooldown and phone access remain independent and never call
  one another's invalidation path.

## Definition of done

The implementation cards satisfy their exact claims and T3 evidence
obligations; `TASK-082` remains the separate planned `Production acceptance:`
card until the deployed edge and evaluator exist; every `FT-006-AC-001..005` is
owned exactly once; task-relevant modules, edges and canonical headings match
the Boundary Map; every task retains the Foundation dependency; and fresh
planning review can approve the queue at Planning Revision `4` without
implementation guesses.
