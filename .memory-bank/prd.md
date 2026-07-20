---
description: Product Requirements Document.
status: draft
type: prd
clarification_status: complete
constitution_checked: true
---
# PRD

## Source Inputs

### Primary and governing sources

- [.memory-bank/analysis/product-brief.md](analysis/product-brief.md): current
  Product Brief and scope contract for the one-СПА pilot.
- [.memory-bank/constitution.md](constitution.md): top governing policy;
  Constitution gate passed for this draft, and no amendment candidate was
  found.
- [.memory-bank/invariants.md](invariants.md): current cross-cutting priority for
  measurable Promo/QR latency and stability.

### Supporting discovery and decision records

- [.memory-bank/analysis/brainstorming/BR-001.md](analysis/brainstorming/BR-001.md):
  initial broad product exploration; directions superseded by BR-002 and the
  Product Brief are not pilot requirements.
- [.memory-bank/analysis/brainstorming/BR-002.md](analysis/brainstorming/BR-002.md):
  user-confirmed pilot slice, automatic Promo/QR flow and acceptance baseline.
- [.memory-bank/analysis/brainstorming/BR-003.md](analysis/brainstorming/BR-003.md):
  user-confirmed developer diagnostics, logging, annotation and calibration
  decisions.
- [IDEA_APP.md](../IDEA_APP.md): application behavior, current best-effort
  search algorithm, data concepts and accepted KISS architecture boundaries.
- [IDEA_INGEST.md](../IDEA_INGEST.md): authoritative pilot batch-ingest and
  `ingest_to_searchable` semantics.
- [IDEA_OS.md](../IDEA_OS.md): server, display, security and deployment
  boundaries; recommendations explicitly marked there are not pilot gates.
- [IDEA_DEBUG.md](../IDEA_DEBUG.md): concise normative input for the first
  developer diagnostics version.

### Readiness and verification context

- [.memory-bank/spec-backbone.md](spec-backbone.md): pre-PRD framing and
  decomposition handoff; global architecture readiness remains pending
  `/spec-design`.
- [.memory-bank/spec-index.md](spec-index.md): registry of current and planned
  canonical specs.
- [.memory-bank/contracts/boundary-map.md](contracts/boundary-map.md): existing
  draft boundary router; concrete boundaries remain for later SDD work.
- [.memory-bank/testing/index.md](testing/index.md): baseline quality gates and
  critical-flow e2e guidance.

### Source precedence used in this draft

The Constitution governs all decisions. The current Product Brief defines the
pilot scope. Explicitly selected directions in BR-002 and BR-003 refine that
scope. `IDEA_*` documents supply accepted behavior and constraints where they do
not conflict with the Product Brief. Historical ideas, post-pilot candidates and
items explicitly labelled as recommendations are not converted into pilot
acceptance gates.

## Clarifications

- Clarification status is complete for the one-СПА pilot. The resolved scope,
  actors, behavior, data semantics, non-goals, and acceptance contract are
  expressed in the normative PRD sections below.
- Remaining site/hardware selection and post-pilot commercial questions do not
  change current actors, core scenarios, feature boundaries, or acceptance and
  must not be converted into pilot requirements without a new product decision.
- Source precedence and superseded `IDEA_*` defaults are recorded in
  [.memory-bank/spec-backbone.md](spec-backbone.md) for decomposition and later
  SDD work.

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
inside the existing backend: correlated attempts, browser/server log search,
manual per-person/per-detection annotation and explainable recommendations for
face-match threshold and individual input quality gates.

## Goals

1. Validate an automatic `ingest -> searchable -> capture -> Promo -> QR ->
   phone continuation` path without participant action before QR scanning.
2. Make at least 95% of accepted JPEGs from confirmed pilot batches searchable
   in under 15 minutes from `batch.confirmed_at`.
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
  photographer's cloud account, Telegram ingest or EXIF-based automatic batch
  splitting.
- Watermarks on Promo or phone previews.
- Guarantee that every unique person in a group receives a detection slot or is
  represented in the result.
- Tracking or identity deduplication across reference frames, automatic identity
  clustering or cross-pipeline person linking.
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

## Users / Actors

### Pilot participant

- Is a known tester participating in controlled pilot attempts.
- Walks through the capture zone at a distance of 3-5 metres without pressing a
  button or otherwise initiating capture.
- Sees four teaser photographs and scans QR to continue the same session on a
  phone without a selfie.

### Photographer

- Authenticates in the web application.
- Creates and confirms JPEG batches immediately after a completed shooting
  series.
- Selects the СПА and authoritative `visit_date`, reviews accepted/rejected
  files and observes processing/searchable status for their own batches; the
  photographer has no diagnostic-page access.

### Face Moment / СПА operator

- Observes batch readiness, failures and Promo operation.
- Explicitly sets the active working `visit_date` for the pilot СПА in the
  server-side application before automatic attempts use that date for search.
- May open a sanitized attempt summary containing outcome, stage timeline,
  latency and issue tags, but cannot access reference images/crops, participant
  names, manual annotations, detailed logs or Calibration.

### Application developer

- Investigates individual attempts and correlated browser/server logs.
- Has full authorized access to protected diagnostic artifacts, real names in
  annotations, detailed Log Explorer records and Calibration.
- Adds ground-truth annotations, compares releases/configurations and examines
  group-search decisions.
- Receives explainable threshold and quality-gate recommendations and applies
  any accepted serving-setting change manually.

### System actors

- `SpaPromoClient`: local or remote display/capture client bound to one СПА by a
  client token.
- Passage sensor and camera: trigger and capture the reference series.
- Backend, `BackgroundPhotoWorker` and `RealtimeFaceService`: ingest/control,
  background photo processing and synchronous realtime search responsibilities.

The economic buyer of the post-pilot product is still a hypothesis and is not a
pilot actor or blocker.

## Functional Requirements

### A. Photographer ingest and searchable inventory

- **FR-ING-01** — The pilot MUST accept commercial photographs only through an
  authenticated direct web uploader over HTTPS and only as ready JPEG files.
- **FR-ING-02** — The photographer MUST create a batch for one СПА and one
  authoritative working `visit_date`; multiple batches on the same day are
  allowed.
- **FR-ING-03** — Before confirmation, the server MUST validate format and image
  decoding, calculate a checksum and show accepted and rejected files.
- **FR-ING-04** — Confirmation MUST freeze the batch manifest and
  `confirmed_at`; EXIF time, filename and upload time may support sorting,
  diagnostics and warnings but MUST NOT silently replace the confirmed
  `visit_date`.
- **FR-ING-05** — JPEG uniqueness MUST be enforced by
  `(spa_id, visit_date, checksum_sha256)` across all batches. When the same file
  is uploaded again for the same СПА and `visit_date`, the second uploaded copy
  MUST be deleted, classified visibly as a duplicate and otherwise ignored: it
  MUST NOT enter the confirmed manifest population or create a new `photo_id`,
  object, processing job, searchable result, teaser candidate or contribution
  to `N`.
- **FR-ING-06** — Accepted originals MUST be stored in private object storage;
  photo records and serving-pipeline processing jobs MUST be created
  idempotently.
- **FR-ING-07** — The uploader MUST expose explicit file/batch states covering
  `pending`, `processing`, `searchable`, `no_faces` and `failed`; `searchable`
  corresponds to `photo_pipeline_states.status = ready` for the serving
  pipeline revision.
- **FR-ING-08** — `ingest_to_searchable` MUST use all unique accepted JPEGs in
  confirmed pilot manifests as its population. Files still `pending`,
  `processing`, `failed` or `no_faces` after 15 minutes remain SLO breaches;
  pre-confirmation rejects, checksum duplicates and non-serving jobs are
  excluded. Photographer delay before confirmation is measured separately.

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
- **FR-CAP-03** — The system MUST select at most five highest-quality face
  detections from the reference series. Each selected detection is searched
  independently; embeddings from different detections MUST NOT be merged.
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

### D. Promo display and QR continuation

- **FR-UX-01** — Between attempts, the display MUST show locally available
  advertising. Capture/search MAY use a non-personal prePromo state; it MUST NOT
  expose a partial or stale participant result.
- **FR-UX-02** — A successful Promo MUST show exactly four low-quality teaser
  photographs without watermark and a high-contrast, fully visible, scannable
  QR code on the 43-inch landscape, 16:9, logical 1920x1080 baseline.
- **FR-UX-03** — The QR MUST continue the same short-lived session on the phone
  without another selfie or participant login step implied by the current
  immediate-continuation flow.
- **FR-UX-04** — The phone landing MUST show the same session's СПА,
  `visit_date`, one of the four low-quality teasers, `N`, and an active
  `Перейти к покупке` button.
- **FR-UX-05** — The Promo display MUST use the truthful copy `Ваши фотографии
  найдены — откройте по QR-коду`. On the valid phone landing, `Перейти к
  покупке` MUST navigate to the existing or separately delivered main Face
  Moment selfie-search/purchase page. This pilot owns the navigation link but
  does not implement or accept the target purchase flow.
- **FR-UX-06** — Display duration, successful-capture cooldown, QR-session TTL
  and browser idle TTL MUST be independent settings. QR first-open TTL MUST be
  30 minutes from `qr_issued_at`; after a successful first open, the browser
  session MUST expire after 60 minutes without activity.
- **FR-UX-07** — After result-display duration expires, the screen MUST return
  to advertising without implicitly invalidating an otherwise active QR
  session.
- **FR-UX-08** — If fewer than four valid unique teasers are produced, or a
  camera/sensor/network/processing failure prevents success, the client MUST
  return to local advertising, omit the final Promo/Chime, create a diagnostic
  event and allow a fresh capture without starting the success cooldown.
- **FR-UX-09** — On timeout or network error, the client MUST discard the stale
  request and retry only with a fresh reference capture.
- **FR-UX-10** — When the QR first-open or browser idle TTL expires, only the
  personalized Promo session becomes unavailable; the browser page MUST remain
  functional and redirect to the main Face Moment page, where the visitor is
  offered photo search and purchase through selfie upload. The redirect MUST
  NOT expose the expired session's teaser, `N` or other personal result data.
  The main selfie-search/purchase page is an existing or separately delivered
  dependency; implementing or accepting that target is outside this pilot.

### E. Attempts and diagnostic bundles

- **FR-DIAG-01** — Every accepted capture/search attempt, including unsuccessful
  outcomes, MUST have one `diagnostic_session_id/correlation_id` connecting its
  browser events, server processing, configuration, face-search decisions and
  artifacts.
- **FR-DIAG-02** — The attempt timeline MUST expose capture/reference readiness,
  request/network, queue wait, inference, vector search, response, browser
  receipt, Promo render and full QR visibility so a `>=10 s` outcome can be
  localized to a stage.
- **FR-DIAG-03** — Attempt detail MUST show release, serving pipeline revision,
  applied threshold and quality values, selected detections, repeated
  detections, candidate pools, selected teasers, `N`, outcome/status and issue
  tags.
- **FR-DIAG-04** — The diagnostic bundle MUST link the source reference series,
  normalized images, selected crops, camera/config metadata, detections,
  candidates, thresholds, selected IDs, timestamps, actually displayed Promo
  screenshot and QR continuation event. A product flow that actually captures a
  selfie MUST also retain that selfie as a diagnostic artifact; the current
  pilot has no selfie capture and therefore creates no selfie artifact.
- **FR-DIAG-05** — Diagnostic images MUST be stored as protected artifacts, not
  embedded in log records. An attempt MUST expose a redacted reproducibility
  manifest with versions, parameters, timestamps and authorized artifact links;
  an automatic replay runner is not required.
- **FR-DIAG-06** — The `Attempts` page MUST support filtering by time, status,
  release, pipeline, latency and issue tags, opening a unified browser/server
  timeline and navigating to relevant logs/artifacts.
- **FR-DIAG-07** — The operator view of an attempt MUST be sanitized to outcome,
  stage timeline, latency and issue tags. Navigation to protected images/crops,
  participant names, manual annotations, detailed logs and Calibration MUST be
  available only to the authorized developer role.

### F. Manual annotation, logs and calibration

- **FR-DEV-01** — An authorized developer MUST be able to annotate ground truth
  at person/detection level, associate a real pilot-participant name and record
  `correct`, `wrong/false` or `missed` outcomes. Exact normalized storage
  vocabulary is deferred to SDD, but its semantics MUST support the stated
  calculations.
- **FR-DEV-02** — Developer-only `Log Explorer` MUST search structured
  browser/server logs by time, source, component, severity, release, message and
  correlation fields, and MUST navigate from a record to its related attempt.
- **FR-DEV-03** — Log search MUST operate through the existing backend and
  PostgreSQL. The browser MUST NOT access PostgreSQL directly.
- **FR-DEV-04** — Browser/server logging MUST be non-blocking for capture,
  search, Promo and QR. Log records MUST NOT contain images, embeddings,
  authentication headers, cookies, tokens, request bodies or session replay.
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

## Non-functional Requirements

### Performance and acceptance priority

- **NFR-PERF-01** — At least 19 of 20 controlled attempts MUST produce a fully
  visible and scannable QR with
  `qr_fully_visible_at - reference_series_ready_at < 10_000 ms`.
- **NFR-PERF-02** — Timeout or no-match without a completed QR is a failed
  attempt, not an excluded observation.
- **NFR-PERF-03** — At least 95% of the metric population defined by FR-ING-08
  MUST become searchable in `<15 min` from `batch.confirmed_at`.
- **NFR-PERF-04** — The system MUST retain stage timestamps sufficient for
  `reference_ready_to_qr`, trigger-to-preview, realtime queue wait and
  ingest-to-searchable diagnosis. Additional percentile cuts are optional until
  justified.
- **NFR-PERF-05** — At least 19 of the same 20 controlled attempts MUST satisfy
  both the latency/QR gate and the full-session correctness gate. A foreign
  teaser or any unrelated `photo_id` included in `N` makes that attempt fail the
  correctness gate, without turning missed group-member coverage into a failure.

### Reliability and operations

- **NFR-REL-01** — The central backend/runtime MUST start and operate
  independently of the local KDE/Chromium display session.
- **NFR-REL-02** — Chromium/display MUST recover automatically after browser or
  network failure and continue local advertising while the server is
  unavailable.
- **NFR-REL-03** — Realtime processing MUST use a bounded, short-lived in-memory
  queue/deadline model; stale reference work is not durable and MUST NOT be
  replayed after restart.
- **NFR-REL-04** — Background processing MUST be idempotent under at-least-once
  execution without duplicate final face records.
- **NFR-REL-05** — Free primary/backup space and diagnostic-retention cleanup
  MUST be observable; a recovery procedure is required for the single-server
  pilot.

### Security, privacy and retention

- **NFR-SEC-01** — The public boundary MUST use HTTPS. PostgreSQL, MinIO,
  internal service ports and Docker API MUST NOT be publicly exposed.
- **NFR-SEC-02** — Each `SpaPromoClient` MUST use a secret token in an
  authorization header. The server MUST derive `spa_id` from a stored token hash
  and MUST NOT trust `spa_id` from the request body or log the token.
- **NFR-SEC-03** — Public requests MUST be rate-limited. SSH MUST be key-only,
  and the display browser MUST run sandboxed under a non-privileged OS user.
- **NFR-SEC-04** — Application authorization MUST enforce a split diagnostic
  access matrix: the operator may read only sanitized attempt outcome/timeline/
  latency/issue tags; the developer may access protected reference images/crops,
  names, annotations, detailed logs and Calibration. The photographer is limited
  to their own batch/upload state and has no diagnostic-page access.
- **NFR-DATA-01** — Technical browser/server logs MUST expire after 30 days.
- **NFR-DATA-02** — Attempts and ordinary diagnostic bundles/artifacts MUST
  expire after 90 days and MUST NOT enter long-lived backup.
- **NFR-DATA-03** — A manually promoted calibration case MAY be retained until
  explicit deletion, but only as a curated reproducible subset: selected source
  reference frames, required face crops or a selfie when one was actually
  captured, versioned parameters/configuration, quality and match scores,
  ground-truth annotations and the entered participant name. The rest of the
  raw reference series and the Promo screenshot MUST expire with the ordinary
  90-day bundle; technical logs MUST still expire after 30 days.
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
- **NFR-ARCH-05** — Commercial originals and PostgreSQL MUST have a backup on a
  different physical medium or server; MinIO on the same disk is not a backup.

## Data / Domain Model

### Core concepts

- **СПА** — pilot venue with a name, timezone, operator-selected active working
  `visit_date`, active serving pipeline and calibrated reference threshold.
- **Batch** — photographer-confirmed immutable manifest of commercial JPEGs for
  one СПА and authoritative `visit_date`; it is distinct from a reference
  series.
- **Photo** — commercial image linked to its batch/СПА/date and private original,
  preview and thumbnail objects; `(spa_id, visit_date, checksum_sha256)` is its
  logical ingest-uniqueness key, while pHash supports teaser diversity only.
- **Pipeline revision** — immutable identity of detector, recognizer, weights,
  preprocessing/alignment, normalization and embedding dimension.
- **Photo pipeline state** — pipeline-specific `pending | processing | ready |
  no_faces | failed` state; `ready` is the searchable state.
- **Photo face** — one face detected by one pipeline revision in one photo.
  Different pipelines create independent records and no shared person identity.
- **Reference series** — sensor-triggered set of frames from the client ring
  buffer used to select up to five independent query detections.
- **Selected detection** — one quality-ranked face occurrence used for a search;
  it is not proof of a unique physical person.
- **Promo/search session** — short-lived context binding СПА, authoritative
  `visit_date`, four teaser IDs, `session_result_photo_ids`, `N`, QR token and
  expiry state. The QR may be opened for the first time within 30 minutes of
  `qr_issued_at`; an opened browser session expires after 60 minutes without
  activity.
- **Attempt** — one correlated automatic capture/search/display execution,
  including unsuccessful outcomes and stage timestamps.
- **Diagnostic bundle** — protected image artifacts plus a versioned manifest,
  indexed events, decisions, configuration and display evidence for an attempt.
- **Structured log record** — non-image browser/server event associated with a
  correlation ID where applicable.
- **Annotation** — authorized ground truth associating a participant/person and
  detection/result outcome.
- **Calibration case/recommendation** — a manually curated reproducible subset
  of selected source frames/crops or an actually captured selfie, parameters,
  scores and annotations retained until explicit deletion, plus a computed
  threshold or one-dimensional quality-gate proposal; it never changes serving
  settings automatically.

### Authoritative relationships and lifecycle

- Confirmed batch `visit_date` is authoritative for commercial-photo search
  scope; EXIF `captured_at` is secondary metadata.
- An automatic attempt uses the server-side active working `visit_date` selected
  by the operator for its СПА; the client token selects the СПА but neither the
  client clock nor the latest batch silently selects the date.
- A photo is searchable only through a `ready` state for the current compatible
  serving pipeline revision.
- Four teaser IDs are a subset of `session_result_photo_ids`; `N` is the count of
  the entire unique union.
- Attempt/log/bundle identifiers must allow navigation without placing image or
  secret payloads in logs.
- Technical logs, normal attempt/bundle data and promoted calibration data have
  distinct retention rules defined by NFR-DATA-01..03.
- Promoting a calibration case does not extend the lifetime of the entire
  diagnostic bundle: only the curated subset named by NFR-DATA-03 survives the
  ordinary 90-day deletion.
- A selfie is a conditional diagnostic artifact: it is stored when a product
  flow actually captures one. The current pilot captures only the automatic
  reference series and selected face crops, so no separate selfie exists or is
  stored in this scope.

## UX / Interaction Flow

### Photographer flow

1. Authenticate and create a batch.
2. Select the СПА and confirm authoritative `visit_date`.
3. Upload ready JPEGs over HTTPS.
4. Review accepted/rejected files and warnings.
5. Confirm the immutable manifest.
6. Observe processing/searchable/no-face/failure states and correct failures.

### Participant Promo and continuation flow

1. The display shows local advertising while the camera stream/ring buffer is
   active.
2. Passage sensor triggers a reference series without participant action.
3. The client captures and searches while preventing overlapping attempts.
4. The service processes up to five detections and either forms four unique
   valid teasers or returns a non-success outcome.
5. On success, the display presents four no-watermark teasers and a scannable QR
   within the performance budget.
6. The participant scans QR and immediately opens the same session on a phone,
   seeing СПА, date, one teaser, `N` and a `Перейти к покупке` button that links
   to the separately delivered main selfie-search/purchase page.
7. The display returns to advertising after its independent display duration;
   the QR session remains usable until its own expiry.
8. If the QR is opened after 30 minutes, or an opened browser session has been
   idle for 60 minutes, the personalized result expires and the browser redirects
   to the main Face Moment page offering photo search and purchase through selfie
   upload, without carrying personal result data from the expired session.

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

- Passage sensor, camera/video stream and 43-inch display; exact models remain a
  site-validation decision.
- Chromium-based `SpaPromoClient`, running locally over HDMI or on a remote
  display computer after site selection; both use the same logical contract.
- Existing backend/admin web application.
- PostgreSQL with pgvector for metadata, state, exact vector search, structured
  logs and indexed diagnostic events.
- MinIO/S3-compatible private object storage for originals, previews and
  diagnostic images.
- SFace/YuNet and Buffalo M/SCRFD pipelines with native preprocessing.
- QR generation performed locally in the client without an external QR service;
  the specific package is an implementation recommendation, not a product gate.
- HTTPS as the public integration boundary.
- Existing or separately delivered main Face Moment selfie-search/purchase page
  as the expired-session redirect target; this pilot does not implement it.

Explicitly absent from the pilot are Yandex Disk, external face-recognition APIs,
payment/fiscal providers, external observability stores and message brokers.

## Edge Cases / Failure Handling

- Invalid, unsupported or undecodable files are rejected before batch
  confirmation and shown explicitly.
- Mixed EXIF dates produce a warning but do not rewrite authoritative
  `visit_date` or auto-split the batch.
- A duplicate JPEG in any later batch for the same СПА and `visit_date` is
  deleted after checksum detection, reported as a duplicate and excluded from
  the accepted manifest, metric population, processing, search, teaser and `N`.
- A missing active working `visit_date` prevents search and produces diagnostic
  evidence rather than falling back to a client clock or arbitrary batch date.
- `no_faces` is a distinct terminal processing state but breaches the 15-minute
  searchable SLO for its accepted JPEG population.
- Sensor events arriving during capture/search or successful cooldown are
  ignored according to client state.
- Multiple detections of one person are allowed and must be visible in
  diagnostics; missing another group member is not itself a group-coverage
  contract breach.
- Fewer than four unique valid teasers, low-quality query faces, no-match,
  timeout, camera/sensor/network/processing failure or stale response must not
  show a partial/stale Promo and must produce diagnostic evidence.
- Missing optional audio/animation assets must have a silent/non-blocking
  fallback and must not prevent a valid QR result.
- Logging/diagnostic ingestion failure must not block the critical capture,
  search, Promo or QR path; evidence gaps must remain observable.
- A QR first opened more than 30 minutes after `qr_issued_at`, or a browser
  session idle for 60 minutes, invalidates the personalized result and redirects
  to the main selfie-based search/purchase page. No teaser, `N` or other data
  from the expired session is disclosed to the redirect target.
- Diagnostic retention expiry must remove ordinary protected artifacts after 90
  days. For a promoted calibration case it preserves only the curated subset in
  NFR-DATA-03; unselected frames and the Promo screenshot are still deleted.
- Full primary storage, process/browser crash and central-server unavailability
  require observable degraded advertising behavior and documented recovery.

## Acceptance Criteria

### Controlled pilot setup

- One selected СПА, one configured `SpaPromoClient`, the 43-inch/16:9/1920x1080
  baseline and validated camera/sensor/lighting geometry at 3-5 metres.
- A selected serving pipeline is pre-warmed; its reference threshold and input
  quality gates are calibrated before the run.
- The operator has explicitly set the active working `visit_date`, and it
  matches the confirmed commercial-photo batches intended for the run.
- Every tester expected in a run has at least four searchable commercial
  photographs in the authoritative СПА/date scope.
- The 20-attempt set includes the current best-effort group flow; exact attempt
  composition may be fixed in the verification plan without promising full
  group-member coverage.

### Product and performance outcomes

- **AC-01** — At least 19 of 20 controlled attempts produce four unique teasers
  and a fully visible, scannable QR in `<10_000 ms` from
  `reference_series_ready_at`.
- **AC-02** — No-match or timeout without a completed QR counts as a failed
  attempt.
- **AC-03** — In at least 19 of the same 20 controlled attempts, all four teasers
  and every unique `photo_id` in `session_result_photo_ids` are manually
  confirmed as containing at least one pilot participant represented by a
  processed selected detection. Any unrelated included photograph fails that
  attempt; failure to cover every unique person in a group does not.
- **AC-04** — Every completed phone continuation shows the correct СПА,
  authoritative `visit_date`, a teaser belonging to that same session and the
  same session's `N`; its `Перейти к покупке` button navigates to the configured
  main selfie-search/purchase page.
- **AC-05** — Every attempt, including the allowed failure, has a correlated
  diagnostic bundle and stage timestamps.
- **AC-06** — At least 95% of unique accepted JPEGs in confirmed pilot manifests
  become searchable in `<15 min` from `batch.confirmed_at`, using the full
  denominator/failure semantics of FR-ING-08.
- **AC-07** — A QR is programmatically decodable and successfully scannable on
  representative real phones from the target screen/distance/brightness setup.

### Functional completion signals

- **AC-08** — A photographer can authenticate, upload/validate/confirm a JPEG
  batch and observe each accepted photo reach an explicit final/current state.
- **AC-09** — An operator can find a failed or slow attempt and see only its
  sanitized outcome, timeline, latency and issue tags; protected artifacts,
  names, annotations, detailed logs and Calibration are inaccessible to that
  role.
- **AC-10** — An authorized developer can trace the same attempt's versions,
  parameters, group/search decisions, protected artifacts and detailed logs by
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
  deletion.
- **AC-14** — Network/search failure leaves the display on local advertising,
  discards stale work and permits a fresh attempt without a success cooldown.
- **AC-15** — Before the 30-minute first-open deadline the QR opens its matching
  session; after that deadline, and after 60 minutes of browser inactivity, the
  personalized result is inaccessible and the browser redirects to the main
  selfie-based search/purchase page without leaking expired-session data. The
  pilot verifies the redirect contract, not the target page's implementation.
- **AC-16** — The Promo display says `Ваши фотографии найдены — откройте по
  QR-коду` and does not claim that download is already available in the pilot.
- **AC-17** — Re-uploading a JPEG with the same SHA-256 in another batch for the
  same СПА and `visit_date` deletes the second copy, reports it as a duplicate
  and leaves the accepted manifest population, `photo_id` set, jobs, search
  results, teaser selection and `N` unchanged.

The smoke run validates the pilot path only. It does not demonstrate public
production readiness, target 10-15-СПА capacity or complete group coverage.

## Verification Strategy

1. **Static and unit verification**
   - configured build/typecheck and relevant unit tests;
   - batch manifest/checksum/idempotency, same-СПА/date cross-batch duplicate
     deletion and metric-population rules;
   - pipeline-revision isolation, threshold gates, pHash-only ranking and `N`
     union/deduplication;
   - attempt timing calculations, recommendation metrics and retention rules;
   - secret/redaction checks for structured logs.
2. **Integration verification**
   - uploader -> object storage -> background processing -> searchable state;
   - sensor/client -> synchronous realtime service -> exact scoped search -> QR
     session;
   - browser/server correlation -> Attempts/Log Explorer -> protected artifact;
   - annotation -> Calibration calculations -> manual-only application boundary.
3. **Critical-flow e2e verification**
   - authenticated photographer journey;
   - successful automatic single-person and best-effort group Promo journeys;
   - phone continuation without selfie and valid-session purchase-button
     navigation to the separately delivered target page;
   - `<4` results, low quality, timeout, network loss, stale response, QR
     first-open expiry and browser idle expiry;
   - developer investigation, annotation and calibration journeys.
4. **Physical-site verification**
   - target distance, face size, motion blur, pose, lighting and exposure;
   - actual 43-inch display layout, QR quiet zone/contrast and real-phone scans;
   - browser/display recovery and local-advertising degraded mode.
5. **Controlled acceptance run**
   - execute 20 instrumented attempts under the agreed setup;
   - retain the per-attempt outcome, `reference_ready_to_qr_ms`, phone-context
     consistency, ground-truth validation of all four teasers and every unique
     `photo_id` in `N`, and diagnostic evidence;
   - evaluate AC-01..07 without silently removing no-match/timeout failures.

Evidence such as screenshots, traces, logs and videos belongs in task artifacts;
the Memory Bank should retain links and conclusions rather than binary evidence.
