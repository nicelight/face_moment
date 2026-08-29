---
description: Implementation plan for truthful Promo presentation, display outcome and visible-QR acceptance in FT-005.
status: active
last_updated: 2026-08-29
---
# IMPL-FT-005 — Promo Presentation And Display Outcome

## Goal

Turn an exact successful realtime result into one truthful four-teaser Promo,
keep every partial or failed path on usable local advertising, persist the
authenticated post-render display outcome, apply independent display/cooldown
lifetimes and prove the same-twenty-Attempt visible/scannable QR gate.

## Normative Basis

- [FT-005](../../features/FT-005.md): `FT-005-AC-001..005` and governing
  `REQ-UX-001`, `REQ-UX-003`, `REQ-UX-004`, `REQ-PERF-001`, `REQ-REL-001`,
  `REQ-SEC-001` and `REQ-ARCH-001`.
- [System Architecture](../../architecture/system-architecture.md): AD-001,
  AD-002, AD-006, AD-008..011 and capability ownership.
- [Boundary Map](../../contracts/boundary-map.md): module inventory, dependency
  graph, capability application boundaries, Participant Promo, central-origin
  client delivery, authentication/data delivery and HTTP failures.
- [Promo Display API](../../contracts/promo-display-api.md): exact config,
  authenticated teaser-media, display acknowledgement, failures and client
  outcome rules.
- [Realtime Attempt API](../../contracts/realtime-attempt-api.md): exact four-
  teaser result and typed non-success input.
- [Promo Attempt](../../domains/promo-attempt.md): existing Attempt/session
  storage and display outcome; no FT-005 migration or historical backfill.
- [Display Client Access](../../domains/display-client-access.md),
  [Photo Processing](../../domains/photo-processing.md),
  [Lifecycle Map](../../states/lifecycle-map.md), [Testing Router](../../testing/index.md)
  and [Client Realtime Verification](../../testing/client-realtime.md).

Global Backbone Planning Revision remains `4`. Foundation final gate
`TASK-002-T2-FT-000-W0` is `done`; every FT-005 task retains it transitively.

## Scope And Non-Goals

In scope are same-origin authenticated teaser delivery, strict complete-result
rendering, local QR generation, exact Promo copy, safe advertising fallback,
post-render acknowledgement, independent result-display/cooldown configuration
and deterministic implementation proof. The controlled physical visible-QR
verdict is post-deployment production acceptance, not an implementation gate.

FT-004 retains search, assembly, result-session publication and server-
correctness ownership. FT-006 owns ticket exchange, phone session/media reads
and final independent phone-session lifetime proof. This plan adds no public
MinIO/presigned path, media cache, replacement selection, acknowledgement
outbox, scheduler, retry queue, settings framework, second client origin or QR
service. No behavior JSON is needed because the exact contract fixtures and
five stable ACs remove material ambiguity.

## Development-Stage Checkpoint (Non-Closure)

- For the current scoped recovery, the accepted intermediate outcome is the
  independently verified Attempt 2 provider-edge repair: zero direct provider
  queries, no forbidden provider imports and authenticated SPA scope. Evidence
  is retained in
  `.tasks/TASK-076-T3-FT-005-W1/attempt-2-verifier-evidence.md` and
  `.tasks/TASK-076-T3-FT-005-W1/attempt-2-provider-edge-green.md`.
- This checkpoint records a bounded development-stage result only. It does
  not close `FT-005-AC-001` or `FT-005-AC-005`, does not change their REQ/AC
  targets, and does not change task identity, tier, wave, dependencies or
  lifecycle.
- QR physical-scan, distinct real four-photo/no-watermark and representative-
  phone evidence are unavailable and are not required for development closure
  because real photos are not available before the ingest/processing pipeline
  is complete. They remain post-deployment pilot obligations; development
  closure requires four distinct issued disposable references and programmatic
  QR decoding. A shared disposable placeholder is acceptable for the local
  rendering flow but is not proof of distinct real media or no-watermark
  content.

## Architecture And Ownership

`promo` is the primary capability owner for all four outcomes. Server work
stays under `src/face_moment/promo/`; the existing backend entrypoint only binds
the public HTTP adapter. The crossed accepted boundaries are:

- central-origin `SpaPromoClient -> backend` through the Promo Display API;
- `promo -> inventory|processing` through Boundary Map `Participant Promo` for
  session-scoped Photo availability and private preview projections;
- `promo -> serving_control` only for the existing display-principal
  authentication projection. `promo` projects its own two deployment-backed
  display values through the Display Configuration endpoint.

The client remains the external presentation party under `client/`. HTTP
handlers, infrastructure, generic helpers and the composition root own no
business transition and write no foreign state. `promo` never reads raw MinIO
keys into public responses or mutates Photo, processing or serving-control
state; provider projections never mutate Promo sessions or Attempts.
`diagnostics` remains a compatible read consumer of the existing core Attempt
projection: FT-005 adds no column or state vocabulary, so propagation stops at
that accepted boundary without diagnostic code changes.

## Execution-Cohesive Slicing And Unique Claims

| Task | Tier | Wave | Direct prerequisites | Exact owned claim | Outcome |
|---|---|---|---|---|---|
| `TASK-076-T3-FT-005-W1` | T3 | W1 | completed derivative, client-shell/outcome/fallback, display-auth and result-session seams | `FT-005-AC-001`, `FT-005-AC-005` | Complete authenticated four-teaser Promo/QR or safe advertising with no partial success/cooldown. |
| `TASK-077-T3-FT-005-W2` | T3 | W2 | `TASK-076`, completed one-clock markers | `FT-005-AC-003` | End-to-end authenticated post-render report and durable effective display status using existing columns. |
| `TASK-078-T3-FT-005-W2` | T3 | W2 | `TASK-076` | `FT-005-AC-004` | Independent positive display/cooldown config and local expiry without QR-session invalidation. |
| `TASK-079-T3-FT-005-W3` | T3 | W3 | all FT-005 implementation tasks | `FT-005-AC-002` | Final same-twenty target-screen, one-clock and representative-phone independent QR/latency `19/20` verdict. |

Authenticated media and render/fallback remain one outcome because a missing or
undecodable teaser must prevent the same participant-visible Promo. Client
report and server transition remain one outcome because neither half alone can
establish `confirmed`. Config projection and client timers remain one outcome
because the two independent positive values jointly define presentation and
trigger availability. Production-only checks remain one final task with no
dependents.

FT-004 separately owns the server-result correctness gate. FT-005 builds
against the accepted v1 response and completed durable session seams without
adopting upstream claims. The production evaluator uses the same 20 Attempt
identities as the controlled corpus, but FT-005 reports only its independent
QR/latency count: it does not filter on correctness, calculate a joint
intersection or joint pass set, consume FT-004 correctness evidence, or depend
on `TASK-075-T3-FT-004-W5`.

## Advisory Expected Change Surface

- `client/promo-display.js`, `client/app.js`, `client/index.html`,
  `client/styles.css` and a minimal release-owned local QR implementation.
- `src/face_moment/promo/display_media.py`,
  `src/face_moment/promo/display_outcome.py`,
  `src/face_moment/promo/http.py`, `src/face_moment/promo/session.py` and
  `src/face_moment/promo/__init__.py`; the existing realtime response serializer
  may project the opaque session-scoped media reference without changing the
  accepted response shape.
- owner projections under `src/face_moment/inventory/` and
  `src/face_moment/processing/` only where the accepted Participant Promo edge
  requires availability and preview bytes.
- `src/face_moment/infrastructure/settings.py` and the existing backend/realtime
  composition binding needed to project one consistent display duration.
- focused `tests/client/` and `tests/promo/` fixtures plus task-owned physical
  evidence under `.tasks/TASK-079-T3-FT-005-W3/`.

These paths are advisory and non-exhaustive. Exact new filenames remain
executor discretion when the owner/root/public boundary and proof path stay
unchanged. No Alembic revision is expected.

## Tests, Gates And UAT

- Every implementation task runs configured Python mypy, focused pytest and
  Node client tests plus `node .memory-bank/scripts/mb-lint.mjs`.
- Authenticated API fixtures cover exact JSON, Bearer scope, token-derived СПА,
  `no-store`, rate limiting, redaction and `401|404|409|422|429|503|5xx` paths.
- Media fixtures prove exactly the four issued low-quality no-watermark JPEGs,
  and unknown/foreign/hard-purged/undecodable cases with no replacement,
  partial Promo or `N` mutation.
- `TASK-076` uses `playwright cli` to load the central-origin client at logical
  1920x1080 and prove exact copy, four unique disposable teaser fixtures,
  high-contrast local QR with programmatic decode, complete-result gating,
  advertising fallback, replaceable communication notice, optional-asset
  silence and no failure cooldown. It retains the CLI transcript plus logical-
  target screenshots/video/trace under its task directory. The authorized
  representative-phone scan is deferred to post-deployment acceptance without
  retaining the ticket.
- Display-state fixtures use unique disposable Attempt/session rows with known
  pending state, safe duplicate/conflict/late reruns, observable stored/effective
  results and task-owned cleanup. They prove no session/ticket/expiry/teaser/
  union/`N` mutation.
- Timer fixtures independently vary the two config values, return local display
  to advertising and emit no session invalidation. Evidence remains joinable to
  FT-006 without claiming a phone read.
- Production acceptance uses the same twenty controlled Attempt IDs and
  records only the FT-005 observations: target-screen render, one-clock
  `<10_000 ms`, programmatic QR decode and representative-phone scan.
  Timeout/no-match rows remain QR-gate failures; at least nineteen of the
  twenty must pass the independent QR/latency gate. FT-004's server-result
  correctness count is separate and is neither a prerequisite nor a filter,
  intersection or joint pass condition for this task. Claim-level RED is not
  applicable because this task changes no behavior and must not induce failure
  in the authorized setup; the full same-twenty evaluation is its alternative
  proof and preserves an already passing observation as GREEN when present.

## Constitution Constraints And Invariants

- Keep the modular monolith, existing capability graph and one owner per
  mutable invariant; no new runtime role or public origin.
- Derive СПА only from the active display token; credentials, raw storage
  identity and personalized result payloads never enter URLs or logs.
- Exactly four unique decoded teasers plus a fully visible QR are required for
  final Promo, optional Chime, `confirmed` and success cooldown.
- Partial, stale, typed non-success, transport, media, decode, QR, camera and
  processing failures stay/return to advertising and permit a fresh capture.
- Display status/lifetime never mutates or invalidates the QR session; FT-006
  retains browser/phone continuation ownership.
- No task inherits dependency evidence. The final production task cannot
  synthesize the unavailable corpus, evaluator or physical scan.

## Definition Of Done

All implementation cards satisfy their exact claims and tier obligations;
`TASK-079` remains the separate planned `Production acceptance:` card until
deployment, corpus and evaluator prerequisites exist; every
`FT-005-AC-001..005` is owned exactly once; every task retains the completed
Foundation gate transitively; task-relevant modules, edges and exact contracts
match the accepted Boundary Map; feature design remains complete; and fresh
planning review can evaluate the queue at Planning Revision `4` without
implementation guesses.
