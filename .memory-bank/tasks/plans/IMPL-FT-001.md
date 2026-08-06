---
description: Implementation plan for authenticated independent Photo admission in FT-001.
status: active
last_updated: 2026-08-06
---
# IMPL-FT-001 — Independent Photo Admission

## Goal

Deliver one authenticated photographer journey in which every ready JPEG is
admitted independently under a selected СПА and authoritative `visit_date`,
with truthful accepted/rejected/duplicate feedback and atomic publication of
one Photo plus its serving-pipeline `pending` state.

## Normative Basis

- [FT-001](../../features/FT-001.md): exact `FT-001-AC-001..005` product closure.
- [Requirements](../../requirements.md): `REQ-ING-001..003`, `REQ-SEC-001`
  and `REQ-ARCH-001`.
- [System architecture](../../architecture/system-architecture.md): AD-001,
  AD-002, AD-003, AD-009, AD-010 and AD-011; capability roots and
  `inventory` orchestration ownership.
- [Boundary map](../../contracts/boundary-map.md): shared PostgreSQL,
  PostgreSQL/MinIO convergence, staff-browser and cross-slice rules.
- [Photo Admission](../../domains/photo-admission.md): internal Photo/original/
  pending data, transaction, duplicate and recovery contract.
- [Staff Access](../../domains/staff-access.md): staff principal, role,
  password, server-session and CSRF contract.
- [Photo Admission API](../../contracts/photo-admission-api.md): exact
  same-origin staff endpoints, per-file response and standard failure contract.
- [Lifecycle map](../../states/lifecycle-map.md): independent Photo admission
  and deliberate non-lifecycles.
- [Testing policy](../../testing/index.md): project gates, artifact routing and
  tier additions.

## Constitution Constraints

- Use the smallest modular-monolith implementation that satisfies current
  acceptance; no broker, outbox, distributed limiter, resumable upload,
  generic IAM/RBAC system or storage-transaction emulator.
- Keep `inventory` as the business orchestration owner. Transport/UI,
  `platform/auth`, infrastructure adapters and the composition root do not
  absorb capability logic.
- Preserve the existing one release, one application schema/Base/Alembic
  stream and private PostgreSQL/MinIO topology.
- T2/T3 execution follows full protocol and independent verification; the T3
  public/security task additionally requires per-task semantic verification
  and the human checkpoint before closure.

## Scope

### In Scope

- Minimal owner-backed active СПА/serving-revision target used by admission.
- Inventory-owned Photo/original persistence and processing-owned initial
  `pending` state in one PostgreSQL transaction.
- Private opaque-key MinIO candidate flow, configurable safe JPEG bounds,
  SHA-256 uniqueness, EXIF-derived effective capture time and mismatch warning.
- Concurrent duplicate arbitration, handled cleanup, injected rollback and the
  accepted pre-commit orphan/re-upload recovery.
- Staff CLI provision/reset/deactivate, Argon2id passwords, hashed opaque
  server sessions, absolute expiry, logout/revocation and CSRF.
- Exact same-origin login, ingest-target and one-file upload endpoints plus the
  minimal photographer page for independent multi-file results.
- Deployment-configured positive auth/upload rate limits and proof that only
  the HTTPS edge is browser-reachable.
- Isolated deterministic PostgreSQL/MinIO/application verification with owned
  setup, rerun and cleanup.

### Non-goals

- Background claiming/inference, `ready|no_faces|failed` publication and the
  15-minute searchable SLO owned by FT-002.
- Photo listing, state observation beyond the admitted `pending` result,
  effective-time selection UI, soft-delete/restore, statistics or hard purge
  owned by FT-012.
- Operator active-search-date UI, manual pipeline revision switching,
  Calibration or general admin/settings work.
- OAuth, MFA, self-registration, email recovery, multi-role policy machinery,
  external ingest, RAW, Batch/manifest/confirmation or resumable upload.
- Production deployment/certificates, public MinIO, presigned browser access,
  backup, broker, distributed rate limiting or multiple backend replicas.

## Architecture And Ownership

The primary owning slice is `inventory` at
`src/face_moment/inventory/`. It owns Photo admission and the observable
per-file outcome. It reads an immutable target through the public
`serving_control` application boundary and commands `processing` to create the
initial `pending` row in the same transaction. `platform/auth` supplies a
narrow authenticated staff principal; it does not authorize or perform Photo
admission.

Crossed boundaries are direct typed Python application calls in the same
release plus the private object-store adapter. Direct foreign repository writes
remain forbidden. Business orchestration MUST NOT move into FastAPI handlers,
browser code, generic/shared helpers, infrastructure or the composition root.

## Cohesive Strategy

1. Implement the owner-scoped persistence and application boundaries needed to
   resolve one `IngestTarget`, store/validate one candidate, arbitrate
   uniqueness and atomically publish Photo plus `pending`.
2. Add the linear migration and isolated core probes for concurrency,
   rollback, crash-window recovery and PostgreSQL/MinIO cleanup.
3. Add staff credential/session/CSRF persistence and explicit owner-backed CLI
   lifecycle without expanding business authorization.
4. Wire the exact login, target-list and one-file upload contract to the
   inventory application boundary, then add the minimal independent-results UI.
5. Extend the isolated probe through the public HTTPS application boundary,
   including role, CSRF, rate-limit, topology and redaction evidence.

## Task Graph

| Task | Tier | Initial status | Depends on | Cohesive outcome |
|---|---|---|---|---|
| [TASK-003-T2-FT-001-W1](../TASK-003-T2-FT-001-W1.task.json) | T2 | ready | TASK-002-T2-FT-000-W0 | Implement and prove the owner-safe Photo/original/serving-pending admission transaction, duplicate arbitration and accepted crash recovery. |
| [TASK-004-T3-FT-001-W2](../TASK-004-T3-FT-001-W2.task.json) | T3 | planned | TASK-003-T2-FT-001-W1 | Expose the complete photographer journey through the authenticated, CSRF-protected, rate-limited HTTPS UI/API boundary. |

The split follows materially different data/recovery and security/public-
boundary risk. It does not create separate tasks per module, file, layer or
test. The Foundation final gate is a direct dependency of TASK-003 and a
transitive dependency of TASK-004.

## Acceptance Closure

| Feature AC | Owning task | Planned proof |
|---|---|---|
| `FT-001-AC-001` | TASK-003 (core data claims) + TASK-004 (public journey) | TASK-003 proves authoritative visit_date, EXIF mismatch/effective captured_at, JPEG validation/bounds and no-admission rejects; TASK-004 proves the exact uploader/target/upload route, method, field and response matrices, including independent valid, invalid, undecodable, mixed-EXIF and duplicate outcomes plus representative `422`. |
| `FT-001-AC-002` | TASK-003 | Isolated sequential and concurrent same-scope duplicates yield exactly one Photo/pending/object winner and delete only losing candidates. |
| `FT-001-AC-003` | TASK-003 | Success and injected pre-commit rollback show complete Photo+pending or no database admission. |
| `FT-001-AC-004` | TASK-003 (architecture ownership claim) + TASK-004 (public/security journey) | TASK-003 proves that `inventory` owns core admission, crosses only typed `serving_control`/`processing` boundaries and leaves no foreign-write or handler/generic-util/composition-root orchestration bypass; TASK-004 proves the exact staff-session surface, credential/token/cookie persistence, restart-safe sessions, cookie/role/CSRF behavior, separate deterministic login/upload limits, `429`, HTTPS-only topology, secret/object-key redaction and public-adapter delegation to `inventory` without foreign writes. |
| `FT-001-AC-005` | TASK-003 | Post-object/pre-commit interruption leaves no database admission or exposure; re-upload succeeds and owned cleanup is safe. |

Every governing `REQ-*` maps to at least one task, and no planned task proves a
product outcome outside these five ACs.

## Advisory Expected Change Surface

### TASK-003 primary data/recovery outcome

- `pyproject.toml` only if the accepted JPEG/EXIF proof needs one minimal
  runtime/test dependency;
- `migrations/versions/` for one new revision on the current linear head;
- `src/face_moment/inventory/` as the Photo-admission owner;
- `src/face_moment/serving_control/` only for the immutable `IngestTarget`;
- `src/face_moment/processing/` only for serving-revision identity and initial
  `pending` creation;
- `src/face_moment/infrastructure/database.py`,
  `src/face_moment/infrastructure/object_store.py` and
  `src/face_moment/infrastructure/settings.py` only for required adapters/
  configuration;
- `tests/` for unit and isolated integration coverage;
- `scripts/verify-photo-admission.sh` for disposable database/object-store
  setup, evidence and owned cleanup.

### TASK-004 public/security outcome

- `pyproject.toml` for the minimum password/multipart/test dependencies;
- `migrations/versions/` for the staff user/session tables on the then-current
  linear head;
- `src/face_moment/platform/auth/` for principals, credentials and sessions;
- `src/face_moment/inventory/` for its staff HTTP/UI adapter while keeping
  orchestration in the inventory application boundary;
- `src/face_moment/entrypoints/backend.py` for composition only;
- `src/face_moment/infrastructure/settings.py`, `compose.yaml` and
  `deploy/Caddyfile` only where the accepted cookie/rate/HTTPS/private topology
  needs configuration;
- `tests/` and `scripts/verify-photo-admission.sh` for the expanded boundary
  journey, security and redaction probes.

These paths are advisory and non-exhaustive. The existing code roots and
framework conventions fix ownership; exact module/template/static filenames
remain executor discretion when they do not alter the canonical API or data
identity. No hard `write_boundary` is inferred from this surface.

## Gates And UAT

Both tasks run the applicable subset of:

- `docker compose config --quiet`
- `docker compose build`
- `docker compose run --rm --no-deps backend python -m mypy src/face_moment`
- `docker compose run --rm --no-deps backend python -m pytest tests/test_foundation.py tests/unit`
- `bash scripts/verify-photo-admission.sh`

TASK-003 creates the isolated verification script and core fixtures; TASK-004
extends the same project-native gate through the staff UI/API boundary. The
script uses a unique non-production Compose identity, disposable volumes/test
credentials, explicit rate/size limits and owned object prefixes; it is safe to
rerun and cleans only its resources.

Manual UAT follows the exact API contract: provision one photographer and one
active target, log in through HTTPS, select СПА/date, upload mixed valid/
invalid/duplicate files, and verify each row independently. UAT is supporting
evidence; tier-routed `/verify` remains authoritative.

## Invariants And Stop Conditions

- Authoritative `visit_date`, one Photo+pending commit and database uniqueness
  MUST remain unchanged.
- PostgreSQL decides accepted usability; MinIO stays private, and a crash-window
  orphan grants no read path.
- `inventory` owns orchestration; direct foreign writes or handler/composition-
  root business logic stop execution.
- Any required change to the canonical endpoint/response, role authorization,
  session/CSRF model, persistent shapes, capability ownership, dependency
  direction or accepted orphan recovery stops and routes back to
  `/feature-to-tasks FT-001` or `/spec-design` for a shared boundary change.
- Product work from FT-002/FT-012, production deployment or a destructive data
  operation is outside both tasks.

## Definition Of Done And Handoff

- Both tasks satisfy their tier gates and independent verification; TASK-004
  additionally has T3 semantic-pass and `HUMAN_CHECKPOINT: done` before closure.
- Every `FT-001-AC-001..005` and governing REQ has claim-linked evidence.
- Reconcile task/feature/RTM state at the W2/feature boundary through
  `/mb-sync`.
