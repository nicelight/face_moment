---
description: Canonical accepted module/change-unit dependency graph and boundary contracts for the Face Moment pilot.
status: active
last_updated: 2026-08-06
source_of_truth:
  - .memory-bank/contracts/boundary-map.md
---
# Boundary Map

## Purpose

- Keep one accepted inventory of project modules/change units and every allowed
  significant dependency between them.
- Treat `Consumer -> Provider` as the direction of dependency. Observed imports
  or calls are evidence, not accepted edges by themselves.
- Constrain the target product implementation together with the
  [system architecture](../architecture/system-architecture.md) and
  [lifecycle map](../states/lifecycle-map.md). The verified Foundation supplies
  runtime substrate but no product behavior.

## Modules

| Module / Change Unit | Parent Architecture Unit | Code Root | Responsibility |
|---|---|---|---|
| `serving_control` | [Capability-sliced server application](../architecture/system-architecture.md#capability-ownership) | `src/face_moment/serving_control/` | Supply immutable serving context and audited setting/revision changes. |
| `inventory` | [Capability-sliced server application](../architecture/system-architecture.md#capability-ownership) | `src/face_moment/inventory/` | Admit and manage commercial Photo inventory. |
| `processing` | [Capability-sliced server application](../architecture/system-architecture.md#capability-ownership) | `src/face_moment/processing/` | Produce compatible searchable Photo and query results. |
| `promo` | [Capability-sliced server application](../architecture/system-architecture.md#capability-ownership) | `src/face_moment/promo/` | Run participant Attempts, Promo results and QR continuation. |
| `diagnostics` | [Capability-sliced server application](../architecture/system-architecture.md#capability-ownership) | `src/face_moment/diagnostics/` | Explain and calibrate Attempts from protected evidence. |
| `staff_access` | [Capability-sliced server application](../architecture/system-architecture.md#capability-ownership) | `src/face_moment/platform/auth/` | Authenticate staff and maintain browser-session security state. |

`SpaPromoClient`, ESP32, PostgreSQL and MinIO are external/runtime boundary
parties, not registered project change units in this graph. Their accepted
interfaces are linked below. No finer product-module identity or code root is
added until an owning canonical specification makes it explicit.

## Dependency Graph

`Consumer -> Provider` means Consumer depends on Provider through the linked
contract.

| Consumer | Provider | Contract |
|---|---|---|
| `inventory` | `staff_access` | [Independent Photo admission](#independent-photo-admission) |
| `inventory` | `serving_control` | [Independent Photo admission](#independent-photo-admission) |
| `inventory` | `processing` | [Independent Photo admission](#independent-photo-admission) |
| `inventory` | `processing` | [Processing status projections](#processing-status-projections) |
| `processing` | `inventory` | [Processing input projections](#processing-input-projections) |
| `processing` | `serving_control` | [Processing input projections](#processing-input-projections) |
| `serving_control` | `staff_access` | [Active search date](#active-search-date) |
| `promo` | `serving_control` | [Participant Promo](#participant-promo) |
| `promo` | `inventory` | [Participant Promo](#participant-promo) |
| `promo` | `processing` | [Participant Promo](#participant-promo) |
| `promo` | `diagnostics` | [Participant Promo](#participant-promo) |
| `diagnostics` | `promo` | [Diagnostic evidence and access](#diagnostic-evidence-and-access) |
| `diagnostics` | `processing` | [Calibration and serving change](#calibration-and-serving-change) |
| `diagnostics` | `serving_control` | [Calibration and serving change](#calibration-and-serving-change) |
| `serving_control` | `processing` | [Manual serving-revision switch](#manual-serving-revision-switch) |
| `promo` | `diagnostics` | [Retention cleanup](#retention-cleanup) |
| `inventory` | `processing` | [Photo Inventory Operations](#photo-inventory-operations) |

## Inline Contracts

The graph alone owns module topology and dependency direction. The blocks below
define the allowed interaction, state authority, failure/compatibility rules,
and forbidden bypasses. Complex external payload, data and verification
contracts remain in their registered subject specifications.

### Capability application boundaries

| Module | Public application boundary | Owned mutable state and transitions | Forbidden ownership |
|---|---|---|---|
| `serving_control` | Read immutable `ServingContext`/`IngestTarget`; apply audited manual setting and serving-revision changes. | СПА/timezone, active `visit_date`, pipeline/settings revision, display-token lifecycle and change audit. | Photos, processing results, Attempts, sessions, evidence or Calibration recommendations. |
| `inventory` | Admit one JPEG; query authorized Photos; soft-delete/restore; restore-all; start/read one global hard purge; read recent per-СПА counters and primary-storage capacity. | Photo identity, uploader, authoritative date, effective capture time, accepted time, original reference, visibility, authorization and purge progress. | Pipeline transition rules, embeddings, Promo integrity, core Attempts or evidence retention. |
| `processing` | Create initial `pending`; report readiness; validate a pipeline revision; process Photo; exact compatible search; offline evaluate; clean Photo-derived state on purge. | Pipeline catalog, processing state, derivatives/faces/embeddings, quality gates, exact search, validation and evaluation. | Photo admission/visibility, live setting mutation, Promo Attempt/session assembly or evidence retention. |
| `promo` | Execute a fresh attempt; accept display outcome; exchange/read QR continuation; skip unavailable hard-purged media; run/read retention cleanup. | Core Attempt, result/session, candidate union, teasers, `N`, QR/browser access and latest retention result. | Photo, processing or settings writes and detailed diagnostic evidence. |
| `diagnostics` | Record/search evidence and logs; expose role-scoped views; annotate; run evaluation; request explicit apply; expire owned data. | Detailed evidence/logs, access views, annotations, curated Calibration cases, recommendations and diagnostic-data expiry. | Core Attempt/result/session, aggregate cleanup result or direct serving-setting mutation. |
| `staff_access` | Authenticate staff browser sessions and return the current principal. | Staff principals, password hashes, opaque session/CSRF token hashes, expiry and revocation. | Photo or other capability authorization, domain state or business orchestration. |

Shared PostgreSQL access does not grant shared write authority. A module may read
a published projection only through an accepted edge; only the owner may
validate and perform its commands or transitions.

Outcome-specific verification remains with the linked subject specifications.
At this boundary, proof must show that state changes only through the named
owner and accepted dependency edge.

### Independent Photo admission

`inventory` owns the per-file outcome:

1. use the authenticated principal from `staff_access` and authorize the
   photographer action inside `inventory`;
2. read an immutable `IngestTarget` from `serving_control`;
3. persist the unique Photo and ask `processing` to create the serving
   `pending` state in one short PostgreSQL transaction;
4. return the independent accepted/rejected/duplicate outcome.

No HTTP handler, shared helper or composition root owns this flow or writes the
three modules' state directly. The exact browser contract is the
[Photo Admission API](photo-admission-api.md); persistence, uniqueness and
recovery are owned by [Photo Admission](../domains/photo-admission.md).

### Processing input projections

`processing` may read the Photo identity/visibility and immutable serving
projections required for compatible work. Read access grants no authority to
change Photo admission/visibility, active СПА/date or serving settings.
Processing publishes only its owned state/timestamp projections for accepted
consumers.

For realtime reference search, this edge supplies the immutable active-search
context and active compatible Photo/face projection defined by
[Realtime Reference Search](../domains/realtime-search.md). `processing` may
filter and search that projection but MUST NOT set the active date, change a
threshold/quality setting, activate a Photo or publish a Promo result.

### Processing status projections

`inventory` may read `processing`-owned pipeline revision, current state,
attempt/timestamp, safe failure, worker-operation and restart-recovery
projections to assemble the authenticated per-Photo and operational views
defined by the [Photo Processing API](photo-processing-api.md). It may also ask
`processing` for the controlled-interval `ingest_to_searchable` classification
defined by [Photo Processing](../domains/photo-processing.md), while supplying
the owner-held Photo/visibility/acceptance projection.

This edge grants no processing claim, transition, inference, face/derivative
write or model-selection authority. `inventory` owns staff authorization and
the user-visible read outcome; `processing` remains the only writer of its
state. PostgreSQL/MinIO capacity probes are infrastructure observations
assembled by `inventory`, not another module edge or shared business owner.

### Active search date

`serving_control` owns the operator-selected active `visit_date` used by
automatic reference search. It authenticates through the existing
`staff_access` principal and authorizes the setting inside `serving_control`;
transport, `staff_access`, `promo` and `processing` MUST NOT write the value.

The minimum same-origin staff surface is:

- `GET /staff/search-settings`: active-operator settings page;
- `GET /api/serving/spas/{spa_id}/active-visit-date`: return `200`
  `application/json` with exactly `schema_version: 1`, UUID `spa_id`, nullable
  ISO `YYYY-MM-DD` `active_visit_date`, positive integer `settings_revision`
  and nullable UTC `updated_at`;
- `PUT /api/serving/spas/{spa_id}/active-visit-date`: accept exactly one JSON
  field, `{"visit_date":"YYYY-MM-DD"}`, require the existing matching
  `fm_staff_csrf` cookie and `X-CSRF-Token`, update the active date and
  increment the settings revision atomically, then return `200` with the same
  response shape and the new date/revision/time.

An active operator may read/change the one-СПА pilot value. Missing/invalid/
revoked authentication returns `401`; wrong role, inaccessible СПА or missing/
mismatched CSRF on `PUT` returns `403`; unknown СПА returns `404`; invalid JSON,
unknown fields or an invalid calendar date returns `422`. The surface uses the
existing HTTPS-only staff session and adds no settings framework, date history,
automatic rollover or client override.

Before the first successful setting, the value is absent. Realtime then reports
closed serving readiness with `503` before `promo` admission, starts no search
or core Attempt, and records only bounded token-free operational diagnostic
evidence. The immutable context and threshold/quality inputs are defined by
[Realtime Reference Search](../domains/realtime-search.md).

### Participant Promo

`promo` owns the participant-visible attempt outcome:

1. read one immutable serving snapshot and active-Photo projection;
2. persist the core Attempt and snapshot before inference for every admitted
   request;
3. call `processing` for one exact compatible reference search;
4. persist the result/session only when the search yields a valid result;
5. write detailed evidence best-effort through `diagnostics`.

`promo` MUST NOT activate Photos, mutate pipeline/search rules, change serving
settings or write diagnostic-owned detail. Query selection and exact search are
defined by [Realtime Reference Search](../domains/realtime-search.md). The exact
transport, idempotency and outcome surface is the
[Realtime Attempt API](realtime-attempt-api.md); core Attempt, result assembly
and result-session persistence are owned by
[Promo Attempt](../domains/promo-attempt.md).

### Diagnostic evidence and access

`diagnostics` may read the `promo` Attempt/correlation projection and attach
detailed evidence best-effort. It MUST NOT create an empty replacement anchor,
mutate the core Attempt/result/session or make evidence completion a
participant-flow prerequisite. Operator, photographer and developer views
remain data-class-specific; missing finalization stays visibly `incomplete`.

### Calibration and serving change

`diagnostics` owns evidence selection and Calibration recommendations. It calls
`processing` for offline evaluation. A recommendation never changes serving
state automatically; only a separate explicit developer action may ask
`serving_control` to apply the accepted setting through its audited command.
The reproducible oracle is owned by
[Calibration verification](../testing/calibration.md).

### Manual serving-revision switch

- Owner: `serving_control`.
- Input: an authenticated operator's explicit target revision.
- Output: an audited success/failure result naming the requested and currently
  committed revisions.
- `serving_control` asks `processing` to validate the target; only a validated
  revision may serve.
- Any failure leaves participant service unavailable and never changes the
  committed revision automatically. Recovery is an explicit retry or manual
  selection of the prior revision; restart uses the committed revision and
  stays unavailable if that revision cannot serve.

### Retention cleanup

`promo` owns the project-wide latest cleanup result and calls `diagnostics` to
expire diagnostic-owned data and report which promo-owned Attempts are eligible
for deletion. Each module deletes only its own rows/objects. Exact cutoffs and
promoted-subset retention are owned by the
[lifecycle map](../states/lifecycle-map.md#diagnostic-and-calibration-retention).
Failure remains observable and rerun is safe. No cleanup history, generic jobs
lifecycle or cross-owner cascade is introduced.

### Photo Inventory Operations

`inventory` owns selection, authorization, visibility and purge commands. It
commands only the `processing` cleanup boundary before deleting its own
Photo/media and MUST NOT mutate or cascade into Promo sessions/results, core
Attempts or diagnostic evidence. Exact visibility, session continuity and
fixed-snapshot purge transitions are owned by the
[lifecycle map](../states/lifecycle-map.md#photo-inventory-visibility); selection,
authorization and observable outcomes remain in
[REQ-INV-001..004](../requirements.md#req-list).

### Shared PostgreSQL contract

- The modular monolith uses one PostgreSQL application schema, one SQLAlchemy
  `Base/MetaData`, one Alembic configuration and one sequential migration
  stream.
- Models and repositories remain in their owning modules. One physical schema
  does not permit foreign commands, foreign writes or duplicated business
  rules.
- Cross-module transactions are allowed only through public application
  boundaries under the named orchestration owner; they do not create shared
  business ownership.
- Foreign keys and `ON DELETE` behavior are deliberate. Database cascade MUST
  NOT cross an ownership boundary: Photo deletion cannot cascade into Promo
  sessions, core Attempts or diagnostic evidence, and Attempt deletion cannot
  cascade into diagnostics rows.
- Per-module PostgreSQL schemas, database users/ACLs and independent migration
  streams are outside the accepted pilot.

### PostgreSQL and MinIO convergence

- The backend writes each upload candidate under a unique opaque private MinIO
  key before JPEG validation and SHA-256 arbitration. The browser never gets
  direct MinIO access.
- PostgreSQL uniqueness on `(spa_id, visit_date, checksum_sha256)` arbitrates
  concurrent admission. A duplicate creates no Photo/processing state and
  deletes only its candidate object; an accepted Photo keeps its initial key.
- The per-Photo PostgreSQL commit publishes
  `Photo + accepted_at + pending`. A pre-commit crash may leave a private orphan
  and lose that admission; ordinary re-upload is sufficient recovery.
- Derived keys are deterministic by
  `(photo_id, pipeline_revision_id, artifact_kind)`, allowing idempotent
  replacement before terminal processing publication.
- Retryable cleanup first makes data inaccessible through owner state, then
  deletes MinIO objects idempotently, then finalizes owner database cleanup.
  No distributed transaction or per-object recovery lifecycle is required.
- MinIO versioning and external volume snapshots remain disabled while the
  accepted no-backup pilot decision is active.

### External and runtime boundaries

These are external/runtime interfaces, not project-module graph edges:

- Staff browser traffic crosses the HTTPS application boundary. Exact login,
  CSRF, uploader and response behavior is in the
  [Photo Admission API](photo-admission-api.md) and
  [Staff Access](../domains/staff-access.md).
- Central-origin `SpaPromoClient` keeps one authenticated 10-second HTTP
  long-poll to the fixed-name mDNS ESP32. Exact event, CORS and failure behavior
  is in the [Sensor Passage API](sensor-passage-api.md).
- `SpaPromoClient` submits one synchronous bounded multipart request to
  realtime. Exact serialization, validation, idempotency and outcomes are in
  the [Realtime Attempt API](realtime-attempt-api.md).
- Display and QR continuation cross the HTTPS application boundary. Their
  success, expiry and missing-media states are owned by the
  [lifecycle map](../states/lifecycle-map.md#promo-qr-and-browser-session);
  exact exchange, phone read, activity, media and redirect behavior is in the
  [QR Continuation API](qr-continuation-api.md).
- PostgreSQL and MinIO remain private; application access follows the
  [shared database](#shared-postgresql-contract) and
  [cross-store convergence](#postgresql-and-minio-convergence) contracts.

### Authentication and data-specific delivery

- `serving_control` owns central display-client token lifecycle under
  [Display Client Access](../domains/display-client-access.md). The server
  stores only its hash and derives authoritative `spa_id`; client input cannot
  override it.
- The sensor Bearer secret is distinct, manually provisioned and sent only in
  ESP32 Authorization headers. It never enters URLs or logs.
- Commercial Photo media and personalized session data are backend-proxied,
  authorized and `no-store`; raw MinIO keys and participant-facing presigned
  URLs are outside the pilot.
- Capture-derived media is not developer-only solely because it contains image
  content. If stored, it stays behind private object storage; any HTTP delivery
  still crosses the application boundary. No logging, cache, persistence or
  delivery mechanism is required merely because it is allowed.
- Credentials/authentication state, infrastructure access, commercial Photo
  media, personalized data, participant names/annotations, detailed logs,
  Calibration and administrative actions retain their own protection.

The exact [QR ticket exchange](qr-continuation-api.md#ticket-exchange) remains:

1. `GET /q?ticket=<opaque>` validates the ticket hash and first-open window.
2. The backend opens/reuses the session-wide browser access state, sets an
   `HttpOnly Secure SameSite=Lax` cookie and returns `303` to a token-free URL.
3. The route omits the query string from access logs and returns
   `Cache-Control: no-store` plus `Referrer-Policy: no-referrer`.

Explicit participant navigation/action extends the shared idle state; asset
loads and background polling do not.

### HTTP failure contract

The application and realtime boundaries use standard transport semantics and
no project-specific error framework:

| Status | Contract |
|---|---|
| `401` | Authentication is missing or invalid. |
| `403` | The authenticated principal lacks permission. |
| `413` | The request exceeds an accepted payload bound; the FT-003 total-body case is rejected before domain admission. |
| `422` | Request validation fails. |
| `429` | The applicable rate limit is exceeded. |
| `503` | Serving maintenance/readiness is closed before capture/search admission. |
| `5xx` | An internal or upstream technical failure occurred. |

An admitted capture/search request returns `2xx` with a compact typed outcome,
including `busy`, `deadline`, `unacceptable_query` or
`insufficient_results`. Clients branch on status/outcome, never response prose.
Feature contracts may define their smallest success payload but MUST NOT add a
shared custom error envelope, code registry or mapping framework.

### Recent statistics read contract

The `inventory` read boundary returns separate 1-, 5- and 60-minute values for
one СПА. Every counter excludes soft-deleted Photos:

| Counter | PostgreSQL source meaning |
|---|---|
| `new` | Unique Photo with `accepted_at` inside the window. |
| `unprocessed` | Photo accepted inside the window and currently `pending \| processing`. |
| `processed` | Photo whose current processing state transitioned to `ready \| no_faces` inside the window. |
| `failed` | Photo whose current processing state transitioned to `failed` inside the window. |

The Admin UI polls every five seconds. Direct PostgreSQL aggregation is the
initial contract; WebSocket, SSE, a metrics store and materialized counters are
outside the pilot.

## Update Rules

- `Module / Change Unit` is the unique graph key. Use stable functional
  responsibility names, not feature/task IDs, current paths or generic
  technical layers.
- Every graph row names registered modules and links to one exact contract
  heading. The graph row alone owns consumer, provider and direction.
- Include every accepted significant inter-module dependency. An absent edge is
  not authorized.
- Add a module or edge only when an accepted canonical specification makes its
  identity, parent, responsibility and interaction explicit. A feature/task or
  observed import cannot create target authority by itself.
- `/feature-to-tasks` owns feature-level leaf modules, consumers and edges
  inside unchanged global boundaries; it MUST NOT infer them from this map's
  silence.
- Keep the detailed module inventory here. `system-architecture.md` owns only
  the larger architecture unit and links to `#modules`.
- Plans and tasks link relevant graph/contract blocks through existing fields;
  they do not copy subgraphs or introduce graph-specific task fields.
