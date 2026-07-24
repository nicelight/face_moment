---
description: Stable product requirements and REQ-to-epic-to-feature traceability for the one-СПА pilot.
status: draft
last_updated: 2026-07-24
---
# Requirements

## Status Model

- Document `status`: `draft|active|deprecated|archived`.
- RTM `Lifecycle`: `planned|implemented|verified`.
- This decomposition preserves the clarified PRD contract; it does not replace
  the detailed FR/NFR wording in [.memory-bank/prd.md](prd.md).

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
| `REQ-SRCH-002` | Participant search MUST use exact scoped cosine search and admit matches only through configured query-quality and calibrated reference-threshold gates; top-1/top-2 margin is forbidden. | FR-SRCH-03..05 |
| `REQ-SRCH-003` | The operator MUST select the server-side active working `visit_date`; search uses all currently `ready` compatible photos in that СПА/date without an ingest-group readiness gate, the client cannot override the scope, and a missing date prevents search with diagnostic evidence. | FR-SRCH-03/06, Clarifications |
| `REQ-CAP-001` | The display client MUST maintain a ring buffer, create an automatic pre/post-trigger reference series and prevent overlapping or stale attempts. | FR-CAP-01..02 |
| `REQ-CAP-002` | The system MUST process at most five quality-ranked detections independently without tracking, identity clustering or cross-frame person deduplication. | FR-CAP-03..04 |
| `REQ-CAP-003` | Result assembly MUST use only threshold-valid candidates, apply pHash as ranking-only, produce four unique teaser IDs, and compute `N` from the complete unique valid-photo union across processed detections. | FR-CAP-05..08 |
| `REQ-UX-001` | The display MUST show local advertising outside results and, on success, exactly four low-quality no-watermark teasers, truthful Promo copy and a fully visible high-contrast QR confirmed by an idempotent display acknowledgement; missing acknowledgement becomes derived `unconfirmed` without scheduler machinery. | FR-UX-01..02, FR-UX-05 |
| `REQ-UX-002` | QR MUST continue the same session without a selfie and show its СПА, authoritative date, available teaser when present, issued `N` and purchase-navigation CTA on the phone; hard-purged media is skipped without invalidating the session. | FR-UX-03..05 |
| `REQ-UX-003` | Display, QR first-open and browser-idle expiry MUST be independent; scans within 30 minutes reuse one session-wide browser access context, which expires after 60 minutes without explicit participant activity across that context, and expired data must not leak through redirect. | FR-UX-06..07, FR-UX-10 |
| `REQ-UX-004` | Insufficient results or runtime failure MUST return to local advertising without final Promo or success cooldown; stale work is discarded and retry uses a fresh capture. A server-communication failure MUST also show the small non-blocking `Попытка связи с сервером была не успешна в hh:mm:ss` notice for 5–10 seconds, with a newer notice allowed to replace it immediately. | FR-UX-08..09 |
| `REQ-PERF-001` | At least 19 of the same 20 controlled attempts MUST meet the under-10-second visible/scannable QR gate and full-session correctness gate, counting timeout/no-match as failures and retaining stage timestamps. | NFR-PERF-01..02, NFR-PERF-04..05, AC-01..03/05 |
| `REQ-DIAG-001` | Every request admitted by the server MUST create one core Attempt/correlation identity before inference and retain a cross-client/server stage timeline sufficient to localize outcome and latency; missing finalized evidence remains visible as `incomplete`. Client-only offline attempt delivery is best-effort and does not guarantee a durable server Attempt. | FR-DIAG-01..02/05 |
| `REQ-DIAG-002` | Detailed diagnostic evidence is best-effort and MUST NOT block the critical flow; when collected, attempt detail MUST expose versions, parameters, search decisions and protected artifacts through a redacted reproducibility manifest without embedding images in logs. | FR-DIAG-03..05 |
| `REQ-DIAG-003` | Attempts MUST be filterable and navigable while enforcing the sanitized operator view and protected developer-only detail boundary. | FR-DIAG-06..07, NFR-SEC-04 |
| `REQ-LOG-001` | Developer Log Explorer MUST search structured browser/server logs through the backend, correlate them to attempts, remain non-blocking and exclude forbidden sensitive payloads. | FR-DEV-02..04 |
| `REQ-ANN-001` | An authorized developer MUST record person/detection ground truth with participant name and correct, false or missed semantics usable by Calibration. | FR-DEV-01 |
| `REQ-CAL-001` | Calibration MUST compare SFace and Buffalo M and show the three named threshold profiles with proposed value, counts, precision, recall, sample size and attempt drill-down. | FR-DEV-05..07 |
| `REQ-CAL-002` | Calibration MUST analyze each input quality gate independently, support version/parameter before-after comparison and leave serving-setting application as an explicit manual developer action. | FR-DEV-08..10 |
| `REQ-CAL-003` | Calibration MAY run on the shared `BackgroundPhotoWorker` and delay photo processing during debugging; interruption MUST become visible, photo processing MUST resume, and rerun remains manual without preemption, priority scheduling or a separate Calibration worker. | FR-DEV-11, NFR-PERF-03 |
| `REQ-REL-001` | Central runtime MUST operate independently of the display session; the display MUST recover and retain local advertising, while realtime work uses one slot/deadline without a waiter queue and remains short-lived and non-replayed. | NFR-REL-01..03 |
| `REQ-REL-002` | The PostgreSQL photo-processing queue MUST preserve its `pending`/`processing` population across backend/worker restart, return unfinished work to `pending`, restart idempotently without duplicate final faces, and keep primary-storage capacity observable. | NFR-REL-04..05 |
| `REQ-SEC-001` | Public access MUST use HTTPS, internal stores/services MUST stay private, СПА identity MUST derive from a hashed client token, and required rate-limit, SSH and browser-sandbox controls MUST apply. | NFR-SEC-01..03 |
| `REQ-DATA-001` | Logs MUST expire after 30 days and ordinary Attempts/evidence after 90 days; only the curated promoted subset may survive until explicit deletion, participant names remain annotation-only, and the latest cleanup outcome MUST be visible as defined by NFR-REL-05. | NFR-REL-05, NFR-DATA-01..04 |
| `REQ-ARCH-001` | The pilot MUST retain the one-СПА, one central CPU-only server and simple backend/worker/realtime/PostgreSQL/object-storage baseline; hardware is site-validated and added complexity requires measured evidence. | NFR-ARCH-01..04 |

## Out of Scope

- Public rollout, multi-СПА production scale and production-readiness claims.
- Payment/fiscal flows, actual original delivery and implementation of the
  redirect target's selfie-search/purchase experience.
- External ingest, RAW, standalone/repeated selfie capture and watermarking.
- Guaranteed complete group coverage, tracking, identity clustering,
  cross-pipeline linking and participant-facing ensembles.
- Speculative ANN, broker, distributed, multi-worker, GPU-first or external
  observability infrastructure.
- Automatic Calibration application or multidimensional joint optimization.
- Backup, replication or recovery from irreversible loss of the sole primary
  disk/server.

## Traceability Matrix (RTM)

| REQ | Epic | Feature | Test / evidence target | Lifecycle |
|---|---|---|---|---|
| `REQ-000` | Foundation (no product epic) | [FT-000](features/FT-000-foundation.md) | [Testing specification](testing/index.md), `Executable Baseline Contract`, and final Foundation gate | planned |
| `REQ-ING-001` | [EP-001](epics/EP-001.md) | [FT-001](features/FT-001.md) | PRD AC-08 | planned |
| `REQ-ING-002` | [EP-001](epics/EP-001.md) | [FT-001](features/FT-001.md) | PRD AC-08 | planned |
| `REQ-ING-003` | [EP-001](epics/EP-001.md) | [FT-001](features/FT-001.md), [FT-002](features/FT-002.md) | PRD AC-17 | planned |
| `REQ-ING-004` | [EP-001](epics/EP-001.md) | [FT-002](features/FT-002.md) | PRD AC-06/08 | planned |
| `REQ-INV-001` | [EP-001](epics/EP-001.md) | [FT-012](features/FT-012.md) | PRD AC-18 | planned |
| `REQ-INV-002` | [EP-001](epics/EP-001.md) | [FT-012](features/FT-012.md) | PRD AC-18 | planned |
| `REQ-INV-003` | [EP-001](epics/EP-001.md) | [FT-012](features/FT-012.md) | PRD AC-18/20 and restore-all e2e | planned |
| `REQ-INV-004` | [EP-001](epics/EP-001.md) | [FT-012](features/FT-012.md) | PRD AC-19 | planned |
| `REQ-SRCH-001` | [EP-001](epics/EP-001.md), [EP-002](epics/EP-002.md) | [FT-002](features/FT-002.md), [FT-004](features/FT-004.md) | PRD AC-03/10 | planned |
| `REQ-SRCH-002` | [EP-002](epics/EP-002.md) | [FT-004](features/FT-004.md) | PRD AC-01/03 | planned |
| `REQ-SRCH-003` | [EP-002](epics/EP-002.md) | [FT-004](features/FT-004.md) | PRD controlled setup, AC-03/05 | planned |
| `REQ-CAP-001` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md) | PRD AC-01/14 | planned |
| `REQ-CAP-002` | [EP-002](epics/EP-002.md) | [FT-004](features/FT-004.md) | PRD AC-03/10 | planned |
| `REQ-CAP-003` | [EP-002](epics/EP-002.md) | [FT-004](features/FT-004.md) | PRD AC-01/03 | planned |
| `REQ-UX-001` | [EP-002](epics/EP-002.md) | [FT-005](features/FT-005.md) | PRD AC-01/07/16 | planned |
| `REQ-UX-002` | [EP-002](epics/EP-002.md) | [FT-006](features/FT-006.md) | PRD AC-04 | planned |
| `REQ-UX-003` | [EP-002](epics/EP-002.md) | [FT-006](features/FT-006.md) | PRD AC-15 | planned |
| `REQ-UX-004` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md), [FT-005](features/FT-005.md) | PRD AC-14 | planned |
| `REQ-PERF-001` | [EP-002](epics/EP-002.md), [EP-003](epics/EP-003.md) | [FT-003](features/FT-003.md), [FT-004](features/FT-004.md), [FT-005](features/FT-005.md), [FT-007](features/FT-007.md) | PRD AC-01..03/05/07 | planned |
| `REQ-DIAG-001` | [EP-003](epics/EP-003.md) | [FT-007](features/FT-007.md) | PRD AC-05/10 | planned |
| `REQ-DIAG-002` | [EP-003](epics/EP-003.md) | [FT-007](features/FT-007.md) | PRD AC-05/10/13 | planned |
| `REQ-DIAG-003` | [EP-003](epics/EP-003.md) | [FT-008](features/FT-008.md) | PRD AC-09/10 | planned |
| `REQ-LOG-001` | [EP-003](epics/EP-003.md) | [FT-009](features/FT-009.md) | PRD AC-10/13 | planned |
| `REQ-ANN-001` | [EP-003](epics/EP-003.md) | [FT-010](features/FT-010.md) | PRD AC-11 | planned |
| `REQ-CAL-001` | [EP-003](epics/EP-003.md) | [FT-011](features/FT-011.md) | PRD AC-12 | planned |
| `REQ-CAL-002` | [EP-003](epics/EP-003.md) | [FT-011](features/FT-011.md) | PRD AC-12 | planned |
| `REQ-CAL-003` | [EP-003](epics/EP-003.md) | [FT-011](features/FT-011.md) | PRD FR-DEV-11 worker-interruption evidence | planned |
| `REQ-REL-001` | [EP-002](epics/EP-002.md) | [FT-003](features/FT-003.md), [FT-005](features/FT-005.md) | PRD AC-14, physical-site verification | planned |
| `REQ-REL-002` | [EP-001](epics/EP-001.md) | [FT-002](features/FT-002.md) | PRD AC-06 and worker-restart recovery evidence | planned |
| `REQ-SEC-001` | [EP-001](epics/EP-001.md), [EP-002](epics/EP-002.md) | [FT-001](features/FT-001.md), [FT-003](features/FT-003.md), [FT-004](features/FT-004.md), [FT-006](features/FT-006.md) | PRD NFR-SEC-01..03 boundary-conformance evidence | planned |
| `REQ-DATA-001` | [EP-003](epics/EP-003.md) | [FT-007](features/FT-007.md), [FT-008](features/FT-008.md), [FT-009](features/FT-009.md), [FT-010](features/FT-010.md), [FT-011](features/FT-011.md) | PRD NFR-REL-05 and AC-13 | planned |
| `REQ-ARCH-001` | [EP-001](epics/EP-001.md), [EP-002](epics/EP-002.md), [EP-003](epics/EP-003.md) | [FT-001](features/FT-001.md)–[FT-012](features/FT-012.md) | PRD controlled setup and architecture constraints | planned |
