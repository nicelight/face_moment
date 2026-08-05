---
description: Product Requirements Document.
status: draft
type: prd
clarification_status: complete
constitution_checked: true
last_updated: 2026-08-05
---
# PRD

## Source Inputs

The [Project Constitution](constitution.md), accepted operator decisions and
[.memory-bank/analysis/product-brief.md](analysis/product-brief.md) govern this
consolidated one-СПА pilot contract. Historical brainstorming and `IDEA_*`
files remain discovery evidence only; they do not add or reopen requirements
beyond the resolved behavior, constraints and acceptance criteria below.

## Clarifications

Clarification is complete. Resolved operator decisions are incorporated into
the FR, NFR and acceptance criteria below rather than repeated as a dated log.

## Product Summary

Face Moment is a controlled one-СПА smoke pilot that tests whether fresh
professional JPEG photographs can become searchable in time for a fully
automatic, sensor-triggered Promo experience at the participant's exit. The
display must find four personal low-quality teaser photographs, show a fully
visible and scannable QR code, and continue the same search session on the
participant's phone without a new selfie.

The pilot ends at a verified phone continuation page. Payment, actual original
download and public use by ordinary СПА visitors are post-pilot context, not
current delivery or acceptance scope.

The same pilot includes a developer-only investigation and calibration contour
in the target backend to be delivered by this project: correlated attempts,
browser/server log search, manual per-person/per-detection annotation and
explainable recommendations for face-match threshold and individual input
quality gates.

## Goals

1. Validate an automatic `ingest -> searchable -> capture -> Promo -> QR ->
   phone continuation` path without participant action before QR scanning.
2. Make at least 95% of independently accepted unique JPEGs searchable in under
   15 minutes from their server-side `photo.accepted_at`.
3. Show a fully visible and scannable QR in under 10 seconds from
   `reference_series_ready_at` in at least 19 of 20 controlled attempts.
4. Preserve СПА, `visit_date`, teaser and `N` consistently within the same
   search/Promo session when it is continued on the phone.
5. Validate that, in at least 19 of the 20 controlled attempts, every displayed
   teaser and every unique photograph counted in `N` belongs to at least one
   pilot participant represented by a processed selected detection. This does
   not require coverage of every unique person in a group.
6. Capture enough correlated evidence to explain failures, latency breakdown,
   group-search choices and threshold/quality-gate effects.
7. Keep the pilot architecture operationally simple and add infrastructure
   complexity only after a measured bottleneck.
8. Let authorized users safely hide, restore and permanently purge selected
   commercial Photos, and let staff observe recent per-СПА ingest/processing
   activity without introducing another queueing subsystem.

## Non-goals

- Public rollout to ordinary СПА visitors or production-readiness claims based
  on the 20-attempt smoke run.
- Deployment to 10-15 СПА in the current pilot.
- Payment provider integration, receipt, refund, actual original delivery or
  repeated paid download.
- Sale of individual photographs; the post-pilot direction is one fixed price
  for the whole found package.
- Standalone selfie/live-selfie search or a repeated selfie after scanning QR.
- Implementation or acceptance of the main selfie-search/purchase page used as
  the expired-session redirect target; this pilot owns only the redirect and
  expired-session data-isolation contract.
- Yandex Disk or any other external ingest channel, RAW processing, OAuth to a
  photographer's cloud account, Telegram ingest or EXIF-based automatic
  grouping.
- Watermarks on Promo or phone previews.
- Guarantee that every unique person in a group receives a detection slot or is
  represented in the result.
- Tracking or identity deduplication across reference frames, automatic identity
  clustering or cross-pipeline person linking.
- Alternative FT-003 routes/runtimes or a representative benchmark gate beyond
  the accepted FR-CAP-13..17 and NFR-ARCH-06 contract.
- Additional proposal-request caps or an oversize domain lifecycle beyond
  FR-CAP-09, including client ranking/truncation to fit the transport limit.
- Mandatory upload of full/downscaled reference frames, proof or annotation of
  occurrences missed by the local detector, or a diagnostic frame-upload mode.
- ANN search, Redis, Celery/RQ/Arq, Kafka, multiple priority queues, Kubernetes,
  distributed scheduling, GPU-first deployment or one inference server per СПА.
- Multi-model ensemble in participant-facing search, automatic serving-pipeline
  switching or mandatory online dual-benchmark mode.
- Automatic application of calibration recommendations, multidimensional joint
  optimization of threshold and quality gates, or an embedded experimentation/
  test-management platform.
- Session replay, bulk diagnostic export, automatic replay runner or a separate
  observability datastore/stack in the first version.
- Automatic tuning of capture-window, frame-interval, group-selection,
  CPU/thread or UI/QR timing parameters.
- A separate backup, replication or primary-storage-loss recovery system. The
  pilot accepts loss of persisted data if its only primary disk or server is
  irrecoverably lost.

## Users / Actors

### Pilot participant

- Is a known tester participating in controlled pilot attempts.
- Walks through the capture zone at a distance of 3-5 metres without pressing a
  button or otherwise initiating capture.
- Sees four teaser photographs and scans QR to continue the same session on a
  phone without a selfie.

### Photographer

- Authenticates in the web application.
- Selects the СПА and authoritative `visit_date`, then uploads ready JPEGs
  independently without creating or confirming a Batch.
- Sees accepted, rejected and duplicate outcomes per file and observes each
  accepted photo's processing/searchable state; the photographer has no
  diagnostic-page access.
- May select their own uploaded Photos by СПА, `visit_date` and capture-time
  range, soft-delete them and restore them while they remain soft-deleted.

### Face Moment / СПА operator

- Observes photo readiness, failures and Promo operation.
- May view recent queue statistics per СПА and soft-delete or restore any Photo
  in an accessible СПА, and may invoke the confirmed project-wide restore-all
  or hard-purge action.
- Explicitly sets the active working `visit_date` for the pilot СПА in the
  server-side application before automatic attempts use that date for search.
- May open a sanitized attempt summary containing outcome, stage timeline,
  latency and issue tags; access to other data follows NFR-SEC-04 and
  NFR-SEC-06.

### Application developer

- Investigates individual attempts and correlated browser/server logs.
- May view recent queue statistics per СПА, soft-delete or restore any Photo,
  and invoke the confirmed project-wide restore-all or hard-purge action.
- Has authorized access to developer-restricted diagnostic data, real names in
  annotations, detailed Log Explorer records and Calibration.
- Adds ground-truth annotations, compares releases/configurations and examines
  group-search decisions.
- Receives explainable threshold and quality-gate recommendations and applies
  any accepted serving-setting change manually.

### System actors

- `SpaPromoClient`: browser-native Chromium display/capture client loaded from
  the central HTTPS origin and bound to one СПА by a client token.
- ESP32 passage sensor: local authenticated trigger source published under one
  fixed mDNS `.local` name.
- Browser-visible camera: captures the reference series after explicit
  configuration and preview.
- Backend, `BackgroundPhotoWorker` and `RealtimeFaceService`: ingest/control,
  background photo processing and synchronous realtime search responsibilities.

The economic buyer of the post-pilot product is still a hypothesis and is not a
pilot actor or blocker.

## Functional Requirements

### A. Photographer ingest and searchable inventory

- **FR-ING-01** — The pilot MUST accept commercial photographs only through an
  authenticated direct web uploader over HTTPS and only as ready JPEG files.
- **FR-ING-02** — Before uploading, the photographer MUST select one СПА and one
  authoritative working `visit_date`; each JPEG is admitted independently
  under that scope without a Batch, manifest or confirmation step.
- **FR-ING-03** — For each completed upload, the server MUST validate format and
  image decoding, calculate SHA-256 and show its accepted, rejected or duplicate
  outcome independently of every other file.
- **FR-ING-04** — The selected `visit_date` stored with each accepted Photo is
  authoritative. EXIF time, filename and upload time may support sorting,
  diagnostics and warnings but MUST NOT silently replace it.
- **FR-ING-05** — JPEG uniqueness MUST be enforced by
  `(spa_id, visit_date, checksum_sha256)`. When the same file is uploaded again
  for the same СПА and `visit_date`, the new uploaded object MUST be deleted,
  classified visibly as a duplicate and otherwise ignored: it MUST NOT create a
  new `photo_id`, processing state, searchable result, teaser candidate or
  contribution to `N`.
- **FR-ING-06** — After a valid unique original exists in private object
  storage, one short PostgreSQL transaction MUST create its Photo and serving-
  pipeline `pending` state together, set server-side `photo.accepted_at`, and
  commit independently of every other upload. A private object left without a
  Photo by a crash before commit is an acceptable orphan and MUST NOT require a
  distributed transaction.
- **FR-ING-07** — The uploader MUST expose explicit per-photo states covering
  `pending`, `processing`, `searchable`, `no_faces` and `failed`; `searchable`
  corresponds to `photo_pipeline_states.status = ready` for the serving
  pipeline revision.
- **FR-ING-08** — `ingest_to_searchable` MUST use all independently accepted
  unique JPEGs as its population and measure each from `photo.accepted_at`.
  Files still `pending`, `processing`, `failed` or `no_faces` after 15 minutes
  remain SLO breaches; rejects, checksum duplicates and non-serving jobs are
  excluded.

### B. Face processing and scoped search

- **FR-SRCH-01** — The one-СПА pilot MUST use one selected and pre-warmed serving
  pipeline for participant-facing search. SFace and Buffalo M MUST retain their
  native detector/preprocessing/alignment paths and may be compared on pilot
  data without combining their participant-facing results.
- **FR-SRCH-02** — Every embedding and face record MUST belong to an immutable
  pipeline revision. Search MUST NOT compare incompatible revisions.
- **FR-SRCH-03** — Search MUST use exact pgvector cosine search after filtering
  by serving pipeline revision, СПА and authoritative `visit_date`; an optional
  time window may be used only when its clock/timezone quality is confirmed.
- **FR-SRCH-04** — A match MUST pass both the configured query-face quality gate
  and the calibrated reference threshold for the СПА, pipeline code and query
  source. A top-1/top-2 margin MUST NOT be used.
- **FR-SRCH-05** — The serving reference threshold MUST be calibrated and
  registerable/editable before the controlled acceptance run.
- **FR-SRCH-06** — The operator MUST explicitly set the active working
  `visit_date` for the СПА in the server-side application. Every automatic
  sensor-triggered attempt MUST use that date until the operator changes it;
  `SpaPromoClient` MUST NOT override it. If no active date is set, search MUST
  not run and the condition MUST be recorded diagnostically.

### C. Automatic reference capture and best-effort group behavior

- **FR-CAP-01** — `SpaPromoClient` MUST continuously receive camera video and
  maintain a short ring buffer. The passage sensor marks an event in that stream
  and starts a configured pre/post-trigger reference series without participant
  action.
- **FR-CAP-02** — While capture or search is active, new sensor events MUST be
  ignored; stale realtime requests MUST NOT later replace a newer display state.
- **FR-CAP-03** — `SpaPromoClient` MUST traverse reference-series frames from
  earliest pre-trigger to latest post-trigger and preserve BlazeFace output
  order within each frame. It MUST stop local detection immediately after the
  twentieth face proposal occurrence and send those first at most 20
  occurrences in one synchronous request. It MUST NOT rank, choose a top-5,
  authoritatively quality-gate, track, cluster, deduplicate, embed or search
  those occurrences. The pre-existing server contract remains at most five
  independently searched detections with no merged embeddings; this
  clarification does not otherwise define server processing.
- **FR-CAP-04** — The pilot MUST preserve the current best-effort behavior: one
  physical person may occupy several detection slots, and tracking, identity
  clustering and cross-frame person deduplication are absent.
- **FR-CAP-05** — Candidate photographs MUST first pass search scope, compatible
  revision, calibrated face threshold and preview readiness. pHash diversity may
  only rank already-valid matches and MUST NOT admit a weak match.
- **FR-CAP-06** — The candidate-pool selection MUST preserve unique `photo_id`
  values across processed detections and form four unique teaser photographs as
  specified by the current algorithm in `IDEA_APP.md` sections 6.4-6.5.
- **FR-CAP-07** — `session_result_photo_ids` MUST be the union of unique
  `photo_id` values passing the calibrated threshold for at least one processed
  selected detection. `N` is the cardinality of this union and is not limited to
  the four teasers.
- **FR-CAP-08** — Runtime Promo MUST be considered successful only when four
  unique threshold-valid teaser photographs are available. For controlled
  acceptance, an attempt is ground-truth correct only when all four teasers and
  every unique `photo_id` counted in `N` belong to at least one pilot participant
  represented by a processed selected detection; complete group coverage is not
  required.
- **FR-CAP-09** — The client proposal envelope MUST be structurally bounded by
  at most 20 occurrence parts and a maximum encoded crop side of 512 pixels.
  The server MUST reject a total multipart request body larger than `20 MiB`
  (`20,971,520` bytes) with HTTP `413` before domain admission. It MUST NOT
  introduce separate aggregate-pixel, per-JPEG-byte or manifest-size caps,
  produce an oversize domain outcome, or rank/drop a subset to fit the
  transport limit.
- **FR-CAP-10** — If the local detector returns no occurrences, the client MUST
  send a metadata-only request with the same attempt correlation and client
  timings. If admitted, it MUST create the core Attempt and return an explicit
  non-success outcome.
- **FR-CAP-11** — Client configuration MUST list available cameras with
  understandable labels, provide preview, explicit selection and refresh. If
  the selected camera becomes unavailable, advertising MUST continue and
  capture MUST wait for operator reselection and preview; no arbitrary camera
  substitution is allowed. Frames larger than the deployment-configured maximum
  MUST be downscaled before entering the ring buffer or detector; the exact
  maximum belongs to camera/site configuration.
- **FR-CAP-12** — Client configuration MUST provide an explicitly labelled test
  trigger. Physical and test triggers MUST follow the same capture, proposal,
  request and overlap/staleness behavior, with distinguishable trigger-source
  metadata.
- **FR-CAP-13** — The single pilot client route MUST be browser-native Chromium
  loaded from the central Face Moment HTTPS origin, without a local bridge or
  local web server. While active, it MUST keep one HTTP long-poll request to the
  fixed mDNS ESP32 `.local` name with a 10-second timeout and open the next
  request immediately after an event or timeout. WebSocket is not part of this
  route.
- **FR-CAP-14** — The local proposal detector MUST be MediaPipe BlazeFace
  Full-range through its browser runtime, without TensorFlow.js or another
  project-selected ML runtime. Its model MUST be a separate versioned asset
  shipped with the `SpaPromoClient` release, not embedded in JavaScript. YuNet
  2026may FP32 MAY replace it only after BlazeFace is shown technically
  unusable; both detectors and a generic detector abstraction MUST NOT be
  implemented simultaneously.
- **FR-CAP-15** — Each occurrence crop MUST be a centered square with side
  `1.2 × max(bbox_width, bbox_height)`, clipped to the source frame without
  alignment, landmark normalization or upscaling. A crop whose longest side
  exceeds 512 pixels MUST be proportionally downscaled to 512 pixels and
  encoded as ordinary sRGB JPEG without EXIF or source metadata.
- **FR-CAP-16** — The configuration/debug page MUST expose JPEG quality as one
  dropdown containing exactly `0.7`, `0.75`, `0.8`, `0.85`, `0.9` and `0.95`,
  with default `0.85`. The selected value MUST be stored in kiosk-profile
  `localStorage`, apply from the next Attempt and be included in its manifest;
  it is not a server-side setting.
- **FR-CAP-17** — One ready reference series MUST produce one synchronous
  `multipart/form-data` request containing a versioned JSON manifest and one
  JPEG part per occurrence; zero occurrences use the same endpoint with the
  manifest only. Its identity block MUST contain only `schema_version: 1`, UUID
  `attempt_id`, `trigger_source`, `client_release`, `detector_id`,
  `model_version` and `jpeg_quality`; it also carries the selected
  `camera_device_id`. Its timing block MUST contain
  `reference_series_ready_at` for correlation plus
  `local_detection_completed_ms` and `request_started_ms` as monotonic offsets
  from ready-series zero; client/server wall clocks MUST NOT be subtracted.
  Every occurrence MUST carry only request-local `occurrence_index`,
  `frame_index`, `frame_offset_ms`, `detector_confidence` and `crop_part`.
  `spa_client_token` stays in the Authorization header and the server derives
  `spa_id`; the manifest MUST NOT carry either one, another secret, an
  occurrence UUID, camera label/configuration snapshot, `bbox_px`,
  `crop_rect_px`, `source_frame_width_px` or `source_frame_height_px`. Exact
  serialization belongs to downstream SDD.

### D. Promo display and QR continuation

- **FR-UX-01** — Between attempts, the display MUST show locally available
  advertising. Capture/search MAY use a non-personal prePromo state; it MUST NOT
  expose a partial or stale participant result.
- **FR-UX-02** — A successful Promo MUST show exactly four low-quality teaser
  photographs without watermark and a high-contrast, fully visible, scannable
  QR code on the 43-inch landscape, 16:9, logical 1920x1080 baseline. The client
  MUST send an idempotent display acknowledgement only after all four teasers
  are decoded and the QR is fully visible. If the result-display window ends
  without confirmation, `display_status=unconfirmed` is derived on read; no
  scheduler or acknowledgement outbox is required.
- **FR-UX-03** — The QR MUST continue the same short-lived session on the phone
  without another selfie or participant login step implied by the current
  immediate-continuation flow.
- **FR-UX-04** — The phone landing MUST show the same session's СПА,
  `visit_date`, an available low-quality teaser when one remains, the issued
  `N`, and an active `Перейти к покупке` button. Media hard-purged after
  issuance is skipped without invalidating or rebuilding the session.
- **FR-UX-05** — The Promo display MUST use the truthful copy `Ваши фотографии
  найдены — откройте по QR-коду`. On the valid phone landing, `Перейти к
  покупке` MUST navigate to the separately delivered main Face
  Moment selfie-search/purchase page. This pilot owns the navigation link but
  does not implement or accept the target purchase flow.
- **FR-UX-06** — Display duration, successful-capture cooldown, QR-session TTL
  and browser idle TTL MUST be independent settings. QR first-open TTL MUST be
  30 minutes from `qr_issued_at`. The pilot MUST use one session-wide browser
  access context rather than independent per-device grants: every scan before
  the first-open deadline opens or reuses that context. After a successful
  first open, the shared context MUST expire after 60 minutes without explicit
  participant navigation or action on any opened phone.
- **FR-UX-07** — After result-display duration expires, the screen MUST return
  to advertising without implicitly invalidating an otherwise active QR
  session.
- **FR-UX-08** — If fewer than four valid unique teasers are produced, or a
  camera/sensor/network/processing failure prevents success, the client MUST
  return to local advertising, omit the final Promo/Chime, create a best-effort
  diagnostic event and allow a fresh capture without starting the success
  cooldown. For a server-communication failure, it MUST also show the small
  non-blocking text `Попытка связи с сервером была не успешна в hh:mm:ss` for
  5–10 seconds in the easiest non-obstructive location, bottom-left by default.
  The timestamp uses client-local failure time; a newer message MAY replace the
  current one immediately, including before five seconds.
- **FR-UX-09** — On timeout or network error, the client MUST discard the stale
  request and retry only with a fresh reference capture.
- **FR-UX-10** — When the QR first-open or session-wide browser idle TTL
  expires, only the personalized Promo session becomes unavailable; the
  browser page MUST remain functional and redirect to the main Face Moment
  page, where the visitor is offered photo search and purchase through selfie
  upload. The redirect MUST NOT expose the expired session's teaser, `N` or
  other personal result data. The main selfie-search/purchase page is a
  separately delivered dependency; implementing or accepting that target is
  outside this pilot.

### E. Attempts and diagnostic evidence

- **FR-DIAG-01** — Every capture/search request admitted by the server,
  including unsuccessful domain outcomes, MUST persist one core Attempt with a
  client-generated `attempt_id/correlation_id` before inference. That identity
  connects browser events, server processing, configuration, face-search
  decisions and artifacts without requiring a separate empty diagnostic-anchor
  row. A client-only offline trigger MAY be delivered through a short-lived
  metadata outbox and server upsert, but this is best-effort and is not
  guaranteed to produce a durable Attempt.
- **FR-DIAG-02** — The diagnostic UI MUST show the client-local moments when
  ready-series processing starts, request sending starts and the response is
  received. The correlated timeline MUST also expose capture/reference
  readiness, request/network, singleton-slot acquisition or `busy`, server
  processing, Promo render and full QR visibility so a `>=10 s` outcome can be
  localized.
- **FR-DIAG-03** — Attempt detail MUST show release, serving pipeline revision,
  applied threshold and quality values, selected detections, repeated
  detections, candidate pools, selected teasers, `N`, outcome/status and issue
  tags.
- **FR-DIAG-04** — Collected diagnostic evidence MUST correlate received
  proposal crops and metadata, camera/config metadata, detections, candidates,
  thresholds, selected IDs, timestamps, actually displayed Promo evidence and
  QR continuation event. A product flow that actually captures a selfie MUST
  also retain that selfie as a diagnostic artifact; the current pilot has no
  selfie capture and therefore creates no selfie artifact.
- **FR-DIAG-05** — Detailed evidence is attached best-effort by `attempt_id`; a
  terminal Attempt without finalized evidence MUST remain visible as
  `incomplete`. When evidence exists, the attempt MUST expose a reproducibility
  manifest with versions, parameters, timestamps and links governed by
  NFR-SEC-06; an automatic replay runner is not required.
- **FR-DIAG-06** — The `Attempts` page MUST support filtering by time, status,
  release, pipeline, latency and issue tags, opening a unified browser/server
  timeline and navigating to relevant logs/artifacts.
- **FR-DIAG-07** — The operator view of an attempt MUST be sanitized to outcome,
  stage timeline, latency and issue tags. Navigation beyond that view MUST
  follow NFR-SEC-04 and NFR-SEC-06.

### F. Manual annotation, logs and calibration

- **FR-DEV-01** — An authorized developer MUST be able to annotate ground truth
  at person/detection level, associate a real pilot-participant name and record
  `correct`, `wrong/false` or `missed` outcomes. Exact normalized storage
  vocabulary is deferred to SDD, but its semantics MUST support the stated
  calculations.
- **FR-DEV-02** — Developer-only `Log Explorer` MUST search structured
  browser/server logs by time, source, component, severity, release, message and
  correlation fields, and MUST navigate from a record to its related attempt.
- **FR-DEV-03** — Log search MUST operate through the project backend and
  PostgreSQL. The browser MUST NOT access PostgreSQL directly.
- **FR-DEV-04** — Browser/server logging MUST be non-blocking for capture,
  search, Promo and QR. Log records MUST NOT contain embeddings, credentials,
  authentication headers, cookies, tokens, participant names, commercial Photo
  originals, personalized session data or session replay. Capture-derived
  media MAY be logged when useful and bounded; logging every crop or complete
  request body is not required.
- **FR-DEV-05** — `Calibration` MUST use annotated attempts to compare SFace and
  Buffalo M and calculate face-match-threshold recommendations without changing
  serving settings automatically.
- **FR-DEV-06** — Threshold analysis MUST show three named profiles:
  `Best face match` minimizes false matches with correct matches as tie-break;
  `Balance` presents a correct/false/missed trade-off; `Minimum missed faces`
  minimizes misses with false matches as tie-break. Exact formula for `Balance`
  belongs to SDD.
- **FR-DEV-07** — Every threshold recommendation MUST show the proposed value,
  correct/false/missed counts, precision, recall, annotated sample size and
  drill-down to contributing attempts.
- **FR-DEV-08** — Face size, detection confidence, blur, brightness and pose
  quality gates MUST be analysed one at a time, not jointly. Each recommendation
  MUST show current/proposed values, sample size, kept/rejected detections and
  expected correct/false/missed changes.
- **FR-DEV-09** — Calibration MUST compare before/after release or parameter-set
  results using stored versions, parameters, outcomes and annotations, without
  introducing a separate experimentation platform.
- **FR-DEV-10** — Applying a recommendation MUST remain an explicit manual
  developer action; the precise operational mechanism and audit details belong
  to SDD.
- **FR-DEV-11** — Developer-triggered Calibration MAY run on the single
  `BackgroundPhotoWorker` and delay photo processing during debugging. No
  preemption, priority scheduler or separate Calibration worker is required. A
  Calibration run interrupted by worker restart MUST become `failed` or
  `interrupted`, photo processing MUST resume, and the developer MAY rerun
  Calibration manually.

### G. Photo Inventory Operations

- **FR-INV-01** — Photo inventory selection for deletion MUST use one СПА,
  authoritative `visit_date` and a selected capture-time range. Each Photo MUST
  have an effective `captured_at`: reliable EXIF time interpreted in the СПА
  timezone, otherwise the server-side start time of that file's upload, and as
  the final fallback 01:00 on its authoritative `visit_date`.
- **FR-INV-02** — A photographer MUST be able to soft-delete and restore only
  Photos uploaded by that photographer. An operator or developer MUST be able
  to soft-delete and restore any Photo in an accessible СПА.
- **FR-INV-03** — Soft deletion MUST preserve the Photo record, stored media,
  face data, pipeline state and other related data while immediately excluding
  the Photo from new participant-facing search/result formation and queue
  statistics. An already issued Promo/session MUST continue using its referenced
  Photo/media while the media exists; soft delete MUST NOT invalidate or rebuild
  that session.
- **FR-INV-04** — Restoring a soft-deleted Photo MUST make the preserved Photo
  active again without re-upload or reprocessing and MUST return it to search,
  media access and statistics according to its preserved state and timestamps.
- **FR-INV-05** — Admin settings MUST provide two project-wide actions:
  `hard delete ALL softed media` and `restore all soft deleted`. The restore-all
  action MUST restore every currently soft-deleted Photo across all СПА except
  Photos already included in a non-terminal confirmed hard-purge snapshot;
  restore of those snapshot members MUST be rejected until the purge completes.
- **FR-INV-06** — `hard delete ALL softed media` MUST require explicit
  confirmation and then operate on a fixed snapshot of every soft-deleted Photo
  across the project. While it runs, its UI MUST be replaced by a progress view
  based on completed Photos versus the snapshot total.
- **FR-INV-07** — The global hard purge MUST wait for the shared worker's
  current operation without preemption. While waiting, the UI MUST show
  `Начну удаление, как только закончится процесс {human-readable process name}`.
- **FR-INV-08** — For every Photo in the confirmed purge snapshot, hard deletion
  MUST remove its Photo record, original/preview/thumbnail media, detected-face
  data and photo-pipeline state. Existing Promo results/sessions, core Attempts
  and diagnostic evidence MUST NOT be removed or rebuilt by this action. A
  UI/device client loading an existing session MUST skip unavailable
  hard-purged media and continue with remaining items; the issued `N` remains
  historical and is not recalculated.
- **FR-INV-09** — One global purge run MUST resume after a backend or worker
  restart until its confirmed snapshot is complete. It MUST NOT introduce a
  per-photo `purge_pending` lifecycle or a separate purge jobs table. An upload
  already in progress MUST NOT be interrupted; uploads allowed to complete
  during purge MAY add ordinary durable photo-processing backlog.
- **FR-INV-10** — The Admin UI MUST show queue statistics separately for each
  СПА for the last 1, 5 and 60 minutes:
  `new` is the count of unique active Photos accepted in the window by
  `accepted_at`; `unprocessed` is the count of active Photos accepted in the
  window whose current state is `pending | processing`; `processed` is the
  count of active Photos that transitioned to `ready | no_faces` in the
  window; and `failed` is the count of active Photos that transitioned to
  `failed` in the window.
- **FR-INV-11** — Queue statistics MUST refresh by polling every five seconds.
  WebSocket and SSE delivery are not required.

## Non-functional Requirements

### Performance and acceptance priority

- **NFR-PERF-01** — At least 19 of 20 controlled attempts MUST produce a fully
  visible and scannable QR with
  `qr_fully_visible_elapsed_ms - reference_series_ready_elapsed_ms < 10_000 ms`
  on one client monotonic clock. `reference_series_ready` is the client-local
  moment when the capture window ends and local processing starts; local
  processing and request sending are therefore inside the interval.
- **NFR-PERF-02** — Timeout or no-match without a completed QR is a failed
  attempt, not an excluded observation.
- **NFR-PERF-03** — At least 95% of the metric population defined by FR-ING-08
  MUST become searchable in `<15 min` from each Photo's server-side
  `accepted_at`. Explicit developer Calibration may delay this metric during a
  debugging interval without requiring scheduling machinery.
- **NFR-PERF-04** — The system MUST retain stage timestamps sufficient for
  `reference_ready_to_qr`, trigger-to-preview, singleton-slot acquisition/
  `busy` and ingest-to-searchable diagnosis. Additional percentile cuts are
  optional until justified.
- **NFR-PERF-05** — At least 19 of the same 20 controlled attempts MUST satisfy
  both the latency/QR gate and the full-session correctness gate. A foreign
  teaser or any unrelated `photo_id` included in `N` makes that attempt fail the
  correctness gate, without turning missed group-member coverage into a failure.

### Reliability and operations

- **NFR-REL-01** — The central backend/runtime MUST start and operate
  independently of the local KDE/Chromium display session.
- **NFR-REL-02** — Chromium/display MUST recover automatically after browser
  failure once the central HTTPS origin is reachable. A currently loaded client
  MUST remain in or return to local advertising during transient server/network
  failure. Recovery after tab reload or Chromium restart while the central
  origin remains unavailable is not required.
- **NFR-REL-03** — Realtime processing MUST use one inference slot and one
  server deadline without a waiter queue. A concurrent admitted request receives
  typed `busy`; stale reference work is not durable and MUST NOT be replayed
  after restart.
- **NFR-REL-04** — The PostgreSQL-backed photo-processing queue MUST survive
  backend and worker restarts without losing its existing `pending` or
  `processing` population. On worker startup, unfinished `processing` work MUST
  return to `pending` and restart from the beginning; at-least-once execution
  MUST NOT create duplicate final face records.
- **NFR-REL-05** — Free space on the configured primary PostgreSQL/MinIO
  volumes and diagnostic-retention cleanup MUST be observable separately.
  Authorized users MUST see the latest cleanup's applied cutoffs, confirmed
  deleted/preserved counts and final outcome/error. Failure or interruption
  MUST remain visible and cleanup MUST be safely rerunnable. A recovery
  procedure for browser and intact-volume restarts is also required for the
  single-server pilot.
- **NFR-REL-06** — A confirmed global hard purge MUST retain enough durable
  run identity, fixed target set and completion progress to resume after an
  ordinary backend or worker restart without reintroducing already purged
  Photos or silently abandoning the remaining targets.

### Security, privacy and retention

- **NFR-SEC-01** — The public boundary MUST use HTTPS. PostgreSQL, MinIO,
  internal service ports and Docker API MUST NOT be publicly exposed.
- **NFR-SEC-02** — Each `SpaPromoClient` MUST use a secret token in an
  authorization header. The server MUST derive `spa_id` from a stored token hash
  and MUST NOT trust `spa_id` from the request body or log the token.
- **NFR-SEC-03** — Public requests MUST be rate-limited. SSH MUST be key-only,
  and the display browser MUST run sandboxed under a non-privileged OS user.
- **NFR-SEC-04** — Application authorization MUST enforce a split diagnostic
  access matrix for protected data and actions: the operator receives the
  sanitized attempt outcome/timeline/latency/issue tags; participant names,
  annotations, detailed logs and Calibration require the developer role. The
  photographer is limited to their own uploaded-photo state and has no
  diagnostic-page access.
- **NFR-SEC-05** — Photo Inventory authorization MUST restrict photographers to
  soft deletion and restoration of their own uploads. Operator/developer access
  MAY cover any accessible СПА, while project-wide restore-all and hard-purge
  actions MUST be restricted to authorized operator/developer admin settings.
- **NFR-SEC-06** — Capture-derived reference images, normalized images and face
  crops are ordinary media, not protected solely because they contain an image
  or face. They MAY be logged, cached, stored or delivered without
  developer-only media authorization; none of those mechanisms is required.
  Credentials, infrastructure, commercial Photo media, personalized data,
  participant names and administrative actions remain protected.
- **NFR-SEC-07** — The managed kiosk MUST pre-authorize the central Face Moment
  origin for Local Network Access. ESP32 MUST allow that exact origin through
  CORS, handle OPTIONS when Authorization is present and validate one manually
  provisioned Bearer secret stored through the client configuration UI in the
  managed kiosk browser profile. The secret MUST be sent only in the
  Authorization header and MUST NOT enter URLs or logs. Pairing, automatic
  rotation, PKI and a separate sensor-credential lifecycle are not required.
- **NFR-DATA-01** — Technical browser/server logs MUST expire after 30 days.
- **NFR-DATA-02** — Attempts and ordinary diagnostic bundles/artifacts MUST
  expire after 90 days, including persisted capture-derived diagnostic media.
- **NFR-DATA-03** — A manually promoted calibration case MAY be retained until
  explicit deletion, but only as a curated reproducible subset: already
  available server-side media, required face crops or an actually captured
  selfie, versioned parameters/configuration, scores, annotations and the
  entered participant name. Other diagnostic media and the Promo screenshot
  MUST expire with the ordinary 90-day bundle; technical logs MUST still expire
  after 30 days.
- **NFR-DATA-04** — Real pilot-participant names may appear only in authorized
  manual diagnostic annotations, not in general technical logs.

### Architecture and maintainability constraints

- **NFR-ARCH-01** — The pilot runs on one central CPU-only server in the Russian
  Federation with one pilot СПА and no external cloud face-recognition API.
- **NFR-ARCH-02** — The simple baseline is backend + one sequential
  `BackgroundPhotoWorker` + one synchronous `RealtimeFaceService`, PostgreSQL +
  pgvector and private MinIO/S3-compatible storage.
- **NFR-ARCH-03** — Redis/brokers, ANN, extra workers/instances, GPU,
  distributed coordination or external observability MUST NOT be added without
  a measured failure of a current requirement or bottleneck evidence.
- **NFR-ARCH-04** — Exact pilot hardware, camera, lens, passage sensor, lighting,
  CPU affinity and thread limits are selected/validated against the actual site
  and are not fixed product gates beyond the stated display/capture baseline.
- **NFR-ARCH-05** — Photo Inventory Operations MUST reuse the single shared
  background worker and durable Photo data. They MUST NOT add a per-photo purge
  state, a purge jobs table, WebSocket/SSE statistics transport or another
  worker solely for deletion and statistics.
- **NFR-ARCH-06** — FT-003 implementation readiness MUST use the selected
  browser-native route and structural bounds directly. A representative
  benchmark MUST NOT be required before design or tasking; implementation and
  site evidence still verify the existing performance acceptance contract.

## Data / Domain Model

### Core concepts

- **СПА** — pilot venue with a name, timezone, operator-selected active working
  `visit_date`, active serving pipeline and calibrated reference threshold.
- **Photo** — independently admitted commercial image linked directly to its
  СПА, authoritative `visit_date`, effective `captured_at`, server-side
  `accepted_at`, uploader identity, active/soft-deleted marker and private
  original, preview and thumbnail objects;
  `(spa_id, visit_date, checksum_sha256)` is its logical ingest-uniqueness key,
  while pHash supports teaser diversity only.
- **Pipeline revision** — immutable identity of detector, recognizer, weights,
  preprocessing/alignment, normalization and embedding dimension.
- **Photo pipeline state** — pipeline-specific `pending | processing | ready |
  no_faces | failed` state; `ready` is the searchable state.
- **Photo face** — one face detected by one pipeline revision in one photo.
  Different pipelines create independent records and no shared person identity.
- **Reference series** — sensor-triggered set of frames from the client ring
  buffer traversed chronologically until the frames end or the first 20 face
  proposal occurrences have been found.
- **Face proposal occurrence** — one BlazeFace detection in one reference frame,
  identified only by request-local order plus frame context. It is not a person
  identity, and repeated occurrences of the same person are valid.
- **Selected detection** — one quality-ranked face occurrence used for a search;
  it is not proof of a unique physical person.
- **Promo/search session** — short-lived context binding СПА, authoritative
  `visit_date`, four teaser IDs, `session_result_photo_ids`, `N`, QR token and
  one session-wide browser-access state. The QR may open or reuse that context
  within 30 minutes of `qr_issued_at`; after the first successful open, the
  shared context expires after 60 minutes without explicit participant
  activity on any opened phone.
- **Attempt** — one correlated automatic capture/search/display execution,
  including unsuccessful outcomes and stage timestamps.
- **Diagnostic evidence** — optional media plus a versioned
  manifest, indexed events, decisions, configuration and display evidence linked
  to a core Attempt. Absence or failed finalization is represented as
  `incomplete`, not by a mandatory empty anchor row.
- **Structured log record** — browser/server event associated with a correlation
  ID where applicable.
- **Annotation** — authorized ground truth associating a participant/person and
  detection/result outcome.
- **Calibration case/recommendation** — a manually curated reproducible subset
  of server-available media/crops or an actually captured selfie, parameters,
  scores and annotations retained until explicit deletion, plus a computed
  threshold or one-dimensional quality-gate proposal; it never changes serving
  settings automatically.
- **Global hard-purge run** — one resumable project-wide operation over the
  fixed snapshot of soft-deleted Photos confirmed at its start, with total and
  completed progress. It is not a per-photo pipeline state or general jobs
  subsystem.

### Authoritative relationships and lifecycle

- Each accepted Photo's photographer-selected `visit_date` is authoritative for
  commercial-photo search scope. Its effective `captured_at` uses reliable EXIF
  time in the СПА timezone, then that file's server-side upload-start time, then
  01:00 on `visit_date`; it scopes time-range inventory actions but does not
  replace the authoritative `visit_date`.
- An automatic attempt uses the server-side active working `visit_date` selected
  by the operator for its СПА; the client token selects the СПА but neither the
  client clock nor the latest uploaded photo silently selects the date.
- A photo is searchable only through a `ready` state for the current compatible
  serving pipeline revision.
- A soft-deleted Photo and all its related data remain stored but are inactive
  for new search/result formation and statistics. An already issued
  Promo/session may continue reading its referenced media. Restore reactivates
  the preserved state. Hard purge physically removes Photo-owned data but leaves
  existing Promo sessions, the core Attempt and diagnostic evidence under their
  independent lifecycles. Missing hard-purged media is skipped during
  UI/device loading; the session is not invalidated or rebuilt and its issued
  `N` is not recalculated.
- Four teaser IDs are a subset of `session_result_photo_ids`; `N` is the count of
  the entire unique union.
- Attempt/log/evidence identifiers must allow navigation without placing
  protected payloads in logs.
- Technical logs, normal attempt/evidence data and promoted calibration data have
  distinct retention rules defined by NFR-DATA-01..03.
- Promoting a calibration case does not extend the lifetime of the entire
  diagnostic evidence set: only the curated subset named by NFR-DATA-03
  survives the ordinary 90-day deletion.
- A selfie is a conditional diagnostic artifact: it is stored when a product
  flow actually captures one. The current pilot captures only the automatic
  reference series and selected face crops, so no separate selfie exists or is
  stored in this scope.

## UX / Interaction Flow

### Photographer flow

1. Authenticate and select the СПА plus authoritative `visit_date`.
2. Upload ready JPEGs over HTTPS; each file is admitted independently.
3. Observe accepted, rejected or duplicate outcome for each file.
4. Observe every accepted Photo progress through
   processing/searchable/no-face/failure state.
5. Select own Photos by СПА, `visit_date` and capture-time range, then
   soft-delete or restore them.

### Photo inventory administration flow

1. Select a СПА and observe `new`, `unprocessed`, `processed` and `failed`
   statistics for the last 1, 5 and 60 minutes, refreshed every five seconds.
2. An authorized operator/developer selects Photos by СПА, `visit_date` and
   capture-time range and soft-deletes or restores them.
3. In admin settings, an authorized user may restore every soft-deleted Photo
   across the project except members of a confirmed non-terminal hard-purge
   snapshot.
4. To permanently remove all soft-deleted Photos across the project, confirm
   the hard-purge action.
5. If the shared worker is busy, observe the human-readable current-operation
   message; once purge starts, observe completed/total progress until it
   finishes.

### Participant Promo and continuation flow

1. The display shows local advertising while the camera stream/ring buffer is
   active.
2. The client keeps one 10-second HTTP long-poll request to the authenticated
   fixed-name mDNS ESP32; a passage event triggers a reference series without
   participant action and the client immediately continues long-polling.
3. The client traverses frames chronologically, stops when it finds occurrence
   20, and submits the first at most 20 crops plus metadata in one multipart
   request. When none are found it submits the manifest only; it does not upload
   full frames and still prevents overlapping attempts.
4. The service processes selected detections and either forms four unique valid
   teasers or returns a non-success outcome.
5. On success, the display presents four no-watermark teasers and a scannable QR
   within the performance budget.
6. A participant scans QR and immediately opens the same session-wide browser
   context on a phone, seeing СПА, date, one teaser, `N` and a `Перейти к
   покупке` button that links to the separately delivered main
   selfie-search/purchase page. Another scan before the 30-minute deadline
   reuses the same context rather than creating an independent grant.
7. The display returns to advertising after its independent display duration;
   the QR session remains usable until its own expiry.
8. If the QR is opened after 30 minutes, or the shared browser context has had
   no explicit participant activity on any opened phone for 60 minutes, the
   personalized result expires and the browser redirects to the main Face
   Moment page offering photo search and purchase through selfie upload,
   without carrying personal result data from the expired session.
9. A server-communication failure returns to advertising and briefly shows
   `Попытка связи с сервером была не успешна в hh:mm:ss`; a newer
   notice may replace it.

### Developer investigation and calibration flow

1. Filter `Attempts` and open a slow, failed or suspicious attempt.
2. Inspect the combined timeline, active versions/parameters, selected
   detections, candidate pools, teaser and `N` decisions.
3. Follow links to authorized artifacts and correlated log records.
4. Add per-person/per-detection ground truth.
5. Use `Calibration` to inspect threshold profiles, individual quality-gate
   recommendations and before/after comparisons.
6. Drill down from an aggregate recommendation to contributing attempts.
7. Apply a chosen setting manually outside automatic recommendation execution.

## Integrations / Dependencies

- One ESP32 passage sensor, browser-visible camera and 43-inch display; exact
  camera, lens, lighting and maximum input dimensions remain site choices.
- Managed Chromium, Local Network Access and the BlazeFace model asset are
  client dependencies governed by FR-CAP-13..17 and NFR-SEC-07.
- PostgreSQL with pgvector for metadata, state, exact vector search, structured
  logs and indexed diagnostic events.
- MinIO/S3-compatible private object storage for originals, previews and
  diagnostic images.
- SFace/YuNet and Buffalo M/SCRFD pipelines with native preprocessing.
- QR generation performed locally in the client without an external QR service.
- HTTPS as the public integration boundary.
- Separately delivered main Face Moment selfie-search/purchase page as the
  expired-session redirect target; this pilot does not implement it.

Explicitly absent from the pilot are Yandex Disk, external face-recognition APIs,
payment/fiscal providers, external observability stores and message brokers.

## Edge Cases / Failure Handling

- Invalid, unsupported or undecodable files are rejected independently and
  shown explicitly.
- Mixed EXIF dates produce a warning but do not rewrite authoritative
  `visit_date` or automatically regroup uploads.
- A duplicate JPEG uploaded again for the same СПА and `visit_date` is deleted
  after checksum detection, reported as a duplicate and excluded from the
  metric population, processing, search, teaser and `N`.
- A crash after private-object upload but before the per-photo PostgreSQL commit
  may leave one orphan object; losing that one admission is acceptable and the
  photographer may upload the JPEG again.
- A missing active working `visit_date` prevents search and produces diagnostic
  evidence rather than falling back to a client clock or arbitrary upload date.
- `no_faces` is a distinct terminal processing state but breaches the 15-minute
  searchable SLO for its accepted JPEG population.
- Sensor events arriving during capture/search or successful cooldown are
  ignored according to client state.
- An ESP32 long-poll timeout continues polling. Sensor unavailability leaves
  the display in local advertising without a durable queue or fallback
  transport.
- A BlazeFace model load/validation failure leaves the client in advertising
  with a recoverable operator-visible error; it does not silently activate a
  second detector.
- Multiple detections of one person are allowed and must be visible in
  diagnostics; missing another group member is not itself a group-coverage
  contract breach.
- Fewer than four unique valid teasers, low-quality query faces, no-match,
  timeout, camera/sensor/network/processing failure or stale response must not
  show a partial/stale Promo. For a server-admitted request, its core Attempt
  must record the terminal outcome; detailed evidence remains best-effort. A
  client-only network failure produces only a best-effort diagnostic event and
  may leave no server record.
- Missing optional audio/animation assets must have a silent/non-blocking
  fallback and must not prevent a valid QR result.
- Logging/diagnostic ingestion failure must not block the critical capture,
  search, Promo or QR path; a terminal server-side core Attempt without
  finalized evidence must remain observable as `incomplete`. A client-only
  offline trigger may have no durable Attempt because its metadata delivery is
  best-effort.
- A QR opened more than 30 minutes after `qr_issued_at`, or a session-wide
  browser context with no explicit participant activity on any opened phone for
  60 minutes, invalidates the personalized result and redirects to the main
  selfie-based search/purchase page. No teaser, `N` or other data from the
  expired session is disclosed to the redirect target.
- Diagnostic retention expiry must remove ordinary records and artifacts after
  90 days. For a promoted calibration case it preserves only the curated subset
  in NFR-DATA-03; other diagnostic media and the Promo screenshot are deleted.
- Soft-deleted Photos remain stored but are absent from new search/result
  formation and all four queue-statistic counters. Already issued sessions keep
  using their referenced media while it exists. Restoring a Photo makes it
  eligible for new results again using its preserved state and timestamps.
- Hard purge waits without preemption when the shared worker is busy and
  exposes the current operation by a human-readable name. A process restart
  resumes the same confirmed snapshot and progress.
- Hard-purging a Photo preserves existing Promo results/sessions, the related
  core Attempt and diagnostic evidence. A UI/device client skips the missing
  media item and continues; no session invalidation, replacement selection or
  `N` recalculation occurs.
- Restore and restore-all reject a Photo that belongs to a confirmed
  non-terminal hard-purge snapshot, so the destructive target set stays fixed.
- Full primary storage, process/browser crash and central-server unavailability
  require observable degraded advertising behavior and documented recovery.

## Acceptance Criteria

### Controlled pilot setup

- One selected СПА, one configured `SpaPromoClient`, the 43-inch/16:9/1920x1080
  baseline and validated camera/sensor/lighting geometry at 3-5 metres.
- The managed Chromium kiosk has Local Network Access and can reach its
  configured authenticated ESP32 route.
- A selected serving pipeline is pre-warmed; its reference threshold and input
  quality gates are calibrated before the run.
- The operator has explicitly set the active working `visit_date`, and it
  matches the independently accepted commercial photos intended for the run.
- Every tester expected in a run has at least four searchable commercial
  photographs in the authoritative СПА/date scope.
- The 20-attempt set includes the current best-effort group flow; exact attempt
  composition may be fixed in the verification plan without promising full
  group-member coverage.

### Product and performance outcomes

- **AC-01** — At least 19 of 20 controlled attempts both produce four unique
  teasers and a fully visible, scannable QR in `<10_000 ms` from
  `reference_series_ready_at` under NFR-PERF-01 and satisfy the correctness rule
  in AC-03.
- **AC-02** — No-match or timeout without a completed QR counts as a failed
  attempt.
- **AC-03** — For every attempt counted among the 19 joint AC-01 successes, all
  four teasers and every unique `photo_id` in `session_result_photo_ids` are
  manually confirmed as containing at least one pilot participant represented
  by a processed selected detection. Any unrelated included photograph fails
  that attempt; failure to cover every unique person in a group does not.
- **AC-04** — Every completed phone continuation shows the correct СПА,
  authoritative `visit_date`, an available teaser belonging to that same
  session and the same issued `N`; its `Перейти к покупке` button navigates to
  the configured main selfie-search/purchase page. If referenced media was
  hard-purged after issuance, the missing item is skipped without invalidating
  the session or recalculating `N`.
- **AC-05** — Every request admitted by the server, including the allowed
  failure, has one persisted core Attempt/correlation identity and stage
  timestamps; missing or failed detailed evidence is explicitly visible as
  `incomplete`. Client-only offline attempts remain best-effort and may have no
  durable server record.
- **AC-06** — At least 95% of independently accepted unique JPEGs become
  searchable in `<15 min` from their server-side `photo.accepted_at`, using the
  full denominator/failure semantics of FR-ING-08.
- **AC-07** — A QR is programmatically decodable and successfully scannable on
  representative real phones from the target screen/distance/brightness setup.

### Functional completion signals

- **AC-08** — A photographer can authenticate, select СПА and authoritative
  `visit_date`, upload JPEGs without confirmation, see each independent
  accepted/rejected/duplicate outcome and observe every accepted photo reach an
  explicit current/final state.
- **AC-09** — An operator can find a failed or slow attempt and see only its
  sanitized outcome, timeline, latency and issue tags; protected data governed
  by NFR-SEC-04 and NFR-SEC-06 is inaccessible to that role.
- **AC-10** — An authorized developer can trace the same attempt's versions,
  parameters, group/search decisions, available artifacts and detailed logs by
  correlation ID; `Log Explorer` supports all required filters and navigation
  without exposing PostgreSQL directly.
- **AC-11** — An authorized developer can annotate person/detection outcomes and
  see those annotations reflected in threshold and individual quality-gate
  recommendation evidence.
- **AC-12** — Calibration shows all three threshold profiles and required
  measures/drill-down, supports before/after comparison, and never changes a
  serving setting automatically.
- **AC-13** — Technical logs exclude forbidden payloads and respect 30-day
  retention; ordinary attempts/bundles respect 90-day retention; promoting a
  calibration case preserves only the curated NFR-DATA-03 subset until explicit
  deletion. The latest cleanup outcome satisfies NFR-REL-05.
- **AC-14** — Network/search failure leaves the display on local advertising,
  discards stale work and permits a fresh attempt without a success cooldown.
  A server-communication failure also shows
  `Попытка связи с сервером была не успешна в hh:mm:ss` non-blockingly for
  5–10 seconds; a newer notice may replace it immediately.
- **AC-15** — Before the 30-minute first-open deadline the QR opens its matching
  session-wide browser context without creating per-device grants; after that
  deadline, and after 60 minutes without explicit participant activity across
  that context, the personalized result is inaccessible and the browser
  redirects to the main selfie-based search/purchase page without leaking
  expired-session data. The pilot verifies the redirect contract, not the
  target page's implementation.
- **AC-16** — The Promo display says `Ваши фотографии найдены — откройте по
  QR-коду` and does not claim that download is already available in the pilot.
- **AC-17** — Re-uploading a JPEG with the same SHA-256 for the same СПА and
  `visit_date` deletes the new copy, reports it as a duplicate and leaves the
  accepted-photo population, `photo_id` set, processing states, search results,
  teaser selection and `N` unchanged.
- **AC-18** — A photographer can select their own uploads by СПА,
  `visit_date` and capture-time range, soft-delete them, observe their immediate
  exclusion from new search/result formation and statistics, and restore them
  without re-upload or reprocessing. An already issued session keeps using the
  referenced media. An operator/developer can perform the same actions for any
  authorized Photo.
- **AC-19** — The 1-, 5- and 60-minute per-СПА counters match the definitions in
  FR-INV-10, omit soft-deleted Photos, reflect restored Photos from their
  preserved states/timestamps, and refresh by polling every five seconds.
- **AC-20** — After confirmation, one project-wide hard purge uses a fixed
  soft-deleted snapshot, waits for the shared worker with the required
  human-readable message, shows completed/total progress, survives a process
  restart, rejects restore of snapshot members until completion, and removes all
  snapshot Photo/media/face/pipeline data while retaining existing Promo
  results/sessions, core Attempts and diagnostic evidence. Existing clients
  skip unavailable media without invalidating the session or recalculating `N`.
- **AC-21** — A chronological reference-series fixture with more than 20
  occurrences proves that the client stops at occurrence 20 and sends exactly
  the first 20 in traversal order; a zero-occurrence fixture sends only the
  manifest. A transport-boundary fixture proves that a request body larger than
  `20 MiB` returns HTTP `413` without core Attempt admission; no oversize domain
  outcome or hidden ranking/subset behavior is present.
- **AC-22** — The diagnostic UI exposes all three client markers in FR-DIAG-02.
- **AC-23** — Camera list, preview, selection/reselection and the same-behavior
  physical/test triggers satisfy FR-CAP-11..12; oversized configured camera
  input is downscaled before ring-buffer/detector work.
- **AC-24** — The configuration/debug page exposes only the six accepted JPEG
  quality values, defaults to `0.85`, persists the selection in kiosk-profile
  `localStorage`, applies it from the next Attempt and records it in the
  manifest.
- **AC-25** — The central-origin Chromium client, managed Local Network Access,
  exact-origin ESP32 CORS/OPTIONS/Bearer handling and continuous one-request
  10-second long-poll behavior satisfy FR-CAP-13 and NFR-SEC-07 without a local
  bridge, local web server or WebSocket.
- **AC-26** — BlazeFace, crop and multipart fixtures satisfy FR-CAP-14..17,
  including separate versioned model delivery, `1.2 × max(width, height)`
  clipping, 512-pixel downscale without upscale, selected manifest fields and
  the explicit omitted fields.

The smoke run validates the pilot path only. It does not demonstrate public
production readiness, target 10-15-СПА capacity or complete group coverage.

## Downstream SDD Inputs

Exact interface serialization and site-specific hardware/configuration remain
owned by their canonical specs and deployment configuration. They do not reopen
the accepted FR, NFR or acceptance criteria without a new product decision.

## Unresolved Blockers

None at product level.
