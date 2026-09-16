---
description: Canonical accepted module/change-unit dependency graph and boundary contracts for the Face Moment pilot.
status: active
last_updated: 2026-09-03
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
| `inventory` | `processing` | [Staff inventory media reads](#staff-inventory-media-reads) |
| `processing` | `inventory` | [Processing input projections](#processing-input-projections) |
| `processing` | `serving_control` | [Processing input projections](#processing-input-projections) |
| `serving_control` | `staff_access` | [Active search date](#active-search-date) |
| `serving_control` | `staff_access` | [Display client administration](#display-client-administration) |
| `promo` | `serving_control` | [Participant Promo](#participant-promo) |
| `promo` | `inventory` | [Participant Promo](#participant-promo) |
| `promo` | `processing` | [Participant Promo](#participant-promo) |
| `promo` | `diagnostics` | [Participant Promo](#participant-promo) |
| `diagnostics` | `promo` | [Diagnostic evidence and access](#diagnostic-evidence-and-access) |
| `diagnostics` | `staff_access` | [Diagnostic evidence and access](#diagnostic-evidence-and-access) |
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
| `serving_control` | Read immutable `ServingContext`/`IngestTarget`; apply audited manual setting and serving-revision changes; administer and reveal current display-client credentials to authorized Admins. | СПА/timezone, automatic-today/manual search range, pipeline/settings revision, display-token value/lifecycle and change audit. | Photos, processing results, Attempts, sessions, evidence or Calibration recommendations. |
| `inventory` | Admit one JPEG; query authorized Photos; soft-delete/restore; restore-all; start/read one global hard purge; read recent per-СПА counters and primary-storage capacity. | Photo identity, uploader, authoritative date, effective capture time, accepted time, original reference, visibility, authorization and purge progress. | Pipeline transition rules, embeddings, Promo integrity, core Attempts or evidence retention. |
| `processing` | Create initial `pending`; report readiness; validate a pipeline revision; process Photo; exact compatible search; offline evaluate; clean Photo-derived state on purge. | Pipeline catalog, processing state, derivatives/faces/embeddings, quality gates, exact search, validation and evaluation. | Photo admission/visibility, live setting mutation, Promo Attempt/session assembly or evidence retention. |
| `promo` | Execute a fresh attempt; accept display outcome; exchange/read QR continuation; skip unavailable hard-purged media; run/read retention cleanup. | Core Attempt, result/session, candidate union, teasers, `N`, QR/browser access and latest retention result. | Photo, processing or settings writes and detailed diagnostic evidence. |
| `diagnostics` | Record/search evidence and logs; expose role-scoped views; annotate; run evaluation; request explicit apply; expire or explicitly remove owned ordinary data. | Detailed evidence/logs, access views, annotations, curated Calibration cases, recommendations and diagnostic-data expiry/removal. | Core Attempt/result/session, aggregate cleanup result or direct serving-setting mutation. |
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
3. persist the unique Photo with its immutable `IngestTarget` revision snapshot
   and ask `processing` to create the same-revision `pending` state in one
   short PostgreSQL transaction;
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
the owner-held Photo/visibility/acceptance projection, including the immutable
admission-time revision snapshot that selects each Photo's single SLO state.
For the per-Photo status read, `inventory` supplies that same immutable
admission revision as the exact state selector; later revision rows do not
replace it, while `processing` still evaluates current compatibility for the
selected state.

This edge grants no processing claim, transition, inference, face/derivative
write or model-selection authority. `inventory` owns staff authorization and
the user-visible read outcome; `processing` remains the only writer of its
state. PostgreSQL/MinIO capacity probes are infrastructure observations
assembled by `inventory`, not another module edge or shared business owner.

### Active search date

`serving_control` owns each площадка's exit-camera search mode and manual
inclusive From/To range. The operator decision in PRD FR-SRCH-06 (2026-09-11)
supersedes the old mandatory single active date. Authentication uses the existing
`staff_access` principal; only `serving_control` writes these settings.

#### Staff active-date surface

`GET /staff/spas` contains independent settings on each площадка card:
«камера на выходе ищет лица ТОЛЬКО из сегодняшних фоток». Automatic mode hides
the manual date controls, hint and save button; switching mode saves immediately.
Manual mode exposes «С»/«По» and explicitly saves the range. Failed mode writes
restore the last saved mode. Operator and developer can read and save each card. The standalone
«Настройки поиска» navigation item is removed; `/staff/search-settings` routes
to `/staff/spas` so existing links remain usable.

`GET|PUT /api/serving/spas/{spa_id}/search-dates` uses JSON schema version 1.
PUT accepts `search_today` (strict boolean) and optional ISO calendar dates
`date_from`/`date_to`. Manual mode requires both with From <= To. Automatic
mode may omit both and preserves the previous saved manual range. Unknown
fields, partial pairs and reversed ranges are rejected. The response contains
`schema_version`, `spa_id`, `search_today`, saved nullable `date_from`/`date_to`,
`timezone`, current server-resolved venue `today`, `settings_revision` and UTC
`updated_at`. Reads and writes use `Cache-Control: no-store`.

Updating mode/range and incrementing revision is atomic. The owner resolves
effective inclusive bounds for every new Attempt through
[Realtime Reference Search](../domains/realtime-search.md#active-search-context-persistence).

Existing HTTPS staff sessions, operator/developer authorization and matching
`fm_staff_csrf` cookie/`X-CSRF-Token` on writes remain mandatory. Missing or
invalid authentication returns `401`; wrong role, inaccessible площадка or
invalid CSRF returns `403`; unknown площадка returns `404`; malformed fields or
invalid manual bounds return `422` without changing the saved setting. All
resulting routes must pass the real HTTPS edge, not only direct ASGI tests.

The old `/api/serving/spas/{spa_id}/active-visit-date` endpoint remains a legacy
manual-day interface for existing tools: GET reads the saved manual start, and
PUT explicitly selects manual mode and sets both bounds to the supplied day.
The staff UI uses the range endpoint. No second settings store is introduced.

#### Per-площадка detector thresholds

Operator decision, 2026-09-14: each card also has independent edit switches for
photographer-photo YuNet and browser capture BlazeFace thresholds. Each numeric
value is in `(0, 1]`, initially `0.90` and `0.50` respectively. Switching editing
off cancels unsaved input; a successful explicit save locks the field and turns
the edit switch off. Failed saves retain the editable draft.

`PUT /api/serving/spas/{spa_id}/detector-thresholds/{detector}` accepts only
`{"threshold": number}`, where detector is `photo_yunet` or `capture_blazeface`.
The existing operator/developer, active-площадка and CSRF rules apply. Each write
updates only that threshold and the settings revision, not the other detector
or search dates. PostgreSQL owns the values in `spas`.

New Photo admission snapshots the площадка's YuNet threshold on the Photo.
Worker retries use that snapshot; saving a setting never reprocesses existing
Photos. Only photographer-photo terminal processing consumes this override;
server reference matching and offline Calibration retain their existing paths.
The authenticated display configuration projects the token-scoped BlazeFace
threshold. The browser reads it before each new series detection, applies it
to the existing detector and reuses the configuration for the resulting Promo.

#### Staff площадка names

Operator addition 2026-09-16: `/staff/spas` includes «Добавить площадку» with
name and a timezone dropdown GMT+1 through GMT+10 (default GMT+7), submit and cancel.
Dropdown values use fixed IANA zones `Etc/GMT-1` through `Etc/GMT-10`;
the reversed identifier sign represents the displayed positive offset, without DST.
Existing saved venue zones remain unchanged. `POST
/api/serving/spas` accepts exactly `{name, timezone}`, requires operator/developer
session and CSRF, and returns 201 with spa_id/name/timezone and no-store.
The server resolves the shared eligible revision; model selection is not an
input. Invalid fields/name/timezone return 422, unavailable/conflicting shared
revision 409, missing session 401, wrong role/CSRF 403. Creation and independent
reference settings commit together: today mode, detector defaults .9/.5,
similarity .38, min quality .5, quality settings version 1. Existing venues and
tokens stay unchanged. Screen provisioning is not part of this form.
The edge must forward the exact `/api/serving/spas` path to backend.

Operator correction 2026-09-11: `GET /staff/spas` is the separate площадка
list and name-editing page for active operators and developers. Both this
page and `/api/serving/spas/*/name` must be forwarded unchanged by the HTTPS
edge to backend; empty unmatched proxy responses are not a successful page. Each active
площадка has its own rename form and the search controls defined above. `serving_control` owns
`PUT /api/serving/spas/{spa_id}/name`, accepting exactly `{"name":"…"}` and
returning `200` with `spa_id` and normalized `name`, `Cache-Control: no-store`.
Existing session, operator/developer role and CSRF checks apply; missing authentication
is `401`, wrong role/CSRF/inactive площадка `403`, unknown UUID `404`, empty or
whitespace-only name, unknown fields or name longer than 255 characters `422`.
Trim outer whitespace; change only the persisted name. UUID, date, pipeline,
settings revision and Photo relationships remain unchanged. HTML escapes names.

`IngestTargetRepository.configure_spa` assigns the first unused «Площадка N»
(starting at 1) when the caller omits the name, and persists it. Explicit names
are preserved; no migration renames existing площадки. Authenticated inventory
pages read active UUID/name pairs through the serving-control repository;
listing names does not depend on pipeline eligibility or change API authority.

#### Missing-date realtime readiness

Before the first successful setting, the value is absent. Realtime then reports
closed serving readiness with `503` before `promo` admission, starts no search
or core Attempt, and records only bounded token-free operational diagnostic
evidence. The immutable context and threshold/quality inputs are defined by
[Realtime Reference Search](../domains/realtime-search.md).

### Display client administration

Operator addition: «Добавить экран» provides name and active-venue selection.
`POST /api/serving/display-clients` is forwarded by the edge and authorizes
operator/developer + CSRF before owner provisioning. Multiple screens may bind
one venue; each gets a separate token. [Creation contract](../domains/display-client-access.md):
payload, errors, persistence, empty-state and verification.

`serving_control` owns the current retrievable token and matching authentication
digest for every configured kiosk. It uses the existing `staff_access`
principal and authorizes the Admin settings read inside `serving_control`:
active `operator|developer` principals may read the current full token;
photographers may not. `staff_access` authenticates the staff session but never
stores, projects or authorizes the display-client credential itself.

The same-origin `GET /staff/display-clients` Admin settings page shows the
current token on every authorized read under the exact persistence, `no-store`
and redaction rules in
[Display Client Access](../domains/display-client-access.md#admin-settings-token-read).
The Admin manually copies that value into the intended kiosk's client
configuration UI. The kiosk profile owns only its local configuration copy;
it does not mutate server credential state. No HTTP handler, `promo`, browser,
deployment policy, pairing path or generic settings helper may bypass
`serving_control` ownership or push the credential to the kiosk.

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
[Promo Attempt](../domains/promo-attempt.md). Best-effort browser response
timing uses the [Client Diagnostic API](client-diagnostic-api.md), while the
detailed write target is [Diagnostic Evidence](../domains/diagnostic-evidence.md).

### Diagnostic evidence and access

`diagnostics` may read the `promo` Attempt/correlation projection and attach
detailed evidence best-effort. It MUST NOT create an empty replacement anchor,
mutate the core Attempt/result/session or make evidence completion a
participant-flow prerequisite. Operator, photographer and developer views
remain data-class-specific; missing finalization stays visibly `incomplete`.
For staff investigation, the diagnostics HTTP adapter obtains the current
principal through the `staff_access` application boundary and passes that
principal to diagnostics-owned business authorization and projection.
`staff_access` authenticates only; it MUST NOT decide diagnostic visibility,
query evidence or own the investigation use case. The backend composition root
registers the adapter and owns neither interaction.
The exact bounded promo query, staff routes, role projections, evidence states
and failures are owned by the
[Attempt Investigation API](attempt-investigation-api.md).
The developer-only annotation child routes, mutation authorization and failure
contract are owned by the
[Ground-Truth Annotation API](ground-truth-annotation-api.md); normalized rows
and calculation input remain diagnostics-owned under
[Ground-Truth Annotations](../domains/ground-truth-annotations.md).
The fixed operational event envelope, non-blocking writer and owner persistence
are defined by [Structured Server Events](../domains/structured-server-events.md),
while the developer-only staff search/filter/navigation surface is defined by
the [Server Event API](server-event-api.md). Promo producers use the existing
`promo -> diagnostics` boundary and MUST NOT write event rows directly;
diagnostics staff search reuses the existing `diagnostics -> staff_access`
authentication edge. No new module edge or read model is introduced.

### Calibration and serving change

`diagnostics` owns evidence selection and Calibration recommendations. It calls
`processing` for offline evaluation and reads its own immutable annotation
projection. A recommendation never changes serving state automatically; only a
separate explicit developer action may ask
`serving_control` to apply the accepted setting through its audited command.
The exact immutable dataset, typed offline-evaluation boundary, run state,
minimal developer surface, apply and retention are owned by
[Calibration](../domains/calibration.md). The reproducible oracle is owned by
[Calibration verification](../testing/calibration.md).

### Manual serving-revision switch

- Owner: `serving_control`.
- Input: an authenticated operator's explicit global target revision B and an
  active initiating `spa_id`; shared current A is resolved inside the owner boundary.
  The retained venue argument does not request a venue-specific model change.
- Output: an audited success/failure result naming the requested and currently
  committed revisions.
- `serving_control` asks `processing` to validate the target; only a validated
  revision may serve. Before B commits, it also asks `processing` for the
  read-only guard for every venue and its exact current revision. The guard reports
  whether any Photo admitted against A has its `(photo_id, A)` state in
  `pending` or `processing`; `serving_control` neither reads nor writes those
  processing-owned rows directly.
- Serving selection and admission serialize on the same serving context: an
  admission either commits its A snapshot and matching A state before the guard
  (therefore blocks B), or observes B only after B commits. A guard rejection
  records the failure result, keeps A committed, and changes no Photo state,
  assets or process. `ready`, `no_faces` and `failed` A states are terminal and
  do not block.
- Creation/switch commands serialize with a transaction advisory lock; switches
  lock all venue rows in UUID order and update all revision pointers atomically.
  Any venue's guard blocks the entire switch. Creation with a different active
  revision and switches from conflicting active revisions fail explicitly.
  Startup resolves the shared eligible revision without selecting a venue.
  Settings remain venue-local; model changes use maintenance and consumer restart.
- Calibration/model comparison is test-only. It neither invokes this command
  nor supplies an exception to its guard; only a separate authenticated manual
  serving-control action can request a revision change.
- During an existing worker's visible `current_operation=calibration`,
  `processing` may bind the two explicitly selected eligible direct adapters
  sequentially from its configured read-only assets solely to evaluate the
  immutable Calibration snapshot. This does not alter the committed serving
  revision, invoke the serving-switch command or guard, replace the startup
  adapter, introduce a registry, or preload both adapters simultaneously.
- The composition root owns only the deployment binding: it reads the committed
  revision, resolves that pipeline's configured detector/recognizer paths from
  the operator-managed read-only mount and asks `processing` to verify the full
  immutable model identity. It owns no revision-selection or fallback policy.
- A failure after B commits leaves participant service unavailable and never
  changes the committed revision automatically. Recovery is an explicit retry
  or manual selection of the prior revision; normal worker and realtime startup
  load only the committed revision and stay unavailable before work if its
  assets cannot be admitted. The Calibration-only sequential bindings above do
  not change that startup rule. The exact admission contract is owned by
  [Photo Processing](../domains/photo-processing.md#model-asset-admission).

### Retention cleanup

`promo` owns the project-wide latest cleanup result, selects its own expired
Attempt candidates and calls `diagnostics` to expire diagnostic-owned data for
those UUIDs. Diagnostics also expires its terminal ordinary Calibration runs
under the same 90-day cutoff. It expires ordinary evidence and annotation rows,
then confirms both converged owner data and the explicit no-row case before
promo deletion. Each module deletes only its own
rows/objects. Exact cutoffs and promoted-subset retention are owned by the
[lifecycle map](../states/lifecycle-map.md#diagnostic-and-calibration-retention).
Diagnostics also deletes its structured server events independently by the
fixed 30-day technical-event cutoff, including uncorrelated rows, and returns
the confirmed count through the same public result shape.
Failure remains observable, a project-scoped advisory lock rejects overlapping
runs without overwriting the active result, and rerun is safe. No cleanup
history, generic jobs lifecycle or cross-owner cascade is introduced. Exact
command ordering, external daily activation and the staff latest-result surface
are owned by the
[Diagnostic Retention API](diagnostic-retention-api.md).

### Photo Inventory Operations

`inventory` owns selection, authorization, visibility and purge commands. It
commands only the `processing` cleanup boundary before deleting its own
Photo/media and MUST NOT mutate or cascade into Promo sessions/results, core
Attempts or diagnostic evidence. Exact visibility, session continuity and
fixed-snapshot purge transitions are owned by the
[lifecycle map](../states/lifecycle-map.md#photo-inventory-visibility); selection,
authorization and observable staff outcomes are owned by the
[Photo Inventory API](photo-inventory-api.md). The singleton run shape,
owner-ordered purge flow and restart convergence are owned by
[Photo Inventory](../domains/photo-inventory.md); processing-owned row and
derivative deletion is the exact
[Inventory Purge Cleanup Boundary](../domains/photo-processing.md#inventory-purge-cleanup-boundary).

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

- After JPEG validation, the backend writes each upload candidate under a
  unique opaque private MinIO key before database arbitration. The browser
  never gets direct MinIO access.
- PostgreSQL uniqueness on `(spa_id, visit_date, checksum_sha256)` arbitrates
  concurrent admission. A duplicate creates no Photo/processing state and
  deletes only its candidate object; an accepted Photo keeps its initial key.
- The per-Photo PostgreSQL commit publishes
  `Photo + accepted_at + pending`. A pre-commit crash may leave a private orphan
  and lose that admission; ordinary re-upload is sufficient admission recovery.
  Operator-triggered candidate cleanup checks MinIO keys against committed
  Photo references while a PostgreSQL lock excludes concurrent candidate
  staging and admission. It never deletes a referenced original.
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
- After that response, `SpaPromoClient` may report the browser-local receipt
  marker best-effort through the exact authenticated
  [Client Diagnostic API](client-diagnostic-api.md); report failure changes no
  participant outcome and creates no replacement Attempt.
- Display and QR continuation cross the HTTPS application boundary. Their
  success, expiry and missing-media states are owned by the
  [lifecycle map](../states/lifecycle-map.md#promo-qr-and-browser-session);
  exact exchange, phone read, activity, media and redirect behavior is in the
  [QR Continuation API](qr-continuation-api.md).
- PostgreSQL and MinIO remain private; application access follows the
  [shared database](#shared-postgresql-contract) and
  [cross-store convergence](#postgresql-and-minio-convergence) contracts.

### Central-origin client delivery

The backend serves the plain static `SpaPromoClient` bundle through the existing
central Face Moment HTTPS origin and edge. The loadable shell provides local
advertising plus configuration/debug navigation without a second public origin,
local web server, local bridge, WebSocket or new runtime role. Camera, sensor,
detector, capture and submission behavior remain separate consumers of this
delivery surface. Verification loads the real bundle through the public HTTPS
origin and inspects runtime topology for every forbidden alternate route.

### Authentication and data-specific delivery

- `serving_control` owns central display-client token value, Admin reveal and
  lifecycle under [Display Client Access](../domains/display-client-access.md).
  The server retains the current retrievable value plus its matching hash,
  authenticates by hash and derives authoritative `spa_id`; client input cannot
  override it. The token appears in the authorized `no-store` Admin settings
  response and client Authorization header only, never in URLs or logs.
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

Date-selector format correction (operator, 2026-09-11): every date input on
this surface displays `dd.mm.yyyy` through validated text with a calendar
trigger. Calendar selection and manual entry stay synchronized. Transport
continues using the existing ISO date/UTC timestamp contracts.

## Staff inventory media reads

`inventory -> processing` extends the existing read edge with persisted
admission-revision thumbnail availability and processing status for authorized
staff media browsing. Processing owns its derivative references; inventory owns
Photo selection, authorization and original references. Infrastructure reads
private bytes after authorization. See [Staff Venue Media](photo-inventory-api.md#staff-venue-media).
No module, worker lifecycle, public Promo/QR delivery or Foundation change.

The owner-local read takes Photo IDs with their immutable admission revision
IDs and returns, per matching pair, only nullable `thumbnail_object_key` and
`status`. An absent admission row returns null values; later revision rows
never substitute for it. The object key remains an internal infrastructure
reference and MUST NOT enter browser payloads or errors. The call performs no
state transition, inference, object write or on-demand derivative generation.
Verify admission-lineage selection with two revisions and an absent row;
staff authorization and byte delivery are verified through the inventory API.
