# Face Moment — accepted KISS target architecture

## 1. Scope and reliability target

This document is the accepted greenfield architecture source for one СПА, one
CPU-only server and one display client. The repository has no working
application, backend, worker or deployed runtime yet; every runtime/component
named below is a target to be implemented. The target is a practical working
horse: normal process/browser crashes recover automatically, background work
safely restarts from the beginning, maintenance downtime is acceptable, and
rare native hangs may require a manual restart.

The recommendation preserves these accepted product constraints:

| Constraint | Key rationale |
|---|---|
| Five capability slices for the current pilot: `serving_control`, `inventory`, `processing`, `promo`, `diagnostics`. | Five is the smallest current map that separates configuration, commercial ingest, ML work, participant results and protected evidence without turning technical layers into slices; later accepted product scope may justify revisiting it. |
| Greenfield staff authentication and role enforcement. | The project has no existing backend or IdP, while photographer/operator/developer access differs materially. |
| Crash/restart behavior for every long-running role. | A one-server pilot needs predictable recovery from ordinary failures, but not distributed or zero-downtime guarantees. |
| Idempotent PostgreSQL/MinIO operations without distributed transactions. | The two stores cannot share a transaction; simple retryable state transitions are sufficient. |
| Role-scoped Photo Inventory Operations and direct PostgreSQL statistics. | Soft deletion is reversible, one global hard purge reuses the shared worker, and 1/5/60-minute counters do not justify another queue, service or realtime transport. |
| Client-generated attempt ID plus a separate display acknowledgement. | Server response proves result construction, while only the client can prove that four teasers and a scannable QR were actually visible. |
| One session-wide browser access state per QR ticket. | Scans during the 30-minute first-open window reuse the same Promo session and shared 60-minute idle state; per-device grant rows add state that the current pilot does not need. |
| Standard HTTP errors plus compact domain outcomes. | Conventional transport semantics keep backend/client contracts small; accepted capture/search outcomes are not disguised as technical failures. |
| One PostgreSQL schema and one sequential migration stream. | Capability slices are ownership boundaries inside one deployable, not independently administered database services. |
| No backup in the MVP. | Loss of the only disk/server is an accepted data-loss event; recovery covers intact primary volumes and ordinary process/host restarts. |
| Extension seams for selfie search, payment and original download. | Stable identifiers and ownership boundaries reduce future migration cost without creating unused MVP code. |

## 2. Strategic decisions

| Area | Recommended decision | Key rationale and rejected alternative |
|---|---|---|
| Architecture | One Python/FastAPI modular monolith, one repository and one release. | Direct in-process calls fit the shared invariants and one-server deployment; microservices would add network, deployment and consistency work without an independent scaling need. |
| Slice map | Five capability packages, not five services. | Packages provide ownership and test seams at low runtime cost; a four-slice map would merge unrelated write invariants, while more slices would mostly represent technical layers. |
| Runtime | `backend`, one `BackgroundPhotoWorker`, one `RealtimeFaceService`, plus the browser client. | Background throughput and realtime latency need process isolation; extra replicas or services provide little value for one СПА. |
| Data | PostgreSQL/pgvector for state and exact search; private MinIO for binaries. | This is the accepted simple baseline; a broker, external vector database or media service would duplicate infrastructure. |
| Internal communication | Direct typed Python calls and one short per-photo PostgreSQL transaction spanning `Photo + pending`. | This protects durable processing admission without Batch-level atomicity, mediator/event-bus abstractions or a generic Unit of Work. |
| Realtime transport | One synchronous HTTPS request and one idempotent display acknowledgement. | The initiating display is the only result consumer; WebSocket/SSE reconnection state would not remove the need for the acknowledgement. |
| Background queue | `photo_pipeline_states` in PostgreSQL, consumed by exactly one configured worker replica. | A row-state queue closes the current at-least-once requirement; advisory locks, fencing tokens and a broker protect concurrency excluded from the target pilot topology. |
| Search | Exact pgvector cosine search after pipeline/СПА/date filtering. | The pilot data set is bounded; ANN introduces recall and index-management risk before a measured bottleneck. |
| HTTP failures | Standard HTTP statuses for authentication, authorization, payload, validation, rate-limit and internal/upstream failures; compact domain outcomes for accepted capture/search requests. | A custom error framework would add an envelope, mapping layer and client dependency without comparable value for one backend. |
| Database layout | One PostgreSQL schema, one SQLAlchemy `Base/MetaData`, one Alembic configuration and one sequential migration stream. | Per-slice schemas/users/ACLs and independent migration pipelines would imitate service isolation inside one deployable and complicate shared transactions, joins and operations. |
| Documentation shape | A small `split-core-docs` set: system architecture, boundary map and applicable lifecycle/security contracts. | A document per edge case creates drift, while one giant document hides the few important contracts. |
| Reliability | Automatic recovery from crashes, restart-from-scratch jobs and manual recovery for rare hangs. | Enterprise split-brain, zero-downtime and automated hang recovery cost more than their pilot value. |
| Foundation | A minimal executable walking skeleton before feature work. | Greenfield runtime/storage/native compatibility is shared by all features; extensive recovery or browser matrices are cheaper inside the owning features. |
| Inventory operations | One active/soft-deleted marker, one resumable global hard-purge run and direct PostgreSQL counter queries. | Per-photo purge states, a purge jobs table, another worker, aggregate counter storage and WebSocket/SSE add lifecycle and recovery cost without pilot value. |

## 3. System topology

```text
HTTPS edge
└── backend
    ├── staff UI/API, Photo Inventory Operations and local staff auth
    ├── serving settings
    ├── QR exchange and phone continuation
    └── diagnostics / annotation / Calibration UI

private network
├── PostgreSQL + pgvector
├── MinIO
├── BackgroundPhotoWorker (photo processing, Calibration, hard purge)
└── RealtimeFaceService

SpaPromoClient
├── camera ring buffer and sensor input
├── local advertising/app shell
├── display state machine
└── HTTPS realtime request + display acknowledgement
```

All server roles are recommended to use the same release image and shared Python packages. Process separation remains an operational boundary rather than a microservice contract.

Recommended discovery roots:

```text
src/face_moment/
  entrypoints/
  platform/auth/
  serving_control/
  inventory/
  processing/
  promo/
  diagnostics/
  infrastructure/

clients/spa-promo/
tests/
```

`platform/auth` is recommended as a narrow technical component rather than a sixth capability slice. It owns only staff principals, credentials and server sessions; business authorization stays with the five slices.

## 4. Five-slice ownership

| Slice | Owned state and behavior | Public boundary | Excluded ownership | Boundary rationale |
|---|---|---|---|---|
| `serving_control` | СПА identity/timezone, active `visit_date`, active pipeline revision, threshold/quality settings, `settings_revision`, SpaPromoClient token lifecycle and manual change audit. | Read immutable `ServingContext`/`IngestTarget`; validate and apply a manual settings change. | Photos, processing state, attempts, sessions, detailed evidence and recommendations. | One write owner prevents participant or Calibration paths from silently changing serving scope. |
| `inventory` | Independent Photo admission, photographer-selected СПА/date, effective `captured_at`, checksum duplicate decision, Photo identity/`accepted_at`/original key/uploader/active marker, role-scoped soft delete/restore, direct recent statistics and the global hard-purge orchestration. | Admit one uploaded JPEG; return accepted/rejected/duplicate outcome; query and change authorized Photo visibility; restore all; start/read one confirmed global hard purge; read per-СПА 1/5/60-minute counters. | Pipeline-state transitions, embeddings/search, Promo result/session state, core Attempts and diagnostic evidence. | Admission, visibility and permanent removal share the Photo ownership invariant; keeping them together avoids a deletion service or another slice. |
| `processing` | Pipeline catalog/compatibility, native FaceEngine adapters, photo processing states, previews/faces/embeddings, query quality, exact search and offline model evaluation. | Create the serving-revision `pending` state during Photo admission; report readiness; process one reference query under an explicit serving snapshot; remove Photo-owned derived state when inventory orchestrates hard purge. | Photo admission/visibility, live settings reads, result/session assembly and recommendation application. | Background and realtime ML share preprocessing/revision invariants; a separate FaceEngine slice would only be a technical layer. |
| `promo` | Attempt/result identity, applied snapshot, candidate/result sets, four teasers, `N`, QR ticket, session-wide browser access state, continuation and SpaPromoClient behavior. Future purchase/payment/entitlement state also stays here. | Execute a fresh attempt; accept display outcome; exchange QR ticket; read session-bound continuation. | Inventory/processing/settings writes and detailed diagnostic evidence. | Search result, QR and continuation form one participant-journey integrity boundary; future payment consumes the immutable result and does not justify a sixth slice. |
| `diagnostics` | Detailed events/artifacts, sanitized/developer views, logs, annotations, curated Calibration cases and recommendations. | Record best-effort evidence; search attempts/logs; authorize artifacts; annotate/evaluate/apply through owning boundaries. | Core result/session and direct settings mutation. | Evidence, annotation and Calibration share privacy/retention rules but remain outside participant success. |

## 5. Dependencies and transaction boundaries

Recommended runtime calls:

```text
inventory ──read ingest target──> serving_control
inventory ──enqueue──> processing
inventory ──hard-purge derived state──> processing
inventory ──hard-purge affected results/sessions──> promo
promo ──read──> serving_control
promo ──search──> processing
promo ──best-effort evidence──> diagnostics
diagnostics ──read projection──> promo
diagnostics ──offline evaluation──> processing
diagnostics ──manual apply──> serving_control
```

One shared PostgreSQL transaction is recommended per independently accepted
Photo. `inventory` owns admission and calls the public `processing` command that
creates the serving-revision `pending` state; the transaction commits `Photo +
pending + accepted_at` together. It never waits for or groups other uploads.

MinIO is outside that transaction. A crash after object upload but before commit
may leave one private orphan and lose that admission; this is an accepted risk
and does not justify distributed transaction machinery.

Attempt creation is not a shared transaction. `promo` persists one core Attempt
before inference. `diagnostics` attaches events and artifacts best-effort by
`attempt_id`; a terminal Attempt without finalized evidence is projected as
`incomplete`, so a separate diagnostic-anchor row is unnecessary.

The shared database permits published read projections while retaining one
write owner per invariant. Foreign direct writes, a generic Unit-of-Work
framework, an event bus and an outbox are not recommended for the pilot.

All capability tables remain in one PostgreSQL schema and use one shared
SQLAlchemy `Base/MetaData`, one Alembic configuration and one sequential
migration stream. Table models and repositories stay in their owning
capability packages. This physical layout does not grant cross-slice command or
write authority. Foreign keys and `ON DELETE` actions are chosen explicitly;
database cascade must not cross an ownership boundary and must never delete a
core Attempt or diagnostic evidence as a side effect of deleting a Photo.

`inventory` orchestrates Photo Inventory Operations through the owning slice
boundaries. Soft delete/restore changes only the inventory-owned Photo
visibility marker. Hard purge may remove state owned by `processing` and
`promo`, but it does so through their cleanup commands rather than by
duplicating their invariants. Core Attempts and diagnostic evidence remain
owned by `promo`/`diagnostics` and are not hard-purge targets.

### HTTP failure semantics

Technical request failures use conventional HTTP semantics without a
project-specific error framework:

| HTTP status | Meaning in the pilot |
|---|---|
| `401` | Authentication is absent or invalid. |
| `403` | The authenticated principal lacks permission. |
| `413` | The accepted payload bound is exceeded. |
| `422` | Request validation fails. |
| `429` | The applicable rate limit is exceeded. |
| `5xx` | An internal or upstream technical failure occurred. |

An admitted capture/search request may instead finish with a successful
transport response (`2xx`) and a compact domain outcome such as `busy`,
`deadline`, `unacceptable_query` or `insufficient_results`. These are normal
business results, not transport errors. `429` denotes rate-limit rejection,
whereas `busy` reports the accepted singleton-slot condition; `422` denotes
request validation failure, whereas `unacceptable_query` reports evaluated
query quality. The client branches on the HTTP status and typed domain outcome
and never parses response prose, especially `5xx` text. A technical failure may
still be persisted on the core Attempt for diagnostics, but its transport
signal remains `5xx`. Concrete endpoint payloads remain feature-level
contracts; they must not introduce a shared custom error envelope or
error-mapping framework.

## 6. Serving context and pipeline changes

PostgreSQL is recommended as the source of truth for identities, state,
settings, attempts, sessions, session-wide browser access and structured
evidence. MinIO is recommended as the source of truth only for binary bytes;
committed PostgreSQL state determines whether an object is usable.

Each attempt is recommended to copy this immutable serving snapshot:

```text
settings_revision
spa_id
visit_date
pipeline_revision_id
pipeline_code
query_source = reference
threshold
quality_settings
calibration_id, if any
release_id
```

Copying values is preferred over a versioned configuration platform because it gives sufficient reproducibility with one query and a small audit trail.

Pipeline changes are recommended as manual maintenance with accepted downtime:

```text
stop participant realtime
→ validate target model/revision
→ update active pointer
→ start and warm realtime
→ run one smoke attempt
→ resume participant flow
```

Manual rollback to the prior pointer is recommended after a failed smoke. Automated admission choreography, hot switching and rollback orchestration are deferred until frequent operational switching creates a measured need.

## 7. Ingest and PostgreSQL/MinIO consistency

### Independent photo upload and admission

The recommended working-horse flow is:

1. The authenticated browser streams an upload through the public HTTPS backend boundary; MinIO remains private and is never a browser endpoint.
2. The backend assigns a unique opaque object key, writes the candidate to MinIO, then decodes and validates JPEG type, compressed bytes and decoded pixels and calculates SHA-256.
3. The photographer-selected СПА and `visit_date` plus the current immutable `IngestTarget(pipeline_revision_id)` form the admission context for this file only.
4. `UNIQUE(spa_id, visit_date, checksum_sha256)` is the concurrency arbiter through `INSERT ... ON CONFLICT DO NOTHING RETURNING`.
5. A losing duplicate keeps its visible duplicate outcome, creates no Photo or processing state and schedules deletion of only its unique uploaded object.
6. One short PostgreSQL transaction commits the new Photo, server-side `accepted_at` and serving-revision `pending` state; it never waits for another upload.
7. The accepted original keeps its initial opaque key without a MinIO move/copy.
8. The Photo receives an effective `captured_at`: reliable EXIF time interpreted
   in the СПА timezone, otherwise that file's server-side upload-start time,
   otherwise 01:00 on the authoritative `visit_date`.

This flow is recommended over a cross-store transaction emulator because a
private orphan or one lost admission during a crash is acceptable and simpler
than coordinating PostgreSQL and MinIO.

There is no Batch, manifest, draft-confirmation lifecycle or aggregate upload
commit. Other readers may observe a partial set while the photographer is still
uploading; search always uses all compatible `ready` photos already present for
the active СПА/date.

### Photo visibility, statistics and deletion

Soft deletion is one inventory-owned active/soft-deleted marker. It preserves
the Photo record, original/preview/thumbnail, faces, pipeline states and other
related data, but all search, participant media reads and recent-statistics
queries must filter soft-deleted Photos out. Restore clears the marker and
reuses the preserved state without re-upload or reprocessing.

A photographer may soft-delete or restore only Photos uploaded by that
photographer. An operator or developer may do so for any Photo in an accessible
СПА. Selection uses one СПА, authoritative `visit_date` and the effective
`captured_at` range. Project-wide restore-all and hard purge are restricted to
authorized operator/developer settings.

The Admin UI polls PostgreSQL-backed per-СПА counters every five seconds for
the last 1, 5 and 60 minutes:

| Counter | Definition for active Photos |
|---|---|
| `new` | Unique Photos whose `accepted_at` is inside the window. |
| `unprocessed` | Photos accepted inside the window and currently `pending \| processing`. |
| `processed` | Photos that transitioned to `ready \| no_faces` inside the window. |
| `failed` | Photos that transitioned to `failed` inside the window. |

The target backend computes these counters directly from Photo and
`photo_pipeline_states` timestamps. No counter materialization, metrics store,
WebSocket or SSE path is recommended before direct SQL becomes a measured
problem.

`hard delete ALL softed media` requires confirmation and creates one durable,
resumable global run over the fixed project-wide snapshot of Photos that were
soft-deleted at confirmation. The run owns only snapshot identity,
waiting/running/completed status and completed/total progress; it does not add a
per-photo `purge_pending` state or a purge jobs table.

The global run waits for the shared worker's current operation without
preemption. While waiting, the UI displays `Начну удаление, как только
закончится процесс {human-readable process name}`; while running, the
destructive settings surface is replaced by completed/total progress. The
worker resumes the same snapshot after process restart and deletes each Photo,
its original/preview/thumbnail, face and pipeline data, and every Promo
result/session containing it. Core Attempts and diagnostic evidence are
preserved under their ordinary retention rules even when they contain
historical references to deleted Photos.

Soft deletes made after confirmation are outside the fixed snapshot. Uploads
already in progress are never interrupted; keeping ordinary upload admission
available during purge is the KISS default, and newly accepted Photos merely
add normal `pending` work while the shared worker is occupied.

Derived preview/thumbnail keys are recommended to be deterministic by `photo_id/pipeline_revision/artifact_kind`. With one worker replica, a retry can safely overwrite the same key and then replace face rows plus terminal state in one transaction.

Recommended retryable binary cleanup remains:

```text
make the object inaccessible through Photo visibility or owning-state deletion
→ idempotent MinIO delete
→ complete the owning database cleanup
```

This sequence is preferred over stronger cross-store machinery because a crash
leaves only a retryable private orphan or an already inaccessible object. The
global run progress supplies hard-purge resumption without another per-object
lifecycle.

MinIO versioning and external volume snapshots are recommended to remain disabled in the no-backup MVP. This keeps retention behavior truthful and avoids hidden copies.

## 8. Startup and crash recovery

Recommended startup path:

```text
PostgreSQL and MinIO healthy
→ one migrate/init command applies the single sequential Alembic stream to the
  one application schema and ensures buckets
→ backend, worker and realtime start or fail fast
→ realtime becomes ready after exact active-model warmup
```

The HTTPS edge is recommended to remain static and return ordinary 502/503 while its upstream is unavailable. Separate readiness orchestration for every role provides little value in a stop-the-world, one-release deployment.

Container restart policies are recommended for the edge, backend, worker, realtime, PostgreSQL and MinIO; persistent primary volumes are recommended for PostgreSQL and MinIO. SpaPromoClient/Chromium is recommended to use a systemd user service.

### BackgroundPhotoWorker

The recommended worker algorithm is intentionally small:

1. Compose/configuration fixes the worker replica count at one.
2. Startup returns old `processing` rows to a retryable `pending` state.
3. One short atomic UPDATE claims the next pending photo and increments `attempts`.
4. Processing restarts from the beginning after a crash.
5. One final transaction replaces faces and publishes `ready|no_faces|failed`.
6. A small retry limit, initially three, prevents poison-file crash loops.
7. A confirmed global hard purge waits for the current operation and then uses
   the same sequential worker until its fixed snapshot completes.

This is recommended instead of advisory locks, leases, `claim_token`, fencing and claim-scoped object keys because concurrent workers are outside the deployment contract. Unique constraints and full face-set replacement still protect the required idempotency.

A process crash is recommended to rely on the container restart policy. Native-operation timestamps and health visibility are recommended for diagnosing a hang; manual `docker compose restart` is acceptable for the MVP. A killable subprocess/watchdog is deferred until an actual native hang is observed.

### RealtimeFaceService

One process and one inference slot are recommended. A concurrent request receives `busy`; a durable queue and waiter add no value because the display already ignores overlapping triggers.

The attempt is recommended to persist before inference with a server deadline. Result publication conditionally succeeds only while the attempt is active; startup closes old `accepted|searching` attempts as `interrupted`, and replay of prior realtime work is not recommended.

The server deadline remains shorter than the client timeout. A returned-late native call is ignored; a genuinely stuck process remains an observable manual-restart condition until evidence justifies stronger isolation.

### Backend and client

Backend commands are recommended to be idempotent where a browser may retry. An
interrupted upload has no durable resumable-upload lifecycle; the photographer
simply retries the file, and the ordinary checksum rule handles an already
completed first upload.

The hard-purge progress view does not require stopping the backend. Ordinary
uploads may continue because the purge snapshot contains only Photos already
soft-deleted at confirmation, while search and media access already exclude
them. This avoids upload-drain coordination and guarantees that an upload
already in progress is not interrupted.

After Chromium restart, SpaPromoClient is recommended to enter local `advertising`, discard personal result/frame state and avoid replaying search. A bounded IndexedDB outbox may retain only diagnostic metadata and `cooldown_until`; frames, tokens and personalized result data stay memory-only.

A simple authenticated client-event upsert is recommended to accept delayed offline failure metadata by `(spa_id, attempt_id)`. This closes the diagnostic gap without replaying frames or creating a durable realtime request.

## 9. Attempt and diagnostic lifecycle

The client is recommended to create one UUID `attempt_id` when an idle sensor trigger is accepted. `(spa_id, attempt_id)` is the idempotency/correlation key; a repeat is recommended to return the existing state rather than start inference again.

Processing and display outcomes are recommended as separate fields:

```text
processing_status: client_offline | accepted → searching
                   → result_issued | no_success | interrupted | deadline | internal_failure

display_status: not_applicable | pending → confirmed | failed | unconfirmed
```

`result_issued` is not counted as Promo success. Only an idempotent client acknowledgement after all four teasers are decoded and the QR is fully visible sets `display_status=confirmed`; an expired acknowledgement becomes `unconfirmed`.

The core Attempt itself is the durable diagnostic correlation point. Detailed
events/artifacts remain direct best-effort writes. An active Attempt is shown as
`collecting`; a terminal Attempt without finalized evidence is derived as
`incomplete`. No empty diagnostic anchor, after-commit delivery state, outbox or
reconciliation pass is recommended.

Client acceptance latency is recommended to use only the client monotonic clock:

```text
qr_fully_visible_elapsed_ms - reference_series_ready_elapsed_ms
```

Server stages are recommended to store their own monotonic durations. Correlation by `attempt_id` is sufficient; distributed tracing and cross-machine clock subtraction are unnecessary.

## 10. Security and public sessions

| Boundary | Recommended choice | Key rationale and rejected alternative |
|---|---|---|
| Network | Public HTTPS edge; PostgreSQL, MinIO and application service ports private. | This directly closes the public attack surface without service-mesh/network-policy machinery. |
| SpaPromoClient identity | High-entropy token in Authorization header; PostgreSQL stores only its hash and resolves `spa_id`. | Server-derived identity prevents body spoofing; OAuth/device IAM is unnecessary for one managed display. |
| Request limits | Bounded frame count, compressed bytes, dimensions/decoded pixels, decode validation and simple per-token/IP rate limits. | Cheap input bounds protect CPU/memory; distributed rate-limit storage is unnecessary with one backend. |
| CORS | Same-origin where possible, otherwise one configured SpaPromoClient origin allowlist. | A fixed allowlist covers the pilot without a general origin-management layer. |
| Staff auth | Small `platform/auth` module with CLI provision/reset/deactivate, Argon2id/bcrypt, hashed opaque PostgreSQL sessions, one short absolute TTL, logout/revoke, CSRF and three roles. | These controls satisfy greenfield access separation; staff idle tracking, self-registration, OAuth/IAM and a policy engine add little pilot value. |
| Artifact access | Backend-proxied previews/artifacts with authorization on every read. | One-server proxying is simpler than presigned-URL expiry coordination and prevents raw MinIO keys from escaping. |

### QR ticket and session-wide browser access

The recommended exchange is intentionally conventional:

```text
GET /q?ticket=<opaque ticket>
→ backend validates the ticket hash and 30-minute first-open window
→ backend opens or reuses the Promo session's single browser access state
→ backend sets the opaque ticket in an HttpOnly Secure SameSite=Lax cookie
→ 303 redirect to a clean token-free session URL
```

The edge/application access log is recommended to omit the query string for this route, with `Cache-Control: no-store` and `Referrer-Policy: no-referrer`. This is preferred over URL-fragment + JavaScript POST exchange because the shorter flow has fewer client failure modes while retaining the important token protections.

The Promo session stores one `qr_ticket_hash`, `browser_opened_at` and shared `browser_last_seen_at`; it has no per-device grant rows. Every scan before the 30-minute deadline may set the same session credential on another phone. Explicit participant navigation/actions from any opened phone update the shared `browser_last_seen_at`; asset loads and background polling provide no extension. After 60 minutes of session-wide inactivity, access expires for every opened phone. A local phone timer clears rendered personal state at expiry, while the server remains authoritative on later reads.

Display teaser reads are recommended to use `spa_client_token` plus opaque attempt/session references. Phone teaser reads use the session cookie. Both paths remain `no-store` backend reads; presigned participant URLs are deferred until backend bandwidth becomes a measured problem.

## 11. Diagnostics, retention and Calibration

Recommended bundle lifecycle:

```text
collecting → complete | incomplete → expired
```

An incomplete bundle is recommended to retain an explicit gap reason. Missing detailed evidence remains acceptable for participant flow, while the core attempt/outcome/snapshot remains available.

Recommended retention:

| Data | Retention | Rationale |
|---|---|---|
| Technical browser/server logs | 30 days | Enough operational history without indefinite privacy/storage cost. |
| Ordinary attempts and diagnostic artifacts | 90 days | Matches the diagnostic product requirement and bounds protected-data exposure. |
| Manually promoted Calibration case | Until explicit deletion | Curated reproducibility has durable value; the full source bundle does not. |
| Browser metadata outbox | Until acknowledged or a short local expiry | Metadata aids outage diagnosis; long-lived local personal data does not. |

One idempotent daily cleanup command is recommended, invoked by the planned BackgroundPhotoWorker or a simple host timer. A durable scheduler and separate retention service are not recommended.

Promotion is recommended to copy only selected frames/crops, parameters, scores and annotations into a self-contained case. Unselected frames, Promo screenshot, ordinary logs and the whole attempt retain their normal expiry.

Photo hard purge does not cascade into the core Attempt or diagnostic-evidence
lifecycle. Historical identifiers may remain in retained evidence, but media
removed with the Photo is no longer available.

Calibration work is recommended to reuse the planned shared
`BackgroundPhotoWorker`. An explicitly started Calibration run may block photo
processing for its full duration during debugging; this impact is accepted. If
the worker restarts, the Calibration run becomes `failed|interrupted`, photo
processing resumes, and the developer reruns Calibration manually. Preemption,
priority scheduling, automatic Calibration reclaim and a separate worker are
not recommended.

Recommendation application remains an explicit audited call through `serving_control`. Automatic tuning is not recommended because a mistaken threshold changes participant-facing results.

## 12. Display, hardware and CPU

Local advertising is recommended to remain available after network/server failure and Chromium restart. The delivery mechanism depends on the selected hardware:

- browser-native camera/sensor favors a versioned Service Worker app shell;
- hardware requiring a local bridge favors the same bridge serving the static bundle/assets;
- deploying both paths or a generic device-plugin framework is not recommended.

If a bridge is selected, it remains a client adapter with systemd restart rather than a capability slice. Exact camera/sensor transport is recommended to be proven at the site before its feature implementation.

Realtime is recommended to load only the active model, while worker and realtime share the same revisioned FaceEngine implementations. One realtime slot, one sequential background operation and conservative native thread caps are recommended initially; cpuset, dynamic priority and pause/resume are deferred until measurements show contention.

## 13. Full-version extension seams

The MVP is recommended to preserve only these low-cost seams:

- immutable `photo_id` and original ownership in `inventory`;
- immutable result/session ID and exact result `photo_id` set in `promo`;
- a persisted extensible `query_source` whose only MVP value is `reference`;
- pipeline/settings snapshots and a query contract that does not assume a specific camera transport.

Selfie endpoints, selfie persistence and alternate query behavior are not recommended in the MVP. A future selfie flow can reuse `promo` orchestration and `processing` search after a dedicated privacy/retention decision.

Future purchase/payment is recommended as a distinct internal module inside `promo`, preserving the accepted five-slice map. An order can copy an immutable result snapshot (`result_id`, exact `photo_id` set, СПА/date and commercial terms), while `inventory` continues to own originals and issues a short-lived download only after a promo-owned entitlement check.

A sixth `commerce` slice is not recommended while purchase remains one local continuation of the participant result. A new slice becomes reasonable only after independent deployment, regulatory ownership or reuse appears.

Payment-provider abstractions, order tables, webhooks and original-download endpoints are not recommended before the full-version scope is active. Activation also reopens the durability/retention decision because the accepted MVP disk-loss risk does not automatically define a paid entitlement guarantee.

## 14. Minimal Foundation and verification

`Foundation Required: true` is recommended because the repository has no executable runtime. The recommended Foundation scope is limited to:

- reproducible build/typecheck/test commands;
- one migrate/init command using one PostgreSQL schema, shared SQLAlchemy
  `Base/MetaData`, one Alembic configuration and one sequential migration
  stream;
- Compose PostgreSQL/pgvector and MinIO with persistent primary volumes;
- backend/worker/realtime entrypoints using a fake FaceEngine;
- one PostgreSQL and MinIO read/write/delete roundtrip;
- actual OpenCV/InsightFace container import compatibility;
- realtime model-warmup readiness seam;
- SpaPromoClient build;
- one end-to-end substrate smoke.

Foundation-level kill/restart matrices, durable reclaim tests and browser-offline hardware proof are not recommended. Background reclaim fits the processing feature; Chromium/offline proof fits capture/display features after hardware selection.

Recommended minimum feature proofs:

| Area | Evidence |
|---|---|
| `serving_control` | Client cannot override СПА/date; one immutable attempt snapshot; audited manual change. |
| `inventory` | Independent Photo admission; concurrent duplicate arbitration; atomic `Photo + pending`; role-scoped soft delete/restore; direct 1/5/60 counters; resumable fixed-snapshot hard purge with Attempt/evidence retention. |
| `processing` | Restart-from-`processing`; bounded retries; one final face set/state. |
| `promo` | Four unique teasers; correct full result/`N`; result vs display acknowledgement; session-wide access expiry. |
| `diagnostics` | Sanitized/developer role split; core Attempt with complete/incomplete evidence; promotion whitelist. |
| Client | Local advertising restart; fresh-only retry; monotonic latency; real QR scan. |

## 15. Explicit deferrals

| Deferred mechanism | Revisit trigger | Rationale |
|---|---|---|
| Advisory locks, leases, `claim_token`, fencing and claim-scoped derived objects | More than one worker replica or overlapping deployments | Singleton deployment makes stale concurrent publication impossible under the accepted model. |
| Killable inference subprocess or hard watchdog | Reproduced native hangs that require operator intervention | Crash restart already covers normal failure; hang isolation is expensive and failure-prone. |
| Redis/broker, generic scheduler or outbox | A durable workflow no longer fits owner-specific PostgreSQL rows/direct calls | Current flows are local and bounded. |
| ANN/external vector store | Measured exact-search latency or scale failure | Exact search is simpler and preserves recall. |
| Automated pipeline switching/rollback | Frequent operational revision changes | Maintenance downtime is acceptable. |
| Multiple worker/realtime replicas | Measured throughput or availability failure | Replication introduces coordination and split-brain work. |
| Presigned participant media delivery | Backend proxy becomes a measured bottleneck | Proxy authorization is simpler for one server. |
| GPU, Kubernetes or external observability stack | Proven CPU/deployment/diagnostic limitation | They add operational surface without current evidence. |
| Payment/selfie/download implementation | Full-version feature activation | Only stable identifiers and ownership seams have current value. |
| Backup/replication/snapshots | Before paid flow or public rollout, or after a new operator durability decision | The current pilot explicitly accepts loss of the only disk/server. |
| Per-photo purge state/jobs, separate purge worker, counter materialization, WebSocket/SSE statistics | Measured purge or five-second polling failure | One global run, the shared worker and direct PostgreSQL queries satisfy current operations with less state. |
| Per-slice PostgreSQL schemas/users/ACLs or independent migration streams | A slice becomes an independently deployed and operated service with an accepted migration plan. | The current capability slices share one deployable and gain no useful isolation from service-shaped database administration. |

## 16. Accepted pilot risks

The following risks are consciously accepted for the current pilot and do not
authorize additional lifecycle, coordination or recovery machinery:

- Irrecoverable loss of the only primary disk or server may destroy all
  persisted data; the pilot has no backup, replication or snapshot guarantee.
- A crash between the MinIO upload and the PostgreSQL commit may leave one
  private orphan and may require that one photograph to be uploaded again.
- While the photographer is still uploading, search and other readers may see
  only the subset of compatible `ready` photos already stored for the active
  СПА/date.
- Ingest metrics observed during an unfinished upload period may temporarily be
  incomplete or misleading; no Batch-level SLO coordination is required.
- A developer-started Calibration run may occupy the single
  `BackgroundPhotoWorker` and delay photo processing for the duration of that
  debugging run. After interruption, the developer may rerun it manually.
- A photograph uploaded under the wrong photographer-selected СПА or
  `visit_date` has no special correction workflow in the pilot; the operator
  accepts this risk because the remedy costs more than the expected problem.
- When EXIF time is missing or unreliable, effective `captured_at` derived from
  the individual file's server-side upload-start time or final `visit_date`
  01:00 fallback may be approximate; no separate manual-resolution path is
  required.
- A global hard purge may delay ordinary Photo processing while it occupies the
  shared worker; uploads may continue and accumulate normal durable `pending`
  work until purge completes.
