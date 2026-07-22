# Face Moment — KISS architecture recommendation

## 1. Scope and reliability target

This document describes an advisory greenfield architecture for one СПА, one CPU-only server and one display client. The target is a practical working horse: normal process/browser crashes recover automatically, background work safely restarts from the beginning, maintenance downtime is acceptable, and rare native hangs may require a manual restart.

The recommendation preserves these accepted product constraints:

| Constraint | Key rationale |
|---|---|
| Exactly five capability slices: `serving_control`, `inventory`, `processing`, `promo`, `diagnostics`. | Five is the smallest map that separates configuration, commercial ingest, ML work, participant results and protected evidence without turning technical layers into slices. |
| Greenfield staff authentication and role enforcement. | No external backend or IdP exists, while photographer/operator/developer access differs materially. |
| Crash/restart behavior for every long-running role. | A one-server pilot needs predictable recovery from ordinary failures, but not distributed or zero-downtime guarantees. |
| Idempotent PostgreSQL/MinIO operations without distributed transactions. | The two stores cannot share a transaction; simple retryable state transitions are sufficient. |
| Client-generated attempt ID plus a separate display acknowledgement. | Server response proves result construction, while only the client can prove that four teasers and a scannable QR were actually visible. |
| Multiple browser grants per QR ticket. | Several phones may scan the same display during the 30-minute grant-creation window; every grant retains an independent 60-minute idle TTL. |
| No backup in the MVP. | Loss of the only disk/server is an accepted data-loss event; recovery covers intact primary volumes and ordinary process/host restarts. |
| Extension seams for selfie search, payment and original download. | Stable identifiers and ownership boundaries reduce future migration cost without creating unused MVP code. |

## 2. Strategic decisions

| Area | Recommended decision | Key rationale and rejected alternative |
|---|---|---|
| Architecture | One Python/FastAPI modular monolith, one repository and one release. | Direct in-process calls fit the shared invariants and one-server deployment; microservices would add network, deployment and consistency work without an independent scaling need. |
| Slice map | Five capability packages, not five services. | Packages provide ownership and test seams at low runtime cost; a four-slice map would merge unrelated write invariants, while more slices would mostly represent technical layers. |
| Runtime | `backend`, one `BackgroundPhotoWorker`, one `RealtimeFaceService`, plus the browser client. | Background throughput and realtime latency need process isolation; extra replicas or services provide little value for one СПА. |
| Data | PostgreSQL/pgvector for state and exact search; private MinIO for binaries. | This is the accepted simple baseline; a broker, external vector database or media service would duplicate infrastructure. |
| Internal communication | Direct typed Python calls and two explicit shared-transaction boundaries. | Visible calls are easier to debug than mediator/event-bus abstractions in a monolith. |
| Realtime transport | One synchronous HTTPS request and one idempotent display acknowledgement. | The initiating display is the only result consumer; WebSocket/SSE reconnection state would not remove the need for the acknowledgement. |
| Background queue | `photo_pipeline_states` in PostgreSQL, consumed by exactly one configured worker replica. | A row-state queue closes the current at-least-once requirement; advisory locks, fencing tokens and a broker protect concurrency that the deployment does not have. |
| Search | Exact pgvector cosine search after pipeline/СПА/date filtering. | The pilot data set is bounded; ANN introduces recall and index-management risk before a measured bottleneck. |
| Documentation shape | A small `split-core-docs` set: system architecture, boundary map and applicable lifecycle/security contracts. | A document per edge case creates drift, while one giant document hides the few important contracts. |
| Reliability | Automatic recovery from crashes, restart-from-scratch jobs and manual recovery for rare hangs. | Enterprise split-brain, zero-downtime and automated hang recovery cost more than their pilot value. |
| Foundation | A minimal executable walking skeleton before feature work. | Greenfield runtime/storage/native compatibility is shared by all features; extensive recovery or browser matrices are cheaper inside the owning features. |

## 3. System topology

```text
HTTPS edge
└── backend
    ├── staff UI/API and local staff auth
    ├── serving settings
    ├── QR exchange and phone continuation
    └── diagnostics / annotation / Calibration UI

private network
├── PostgreSQL + pgvector
├── MinIO
├── BackgroundPhotoWorker
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
| `serving_control` | СПА identity/timezone, active `visit_date`, active pipeline revision, threshold/quality settings, `settings_revision`, SpaPromoClient token lifecycle and manual change audit. | Read immutable `ServingContext`/`IngestTarget`; validate and apply a manual settings change. | Batches, processing state, attempts, sessions, detailed evidence and recommendations. | One write owner prevents participant or Calibration paths from silently changing serving scope. |
| `inventory` | Draft candidates, Batch and immutable manifest, authoritative date, checksum duplicate decision, Photo identity/original key and photographer ownership. | Upload/review/discard/confirm Batch; expose immutable photo projections; authorize access to owned batches. | Pipeline state, embeddings/search, Promo sessions and diagnostics. | Commercial ingest immutability changes independently from ML retries and model revisions. |
| `processing` | Pipeline catalog/compatibility, native FaceEngine adapters, photo processing states, previews/faces/embeddings, query quality, exact search and offline model evaluation. | Enqueue immutable photo input; report readiness; process one reference query under an explicit serving snapshot. | Batch confirmation, live settings reads, result/session assembly and recommendation application. | Background and realtime ML share preprocessing/revision invariants; a separate FaceEngine slice would only be a technical layer. |
| `promo` | Attempt/result identity, applied snapshot, candidate/result sets, four teasers, `N`, QR ticket, browser grants, continuation and SpaPromoClient behavior. Future purchase/payment/entitlement state also stays here. | Execute a fresh attempt; accept display outcome; exchange QR ticket; read session-bound continuation. | Inventory/processing/settings writes and detailed diagnostic evidence. | Search result, QR and continuation form one participant-journey integrity boundary; future payment consumes the immutable result and does not justify a sixth slice. |
| `diagnostics` | Detailed events/artifacts, sanitized/developer views, logs, annotations, curated Calibration cases and recommendations. | Record best-effort evidence; search attempts/logs; authorize artifacts; annotate/evaluate/apply through owning boundaries. | Core result/session and direct settings mutation. | Evidence, annotation and Calibration share privacy/retention rules but remain outside participant success. |

## 5. Dependencies and transaction boundaries

Recommended runtime calls:

```text
inventory ──read ingest target──> serving_control
inventory ──enqueue──> processing
promo ──read──> serving_control
promo ──search──> processing
promo ──best-effort evidence──> diagnostics
diagnostics ──read projection──> promo
diagnostics ──offline evaluation──> processing
diagnostics ──manual apply──> serving_control
```

Two shared PostgreSQL transactions are recommended because they reduce failure states without introducing distributed coupling:

1. Batch confirmation freezes the manifest, creates Photos and inserts initial processing rows.
2. Attempt creation/result publication creates the promo core record and its small diagnostic anchor row; detailed evidence remains best-effort after commit.

The shared database is recommended to permit published read projections while retaining one write owner per invariant. Foreign direct writes, a generic Unit-of-Work framework, an event bus and an outbox are not recommended for the MVP because direct calls and two documented transactions cover the current flows.

## 6. Serving context and pipeline changes

PostgreSQL is recommended as the source of truth for identities, state, settings, attempts, sessions, grants and structured evidence. MinIO is recommended as the source of truth only for binary bytes; committed PostgreSQL state determines whether an object is usable.

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

### Upload and confirmation

The recommended working-horse flow is:

1. A draft candidate receives a unique opaque object key before upload.
2. A completed MinIO PUT is decoded and validated for JPEG type, compressed bytes and decoded pixels.
3. A stale `uploading` candidate becomes `failed/delete_pending`; the photographer reuploads instead of resuming an ambiguous partial request.
4. Confirmation locks the draft Batch and reads one immutable active `IngestTarget(pipeline_revision_id)`.
5. `UNIQUE(spa_id, visit_date, checksum_sha256)` remains the concurrency arbiter through `INSERT ... ON CONFLICT DO NOTHING RETURNING`.
6. A losing duplicate keeps its visible outcome, creates no Photo/job and schedules deletion of only its unique upload key.
7. Manifest, Photos and initial processing rows commit in one PostgreSQL transaction; accepted originals keep their original upload keys without MinIO move/copy.

This flow is recommended over a cross-store transaction emulator because retryable private orphans are harmless and simpler to clean.

Valid unconfirmed drafts are recommended to remain until explicit confirmation/discard. Existing batch/storage views can expose stale drafts; an automatic draft TTL is deferred until storage pressure demonstrates a need.

### Derived objects and deletion

Derived preview/thumbnail keys are recommended to be deterministic by `photo_id/pipeline_revision/artifact_kind`. With one worker replica, a retry can safely overwrite the same key and then replace face rows plus terminal state in one transaction.

Recommended delete sequence:

```text
mark object inaccessible/delete_pending in PostgreSQL
→ idempotent MinIO delete
→ clear the object reference while preserving the visible outcome
```

This three-step sequence is preferred over stronger cross-store machinery because a crash leaves only a retryable private orphan or an inaccessible pending deletion.

MinIO versioning and external volume snapshots are recommended to remain disabled in the no-backup MVP. This keeps retention behavior truthful and avoids hidden copies.

## 8. Startup and crash recovery

Recommended startup path:

```text
PostgreSQL and MinIO healthy
→ one migrate/init command applies schema and ensures buckets
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

This is recommended instead of advisory locks, leases, `claim_token`, fencing and claim-scoped object keys because concurrent workers are outside the deployment contract. Unique constraints and full face-set replacement still protect the required idempotency.

A process crash is recommended to rely on the container restart policy. Native-operation timestamps and health visibility are recommended for diagnosing a hang; manual `docker compose restart` is acceptable for the MVP. A killable subprocess/watchdog is deferred until an actual native hang is observed.

### RealtimeFaceService

One process and one inference slot are recommended. A concurrent request receives `busy`; a durable queue and waiter add no value because the display already ignores overlapping triggers.

The attempt is recommended to persist before inference with a server deadline. Result publication conditionally succeeds only while the attempt is active; startup closes old `accepted|searching` attempts as `interrupted`, and replay of prior realtime work is not recommended.

The server deadline remains shorter than the client timeout. A returned-late native call is ignored; a genuinely stuck process remains an observable manual-restart condition until evidence justifies stronger isolation.

### Backend and client

Backend commands are recommended to be idempotent where a browser may retry. Ambiguous stale uploads become failed and reuploadable rather than receiving a resumable-upload state machine.

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

The core attempt and a small `collecting` diagnostic anchor are recommended in the same PostgreSQL transaction. Detailed events/artifacts remain direct best-effort writes; finalization marks the bundle `complete|incomplete`, and an old unfinished anchor can become `incomplete` during daily cleanup.

This is recommended over `EvidenceSink` adapters, after-commit delivery state and reconciliation because one extra row in the already-required database transaction is cheap and guarantees an observable bundle anchor.

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

### QR ticket and browser grants

The recommended exchange is intentionally conventional:

```text
GET /q?ticket=<opaque ticket>
→ backend validates ticket hash and 30-minute grant-creation window
→ backend reuses this browser's active grant or creates an independent grant
→ HttpOnly Secure SameSite=Lax cookie
→ 303 redirect to a clean token-free session URL
```

The edge/application access log is recommended to omit the query string for this route, with `Cache-Control: no-store` and `Referrer-Policy: no-referrer`. This is preferred over URL-fragment + JavaScript POST exchange because the shorter flow has fewer client failure modes while retaining the important token protections.

Every grant is recommended to store only a token hash and to enforce its own 60-minute idle TTL on personalized reads. Ordinary authenticated navigation/actions can update `last_seen`; asset loads and background polling provide no extension. A local phone timer clears rendered personal state at expiry, while the server remains authoritative on later reads.

Display teaser reads are recommended to use `spa_client_token` plus opaque attempt/session references. Phone teaser reads use the browser grant. Both paths remain `no-store` backend reads; presigned participant URLs are deferred until backend bandwidth becomes a measured problem.

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
| Ordinary attempts, diagnostic anchors and artifacts | 90 days | Matches the diagnostic product requirement and bounds protected-data exposure. |
| Manually promoted Calibration case | Until explicit deletion | Curated reproducibility has durable value; the full source bundle does not. |
| Browser metadata outbox | Until acknowledged or a short local expiry | Metadata aids outage diagnosis; long-lived local personal data does not. |

One idempotent daily cleanup command is recommended, invoked by the existing BackgroundPhotoWorker or a simple host timer. A durable scheduler and separate retention service are not recommended.

Promotion is recommended to copy only selected frames/crops, parameters, scores and annotations into a self-contained case. Unselected frames, Promo screenshot, ordinary logs and the whole attempt retain their normal expiry.

Calibration work is recommended to reuse the existing worker below fresh photo processing. A crash may mark the run `failed`, after which the developer reruns it manually; automatic reclaim, chunk scheduling and priority machinery are deferred to measured workload pressure.

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
- one migrate/init command;
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
| `inventory` | Immutable manifest; concurrent duplicate arbitration; losing-object cleanup. |
| `processing` | Restart-from-`processing`; bounded retries; one final face set/state. |
| `promo` | Four unique teasers; correct full result/`N`; result vs display acknowledgement; grant expiry. |
| `diagnostics` | Sanitized/developer role split; complete/incomplete bundle; promotion whitelist. |
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
| Backup/replication/snapshots | A new operator durability decision | The current MVP explicitly accepts loss of the only disk/server. |
