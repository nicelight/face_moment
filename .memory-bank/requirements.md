---
description: Stable product requirements and traceability for Face Moment, including functional multi-venue operation.
status: draft
last_updated: 2026-10-06
---
# Requirements

## Status Model

- Document `status`: `draft|active|deprecated|archived`.
- RTM `Lifecycle`: `planned|implemented|verified`.
- This decomposition preserves the clarified PRD contract; it does not replace
  the detailed FR/NFR wording in [.memory-bank/prd.md](prd.md).
- Product verification targets below route to stable feature AC IDs. Each
  feature AC carries its governing `REQ-*`, observable criterion and
  verification method; PRD AC references remain the source-level acceptance
  basis rather than a duplicate feature numbering scheme.

## REQ List

| ID | Requirement | PRD basis |
|---|---|---|
| `REQ-000` | The repository MUST provide a reproducible executable baseline that builds one application image, invokes backend/background-worker/realtime roles from the same release, typechecks and tests the Python package, applies one Alembic stream with one SQLAlchemy `Base/MetaData` to an empty PostgreSQL/pgvector database, keeps PostgreSQL/MinIO/internal ports private behind a non-production HTTPS edge, and passes isolated fake-`FaceEngine`, import, storage and restart probes without implementing product behavior. | Accepted [.memory-bank/foundation.md](foundation.md) decision; NFR-ARCH-01..03 and NFR-SEC-01 substrate pressure |
| `REQ-ING-001` | The photographer MUST authenticate, select one СПА and authoritative `visit_date`, and upload only ready JPEGs independently through the HTTPS application boundary without Batch/manifest/confirmation. | FR-ING-01..02 |
| `REQ-ING-002` | Every completed upload MUST be validated and reported independently as accepted, rejected or duplicate; EXIF, filename and upload time MUST NOT silently replace the selected `visit_date`. | FR-ING-03..04 |
| `REQ-ING-003` | Uniqueness MUST be enforced by `(spa_id, visit_date, checksum_sha256)`; duplicates are visibly excluded/deleted, while each unique Photo, `accepted_at` and serving `pending` state are committed atomically per photo. | FR-ING-05..06, AC-17 |
| `REQ-ING-004` | Accepted photos MUST expose explicit processing/searchable states, and at least 95% of all independently accepted unique JPEGs MUST become searchable within 15 minutes of `photo.accepted_at`. | FR-ING-07..08, NFR-PERF-03, AC-06/08 |
| `REQ-INV-001` | Inventory time-range selection MUST use one СПА, authoritative `visit_date` and effective `captured_at`: reliable EXIF time in the СПА timezone, otherwise that file's server-side upload-start time, otherwise 01:00 on `visit_date`. The separate staff Library Media view MUST browse active venue uploads by inclusive acceptance-date range, excluding admission-revision `no_faces` while retaining pending/processing/failed or missing state, and showing thumbnails or placeholders, added time and existing metadata with authorized original access. | FR-INV-01, AC-18; PRD Staff media browsing |
| `REQ-INV-002` | A photographer MUST be able to soft-delete and restore only their own uploads, while an operator/developer may act on any Photo in an accessible СПА; soft deletion preserves all Photo data, excludes it from new search/result formation and statistics, but does not invalidate an already issued session, and restore reactivates the preserved state without reprocessing. | FR-INV-02..04, NFR-SEC-05, AC-18 |
| `REQ-INV-003` | Authorized operator/developer settings MUST support project-wide restore-all and a confirmed, resumable hard purge over one fixed snapshot of all soft-deleted Photos. Purge MUST reject restore of snapshot members until completion, wait for the shared worker, show waiting/completed/total progress, remove Photo/media/face/pipeline data, retain existing Promo sessions, core Attempts and diagnostic evidence, let clients skip unavailable hard-purged media without recalculating `N`, avoid interrupting an upload already in progress, and add no per-photo purge state or purge jobs table. | FR-INV-05..09, NFR-REL-06, NFR-ARCH-05, AC-18/20 |
| `REQ-INV-004` | Admin UI MUST poll every five seconds for separate per-СПА 1-, 5- and 60-minute counters: active unique Photos accepted in-window as `new`; active in-window accepted Photos currently `pending \| processing` as `unprocessed`; active Photos transitioned in-window to `ready \| no_faces` as `processed`; and active Photos transitioned in-window to `failed` as `failed`. | FR-INV-10..11, AC-19 |
| `REQ-SRCH-001` | Active venues MUST share one eligible serving model/revision; startup must support multiple venues and reject conflicting revisions. Supported switches are global. SFace and Buffalo M retain native paths and historical embeddings retain their immutable revision. | FR-SRCH-01..02, AC-27 |
| `REQ-SRCH-002` | Selection of at most five admitted proposal occurrences MUST remain server-authoritative, and each selected detection MUST be searched independently with exact scoped cosine search. Matches MUST pass configured query-quality and calibrated reference-threshold gates; top-1/top-2 margin is forbidden. | FR-SRCH-03..05, FR-CAP-03..04 |
| `REQ-SRCH-003` | Each СПА MUST independently select automatic today in its timezone or a manual inclusive From/To range in «Площадки»; each attempt freezes that server-resolved range and searches all currently `ready` compatible Photos within it, without an ingest-group readiness gate or client override. Invalid manual ranges prevent search. | FR-SRCH-03/06, operator decision 2026-09-11 |
| `REQ-CAP-001` | The browser-native Chromium `SpaPromoClient` MUST load from the central HTTPS origin, maintain a recoverably selected-camera ring buffer, and create one pre/post-trigger reference series through the same distinguishable physical/test-trigger path without overlapping or stale attempts. Camera input above the site-configured maximum MUST be downscaled before the ring buffer and detector. While active the client MUST hold one authenticated 10-second HTTP long-poll request directly to the fixed-name mDNS ESP32 and immediately open the next after an event or timeout; local bridge, local web server, WebSocket and arbitrary camera substitution are absent. | FR-CAP-01..02, FR-CAP-11..13, AC-23/25 |
| `REQ-CAP-002` | `SpaPromoClient` MUST use MediaPipe BlazeFace Full-range, with YuNet 2026may FP32 allowed only as a sequential fallback after concrete incompatibility, and submit the first at most 20 chronological detector-ordered occurrences through the accepted crop, JPEG and versioned multipart contract. Client-side ranking, top-5, authoritative quality gating, tracking, clustering and deduplication are forbidden. Zero occurrences MUST use the manifest-only request, and a body larger than `20 MiB` MUST receive HTTP `413` before domain admission without a core Attempt or oversize domain outcome. | FR-CAP-03..04, FR-CAP-09..10, FR-CAP-14..17, NFR-ARCH-06, AC-21/24/26 |
| `REQ-CAP-003` | Result assembly MUST use only threshold-valid candidates, apply pHash as ranking-only, produce four unique teaser IDs, and compute `N` from the complete unique valid-photo union across processed detections. The accepted optional initial gallery may additionally contain same-venue commons outside that union, with fixed repeat/replay membership under [Optional Second Slide](contracts/promo-display-api.md#optional-second-slide). | FR-CAP-05..08; operator decision 2026-10-04 |
| `REQ-UX-001` | The display MUST show local advertising outside results and, on the first success slide, exactly four low-quality no-watermark teasers, the default operator-approved Promo copy or a saved kiosk-local text override, and a fully visible high-contrast QR confirmed by an idempotent display acknowledgement; missing acknowledgement becomes derived `unconfirmed` without scheduler machinery. | FR-UX-01..02, FR-UX-05 |
| `REQ-UX-002` | QR MUST continue the same session without a selfie and show its СПА, authoritative date, available teaser when present, issued `N` and purchase-navigation CTA on the phone; hard-purged media is skipped without invalidating the session. | FR-UX-03..05 |
| `REQ-UX-003` | Display, QR first-open and browser-idle expiry MUST be independent; scans within 30 minutes reuse one session-wide browser access context, which expires after 60 minutes without explicit participant activity across that context, and expired data must not leak through redirect. | FR-UX-06..07, FR-UX-10 |
| `REQ-UX-004` | Insufficient results or runtime failure MUST return to local advertising without final Promo or success cooldown; stale work is discarded and retry uses a fresh capture. A server-communication failure MUST also show the small non-blocking `Попытка связи с сервером была не успешна в hh:mm:ss` notice for 5–10 seconds, with a newer notice allowed to replace it immediately. | FR-UX-08..09 |
| `REQ-PERF-001` | Over the same 20 controlled production attempts, two gates are reported independently: at least 19 MUST pass the under-10-second visible/scannable QR gate, and at least 19 MUST pass the full-session server-correctness gate. No joint intersection is required. QR latency MUST run from `reference_series_ready_at`, when capture ends and local processing starts, through request sending and QR visibility on one client monotonic clock; timeout/no-match remain failures. | NFR-PERF-01..02, NFR-PERF-04..05, AC-01..03/05 |
| `REQ-DIAG-001` | Every server-admitted request MUST create one core Attempt/correlation identity before inference and retain a timeline sufficient to localize outcome and latency, including client-local ready-series processing start, request-send start and response receipt. Missing finalized evidence remains `incomplete`; client-only offline delivery is best-effort. | FR-DIAG-01..02/05, AC-22 |
| `REQ-DIAG-002` | Detailed diagnostic evidence MUST remain best-effort and non-blocking. When collected, it MUST expose the required reproducibility context; capture-derived media MAY be logged, cached, stored or delivered, but no such mechanism or per-crop logging is required. | FR-DIAG-03..05, NFR-SEC-06 |
| `REQ-DIAG-003` | Attempts MUST support exact `attempt_id`/`correlation_id` lookup, minimal time/state filters and tabular state, stages, durations, client markers and available `DiagnosticEvidence`. Operator access remains sanitized, developer access follows the evidence boundary, and incomplete, expired or removed data MUST remain explicit. Annotations, Calibration and specialized diagnostics do not automatically expand FT-008. | FR-DIAG-02..07, NFR-SEC-04/06, AC-09/10 |
| `REQ-LOG-001` | FT-009 MUST persist only important redacted structured server events in the existing PostgreSQL and expose one developer-only backend web view with bounded time, severity, component, event-code and exact Attempt/correlation filters. Events carry paired Attempt/correlation identities or neither, and FT-008 navigation uses a known `attempt_id`; correlation-only persistence/navigation is not required. Emission MUST remain non-blocking; browser logs, images, embeddings, secrets, personal data, request bodies and arbitrary payloads are forbidden. | FR-DEV-02..04, NFR-SEC-04/06, AC-10 |
| `REQ-ANN-001` | An authorized developer MUST record person/detection ground truth with participant name and correct, false or missed semantics usable by Calibration. | FR-DEV-01 |
| `REQ-CAL-001` | Calibration MUST compare SFace and Buffalo M and show the three named threshold profiles with proposed value, counts, precision, recall, sample size and attempt drill-down. | FR-DEV-05..07 |
| `REQ-CAL-002` | Calibration MUST support version/parameter before-after comparison and leave serving-setting application as an explicit manual developer action. Independent input-quality analysis and its extra measurement collection are deferred outside the pilot by the 2026-09-07 operator decision (FR-DEV-08). | FR-DEV-08..10 |
| `REQ-CAL-003` | Calibration MAY run on the shared `BackgroundPhotoWorker` and delay photo processing during debugging; interruption MUST become visible, photo processing MUST resume, and rerun remains manual without preemption, priority scheduling or a separate Calibration worker. | FR-DEV-11, NFR-PERF-03 |
| `REQ-REL-001` | Central runtime MUST start and operate independently of the local display session. Chromium/display MUST restart automatically after browser failure and return to local advertising when the central HTTPS origin is reachable, while an already loaded client retains advertising through transient server/network failure. Realtime MUST use exactly one inference slot and one server deadline without a waiter queue; a concurrent admitted request receives typed `busy`, and unfinished realtime work is interrupted rather than replayed after restart. | NFR-REL-01..03 |
| `REQ-REL-002` | The PostgreSQL photo-processing queue MUST preserve its `pending`/`processing` population across backend/worker restart, return unfinished work to `pending`, restart idempotently without duplicate final faces, and keep primary-storage capacity observable. | NFR-REL-04..05 |
| `REQ-REL-003` | An authorized operator MUST have a documented, executable recovery procedure for browser failure and ordinary central-runtime/server restart while the primary PostgreSQL/MinIO volumes remain intact. Its steps and recovery checks MUST be verifiable without claiming recovery from irreversible loss of the sole primary disk/server. | NFR-REL-05 |
| `REQ-SEC-001` | Public access MUST use HTTPS, internal stores/services MUST stay private, СПА identity MUST derive from a hashed client token, and required rate-limit and browser-sandbox controls MUST apply. Administrative SSH access remains an operational channel. | NFR-SEC-01..03 |
| `REQ-SEC-002` | The managed kiosk MUST pre-authorize its central origin for Local Network Access. ESP32 MUST allow that exact origin through CORS, handle Authorization preflight and validate one manually provisioned Bearer secret stored in the kiosk browser profile and absent from URLs and logs; pairing, automatic rotation, PKI and a separate sensor-credential lifecycle are absent. | NFR-SEC-07, AC-25 |
| `REQ-DATA-001` | Structured server events MUST expire after 30 days and ordinary Attempts/evidence, including persisted capture-derived diagnostic media, after 90 days. Only the curated promoted subset may survive until explicit deletion; participant names remain annotation-only, and the latest cleanup outcome MUST be visible. | NFR-REL-05, NFR-DATA-01..04 |
| `REQ-ARCH-001` | Multiple venues MUST work on one central CPU-only server with the existing backend, one sequential worker, one realtime slot with busy, PostgreSQL and object storage. Settings/data stay venue-scoped; 10–15 venue capacity is not promised. | NFR-ARCH-01..04, AC-27 |

## Public extension requirements — 2026-10-03

These requirements derive from the clarified PRD and accepted delta,
not from a completed design. Historical RTM lifecycle/evidence remains unchanged.

| ID | Requirement | PRD basis |
|---|---|---|
| `REQ-PUB-001` | All camera-only captures MUST remain locally as IndexedDB JPEG Blob through retake, A/B denial and failed/successful search (starter long edge <=960 px, q0.85, no upscale, face >=30% image, empirical quality verification without accuracy promise); quota/unavailable storage MUST warn and allow current search without retaining the new image or evicting old ones. A hidden protected-cookie profile MUST retain fixed A/B with one confirmed reset preceded by a foreign-face warning; Developer MUST configure the A/B threshold independently of professional-photo search threshold without automatically changing it, non-consuming unusable captures, server-authoritative limits, no signup/recovery, retained email/last visit and no automatic profile deletion. | FR-PUB-01/04/05/10; AC-PUB-02 |
| `REQ-PUB-002` | Search MUST submit only the current selfie after explicit 1–3 venue selection and «Найти меня», validate that scope on the server, use all available undeleted compatible dates inside selection regardless of Promo date settings, reveal no outside-venue results, and show animation/progress without presenting simulation as measured percentage absent server measurements, plus personal count, venue names and visit dates. | FR-PUB-02/03; AC-PUB-01/02 |
| `REQ-PUB-003` | One public feed MUST group venue heading -> personal photos -> common -> next venue; personal previews use accepted removable frontend watermark; all public gallery preview images have actual width >=320 px, without changing Promo/QR. Common processed no_faces photos MUST be limited to personal-match dates of that venue and free everywhere. Selection uses green for free and blue for paid personal, select-all is venue-local, combined count includes all selected photos. | FR-PUB-06/07; ACverified |
| `REQ-PUB-004` | Operator/developer MUST manage free/paid venue mode at create/settings, confirm enabling free mode by popup, and configure one global RUB Base/d1/d2/d3 tariff. For n selected paid personal photos across paid venues total MUST be Base*(min(n,1)+d1*min(max(n-1,0),4)+d2*min(max(n-5,0),15)+d3*max(n-20,0)); all free media is excluded. Sticky top MUST show all-selected count, authoritative total and «Скачать». One cross-venue order freezes selected composition, price and free mode; later setting changes apply to new orders. | FR-PUB-07/08; ACverified |
| `REQ-PUB-005` | A free-only selected set MUST deliver an archive bearer link without payment initiation or mandatory receipt email; both free-venue personal and allowed common photos qualify. Mixed selection keeps free photos free inside one paid order. | FR-PUB-08/10; AC-PUB-04/05 |
| `REQ-PUB-006` | One cross-venue paid selection MUST use only YooKassa, collect/store profile email for receipt, choose card/QR method, prepare archive BEFORE opening the provider form and permit paid-original access only after server-confirmed payment. Duplicate confirmations MUST not duplicate purchases; refunds are manual. No charge may start before archive ready. | FR-PUB-09; AC-PUB-04/05 |
| `REQ-PUB-007` | Allowed selected originals MUST form one archive with bearer access expiring at ready+3 days, usable independently of browser cookie. While preparing, user sees retry-in-30-seconds instruction. Generation failure MUST show user error, initiate no payment and send admin email to sergiosandroid2@gmail.com. Preservation against deletion is NOT promised; unavailable paid delivery routes to manual support/refund rather than silently claiming successful access. | FR-PUB-09/10; AC-PUB-05 |
| `REQ-PUB-008` | Public extension MUST use HTTPS, protected profile cookie and server-authoritative profile/IP rate limiting (IP is not identity); originals/private stores MUST stay private and media access MUST enforce free entitlement or server-confirmed payment. Browser receives reduced previews only; removable frontend watermark does not protect originals. | FR-PUB-04/06/09/10; NFR-SEC-01/03; AC-PUB-01/03/04 |

## Material NFR Ownership

This reverse router maps each material PRD NFR to the `REQ-*` rows above,
which retain the full observable target and pass/fail conditions.

| PRD NFR | Owning REQ |
|---|---|
| `NFR-PERF-01`, `NFR-PERF-02`, `NFR-PERF-04`, `NFR-PERF-05` | `REQ-PERF-001` |
| `NFR-PERF-03` | `REQ-ING-004`, `REQ-CAL-003` |
| `NFR-REL-01`, `NFR-REL-02`, `NFR-REL-03` | `REQ-REL-001` |
| `NFR-REL-04`, `NFR-REL-05` | `REQ-REL-002`, `REQ-REL-003`, `REQ-DATA-001` |
| `NFR-REL-06` | `REQ-INV-003` |
| `NFR-SEC-01`, `NFR-SEC-02`, `NFR-SEC-03` | `REQ-SEC-001`; public HTTPS/rate-limit application: `REQ-PUB-008` (NFR-SEC-01/03) |
| `NFR-SEC-04` | `REQ-DIAG-003` |
| `NFR-SEC-05` | `REQ-INV-002`, `REQ-INV-003` |
| `NFR-SEC-06` | `REQ-DIAG-002`, `REQ-DIAG-003`, `REQ-LOG-001` |
| `NFR-SEC-07` | `REQ-SEC-002` |
| `NFR-DATA-01`, `NFR-DATA-02`, `NFR-DATA-03`, `NFR-DATA-04` | `REQ-DATA-001` |
| `NFR-ARCH-01`, `NFR-ARCH-02`, `NFR-ARCH-03`, `NFR-ARCH-04` | `REQ-ARCH-001` |
| `NFR-ARCH-05` | `REQ-INV-003`, `REQ-INV-004` |
| `NFR-ARCH-06` | `REQ-CAP-002` |

## Scope Boundary

Canonical exclusions remain in the PRD
[Non-goals](prd.md#non-goals). This decomposition introduces no additional
product scope; feature and task anti-goals only narrow their assigned work.

## Traceability Matrix (RTM)

Wave 6: scheduler закрыл [TASK-123](tasks/TASK-123-T3-FT-013-W6.task.json)
(public API/current result и paid/free supplier, FT-013-AC-002/006/008,
часть REQ-PUB-002/003/008) после independent
[functional PASS](../.protocols/TASK-123-T3-FT-013-W6/verification.md) и
[semantic-pass](../.protocols/TASK-123-T3-FT-013-W6/red-verification.md).
На границе Wave 6 preview/browser gallery и feature verification ещё
предстояли; актуальное покрытие приведено в Public extension RTM ниже.

| REQ | Epic | Feature | Test / evidence target | Lifecycle |
|---|---|---|---|---|
| `REQ-000` | Foundation (no product epic) | [FT-000](features/FT-000-foundation.md) | [Executable Baseline Contract](testing/index.md), [final-gate verification](../.tasks/TASK-002-T2-FT-000-W0/TASK-002-T2-FT-000-W0-S-VERIFY-final-report-docs-01.md), and [REQ-000 evidence map](../.tasks/TASK-002-T2-FT-000-W0/req-foundation-evidence-map.md) | verified |
| `REQ-ING-001` | [EP-001](epics/EP-001.md) | [FT-001](features/FT-001.md) | `FT-001-AC-001`, `FT-001-AC-004`, `FT-001-AC-006..008`, `FT-001-AC-010..012`; `FT-001-AC-013`; PRD AC-08 | verified |
| `REQ-ING-002` | [EP-001](epics/EP-001.md) | [FT-001](features/FT-001.md) | `FT-001-AC-001`; PRD AC-08 | verified |
| `REQ-ING-003` | [EP-001](epics/EP-001.md) | [FT-001](features/FT-001.md), [FT-002](features/FT-002.md) | `FT-001-AC-002..003`, `FT-001-AC-005`, `FT-001-AC-009..011`, `FT-002-AC-001`, `FT-002-AC-012`; PRD AC-17 | verified |
| `REQ-ING-004` | [EP-001](epics/EP-001.md) | [FT-002](features/FT-002.md) | `FT-002-AC-001`, `FT-002-AC-004..005`; PRD AC-06/08 | verified |
| `REQ-INV-001` | [EP-001](epics/EP-001.md) | [FT-012](features/FT-012.md) | `FT-012-AC-001`, `FT-012-AC-008`; PRD AC-18 and Staff media browsing | planned |
| `REQ-INV-002` | [EP-001](epics/EP-001.md) | [FT-012](features/FT-012.md) | `FT-012-AC-001..002`, `FT-012-AC-008`; PRD AC-18 and Staff media browsing | planned |
| `REQ-INV-003` | [EP-001](epics/EP-001.md) | [FT-012](features/FT-012.md) | `FT-012-AC-003..005`, `FT-012-AC-007`; PRD AC-18/20 and restore-all e2e | planned |
| `REQ-INV-004` | [EP-001](epics/EP-001.md) | [FT-012](features/FT-012.md) | `FT-012-AC-006`; PRD AC-19 | verified |
| `REQ-SRCH-001` | [EP-001](epics/EP-001.md), [EP-002](epics/EP-002.md) | [FT-002](features/FT-002.md), [FT-004](features/FT-004.md) | `FT-002-AC-001`, `FT-002-AC-007..012`, `FT-004-AC-001`; PRD AC-03/10 | planned |
| `REQ-SRCH-002` | [EP-002](epics/EP-002.md) | [FT-004](features/FT-004.md) | `FT-004-AC-002`; PRD AC-01/03 | planned |
| `REQ-SRCH-003` | Each СПА MUST independently select automatic today in its timezone or a manual inclusive From/To range in «Площадки»; each attempt freezes that server-resolved range and searches all currently `ready` compatible Photos within it, without an ingest-group readiness gate or client override. Invalid manual ranges prevent search. | FR-SRCH-03/06, operator decision 2026-09-11 |
| `REQ-CAP-001` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md) | `FT-003-AC-001..003`, `FT-003-AC-007`; PRD AC-01/14/23/25 | planned |
| `REQ-CAP-002` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md) | `FT-003-AC-004..006`, `FT-003-AC-010`, `FT-003-AC-014..015`, `FT-003-AC-021`; PRD AC-21/24/26 | planned |
| `REQ-CAP-003` | [EP-002](epics/EP-002.md) | [FT-004](features/FT-004.md) | `FT-004-AC-003..004`, `FT-004-AC-006`, `FT-004-AC-009..010`; PRD AC-01/03 and accepted optional second slide | planned |
| `REQ-UX-001` | [EP-002](epics/EP-002.md) | [FT-005](features/FT-005.md) | `FT-005-AC-001..003`; `FT-005-AC-006..008`; PRD AC-01/07/16 | planned |
| `REQ-UX-002` | [EP-002](epics/EP-002.md) | [FT-006](features/FT-006.md) | `FT-006-AC-001`, `FT-006-AC-005`; PRD AC-04 | planned |
| `REQ-UX-003` | [EP-002](epics/EP-002.md) | [FT-005](features/FT-005.md), [FT-006](features/FT-006.md) | `FT-005-AC-004`, `FT-005-AC-007`, `FT-006-AC-002..003`; PRD AC-15 and independent display/session expiry | planned |
| `REQ-UX-004` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md), [FT-005](features/FT-005.md) | `FT-003-AC-007..008`, `FT-003-AC-016`, `FT-005-AC-005`; PRD AC-14 | planned |
| `REQ-PERF-001` | [EP-002](epics/EP-002.md), [EP-003](epics/EP-003.md) | [FT-003](features/FT-003.md), [FT-004](features/FT-004.md), [FT-005](features/FT-005.md), [FT-007](features/FT-007.md) | `FT-003-AC-010`, `FT-004-AC-004`, `FT-005-AC-002`, `FT-007-AC-001`; PRD AC-01..03/05/07 | planned |
| `REQ-DIAG-001` | [EP-002](epics/EP-002.md), [EP-003](epics/EP-003.md) | [FT-003](features/FT-003.md), [FT-004](features/FT-004.md), [FT-007](features/FT-007.md), [FT-008](features/FT-008.md) | `FT-003-AC-006`, `FT-003-AC-008`, `FT-003-AC-015`, `FT-004-AC-007..008`, `FT-007-AC-001`, `FT-007-AC-005`, `FT-008-AC-001`; PRD AC-05/10/22 and NFR-REL-03 interruption evidence | planned |
| `REQ-DIAG-002` | [EP-003](epics/EP-003.md) | [FT-007](features/FT-007.md) | `FT-007-AC-002..004`; PRD AC-05/10/13 | verified |
| `REQ-DIAG-003` | [EP-003](epics/EP-003.md) | [FT-007](features/FT-007.md), [FT-008](features/FT-008.md) | `FT-007-AC-004`, `FT-008-AC-001..005`; PRD AC-09/10 and the latest-retention-result role boundary | verified |
| `REQ-LOG-001` | [EP-003](epics/EP-003.md) | [FT-009](features/FT-009.md) | `FT-009-AC-001..004`; PRD AC-10/13 | verified |
| `REQ-ANN-001` | [EP-003](epics/EP-003.md) | [FT-010](features/FT-010.md) | `FT-010-AC-001..003`; PRD AC-11 | verified |
| `REQ-CAL-001` | [EP-003](epics/EP-003.md) | [FT-011](features/FT-011.md) | `FT-011-AC-001`, `FT-011-AC-006`; PRD AC-12 | planned |
| `REQ-CAL-002` | [EP-003](epics/EP-003.md) | [FT-011](features/FT-011.md) | `FT-011-AC-003..004`, `FT-011-AC-006`; PRD AC-12; `FT-011-AC-002` deferred outside pilot | planned |
| `REQ-CAL-003` | [EP-003](epics/EP-003.md) | [FT-011](features/FT-011.md) | `FT-011-AC-005`; PRD FR-DEV-11 worker-interruption evidence | verified |
| `REQ-REL-001` | [EP-002](epics/EP-002.md), [EP-003](epics/EP-003.md) | [FT-003](features/FT-003.md), [FT-004](features/FT-004.md), [FT-005](features/FT-005.md), [FT-007](features/FT-007.md) | `FT-003-AC-002`, `FT-003-AC-007..008`, `FT-003-AC-011..012`, `FT-003-AC-020`, `FT-004-AC-007..008`, `FT-004-AC-010`, `FT-005-AC-005`, `FT-005-AC-007`, `FT-007-AC-005`; `FT-003-AC-022`; PRD AC-14, NFR-REL-01..03 and physical-site verification | planned |
| `REQ-REL-002` | [EP-001](epics/EP-001.md) | [FT-002](features/FT-002.md) | `FT-002-AC-002..003`, `FT-002-AC-006`, `FT-002-AC-012`; PRD AC-06 and worker-restart recovery evidence | verified |
| `REQ-REL-003` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md) | `FT-003-AC-013`; PRD NFR-REL-05 browser/intact-volume recovery-procedure evidence | planned |
| `REQ-SEC-001` | [EP-001](epics/EP-001.md), [EP-002](epics/EP-002.md), [EP-003](epics/EP-003.md) | [FT-001](features/FT-001.md), [FT-002](features/FT-002.md), [FT-003](features/FT-003.md), [FT-004](features/FT-004.md), [FT-005](features/FT-005.md), [FT-006](features/FT-006.md), [FT-007](features/FT-007.md) | `FT-001-AC-004`, `FT-001-AC-006..008`, `FT-001-AC-011..013`, `FT-002-AC-006`, `FT-003-AC-003`, `FT-003-AC-009`, `FT-003-AC-017`, `FT-003-AC-019..022`, `FT-004-AC-005`, `FT-005-AC-003`, `FT-005-AC-006`, `FT-005-AC-008`, `FT-006-AC-004..005`, `FT-007-AC-001`; PRD NFR-SEC-01..03 | planned |
| `REQ-SEC-002` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md) | `FT-003-AC-003`, `FT-003-AC-017`; PRD AC-25 | planned |
| `REQ-DATA-001` | [EP-003](epics/EP-003.md) | [FT-007](features/FT-007.md), [FT-008](features/FT-008.md), [FT-009](features/FT-009.md), [FT-010](features/FT-010.md), [FT-011](features/FT-011.md) | `FT-007-AC-004`, `FT-007-AC-006..007`, `FT-008-AC-005`, `FT-009-AC-003`, `FT-010-AC-002`, `FT-010-AC-004..005`, `FT-011-AC-007..008`; PRD NFR-REL-05 and AC-13 | planned |
| `REQ-ARCH-001` | [EP-001](epics/EP-001.md), [EP-002](epics/EP-002.md), [EP-003](epics/EP-003.md) | [FT-001](features/FT-001.md)–[FT-012](features/FT-012.md) | `FT-001-AC-004..005`, `FT-001-AC-009..010`, plus other feature SDD gates and cross-cutting `REQ-ARCH-001` AC lines; `FT-003-AC-022`; `FT-002-AC-009`, `FT-002-AC-011`; `FT-005-AC-006`, `FT-005-AC-008`; PRD controlled setup and NFR-ARCH-01..06 | planned |

## Public extension RTM

Wave 3: scheduler закрыл [TASK-121](tasks/TASK-121-T3-FT-013-W3.task.json)
(profile/A/B, AC-004, REQ-PUB-001/008),
[TASK-122](tasks/TASK-122-T2-FT-013-W3.task.json)
(native search/compression, AC-007, REQ-PUB-001/002) и
[TASK-127](tasks/TASK-127-T3-FT-014-W3.task.json)
(tariff API, AC-004, REQ-PUB-004/008). Independent functional PASS и требуемые
T3 semantic-pass связаны в task records и [FT-013](features/FT-013.md) /
[FT-014](features/FT-014.md). Это частичное покрытие требований; оставшиеся
на границе Wave 3 задачи и feature verification ещё не были завершены.

Wave 4: scheduler закрыл [TASK-130](tasks/TASK-130-T2-FT-014-W4.task.json)
(staff tariff editor, FT-014-AC-005, часть REQ-PUB-004) после independent
[functional PASS](../.protocols/TASK-130-T2-FT-014-W4/verification.md).
Остальное покрытие требования и feature semantic verification ещё предстоят;
REQ-PUB-004 lifecycle остаётся planned.

Wave 6: scheduler закрыл [TASK-123](tasks/TASK-123-T3-FT-013-W6.task.json)
(public API/current result и paid/free supplier, FT-013-AC-002/006/008,
часть REQ-PUB-002/003/008) после independent
[functional PASS](../.protocols/TASK-123-T3-FT-013-W6/verification.md) и
[semantic-pass](../.protocols/TASK-123-T3-FT-013-W6/red-verification.md).
На границе Wave 6 preview/browser gallery и feature verification ещё
предстояли; актуальное покрытие приведено в Wave 8 ниже.

Wave 7: scheduler закрыл [TASK-124](tasks/TASK-124-T3-FT-013-W7.task.json)
(private reduced previews, FT-013-AC-009, REQ-PUB-003/008),
[TASK-125](tasks/TASK-125-T2-FT-013-W7.task.json)
(explicit browser search/progress, FT-013-AC-003, REQ-PUB-001/002 subset),
[TASK-128](tasks/TASK-128-T3-FT-014-W7.task.json)
(authoritative quote, FT-014-AC-002, REQ-PUB-004/008 subset) и
[TASK-131](tasks/TASK-131-T3-FT-014-W7.task.json)
(staff paid/free administration, FT-014-AC-003, REQ-PUB-004/008 subset).
Все получили independent functional PASS; TASK-124/128/131 — semantic-pass,
TASK-125 — independent expert UX assessment. Verification links находятся в
[FT-013](features/FT-013.md) и [FT-014](features/FT-014.md).
На границе Wave 7 TASK-126/129/132 и feature semantic verification ещё
предстояли, все Public extension REQ lifecycle были planned.

Wave 8: scheduler закрыл [TASK-126](tasks/TASK-126-T2-FT-013-W8.task.json)
после independent [functional PASS](../.protocols/TASK-126-T2-FT-013-W8/verification.md)
и [TASK-132](tasks/TASK-132-T3-FT-014-W8.task.json) после
[functional PASS](../.protocols/TASK-132-T3-FT-014-W8/verification.md) и
[semantic-pass](../.protocols/TASK-132-T3-FT-014-W8/red-verification.md).
Все TASK-120..126 done; [feature semantic-pass](../.tasks/FT-013/FT-013-S-RED-VERIFY-final-report-docs-01.md)
подтвердил FT-013-AC-001..009, root scheduler завершил FT-013 (verified).
REQ-PUB-002 полностью verified. REQ-PUB-001/003/008 имеют проверенный FT-013
subset, но сохраняют planned: retained purchase email/flow — FT-016,
selection — TASK-129, delivery entitlement/payment — FT-015/016 ещё не завершены.
Frozen-core supplier FT-014-AC-006 проверен TASK-132; lifecycle FT-014,
FT-015/016 и EP-004 остаётся planned.

Wave 9: owner закрыл [TASK-129](tasks/TASK-129-T2-FT-014-W9.task.json)
после [functional PASS](../.protocols/TASK-129-T2-FT-014-W9/verification.md)
и [TASK-133](tasks/TASK-133-T3-FT-015-W9.task.json) после
[functional PASS](../.protocols/TASK-133-T3-FT-015-W9/verification.md) и
[semantic-pass](../.protocols/TASK-133-T3-FT-015-W9/red-verification.md).
Все TASK-127..132 done; [feature semantic-pass](../.tasks/FT-014/FT-014-S-RED-VERIFY-final-report-docs-01.md)
и записанное owner completion подтверждают FT-014 verified. REQ-PUB-003 теперь
полностью verified через FT-013 gallery + FT-014 selection; REQ-PUB-004 verified
через все FT-014-AC-001..006 (admin, marginal quote, sticky, frozen cross-venue
order). FT-016-AC-001 остаётся downstream consumer интеграцией этого supplier,
а незавершённые paid flow/entitlement учитываются REQ-PUB-001/005/006/008.
REQ-PUB-007 имеет подтверждённый ZIP subset FT-015-AC-004, но expiry/browser/
paid delivery ещё planned; FT-015/016 и EP-004 lifecycle planned.

Wave 10: owner закрыл [TASK-134](tasks/TASK-134-T3-FT-015-W10.task.json)
после independent [functional PASS](../.protocols/TASK-134-T3-FT-015-W10/verification.md)
и [semantic-pass](../.protocols/TASK-134-T3-FT-015-W10/red-verification.md).
FT-015-AC-003 подтверждает private anonymous bearer ZIP streaming, stored
entitlement и exact ready+3days expiry — subset REQ-PUB-007/008.
Вместе с AC-004 ZIP runtime это частичное покрытие FT-015; TASK-135..136
order HTTP/browser flow и FT-016 payment integration ещё planned.
REQ-PUB-007/008 и FT-015/016/EP-004 сохраняют lifecycle planned;
REQ-PUB-002/003/004 сохраняют verified. Всего TASK-120..134 done (15/20),
TASK-135..139 planned; feature completion для FT-015 не заявлено.

Wave 11: owner закрыл [TASK-135](tasks/TASK-135-T3-FT-015-W11.task.json)
после independent [functional PASS](../.protocols/TASK-135-T3-FT-015-W11/verification.md)
и [semantic-pass](../.protocols/TASK-135-T3-FT-015-W11/red-verification.md).
FT-015-AC-001 подтверждает free order HTTP/owner status/entitled ready link,
strict admission и отсутствие обязательных email/payment — subset REQ-PUB-005/008.
FT-015 покрывает AC-001/003/004; browser AC-002 и FT-016 ещё planned.
REQ-PUB-002/003/004 verified; остальные public REQ и FT-015/016/EP-004 planned.
Всего TASK-120..135 done (16/20), TASK-136..139 planned; feature completion
FT-015 не заявлено.

Wave 12 initial terminal checkpoint (historical): owner закрыл [TASK-136](tasks/TASK-136-T2-FT-015-W12.task.json)
после independent [functional PASS](../.protocols/TASK-136-T2-FT-015-W12/verification.md).
Все TASK-133..136 done; [feature semantic-pass](../.tasks/FT-015/FT-015-S-RED-VERIFY-final-report-docs-01.md)
и явное owner completion подтверждают FT-015 active/verified, AC-001..004.
REQ-PUB-005 полностью подтверждён в free-only части, но mixed selection внутри
paid order требует FT-016-AC-001 и сохраняет planned. REQ-PUB-001/006/007/008
также сохраняют planned из-за незавершённых paid profile/payment/delivery
стыков. REQ-PUB-002/003/004 остаются verified. FT-016 и EP-004 planned.

Всего TASK-120..136 done (17/20), TASK-137..139 blocked.
[TASK-137 stop evidence](../.tasks/TASK-137-T3-FT-016-W12/TASK-137-T3-FT-016-W12-S-EXECUTE-final-report-docs-01.md):
нет required external YooKassa TEST merchant/fiscal config и authorization
на preflight; implementation/provider calls/execution attempt не было.
TASK-138/139 blocked по зависимостям.
[Checkpoint](../.protocols/AUTONOMOUS-RUN/status.md): HALT_BLOCKING_QUESTIONS.
После предоставления local TEST configuration и разрешения external TEST calls
возобновить `/autopilot`; scheduler проверяет входы и направляет fresh
`/exe TASK-137-T3-FT-016-W12`, dependent unblock только после prerequisites.

Resumed Wave 12: owner закрыл [TASK-137](tasks/TASK-137-T3-FT-016-W12.task.json)
после independent [functional PASS](../.protocols/TASK-137-T3-FT-016-W12/verification.md)
и [semantic-pass](../.protocols/TASK-137-T3-FT-016-W12/red-verification.md).
FT-016-AC-002 подтверждает ready paid ZIP admission, TEST card redirect и
принятый frozen receipt payload — subset REQ-PUB-006/007. Фактический режим
регистрации чеков и фискальный выпуск не доказаны. Всего TASK-120..137 done
(18/20); TASK-138/139 остаются blocked до отдельного scheduler promotion.
REQ-PUB-001/005/006/007/008, FT-016 и EP-004 остаются planned: server
confirmation, paid entitlement и browser flow ещё не завершены.
REQ-PUB-002/003/004 сохраняют verified.

Wave 13: owner закрыл [TASK-138](tasks/TASK-138-T3-FT-016-W13.task.json) после
исправления attempt 1, independent [functional PASS](../.protocols/TASK-138-T3-FT-016-W13/verification.md)
и [semantic-pass](../.protocols/TASK-138-T3-FT-016-W13/red-verification.md).
FT-016-AC-003/004 подтверждают server-confirmed paid entitlement и доступ к
выбранному bearer ZIP с исходным ready+3days — subset REQ-PUB-006/007/008.
Всего TASK-120..138 done (19/20); TASK-139 blocked до scheduler promotion.
REQ-PUB-001/005/006/007/008, FT-016 и EP-004 сохраняют planned: browser
AC-001/005 и итоговая feature verification ещё впереди. REQ-PUB-002/003/004
остаются verified.

Wave 14: [TASK-139](tasks/TASK-139-T3-FT-016-W14.task.json) завершилась
финальным independent [functional FAIL](../.protocols/TASK-139-T3-FT-016-W14/verification.md)
после начальной попытки и двух повторов. При free-to-paid смене до POST
браузер получает 422 без формы оплаты; после pending provider return и нового
поиска повтор не запрашивает owner status. [BUG](bugs/public-photo-purchase-browser-continuation.md)
фиксирует successor route. TASK-120..138 остаются 19 done; TASK-139 failed.
Подтверждённые supplier/server и free subsets сохраняются, но browser
FT-016-AC-001/005 не закрыты. RTM lifecycle остаётся: REQ-PUB-002/003/004
verified, REQ-PUB-001/005/006/007/008 planned; FT-016 и EP-004 planned.

Wave 15: root закрыл [TASK-144](tasks/TASK-144-T3-FT-016-W15.task.json)
для FT-016-AC-001 и [TASK-145](tasks/TASK-145-T3-FT-016-W15.task.json)
для FT-016-AC-005 после независимых functional PASS и semantic-pass, связанных
в карточках. С уже done TASK-137/138 это покрывает все development AC-001..005;
FT-013/014/015 были verified ранее. [Решение владельца](../.protocols/AUTONOMOUS-RUN/decision-log.md#wave15-closure-owner-decision)
разрешает FT-016, EP-004 и REQ-PUB-001..008 lifecycle verified по принятому
development scope. Исторический TASK-139 остаётся failed; успешен только
двухзадачный successor run. Production activation, фискальный чек, внешний
real-shop SBP, SMTP setup и deployment отдельно не доказаны.

| REQ | Epic | Feature | Test / evidence target | Lifecycle |
|---|---|---|---|---|
| `REQ-PUB-001` | [EP-004](epics/EP-004.md) | [FT-013](features/FT-013.md), [FT-014](features/FT-014.md) (order-core supplier), [FT-016](features/FT-016.md) | `FT-013-AC-001..004`, `FT-013-AC-007`, `FT-014-AC-006`, `FT-016-AC-001`; PRD AC-PUB | verified |
| `REQ-PUB-002` | [EP-004](epics/EP-004.md) | [FT-013](features/FT-013.md) | `FT-013-AC-002..003`, `FT-013-AC-007..008`; PRD AC-PUB | verified |
| `REQ-PUB-003` | [EP-004](epics/EP-004.md) | [FT-013](features/FT-013.md), [FT-014](features/FT-014.md) | `FT-013-AC-005`, `FT-013-AC-008`, `FT-013-AC-009`, `FT-014-AC-001`; PRD AC-PUB | verified |
| `REQ-PUB-004` | [EP-004](epics/EP-004.md) | [FT-014](features/FT-014.md), [FT-016](features/FT-016.md) | `FT-014-AC-001..006`, `FT-016-AC-001`; PRD AC-PUB | verified |
| `REQ-PUB-005` | [EP-004](epics/EP-004.md) | [FT-015](features/FT-015.md), [FT-016](features/FT-016.md) | `FT-015-AC-001..002`, `FT-016-AC-001`; PRD AC-PUB | verified |
| `REQ-PUB-006` | [EP-004](epics/EP-004.md) | [FT-014](features/FT-014.md) (order-core supplier), [FT-016](features/FT-016.md) | `FT-014-AC-006`, `FT-016-AC-001..003`, `FT-016-AC-005`; PRD AC-PUB | verified |
| `REQ-PUB-007` | [EP-004](epics/EP-004.md) | [FT-015](features/FT-015.md), [FT-016](features/FT-016.md) | `FT-015-AC-002..004`, `FT-016-AC-002..005`; PRD AC-PUB | verified |
| `REQ-PUB-008` | [EP-004](epics/EP-004.md) | [FT-013](features/FT-013.md), [FT-014](features/FT-014.md), [FT-015](features/FT-015.md), [FT-016](features/FT-016.md) | `FT-013-AC-006`, `FT-013-AC-008..009`, `FT-014-AC-003..004`, `FT-015-AC-001`, `FT-015-AC-003`, `FT-016-AC-003..004`; PRD AC-PUB | verified |
