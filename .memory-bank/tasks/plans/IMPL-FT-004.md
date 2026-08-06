---
description: Implementation plan for scoped realtime reference search and truthful result assembly in FT-004.
status: active
last_updated: 2026-08-06
---
# IMPL-FT-004 — Scoped Realtime Search And Result Assembly

## Goal

Deliver one authenticated realtime path in which the server selects at most
five proposal occurrences, runs native compatible exact search under the
token-bound СПА and operator-selected active date, assembles four unique valid
teasers with truthful `N`, and returns explicit non-success without a waiter,
replay or late result.

## Normative Basis

- [FT-004](../../features/FT-004.md): exact `FT-004-AC-001..008` closure.
- [Requirements](../../requirements.md): `REQ-SRCH-001..003`,
  `REQ-CAP-003`, `REQ-PERF-001`, `REQ-REL-001`, `REQ-DIAG-001`,
  `REQ-SEC-001` and `REQ-ARCH-001`.
- [System architecture](../../architecture/system-architecture.md): AD-001,
  AD-002, AD-006, AD-007, AD-009, AD-010 and AD-011.
- [Boundary map](../../contracts/boundary-map.md): Processing input
  projections, Active search date, Participant Promo, authentication and HTTP
  failure contracts.
- [Realtime Reference Search](../../domains/realtime-search.md): immutable
  context, at-most-five native query preparation and exact compatible search.
- [Photo Processing](../../domains/photo-processing.md): dependent revision,
  engine, ready Photo/face and private-preview truth.
- [Promo Attempt](../../domains/promo-attempt.md): core Attempt, singleton,
  deadline, candidate pools and result-session publication.
- [Realtime Attempt API](../../contracts/realtime-attempt-api.md): exact
  authenticated typed response and idempotency surface.
- [Display Client Access](../../domains/display-client-access.md): reused
  display-token principal and rate/redaction rules.
- [Lifecycle map](../../states/lifecycle-map.md): accepted Attempt/search/
  restart transitions.
- [Client realtime verification](../../testing/client-realtime.md): exact
  search, concurrency/restart and joint-correctness evidence route.

## Constitution Constraints

- Preserve one pre-warmed pipeline, one realtime process/slot/deadline, exact
  PostgreSQL search and the existing one-release/private-store topology.
- `processing` owns query preparation and search. `promo` owns the
  participant-visible orchestration, candidate union, teasers, `N`, Attempt
  and result session. `serving_control` owns active date/settings and
  `staff_access` only authenticates the operator.
- Do not add ANN, a waiter/replay queue, broker, distributed limiter, second
  realtime process, tracking, identity clustering, pHash threshold/cache or a
  generic settings/result framework.
- Both tasks use full T2/T3 protocol and independent verification; the T3 task
  additionally requires per-task semantic verification before explicit-owner
  closure.

## Scope

### In Scope

- Processing-owned immutable active-search input and typed selected-detection
  match output.
- Pre-warmed native query preparation, deterministic server ranking, at most
  five independent searches and exact compatible pgvector filtering.
- Operator-only active-date setting on the reused staff session boundary, plus
  owner-backed reference threshold/quality settings.
- One non-blocking realtime slot and one configured deadline without waiting,
  replay or late publication.
- Promo-owned candidate pools, pHash ranking, complete union, truthful `N`,
  four-teaser result and atomic result-session/Attempt publication.
- Typed missing-date, unacceptable-query, insufficient-result, busy, deadline,
  interrupted and technical failure behavior.
- Integrated display-token rate/binding/redaction proof and controlled
  server-owned correctness rows for the shared 20-attempt acceptance set.

### Non-goals

- Browser capture/proposal/sensor/host recovery already owned by FT-003.
- Promo render, Chime, QR visibility, display acknowledgement/cooldown and the
  physical QR half of the joint acceptance owned by FT-005.
- QR exchange, phone continuation, shared browser access and expiry owned by
  FT-006.
- Detailed diagnostic UI/evidence, annotations, Calibration, Photo inventory
  operations, production deployment or model/threshold auto-selection.

## Architecture And Ownership

TASK-011 is owned by `processing` at `src/face_moment/processing/`. It reads
only immutable `inventory` and `serving_control` projections and returns
selected-detection match sets. It does not persist an Attempt/session or decide
the participant result.

TASK-012 is orchestrated by `promo` at `src/face_moment/promo/`. It uses the
existing `serving_control` display principal, the new owner-held active-search
context and TASK-011 processing boundary. `promo` alone owns the runtime slot,
deadline, candidate pools, union, teasers, `N` and result publication.
`serving_control` owns its operator setting surface. FastAPI/UI, platform auth,
infrastructure and composition code adapt/wire only; direct foreign repository
writes and business orchestration there remain forbidden.

## Cohesive Strategy

1. Extend the existing engine seam with reference-query inspection/preparation
   and implement deterministic at-most-five exact scoped search behind one
   processing application boundary.
2. Prove native revision isolation, every scope filter, query gate, exact
   candidate result and ownership in disposable fixtures.
3. Extend the current linear data model with owner-held active search settings
   and one promo result-session row, then expose the minimum operator date
   setting through the reused staff session.
4. Replace TASK-009's fake downstream adapter with promo-owned non-blocking
   singleton/deadline orchestration and deterministic candidate/result
   assembly, preserving the exact realtime API.
5. Prove exact session/response/ticket publication and idempotent
   reconstruction, plus typed injected processing/write failures, security,
   concurrency, restart/no-replay and the server-owned correctness side of the
   controlled 20-attempt set.

## Task Graph

| Task | Tier | Initial status | Depends on | Cohesive outcome |
|---|---|---|---|---|
| [TASK-011-T2-FT-004-W3](../TASK-011-T2-FT-004-W3.task.json) | T2 | planned | TASK-005-T2-FT-002-W2 | Implement and prove native at-most-five proposal evaluation plus exact compatible Photo search. |
| [TASK-012-T3-FT-004-W4](../TASK-012-T3-FT-004-W4.task.json) | T3 | planned | TASK-004-T3-FT-001-W2, TASK-009-T3-FT-003-W2, TASK-011-T2-FT-004-W3 | Deliver and prove the operator date, singleton/deadline, result assembly/session and authenticated runtime outcome. |

The Foundation final gate is transitive through the dependency records.
TASK-011 can follow the processing core independently. TASK-012 waits for the
staff-session, realtime-admission/core-Attempt and exact-search seams. The split
follows the materially different T2 native search and T3 public/auth/runtime
risk, not modules, files or tests.

## Acceptance Closure

| Feature AC | Owning task(s) | Planned proof |
|---|---|---|
| `FT-004-AC-001` | TASK-011 + TASK-012 | Core mixed-scope/native-path matrix proves exact compatibility; integrated result proof repeats token СПА, active date, readiness and no-unconfirmed-time-window behavior. |
| `FT-004-AC-002` | TASK-011 + TASK-012 | Ordered/tied/repeated/low-quality fixtures prove server at-most-five selection, independent native queries, query gate and every forbidden clustering/margin path; integration retains the applied decisions. |
| `FT-004-AC-003` | TASK-012 | Candidate-pool fixtures distinguish every threshold-valid match, pHash-only ranking, four unique teasers, complete union and exact `N`. |
| `FT-004-AC-004` | TASK-012 plus feature-completion joint evidence | The task retains manually reviewed correctness rows keyed by the fixed 20 attempt IDs. FT-004 feature completion later joins those same IDs to FT-005 physical QR evidence; task closure neither implements FT-005 nor claims the joint feature verdict early. |
| `FT-004-AC-005` | TASK-012 | Realtime and active-date security matrices prove token-derived СПА, override rejection, rate limit, redaction, operator-only date update and private topology. |
| `FT-004-AC-006` | TASK-012 | Missing date returns pre-admission `503`; partial-ready, insufficient and repeated-Photo fixtures prove explicit outcomes, current-ready visibility and union deduplication. |
| `FT-004-AC-007` | TASK-012 | A held slot produces a separate admitted `busy` Attempt before owner release with zero inference/waiting, then only a fresh request acquires the slot. |
| `FT-004-AC-008` | TASK-012 | Restart in accepted/searching states publishes `interrupted`, no replay/late session and allows only fresh post-start work. |

All governing REQs map to at least one task. The joint physical QR conjunct is
not a hidden task dependency: task-level implementation closes the server
outcome, while feature semantic completion remains truthful until the later
shared-attempt artifact exists.

## Advisory Expected Change Surface

### TASK-011 exact search core

- `src/face_moment/processing/` for query inspection/preparation and exact
  search ownership;
- `src/face_moment/inventory/` and
  `src/face_moment/serving_control/` only for typed immutable projections;
- `tests/` and `scripts/verify-realtime-search.sh` for deterministic query,
  scope, candidate and ownership evidence.

### TASK-012 authenticated runtime/result outcome

- `migrations/versions/` for one revision from the then-current linear head;
- `src/face_moment/serving_control/` for active date/search settings and its
  staff adapter;
- `src/face_moment/promo/` for slot/deadline, assembly, Attempt and session;
- `src/face_moment/processing/` only through the published TASK-011 boundary;
- `src/face_moment/entrypoints/backend.py` and
  `src/face_moment/entrypoints/realtime.py` for composition only;
- `src/face_moment/infrastructure/settings.py` and `deploy/Caddyfile` only for
  accepted deadline/ticket/rate/HTTPS configuration;
- `tests/` and `scripts/verify-realtime-search.sh` for integrated security,
  runtime, restart, result and controlled-corpus evidence.

These paths are advisory and non-exhaustive. Accepted capability roots,
existing public routes and framework conventions fix durable identities;
owner-local filenames remain executor discretion. No hard `write_boundary` is
inferred.

## Gates And UAT

Applicable project gates are:

- `docker compose config --quiet`
- `docker compose build`
- `docker compose run --rm --no-deps backend python -m mypy src/face_moment`
- `docker compose run --rm --no-deps backend python -m pytest tests/test_foundation.py tests/unit`
- `bash scripts/verify-realtime-search.sh`

TASK-011 creates the isolated core gate; TASK-012 extends it through the
authenticated realtime and operator setting surfaces. It uses a unique
disposable Compose identity, synthetic commercial Photos/proposals, test
display/staff tokens, deterministic clock/settings/deadline, task-owned object
prefix and owned cleanup. Existing engine/repository/transaction seams receive
controlled task-only faults to prove query, core-write and result-publication
failure behavior; no production fault framework or new runtime mechanism is
introduced.

Task-level UAT runs the fixed 20-attempt result corpus and an authorized pilot
evaluator reviews every teaser/union membership. The final FT-004 joint
feature verdict is intentionally delayed until FT-005 contributes physical
same-attempt QR visibility/scannability evidence; no task or feature status is
closed by this plan.

## Invariants And Stop Conditions

- Client/token/date/revision/visibility filters and query quality/threshold
  gates cannot be weakened or reordered to manufacture results.
- Repeated detections are allowed; one Photo contributes once to the complete
  union; pHash ranks only already-valid Photos; teasers are four unique union
  members.
- One admitted Attempt tries one slot under one deadline. Busy work never
  waits/resumes, and restart/late work never publishes a session.
- `processing`, `promo` and `serving_control` remain the only writers of their
  owned state. No handler, platform-auth, infrastructure, generic-util or
  composition-root business orchestration is allowed.
- Any need to change the exact realtime result/outcome contract, active-date
  role/API, candidate algorithm, pipeline compatibility, task dependency,
  owner/edge, session identity or accepted joint criterion stops and routes to
  `/feature-to-tasks FT-004` or `/spec-design` for a shared/global change.

## Definition Of Done And Handoff

- Both tasks satisfy full tier gates and independent `/verify`; TASK-012 also
  has per-task semantic-pass before explicit-owner closure.
- Every `FT-004-AC-001..008` has claim-linked task evidence for the FT-004
  implementation surface. Feature semantic completion remains open until the
  same-attempt FT-005 QR artifact closes the joint AC-004 criterion.
- Reconcile task state at the W4 boundary and feature state only when its full
  acceptance evidence is available through `/mb-sync`.
