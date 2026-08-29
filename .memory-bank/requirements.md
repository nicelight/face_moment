---
description: Stable product requirements and REQ-to-epic-to-feature traceability for the one-СПА pilot.
status: draft
last_updated: 2026-08-29
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
| `REQ-INV-001` | Inventory time-range selection MUST use one СПА, authoritative `visit_date` and effective `captured_at`: reliable EXIF time in the СПА timezone, otherwise that file's server-side upload-start time, otherwise 01:00 on `visit_date`. | FR-INV-01, AC-18 |
| `REQ-INV-002` | A photographer MUST be able to soft-delete and restore only their own uploads, while an operator/developer may act on any Photo in an accessible СПА; soft deletion preserves all Photo data, excludes it from new search/result formation and statistics, but does not invalidate an already issued session, and restore reactivates the preserved state without reprocessing. | FR-INV-02..04, NFR-SEC-05, AC-18 |
| `REQ-INV-003` | Authorized operator/developer settings MUST support project-wide restore-all and a confirmed, resumable hard purge over one fixed snapshot of all soft-deleted Photos. Purge MUST reject restore of snapshot members until completion, wait for the shared worker, show waiting/completed/total progress, remove Photo/media/face/pipeline data, retain existing Promo sessions, core Attempts and diagnostic evidence, let clients skip unavailable hard-purged media without recalculating `N`, avoid interrupting an upload already in progress, and add no per-photo purge state or purge jobs table. | FR-INV-05..09, NFR-REL-06, NFR-ARCH-05, AC-18/20 |
| `REQ-INV-004` | Admin UI MUST poll every five seconds for separate per-СПА 1-, 5- and 60-minute counters: active unique Photos accepted in-window as `new`; active in-window accepted Photos currently `pending \| processing` as `unprocessed`; active Photos transitioned in-window to `ready \| no_faces` as `processed`; and active Photos transitioned in-window to `failed` as `failed`. | FR-INV-10..11, AC-19 |
| `REQ-SRCH-001` | SFace and Buffalo M MUST retain native processing paths, and embeddings/search MUST remain isolated by immutable compatible pipeline revision. | FR-SRCH-01..02 |
| `REQ-SRCH-002` | Selection of at most five admitted proposal occurrences MUST remain server-authoritative, and each selected detection MUST be searched independently with exact scoped cosine search. Matches MUST pass configured query-quality and calibrated reference-threshold gates; top-1/top-2 margin is forbidden. | FR-SRCH-03..05, FR-CAP-03..04 |
| `REQ-SRCH-003` | The operator MUST select the server-side active working `visit_date`; search uses all currently `ready` compatible photos in that СПА/date without an ingest-group readiness gate, the client cannot override the scope, and a missing date prevents search with diagnostic evidence. | FR-SRCH-03/06, Clarifications |
| `REQ-CAP-001` | The browser-native Chromium `SpaPromoClient` MUST load from the central HTTPS origin, maintain a recoverably selected-camera ring buffer, and create one pre/post-trigger reference series through the same distinguishable physical/test-trigger path without overlapping or stale attempts. Camera input above the site-configured maximum MUST be downscaled before the ring buffer and detector. While active the client MUST hold one authenticated 10-second HTTP long-poll request directly to the fixed-name mDNS ESP32 and immediately open the next after an event or timeout; local bridge, local web server, WebSocket and arbitrary camera substitution are absent. | FR-CAP-01..02, FR-CAP-11..13, AC-23/25 |
| `REQ-CAP-002` | `SpaPromoClient` MUST use MediaPipe BlazeFace Full-range, with YuNet 2026may FP32 allowed only as a sequential fallback after concrete incompatibility, and submit the first at most 20 chronological detector-ordered occurrences through the accepted crop, JPEG and versioned multipart contract. Client-side ranking, top-5, authoritative quality gating, tracking, clustering and deduplication are forbidden. Zero occurrences MUST use the manifest-only request, and a body larger than `20 MiB` MUST receive HTTP `413` before domain admission without a core Attempt or oversize domain outcome. | FR-CAP-03..04, FR-CAP-09..10, FR-CAP-14..17, NFR-ARCH-06, AC-21/24/26 |
| `REQ-CAP-003` | Result assembly MUST use only threshold-valid candidates, apply pHash as ranking-only, produce four unique teaser IDs, and compute `N` from the complete unique valid-photo union across processed detections. | FR-CAP-05..08 |
| `REQ-UX-001` | The display MUST show local advertising outside results and, on success, exactly four low-quality no-watermark teasers, truthful Promo copy and a fully visible high-contrast QR confirmed by an idempotent display acknowledgement; missing acknowledgement becomes derived `unconfirmed` without scheduler machinery. | FR-UX-01..02, FR-UX-05 |
| `REQ-UX-002` | QR MUST continue the same session without a selfie and show its СПА, authoritative date, available teaser when present, issued `N` and purchase-navigation CTA on the phone; hard-purged media is skipped without invalidating the session. | FR-UX-03..05 |
| `REQ-UX-003` | Display, QR first-open and browser-idle expiry MUST be independent; scans within 30 minutes reuse one session-wide browser access context, which expires after 60 minutes without explicit participant activity across that context, and expired data must not leak through redirect. | FR-UX-06..07, FR-UX-10 |
| `REQ-UX-004` | Insufficient results or runtime failure MUST return to local advertising without final Promo or success cooldown; stale work is discarded and retry uses a fresh capture. A server-communication failure MUST also show the small non-blocking `Попытка связи с сервером была не успешна в hh:mm:ss` notice for 5–10 seconds, with a newer notice allowed to replace it immediately. | FR-UX-08..09 |
| `REQ-PERF-001` | At least 19 of the same 20 controlled attempts MUST meet the under-10-second visible/scannable QR and full-session correctness gates. Latency MUST run from `reference_series_ready_at`, when capture ends and local processing starts, through request sending and QR visibility on one client monotonic clock; timeout/no-match remain failures. | NFR-PERF-01..02, NFR-PERF-04..05, AC-01..03/05 |
| `REQ-DIAG-001` | Every server-admitted request MUST create one core Attempt/correlation identity before inference and retain a timeline sufficient to localize outcome and latency, including client-local ready-series processing start, request-send start and response receipt. Missing finalized evidence remains `incomplete`; client-only offline delivery is best-effort. | FR-DIAG-01..02/05, AC-22 |
| `REQ-DIAG-002` | Detailed diagnostic evidence MUST remain best-effort and non-blocking. When collected, it MUST expose the required reproducibility context; capture-derived media MAY be logged, cached, stored or delivered without developer-only media authorization, but no such mechanism or per-crop logging is required. | FR-DIAG-03..05, NFR-SEC-06 |
| `REQ-DIAG-003` | Attempts MUST be filterable and navigable with the sanitized operator view and developer-only names, annotations, detailed logs and Calibration. Capture-derived media MUST NOT become developer-only solely because it is image content. | FR-DIAG-06..07, NFR-SEC-04/06 |
| `REQ-LOG-001` | Developer Log Explorer MUST search structured browser/server logs through the backend, correlate them to Attempts and remain non-blocking. Bounded capture-derived media MAY be logged; embeddings, credentials/authentication state, participant names, commercial Photo originals, personalized session data and session replay MUST NOT be logged. | FR-DEV-02..04, NFR-SEC-06 |
| `REQ-ANN-001` | An authorized developer MUST record person/detection ground truth with participant name and correct, false or missed semantics usable by Calibration. | FR-DEV-01 |
| `REQ-CAL-001` | Calibration MUST compare SFace and Buffalo M and show the three named threshold profiles with proposed value, counts, precision, recall, sample size and attempt drill-down. | FR-DEV-05..07 |
| `REQ-CAL-002` | Calibration MUST analyze each input quality gate independently, support version/parameter before-after comparison and leave serving-setting application as an explicit manual developer action. | FR-DEV-08..10 |
| `REQ-CAL-003` | Calibration MAY run on the shared `BackgroundPhotoWorker` and delay photo processing during debugging; interruption MUST become visible, photo processing MUST resume, and rerun remains manual without preemption, priority scheduling or a separate Calibration worker. | FR-DEV-11, NFR-PERF-03 |
| `REQ-REL-001` | Central runtime MUST start and operate independently of the local display session. Chromium/display MUST restart automatically after browser failure and return to local advertising when the central HTTPS origin is reachable, while an already loaded client retains advertising through transient server/network failure. Realtime MUST use exactly one inference slot and one server deadline without a waiter queue; a concurrent admitted request receives typed `busy`, and unfinished realtime work is interrupted rather than replayed after restart. | NFR-REL-01..03 |
| `REQ-REL-002` | The PostgreSQL photo-processing queue MUST preserve its `pending`/`processing` population across backend/worker restart, return unfinished work to `pending`, restart idempotently without duplicate final faces, and keep primary-storage capacity observable. | NFR-REL-04..05 |
| `REQ-REL-003` | An authorized operator MUST have a documented, executable recovery procedure for browser failure and ordinary central-runtime/server restart while the primary PostgreSQL/MinIO volumes remain intact. Its steps and recovery checks MUST be verifiable without claiming recovery from irreversible loss of the sole primary disk/server. | NFR-REL-05 |
| `REQ-SEC-001` | Public access MUST use HTTPS, internal stores/services MUST stay private, СПА identity MUST derive from a hashed client token, and required rate-limit and browser-sandbox controls MUST apply. Administrative SSH access remains an operational channel. | NFR-SEC-01..03 |
| `REQ-SEC-002` | The managed kiosk MUST pre-authorize its central origin for Local Network Access. ESP32 MUST allow that exact origin through CORS, handle Authorization preflight and validate one manually provisioned Bearer secret stored in the kiosk browser profile and absent from URLs and logs; pairing, automatic rotation, PKI and a separate sensor-credential lifecycle are absent. | NFR-SEC-07, AC-25 |
| `REQ-DATA-001` | Logs MUST expire after 30 days and ordinary Attempts/evidence, including persisted capture-derived diagnostic media, after 90 days. Only the curated promoted subset may survive until explicit deletion; participant names remain annotation-only, and the latest cleanup outcome MUST be visible. | NFR-REL-05, NFR-DATA-01..04 |
| `REQ-ARCH-001` | The pilot MUST retain the one-СПА, one central CPU-only server and simple backend/worker/realtime/PostgreSQL/object-storage baseline; hardware is site-validated and added complexity requires measured evidence. | NFR-ARCH-01..04 |

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
| `NFR-SEC-01`, `NFR-SEC-02`, `NFR-SEC-03` | `REQ-SEC-001` |
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

| REQ | Epic | Feature | Test / evidence target | Lifecycle |
|---|---|---|---|---|
| `REQ-000` | Foundation (no product epic) | [FT-000](features/FT-000-foundation.md) | [Executable Baseline Contract](testing/index.md), [final-gate verification](../.tasks/TASK-002-T2-FT-000-W0/TASK-002-T2-FT-000-W0-S-VERIFY-final-report-docs-01.md), and [REQ-000 evidence map](../.tasks/TASK-002-T2-FT-000-W0/req-foundation-evidence-map.md) | verified |
| `REQ-ING-001` | [EP-001](epics/EP-001.md) | [FT-001](features/FT-001.md) | `FT-001-AC-001`, `FT-001-AC-004`, `FT-001-AC-006..008`, `FT-001-AC-010..012`; PRD AC-08 | verified |
| `REQ-ING-002` | [EP-001](epics/EP-001.md) | [FT-001](features/FT-001.md) | `FT-001-AC-001`; PRD AC-08 | verified |
| `REQ-ING-003` | [EP-001](epics/EP-001.md) | [FT-001](features/FT-001.md), [FT-002](features/FT-002.md) | `FT-001-AC-002..003`, `FT-001-AC-005`, `FT-001-AC-009..011`, `FT-002-AC-001`; PRD AC-17 | verified |
| `REQ-ING-004` | [EP-001](epics/EP-001.md) | [FT-002](features/FT-002.md) | `FT-002-AC-001`, `FT-002-AC-004..005`; PRD AC-06/08 | verified |
| `REQ-INV-001` | [EP-001](epics/EP-001.md) | [FT-012](features/FT-012.md) | `FT-012-AC-001`; PRD AC-18 | planned |
| `REQ-INV-002` | [EP-001](epics/EP-001.md) | [FT-012](features/FT-012.md) | `FT-012-AC-001..002`; PRD AC-18 | planned |
| `REQ-INV-003` | [EP-001](epics/EP-001.md) | [FT-012](features/FT-012.md) | `FT-012-AC-003..005`, `FT-012-AC-007`; PRD AC-18/20 and restore-all e2e | planned |
| `REQ-INV-004` | [EP-001](epics/EP-001.md) | [FT-012](features/FT-012.md) | `FT-012-AC-006..007`; PRD AC-19 | planned |
| `REQ-SRCH-001` | [EP-001](epics/EP-001.md), [EP-002](epics/EP-002.md) | [FT-002](features/FT-002.md), [FT-004](features/FT-004.md) | `FT-002-AC-001`, `FT-002-AC-007..008`, `FT-004-AC-001`; PRD AC-03/10 | planned |
| `REQ-SRCH-002` | [EP-002](epics/EP-002.md) | [FT-004](features/FT-004.md) | `FT-004-AC-002`; PRD AC-01/03 | planned |
| `REQ-SRCH-003` | [EP-002](epics/EP-002.md) | [FT-004](features/FT-004.md) | `FT-004-AC-001`, `FT-004-AC-006`; PRD controlled setup, AC-03/05 | planned |
| `REQ-CAP-001` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md) | `FT-003-AC-001..003`, `FT-003-AC-007`; PRD AC-01/14/23/25 | planned |
| `REQ-CAP-002` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md) | `FT-003-AC-004..006`, `FT-003-AC-010`, `FT-003-AC-014..015`; PRD AC-21/24/26 | planned |
| `REQ-CAP-003` | [EP-002](epics/EP-002.md) | [FT-004](features/FT-004.md) | `FT-004-AC-003..004`, `FT-004-AC-006`; PRD AC-01/03 | planned |
| `REQ-UX-001` | [EP-002](epics/EP-002.md) | [FT-005](features/FT-005.md) | `FT-005-AC-001..003`; PRD AC-01/07/16 | planned |
| `REQ-UX-002` | [EP-002](epics/EP-002.md) | [FT-006](features/FT-006.md) | `FT-006-AC-001`, `FT-006-AC-005`; PRD AC-04 | planned |
| `REQ-UX-003` | [EP-002](epics/EP-002.md) | [FT-005](features/FT-005.md), [FT-006](features/FT-006.md) | `FT-005-AC-004`, `FT-006-AC-002..003`; PRD AC-15 and independent display/session expiry | planned |
| `REQ-UX-004` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md), [FT-005](features/FT-005.md) | `FT-003-AC-007..008`, `FT-003-AC-016`, `FT-005-AC-005`; PRD AC-14 | planned |
| `REQ-PERF-001` | [EP-002](epics/EP-002.md), [EP-003](epics/EP-003.md) | [FT-003](features/FT-003.md), [FT-004](features/FT-004.md), [FT-005](features/FT-005.md), [FT-007](features/FT-007.md) | `FT-003-AC-010`, `FT-004-AC-004`, `FT-005-AC-002`, `FT-007-AC-001`; PRD AC-01..03/05/07 | planned |
| `REQ-DIAG-001` | [EP-002](epics/EP-002.md), [EP-003](epics/EP-003.md) | [FT-003](features/FT-003.md), [FT-004](features/FT-004.md), [FT-007](features/FT-007.md), [FT-008](features/FT-008.md) | `FT-003-AC-006`, `FT-003-AC-008`, `FT-003-AC-015`, `FT-004-AC-007..008`, `FT-007-AC-001`, `FT-007-AC-005`, `FT-008-AC-001`; PRD AC-05/10/22 and NFR-REL-03 interruption evidence | planned |
| `REQ-DIAG-002` | [EP-003](epics/EP-003.md) | [FT-007](features/FT-007.md) | `FT-007-AC-002..004`; PRD AC-05/10/13 | verified |
| `REQ-DIAG-003` | [EP-003](epics/EP-003.md) | [FT-007](features/FT-007.md), [FT-008](features/FT-008.md) | `FT-007-AC-004`, `FT-008-AC-001..005`; PRD AC-09/10 and the latest-retention-result role boundary | planned |
| `REQ-LOG-001` | [EP-003](epics/EP-003.md) | [FT-009](features/FT-009.md) | `FT-009-AC-001..004`; PRD AC-10/13 | planned |
| `REQ-ANN-001` | [EP-003](epics/EP-003.md) | [FT-010](features/FT-010.md) | `FT-010-AC-001..003`; PRD AC-11 | planned |
| `REQ-CAL-001` | [EP-003](epics/EP-003.md) | [FT-011](features/FT-011.md) | `FT-011-AC-001`, `FT-011-AC-006`; PRD AC-12 | planned |
| `REQ-CAL-002` | [EP-003](epics/EP-003.md) | [FT-011](features/FT-011.md) | `FT-011-AC-002..004`, `FT-011-AC-006`; PRD AC-12 | planned |
| `REQ-CAL-003` | [EP-003](epics/EP-003.md) | [FT-011](features/FT-011.md) | `FT-011-AC-005`; PRD FR-DEV-11 worker-interruption evidence | planned |
| `REQ-REL-001` | [EP-002](epics/EP-002.md), [EP-003](epics/EP-003.md) | [FT-003](features/FT-003.md), [FT-004](features/FT-004.md), [FT-005](features/FT-005.md), [FT-007](features/FT-007.md) | `FT-003-AC-002`, `FT-003-AC-007..008`, `FT-003-AC-011..012`, `FT-003-AC-020`, `FT-004-AC-007..008`, `FT-005-AC-005`, `FT-007-AC-005`; PRD AC-14, NFR-REL-01..03 and physical-site verification | planned |
| `REQ-REL-002` | [EP-001](epics/EP-001.md) | [FT-002](features/FT-002.md) | `FT-002-AC-002..003`, `FT-002-AC-006`; PRD AC-06 and worker-restart recovery evidence | verified |
| `REQ-REL-003` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md) | `FT-003-AC-013`; PRD NFR-REL-05 browser/intact-volume recovery-procedure evidence | planned |
| `REQ-SEC-001` | [EP-001](epics/EP-001.md), [EP-002](epics/EP-002.md), [EP-003](epics/EP-003.md) | [FT-001](features/FT-001.md), [FT-002](features/FT-002.md), [FT-003](features/FT-003.md), [FT-004](features/FT-004.md), [FT-005](features/FT-005.md), [FT-006](features/FT-006.md), [FT-007](features/FT-007.md) | `FT-001-AC-004`, `FT-001-AC-006..008`, `FT-001-AC-011..012`, `FT-002-AC-006`, `FT-003-AC-003`, `FT-003-AC-009`, `FT-003-AC-017`, `FT-003-AC-019..020`, `FT-004-AC-005`, `FT-005-AC-003`, `FT-006-AC-004..005`, `FT-007-AC-001`; PRD NFR-SEC-01..03 | planned |
| `REQ-SEC-002` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md) | `FT-003-AC-003`, `FT-003-AC-017`; PRD AC-25 | planned |
| `REQ-DATA-001` | [EP-003](epics/EP-003.md) | [FT-007](features/FT-007.md), [FT-008](features/FT-008.md), [FT-009](features/FT-009.md), [FT-010](features/FT-010.md), [FT-011](features/FT-011.md) | `FT-007-AC-004`, `FT-007-AC-006..007`, `FT-008-AC-005`, `FT-009-AC-003`, `FT-010-AC-002`, `FT-010-AC-004`, `FT-011-AC-006`; PRD NFR-REL-05 and AC-13 | planned |
| `REQ-ARCH-001` | [EP-001](epics/EP-001.md), [EP-002](epics/EP-002.md), [EP-003](epics/EP-003.md) | [FT-001](features/FT-001.md)–[FT-012](features/FT-012.md) | `FT-001-AC-004..005`, `FT-001-AC-009..010`, plus other feature SDD gates and cross-cutting `REQ-ARCH-001` AC lines; PRD controlled setup and NFR-ARCH-01..06 | planned |
