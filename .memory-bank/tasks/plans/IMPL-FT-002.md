---
description: Implementation plan for compatible Photo processing and searchable readiness in FT-002.
status: active
last_updated: 2026-08-06
---
# IMPL-FT-002 — Processing And Searchable Readiness

## Goal

Deliver one compatible processing path in which every independently accepted
Photo advances from durable serving `pending` through idempotent background
work to truthful `searchable`, `no_faces` or `failed`, survives ordinary worker
restart, contributes honestly to the 15-minute SLO, and exposes current
authorized processing/storage health.

## Normative Basis

- [FT-002](../../features/FT-002.md): exact `FT-002-AC-001..006` closure.
- [Requirements](../../requirements.md): `REQ-ING-003..004`,
  `REQ-SRCH-001`, `REQ-REL-002`, `REQ-SEC-001` and `REQ-ARCH-001`.
- [System architecture](../../architecture/system-architecture.md): AD-001,
  AD-002, AD-004, AD-010 and AD-011; `processing` ownership and singleton
  worker runtime.
- [Boundary map](../../contracts/boundary-map.md): processing input/status
  projections, shared PostgreSQL, private MinIO and forbidden foreign writes.
- [Photo Admission](../../domains/photo-admission.md): dependent Photo,
  revision identity and initial serving `pending` transaction.
- [Photo Processing](../../domains/photo-processing.md): executable revision,
  engine, state, derivative, face, worker, recovery and SLO contract.
- [Photo Processing API](../../contracts/photo-processing-api.md): exact staff
  status/health/SLO UI/API and authorization surface.
- [Staff Access](../../domains/staff-access.md): reused staff principal,
  session and CSRF contract.
- [Lifecycle map](../../states/lifecycle-map.md): canonical Photo pipeline and
  Calibration/shared-worker behavior.
- [Photo processing verification](../../testing/photo-processing.md):
  deterministic terminal, restart, SLO and capacity evidence.
- [Testing policy](../../testing/index.md): project gates and tier additions.

## Constitution Constraints

- Use the existing one release, one application schema/Base/Alembic stream,
  one worker and private PostgreSQL/MinIO baseline.
- Preserve `REQ-SEC-001` private PostgreSQL/MinIO/internal-port topology and
  the Photo Processing API redaction contract on every status/capacity read.
- `processing` owns claims, engines, state, faces and derivatives. `inventory`
  owns the staff-visible outcome and capability authorization. Transport,
  infrastructure and composition code do not absorb business orchestration.
- Do not add a broker, job table, lease, fencing, `SKIP LOCKED`, extra worker,
  priority/preemption scheduler, monitoring service, ANN index or automatic
  pipeline switching.
- T2/T3 execution follows full protocol and independent verification. The T3
  staff/capacity task also requires semantic verification and a human
  checkpoint before closure.

## Scope

### In Scope

- Complete immutable revision identity and separate native SFace/Buffalo M
  Photo-engine adapters over configured model assets.
- Processing-owned state/face/derivative/runtime-status persistence in one
  new linear migration after FT-001's admission schema.
- Oldest-serving-pending atomic claim, three-attempt retry, deterministic
  preview/thumbnail keys, full face-set replacement and terminal publication.
- Startup reset of unfinished processing, latest recovery projection and
  restart-from-beginning convergence.
- Controlled-interval full-population SLO classification, including late
  no-face/failure/backlog and explicit exclusions.
- Shared-worker current-operation projection sufficient to show Calibration
  delay and ordinary Photo resumption without implementing Calibration logic.
- Authenticated photographer per-Photo polling and operator/developer health
  page/API for queue, SLO, recovery and separate PostgreSQL/MinIO capacity.
- Configured read-only primary-volume capacity views with positive low
  thresholds and isolated normal/low/unavailable, private-topology and
  protected-data redaction proof.

### Non-goals

- Photo admission, authentication/session implementation or uploader behavior
  already owned by FT-001.
- Realtime query processing, exact Photo search/ranking, thresholds, Promo,
  `N`, QR or result assembly owned by later features.
- Calibration calculation/UI, automatic serving changes, dual online
  benchmark, pending-revision migration or model-quality acceptance.
- FT-012 soft delete/restore, recent 1/5/60-minute counters or hard purge.
- Production model asset selection, production deployment, backup,
  observability stack, second worker or distributed scheduling.

## Architecture And Ownership

The primary owner of TASK-005 is `processing` at
`src/face_moment/processing/`. It reads immutable Photo and serving projections,
owns the sequential claim/inference/publication flow and exposes only typed
state/SLO projections. Cross-store convergence uses the private object-store
adapter; committed PostgreSQL state decides whether derivatives are usable.

The primary orchestration owner of TASK-006 is `inventory` at
`src/face_moment/inventory/` because the photographer/operator-visible read is
the outcome. It authenticates through the existing `platform/auth` principal,
authorizes inside inventory, reads processing through
`#processing-status-projections`, and assembles independent infrastructure
capacity observations. FastAPI/UI, generic helpers and the composition root
MUST NOT query foreign repositories or calculate processing truth directly.

## Cohesive Strategy

1. Extend the FT-001 migration/model seam with complete immutable revisions,
   processing state/face/runtime status and explicit constraints.
2. Implement separate native engine adapters, one oldest-pending atomic claim
   and deterministic terminal publication outside/inside the required
   transaction boundaries.
3. Add startup recovery, bounded retry and controlled SLO projections, then
   prove terminal compatibility, crash/retry convergence and Calibration-held
   backlog behavior in isolated state.
4. Reuse FT-001 staff sessions to expose exact per-Photo status and processing
   health through inventory-owned authorization and assembly.
5. Add the two configured read-only capacity probes and extend the same
   isolated gate through role, privacy, normal/low/unavailable and public UI/API
   evidence.

## Task Graph

| Task | Tier | Initial status | Depends on | Cohesive outcome |
|---|---|---|---|---|
| [TASK-005-T2-FT-002-W2](../TASK-005-T2-FT-002-W2.task.json) | T2 | planned | TASK-003-T2-FT-001-W1 | Implement and prove compatible terminal processing, deterministic face/derivative publication, restart recovery and full-population SLO. |
| [TASK-006-T3-FT-002-W3](../TASK-006-T3-FT-002-W3.task.json) | T3 | planned | TASK-004-T3-FT-001-W2, TASK-005-T2-FT-002-W2 | Expose truthful photographer status and operator/developer processing/SLO/recovery/capacity health through the authenticated staff boundary. |

The Foundation final gate is transitive through TASK-003. TASK-005 and the
FT-001 public-boundary TASK-004 can proceed independently in W2; TASK-006 waits
for both. The split follows materially different data/recovery and public
authorization/primary-volume risk, not modules, layers or tests.

## Acceptance Closure

| Feature AC | Owning task | Planned proof |
|---|---|---|
| `FT-002-AC-001` | TASK-005 (state/searchable truth) + TASK-006 (staff-visible truth) | Terminal/compatibility fixtures prove the persisted rule and the authenticated route maps only complete active current-revision `ready` to `searchable`. |
| `FT-002-AC-002` | TASK-005 | Repeated terminal delivery and an interruption after derivative publication converge on one deterministic derivative/face set and terminal row. |
| `FT-002-AC-003` | TASK-005 | Startup reset preserves the full pending/processing population, records recovery and reaches idempotent outcomes from the immutable original. |
| `FT-002-AC-004` | TASK-005 (classifier) + TASK-006 (operational interval surface) | Controlled-clock population includes every accepted Photo, classifies late/unsearchable outcomes as breaches, excludes only rejects/duplicates/non-serving work and compares the completed ratio with 95%. |
| `FT-002-AC-005` | TASK-005 (serialization/resumption/SLO) + TASK-006 (visibility) | A controlled Calibration operation holds the singleton worker, backlog and SLO effect remain present, the health view names the operation, then ordinary processing resumes without preemption/priority/extra worker. |
| `FT-002-AC-006` | TASK-005 (failure/recovery projections) + TASK-006 (authorized health/capacity/privacy surface) | Current failures/recovery and independent normal/low/unavailable PostgreSQL/MinIO observations are compared through the exact operator/developer contract; TASK-006 also proves the governing `REQ-SEC-001` private topology and response/URL/log redaction. |

Every governing REQ maps to at least one task, and no task claims later search,
Calibration, inventory-management or deployment outcomes.

## Advisory Expected Change Surface

### TASK-005 primary processing/recovery outcome

- `migrations/versions/` for one revision on the then-current linear head;
- `src/face_moment/processing/` for revision/engine/state/worker/SLO ownership;
- `src/face_moment/inventory/` and
  `src/face_moment/serving_control/` only for typed immutable projections;
- `src/face_moment/entrypoints/background_worker.py` for composition/startup;
- `src/face_moment/infrastructure/database.py`,
  `src/face_moment/infrastructure/object_store.py` and
  `src/face_moment/infrastructure/settings.py` only for owner-used adapters and
  configured model/derivative values;
- `tests/` and `scripts/verify-photo-processing.sh` for deterministic unit and
  disposable PostgreSQL/MinIO/restart evidence.

### TASK-006 authenticated status/health outcome

- `src/face_moment/inventory/` for capability-owned authorization, outcome
  assembly and its staff HTTP/UI adapter;
- `src/face_moment/processing/` only for the published read projection;
- `src/face_moment/entrypoints/backend.py` for composition only;
- `src/face_moment/infrastructure/settings.py` and `compose.yaml` for two
  configured read-only volume views and positive thresholds;
- `tests/` and `scripts/verify-photo-processing.sh` for role/ownership,
  controlled interval, capacity, topology and redaction evidence.

These paths are advisory and non-exhaustive. Accepted capability roots and
framework conventions fix ownership; exact owner-local module/template/static
filenames remain executor discretion when they preserve canonical API/data
identities. No hard `write_boundary` is inferred.

## Gates And UAT

Both tasks run the applicable subset of:

- `docker compose config --quiet`
- `docker compose build`
- `docker compose run --rm --no-deps backend python -m mypy src/face_moment`
- `docker compose run --rm --no-deps backend python -m pytest tests/test_foundation.py tests/unit`
- `bash scripts/verify-photo-processing.sh`

TASK-005 creates the isolated processing gate; TASK-006 extends it through the
staff HTTPS boundary and configured volume observations. The script uses a
unique Compose identity, disposable volumes/test credentials, controlled
clock/model fixtures, explicit thresholds, a task-owned object prefix and
owned cleanup.

Manual UAT admits configured test Photos, watches terminal states, opens the
operator/developer health page for a completed SLO interval, and injects one
low/unavailable capacity observation. UAT is supporting evidence; tier-routed
`/verify` remains authoritative.

## Invariants And Stop Conditions

- Only complete active `ready` for the current serving revision is searchable;
  incompatible, partial and every other state remain ineligible.
- One configured worker owns claims; startup begins unfinished work from the
  original and no broker/lease/fencing/extra-worker machinery appears.
- Face rows and engine preparation never cross revisions. PostgreSQL terminal
  publication and deterministic private objects converge under retry.
- Inventory assembles and authorizes staff reads but never writes processing
  state; transport/infrastructure/composition code never owns business truth.
- Any required change to pipeline compatibility, retry limit, SLO population/
  target, endpoint/role contract, capability edge, storage privacy or accepted
  worker topology stops and routes back to `/feature-to-tasks FT-002` or
  `/spec-design` for a shared boundary change.

## Definition Of Done And Handoff

- Both tasks satisfy tier gates and independent verification; TASK-006 also
  has T3 semantic-pass and `HUMAN_CHECKPOINT: done` before closure.
- Every `FT-002-AC-001..006` and governing REQ has claim-linked evidence.
- Reconcile task/feature/RTM state at the W3/feature boundary through
  `/mb-sync`.
