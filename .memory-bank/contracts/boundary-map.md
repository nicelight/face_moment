---
description: Canonical capability ownership, public application boundaries and cross-slice write rules for the greenfield pilot.
status: active
last_updated: 2026-07-29
source_of_truth:
  - .memory-bank/contracts/boundary-map.md
---
# Boundary Map

## Status And Scope

The verified Foundation supplies runtime substrate but no product behavior.
This map constrains the accepted target implementation together with the
[system architecture](../architecture/system-architecture.md) and
[lifecycle map](../states/lifecycle-map.md); it does not describe existing
code.

## Capability Boundaries

| Owner | Public application boundary | Owned mutable state and transitions | Forbidden ownership | Allowed dependencies | Minimum credible proof |
|---|---|---|---|---|---|
| `serving_control` | Read immutable `ServingContext`/`IngestTarget`; apply audited manual setting and serving-revision changes. | СПА/timezone, active `visit_date`, pipeline/settings revision, display token lifecycle and change audit. | Photos, processing results, Attempts, sessions, evidence or Calibration recommendations. | Command `processing` revision validation; use platform auth/runtime adapters. | Client input cannot override СПА/date; one Attempt sees one immutable snapshot; failed revision changes require explicit operator recovery. |
| `inventory` | Admit one JPEG; query authorized Photos; soft-delete/restore; restore-all; start/read one global hard purge; read recent per-СПА counters and configured primary-storage free capacity. | Photo identity, uploader, authoritative date, effective capture time, accepted time, checksum/original reference, active marker, authorization and global purge orchestration/progress. | Pipeline transition rules, embeddings, Promo integrity, core Attempt or evidence retention. | Read `serving_control` targets and published `processing` state/timestamp projections; command `processing`; use platform auth/storage/host-capacity adapters. | Duplicate arbitration; owner-scoped visibility; processing-projection counters; separate PostgreSQL/MinIO free-capacity values; fixed-snapshot purge recovery. |
| `processing` | Create initial `pending`; report readiness; validate a pipeline revision; process Photo; exact compatible search; offline evaluate; clean Photo-derived state on inventory purge. | Pipeline catalog, processing state, derivatives/faces/embeddings, quality gates, exact-search, validation and evaluation rules. | Photo admission/visibility, live setting mutation, Promo Attempt/session assembly or evidence retention. | Read Photo/serving projections; use storage/model adapters. | Restart from `processing`, one final face set, compatible exact search, revision validation and idempotent cleanup. |
| `promo` | Execute fresh attempt; accept display outcome; exchange/read QR continuation; skip unavailable hard-purged media during an existing session read; run/read retention cleanup. | Core Attempt, result/session, candidate union, teasers, `N`, QR ticket, session-wide browser access and latest retention result. | Photo/processing/settings writes or detailed diagnostic evidence. | Read `serving_control`/`inventory`; command `processing`; command `diagnostics` best-effort evidence and retention expiry. | Chronological first-at-most-20 and zero-proposal request behavior; four unique teasers; correct issued `N`; display acknowledgement; session expiry; missing-media skip and observable retention outcome. |
| `diagnostics` | Record/search evidence and logs under their data-specific access rules; annotate; run evaluation; request audited manual apply; expire owned logs/evidence and report Attempt-deletion eligibility. | Detailed evidence/logs, access views, annotations, curated Calibration cases, recommendations and diagnostic-data expiry. | Core Attempt/result/session, aggregate cleanup result or direct serving-setting change. | Read `promo`; command `processing` evaluation and `serving_control` apply. | Sanitized/developer split for protected detail, capture-media classification, visible incomplete evidence, promotion whitelist and 30/90-day expiry. |

Shared PostgreSQL access does not grant shared write authority. A slice may read
a published projection; only the owner may validate and perform its command or
transition.

## Shared PostgreSQL Contract

- The modular monolith uses one PostgreSQL application schema, one SQLAlchemy
  `Base/MetaData`, one Alembic configuration and one sequential migration
  stream.
- Table models and repositories remain in their owning capability packages.
  One physical schema does not permit a slice to issue foreign commands,
  mutate foreign-owned state or duplicate another slice's business rules.
- Cross-slice transactions are allowed only through public application
  boundaries under the named orchestration owner; they do not create shared
  business ownership.
- Foreign keys and `ON DELETE` behavior are deliberate per relation. Database
  cascade MUST NOT cross a capability ownership boundary. In particular,
  deleting a Photo MUST NOT cascade into Promo sessions, core Attempts or
  diagnostic evidence; the inventory-owned hard-purge flow calls only the
  `processing` cleanup boundary and preserves those records.
- Deleting a core Attempt MUST NOT cascade into `diagnostics` rows. Each
  capability deletes only its own retention data; `promo` removes only Attempts
  reported eligible by `diagnostics`.
- `promo` owns one project-wide latest retention result, not cleanup history or
  a jobs lifecycle.
- Per-slice PostgreSQL schemas, database users/ACLs and independent migration
  pipelines are outside the accepted pilot.

## PostgreSQL And MinIO Convergence

- The backend writes each upload candidate under a unique opaque MinIO key,
  then validates JPEG type, compressed size, decoded dimensions/pixels and
  SHA-256. The browser never receives direct MinIO access.
- PostgreSQL uniqueness on `(spa_id, visit_date, checksum_sha256)` is the
  concurrent-admission arbiter. A duplicate creates no Photo or processing
  state and deletes only its own candidate object; an accepted Photo keeps its
  initial key without object move/copy.
- The per-Photo PostgreSQL commit publishes `Photo + accepted_at + pending`.
  A crash before commit may leave a private orphan and lose that admission;
  retrying the upload is sufficient.
- Derived media keys are deterministic by
  `(photo_id, pipeline_revision_id, artifact_kind)`, so the singleton worker may
  overwrite them safely before atomically replacing face rows and terminal
  processing state.
- Retryable cleanup first makes data inaccessible through owner state, then
  performs idempotent MinIO deletion, then finalizes owning database cleanup.
  No distributed transaction or per-object recovery lifecycle is required.
- MinIO versioning and external volume snapshots remain disabled while the
  no-backup pilot decision is active.

## External And Runtime Boundaries

| Boundary | Contract | Owner | Required constraints |
|---|---|---|---|
| Staff browser -> application | HTTPS staff authentication, independent JPEG upload and authorized Admin UI commands. | `platform/auth` authenticates; the target capability authorizes and handles the command. | MinIO/PostgreSQL stay private; no Batch/manifest/confirmation. |
| Central HTTPS `SpaPromoClient` -> ESP32 | While active, one HTTP long-poll request to the sensor's fixed mDNS `.local` name with a 10-second timeout; open the next immediately after an event or timeout. | The browser client owns request continuation; ESP32 owns passage-event delivery. | Managed kiosk pre-authorizes the central origin for Local Network Access through `LocalNetworkAccessAllowedForUrls`. ESP32 allows that exact origin through CORS, handles OPTIONS for Authorization and validates one manually provisioned Bearer secret kept out of URLs/logs. No WebSocket, local bridge, separate local client web server, discovery service, pairing, PKI or rotation lifecycle. |
| `SpaPromoClient` -> realtime | One synchronous `multipart/form-data` request with client-generated `attempt_id`, server-derived СПА, versioned manifest and the first at most 20 chronological BlazeFace crop parts; zero proposals use the same endpoint with the manifest only. | `promo` orchestrates; `processing` performs the already accepted compatible inference/search contract. | No client ranking/top-5/gating/tracking/clustering/deduplication; repeated people are allowed. The request has structural 20-occurrence and 512-pixel crop-side bounds plus a `20 MiB` total-body transport limit; a larger body returns `413` before admission and creates no domain outcome. Concurrent admitted request returns `busy`; closed maintenance/readiness returns `503` before admission and creates no core Attempt. |
| Display -> application | Idempotent acknowledgement after four teasers decode and QR is fully visible. | `promo`. | Server result issue alone is not Promo success. |
| QR browser -> application | Ticket exchange and authorized no-store session reads. | `promo`. | 30-minute first-open, shared 60-minute idle state, no per-device grants. |
| Application/worker -> PostgreSQL | Owner-scoped state writes and published projections. | Each capability owns its rows/invariants. | Direct foreign writes are forbidden even in one database. |
| Application/worker -> MinIO | Opaque-key private binary read/write/delete behind owner state and applicable authorization. | `inventory` owns originals; `processing` owns derivatives; `diagnostics` owns persisted diagnostic media. | PostgreSQL state determines usability; all stored objects remain private from direct browser access regardless of media classification. |

## Authentication And Data-Specific Delivery

- `platform/auth` owns staff principals, credentials and server sessions only.
  It supports CLI provision/reset/deactivate, Argon2id or bcrypt password
  hashing, hashed opaque PostgreSQL sessions with one short absolute TTL,
  logout/revoke and CSRF protection. Photographer, operator and developer
  authorization remains in the owning capability.
- SpaPromoClient sends its central-service high-entropy token in the
  Authorization header;
  PostgreSQL stores only its hash and the server derives `spa_id`. Client input
  cannot override that identity.
- The sensor Bearer secret is a distinct manually provisioned kiosk-profile
  setting used only in the Authorization header of ESP32 requests. It never
  enters URLs or logs. The sensor permits only the exact central client origin
  through CORS and handles its Authorization preflight.
- Public capture/continuation requests validate the accepted structural and
  decoded-media constraints plus simple per-token/IP rate limits. The FT-003
  proposal request has a `20 MiB` total request-body transport limit enforced
  before domain admission.
- Commercial Photo originals/previews/teasers and personalized session data
  remain backend-proxied, authorized and `no-store`. Raw MinIO keys and
  participant-facing presigned URLs are outside the pilot.
- Capture-derived reference images, normalized images and face crops are not
  developer-only solely because they contain media. They may be logged, cached,
  stored or delivered, but no endpoint, cache or logging path is required. If
  stored in MinIO, they remain behind the private object-store boundary; any
  HTTP delivery still enters through the application/edge.
- Credentials, authentication headers/cookies/tokens, private infrastructure,
  commercial Photo media, personalized data, participant names/annotations,
  detailed logs, Calibration and administrative actions retain their existing
  protection.
- Display media reads require the SpaPromoClient token plus opaque
  Attempt/session references. Phone media reads require the Promo session
  cookie.

QR ticket exchange is fixed:

1. `GET /q?ticket=<opaque>` validates the ticket hash and 30-minute first-open
   window.
2. The backend opens or reuses the Promo session's single browser access state,
   sets the opaque credential in an `HttpOnly Secure SameSite=Lax` cookie and
   returns `303` to a token-free session URL.
3. This route omits the query string from access logs and returns
   `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.

The session stores one `qr_ticket_hash`, `browser_opened_at` and shared
`browser_last_seen_at`. Explicit navigation/action from any opened phone
extends the shared 60-minute idle state; asset loads and background polling do
not.

## HTTP Failure Contract

The application and realtime boundaries use standard HTTP transport semantics
without a project-specific error framework:

| Status | Contract |
|---|---|
| `401` | Authentication is missing or invalid. |
| `403` | The authenticated principal lacks permission. |
| `413` | The request exceeds an accepted payload bound. An FT-003 total multipart body larger than `20 MiB` is rejected before domain admission and creates no core Attempt or oversize domain outcome. |
| `422` | Request validation fails. |
| `429` | The applicable rate limit is exceeded. |
| `503` | Serving maintenance or runtime readiness is closed; capture/search is rejected before admission and creates no core Attempt. |
| `5xx` | An internal or upstream technical failure occurred. |

An admitted capture/search request returns `2xx` with a compact typed domain
result even when its outcome is `busy`, `deadline`, `unacceptable_query` or
`insufficient_results`. These outcomes are not transport errors. `429` is a
rate-limit rejection, while `busy` describes the valid request's singleton-slot
condition; `422` is request validation failure, while `unacceptable_query`
describes evaluated query quality. Clients make decisions from the HTTP status
and typed outcome; response prose, especially `5xx` text, is never a control
contract. A technical failure may also be persisted on the core Attempt for
diagnostics, but its transport signal remains `5xx`.

Feature-level endpoint design may define the smallest required success payload,
but MUST NOT add a shared custom error envelope, error-code registry or mapping
framework. Contract verification must cover representative standard-status
mappings and prove that admitted non-success capture/search outcomes remain
domain outcomes.

## SpaPromoClient Proposal Contract

- The browser-native Chromium client loads from the central HTTPS origin.
  MediaPipe BlazeFace Full-range runs in its browser runtime with a separate
  release-versioned model asset; TensorFlow.js and a second project-selected ML
  runtime are absent. YuNet 2026may FP32 is a sequential replacement only after
  concrete BlazeFace incompatibility, never a parallel implementation or
  generic detector abstraction.
- Frames above the deployment-configured maximum are downscaled before entering
  the ring buffer or detector. The client traverses a ready reference series
  from earliest pre-trigger to latest post-trigger, preserves BlazeFace output
  order within each frame and stops processing immediately at occurrence 20.
  Repeated occurrences of one person are valid.
- The client does not rank, select a top-5, authoritatively quality-gate, track,
  cluster, deduplicate, embed or search proposals.
- Each occurrence becomes a centered square crop with side
  `1.2 × max(bbox_width, bbox_height)`, clipped to the source frame without
  alignment, landmark normalization or upscaling. A crop longer than 512 pixels
  is proportionally downscaled to 512 and encoded as ordinary sRGB JPEG without
  EXIF/source metadata.
- JPEG quality is selected on the configuration/debug page from exactly `0.7`,
  `0.75`, `0.8`, `0.85`, `0.9`, `0.95`; default `0.85`. Kiosk-profile
  `localStorage` retains it, the value applies from the next Attempt and is
  recorded in that request's manifest.
- One ready series yields one synchronous `multipart/form-data` request with a
  versioned JSON manifest and one JPEG part for each of the first at most 20
  occurrences. Structural bounds are 20 occurrence parts and a 512-pixel
  encoded crop side. The server rejects a total body larger than `20 MiB` with
  HTTP `413` before domain admission. There are no separate aggregate-pixel,
  per-JPEG-byte or manifest-size caps and no oversize domain outcome.
- Zero proposals produce a metadata-only request with the same correlation and
  client timings; server admission creates the core Attempt and an explicit
  non-success outcome.
- Manifest identity contains only `schema_version: 1`, UUID `attempt_id`,
  `trigger_source`, `client_release`, `detector_id`, `model_version` and
  `jpeg_quality`; camera context adds only `camera_device_id`.
- Timing contains wall-clock `reference_series_ready_at` for correlation plus
  monotonic `local_detection_completed_ms` and `request_started_ms` offsets
  from ready-series zero. Client/server wall clocks are never subtracted.
- Each occurrence contains only request-local `occurrence_index`,
  `frame_index`, `frame_offset_ms`, `detector_confidence` and `crop_part`.
  The manifest omits `spa_client_token`, `spa_id`, every other secret, an
  occurrence UUID, camera label/config snapshot, `bbox_px`, `crop_rect_px`,
  `source_frame_width_px` and `source_frame_height_px`.
- This client payload contract does not define server ranking, selection or
  search internals; their existing canonical owners retain authority.
- The normal flow requires neither full/downscaled reference-frame upload nor
  proof or annotation of local-detector misses.
- The `<10 s` interval starts when the capture window ends and local processing
  begins, then includes local processing and request sending on one client
  monotonic clock. Diagnostics exposes the client-local processing-start,
  request-send-start and response-received markers.
- Exact endpoint path, multipart part naming/serialization, validation detail
  and compact machine outcome names remain feature-level design before FT-003
  task planning. They must preserve this allow/omit and structural contract.

## Realtime Idempotency And Client Retry

- The client creates one UUID `attempt_id` when an idle sensor trigger is
  accepted. For a server-admitted request, `(spa_id, attempt_id)` is the
  idempotency/correlation key; a repeat returns existing state and never starts
  inference twice.
- `promo` persists the core Attempt before inference. The server deadline is
  shorter than the client timeout; a late native return cannot publish a
  result.
- Serving maintenance/readiness rejection occurs before `promo` admission,
  returns `503` and creates no core Attempt or idempotency record.
- Browser-retryable commands are idempotent. Upload retry uses ordinary checksum
  arbitration; there is no resumable-upload lifecycle.
- An authenticated client-event upsert may accept delayed offline metadata by
  `(spa_id, attempt_id)`. The client outbox contains only short-lived diagnostic
  metadata and `cooldown_until`; frames, tokens and personalized results remain
  memory-only. Delivery is best-effort and may be lost on expiry or restart.

## Cross-Slice Orchestration

### Independent Photo admission

`inventory` is the orchestration owner:

1. read immutable `IngestTarget` from `serving_control`;
2. persist the unique Photo and ask `processing` to create its serving
   `pending` state in one short PostgreSQL transaction;
3. return the per-file accepted/rejected/duplicate outcome.

No HTTP handler, shared helper or composition root owns this flow.

### Participant Promo

`promo` is the orchestration owner:

1. read immutable serving and active-Photo projections;
2. persist the core Attempt and immutable serving snapshot for the
   server-admitted request;
3. call `processing` for one exact compatible reference search;
4. persist the result/session when search succeeds;
5. write detailed diagnostics best-effort through `diagnostics`.

`promo` cannot make a Photo active or mutate pipeline/search rules.

### Calibration and serving change

`diagnostics` owns evidence selection and recommendation. It calls
`processing` for offline evaluation. Only `serving_control` may apply a
developer-confirmed setting through its audited command. A change that selects
a different pipeline revision additionally follows the manual switch below.

### Manual serving-revision switch

- Owner: `serving_control`.
- Input: an authenticated operator's explicit target revision.
- Output: an audited success/failure result naming the requested and currently
  committed revisions.
- Invariants:
  - only a revision validated by `processing` may serve;
  - any failure leaves participant service unavailable and never changes the
    committed revision automatically;
  - recovery is an explicit retry or manual selection of the prior revision;
  - ordinary restart uses the committed revision and stays unavailable if that
    revision cannot serve.

### Retention cleanup

- Owner: `promo`.
- Input: the applied 30-day log and 90-day ordinary-data cutoffs.
- Outputs:
  - `diagnostics` reports which promo-owned Attempts are eligible for deletion;
  - authorized users can read one latest result with the applied cutoffs,
    confirmed deleted/preserved counts and outcome/error.
- Invariants:
  - each capability deletes only its own data;
  - persisted capture-derived diagnostic media follows the ordinary 90-day
    cutoff without a separate media lifecycle;
  - the promoted Calibration subset is preserved;
  - failure remains observable and cleanup is safe to rerun;
  - no cleanup history or generic jobs lifecycle is introduced.

### Photo Inventory Operations

`inventory` owns the operator-visible outcome:

- effective `captured_at` is reliable EXIF in the СПА timezone, otherwise the
  file's server-side upload-start time, otherwise 01:00 on `visit_date`;
- photographer soft-delete/restore is restricted to `uploader_id`; an
  operator/developer may act on any Photo in an accessible СПА;
- soft delete/restore changes only the inventory-owned active marker;
  new participant-facing search/result formation and recent-statistics reads
  must filter the marker, while an already issued session may continue reading
  the referenced media while it exists;
- restore-all clears the marker for every soft-deleted Photo in the project
  except members of a confirmed non-terminal hard-purge snapshot; restore of
  those members is rejected until completion;
- hard purge follows the [runtime contract](#hard-purge-runtime-contract) and
  [global-run lifecycle](../states/lifecycle-map.md);
  `inventory` commands only `processing` cleanup before deleting its own
  Photo/media and sends no purge command to `promo` or `diagnostics`.

## Recent Statistics Read Contract

The `inventory` read boundary returns separate 1-, 5- and 60-minute values for
one СПА. Every counter excludes soft-deleted Photos:

| Counter | PostgreSQL source meaning |
|---|---|
| `new` | Unique Photo with `accepted_at` inside the window. |
| `unprocessed` | Photo accepted inside the window and currently `pending \| processing`. |
| `processed` | Photo whose current processing state transitioned to `ready \| no_faces` inside the window. |
| `failed` | Photo whose current processing state transitioned to `failed` inside the window. |

The Admin UI polls this read boundary every five seconds. Direct PostgreSQL
aggregation is the initial contract; WebSocket, SSE, a metrics store and
materialized counters are outside the pilot.

## Hard-Purge Runtime Contract

- Confirmation fixes all currently soft-deleted Photos across every СПА.
- If the shared worker is busy, purge waits without preemption and the UI shows
  `Начну удаление, как только закончится процесс {human-readable process name}`.
- During execution, destructive settings are replaced by completed/total
  progress for the fixed snapshot.
- Restore and restore-all reject snapshot members until the run reaches
  `completed`.
- Restart resumes the same run and may repeat idempotent cleanup.
- An upload already in progress is not interrupted. Ordinary uploads may
  continue and accumulate normal `pending` work while purge occupies the
  worker.
- Hard purge removes Photo, original/preview/thumbnail, faces and pipeline
  states. It preserves existing Promo results/sessions, core Attempts and
  diagnostic evidence; historical references and issued `N` may remain while
  UI/device loading skips deleted media.
