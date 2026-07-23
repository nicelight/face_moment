# Face Moment synchronization handoff

Status: pending  
Scope: documentation only; no code, TASK records or implementation plans.

## Current authority

- `.memory-bank/prd.md` contains the latest accepted product decisions.
- `arch_vision.md` is the current architecture proposal. Its explicitly accepted
  decisions may be propagated, but the global architecture must remain pending
  until the operator accepts the proposal as a whole.
- Historical `BR-*` records must not be rewritten.

## Synchronization order

### 1. Reconcile the Product Brief

Update `.memory-bank/analysis/product-brief.md` to remove Batch/manifest/
confirmation, `batch.confirmed_at`, mandatory diagnostic bundles and the
assumption of an existing backend.

Why: it is still a declared PRD input and currently conflicts with the clarified
PRD. Do not change product scope. If reconciliation exposes a real PRD delta,
route it through `/write-prd` before continuing.

### 2. Re-run `/prd-to-features`

Reconcile its owned L1-L3 artifacts:

- `.memory-bank/product.md`;
- `.memory-bank/requirements.md` and RTM;
- `EP-001`, `EP-003`;
- at minimum `FT-001`, `FT-002`, `FT-007`, `FT-008`, `FT-011`;
- affected epic/feature indexes and `.protocols/PRD-BOOTSTRAP/*`.

Required semantic corrections:

- independent per-photo admission under selected СПА/date;
- `UNIQUE(spa_id, visit_date, checksum_sha256)`;
- `photo.accepted_at` ingest SLO;
- atomic `Photo + pending` admission and durable restart-safe queue;
- core Attempt with best-effort evidence and visible `incomplete` state;
- Calibration on `BackgroundPhotoWorker`, manual rerun after interruption.

Why: `/spec-design` consumes the feature set; stale Batch and diagnostic
contracts would otherwise be promoted into canonical design and later tasks.
The current eleven-feature boundary should be preserved unless the refreshed
decomposition finds an independently accepted product outcome.

### 3. Re-run `/review-feat-plan`

Require approval of the refreshed product decomposition before resuming the
global design gate.

Why: the previous decomposition review predates the per-photo ingest and
best-effort diagnostic decisions.

### 4. Complete `/spec-design` after architecture acceptance

Canonicalize accepted architecture into the existing smallest useful document
set:

- `.memory-bank/architecture/system-architecture.md`;
- `.memory-bank/contracts/boundary-map.md`;
- `.memory-bank/states/lifecycle-map.md`;
- `.memory-bank/glossary.md`;
- `.memory-bank/invariants.md`;
- `.memory-bank/spec-backbone.md`;
- `.memory-bank/spec-index.md` as registry metadata only;
- new `.memory-bank/foundation.md` with the explicit Foundation decision;
- affected feature SDD Gate notes/global links.

The canonical design must cover the five current-pilot capability slices,
write ownership, per-photo transaction boundary, PostgreSQL queue recovery,
HTTPS/private-MinIO boundary, core Attempt/evidence behavior, shared QR browser
state, single-worker Calibration and accepted pilot risks.

Why: `arch_vision.md` is a proposal/handoff, not a parallel canonical source of
truth. Do not mark the Global Backbone complete or advance Planning Revision
before operator acceptance.

Do not create ADRs, a domain hub, API specs, runbooks or new testing policy only
for completeness. Add a subject spec later only when a concrete feature/task
contract cannot be expressed safely by the existing backbone documents.
`.memory-bank/testing/index.md` remains unchanged in this pass.

### 5. Reconcile supporting and derived documents

- Mark `IDEA_INGEST.md` historical/superseded; do not rewrite its old proposal.
- Remove or clearly supersede conflicting Batch and mandatory-bundle wording in
  `IDEA_APP.md` and `IDEA_DEBUG.md`; only validate `IDEA_OS.md` unless new drift
  is found.
- Update `.memory-bank/index.md`, `.memory-bank/analysis/index.md` and
  `.memory-bank/changelog.md`.
- Update `mermaids/README.md` and affected diagrams `01`, `02`, `03`, `04`,
  and `06`; diagram `05` needs no change unless canonical design changes its
  realtime flow.

Why: these documents are discovery/navigation/visual aids. They must not
contradict canonical sources, but they should be updated after those sources to
avoid repeated churn.

## Validation

- `rg` finds no active Batch/manifest/`batch.confirmed_at` contract outside
  explicitly historical material.
- Product Brief, PRD, requirements, RTM, epics and features agree.
- `spec-backbone` status/matrix, Planning Revision, registered specs and
  Foundation anchors are mutually consistent.
- `git diff --check` passes.
- `node scripts/mb-lint.mjs` passes; unrelated existing warnings remain
  separately reported.

