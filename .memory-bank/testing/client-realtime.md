---
description: Canonical verification contract for client proposal submission, one-clock Promo latency and related diagnostics.
status: active
last_updated: 2026-08-13
source_of_truth:
  - .memory-bank/testing/client-realtime.md
---
# Client Realtime Verification

## Contract Inputs

- [Sensor Passage API](../contracts/sensor-passage-api.md): exact long-poll,
  versioned event, CORS/authentication and timeout behavior.
- [Realtime Attempt API](../contracts/realtime-attempt-api.md): exact endpoint,
  multipart serialization, validation, idempotency and typed outcomes.
- [Display Client Access](../domains/display-client-access.md): central token
  persistence, СПА derivation, reset/deactivation and redaction.
- [Promo Attempt](../domains/promo-attempt.md): core Attempt persistence and
  state/outcome mapping.
- [QR Continuation API](../contracts/qr-continuation-api.md): exact ticket
  exchange, shared browser access, protected phone reads and expiry redirects.
- [Display and central restart recovery](../runbooks/display-and-central-restart.md):
  operator procedure, limits and success checks.

## Required Proof

- A reference-series fixture containing more than 20 occurrences proves
  earliest-to-latest frame traversal, preserved BlazeFace output order within
  a frame, immediate stop at occurrence 20 and submission of exactly those
  first 20. Repeated occurrences of one person remain valid; the outbound path
  performs no ranking, top-5 selection, authoritative quality gate, tracking,
  clustering or deduplication.
- A zero-occurrence fixture proves a metadata-only request with the same
  correlation and client timings. If admitted, it creates the core Attempt and
  a typed non-success without requiring a particular machine outcome name.
- Crop fixtures prove centered-square `1.2 × max(width, height)` geometry,
  source-frame clipping, no alignment/landmark normalization/upscale, and
  proportional downscale to a maximum 512-pixel side before ordinary sRGB JPEG
  encoding without EXIF/source metadata.
- Configuration UI proof covers exactly `0.7`, `0.75`, `0.8`, `0.85`, `0.9`,
  `0.95`, default `0.85`, kiosk-profile `localStorage`, next-Attempt
  application and manifest recording.
- Multipart fixtures prove one synchronous request, one versioned manifest and
  one JPEG part per occurrence, with the exact FR-CAP-17 allowed identity,
  timing, camera and occurrence fields and all explicit omissions. Zero
  occurrences use the same endpoint with the manifest only.
- Structural-bound proof covers at most 20 occurrence parts and at most
  512-pixel crop side. A transport-boundary fixture proves that a total request
  body larger than `20 MiB` returns HTTP `413` without core Attempt admission.
  Verification must not invent separate aggregate-pixel, per-JPEG-byte or
  manifest-size caps, an oversize domain outcome or client-side truncation.
- Browser integration proves central HTTPS loading, managed
  `LocalNetworkAccessAllowedForUrls`, exact-origin ESP32 CORS, Authorization
  OPTIONS handling, Bearer redaction and continuous one-request-at-a-time
  10-second HTTP long-polling to the fixed mDNS `.local` name.
- Detector delivery proof covers BlazeFace Full-range in its browser runtime
  with a separate release-versioned model asset and no TensorFlow.js, second ML
  runtime, parallel YuNet implementation or generic detector abstraction.
- Camera proof shows that input above the site-configured maximum is downscaled
  before ring-buffer/detector work without turning the exact site value into a
  design/tasking gate.
- The controlled 20-attempt run measures
  `qr_fully_visible_elapsed_ms - reference_series_ready_elapsed_ms` on one
  client monotonic clock. The interval includes local detection, crop
  extraction/encoding, request upload, server processing, response receipt and
  Promo/QR render.
- The diagnostic UI shows client-local ready-series processing start,
  request-send start and response receipt for a correlated admitted Attempt.
- Retention proof applies 30 days to technical logs, 90 days to ordinary
  Attempts/evidence including persisted capture-derived media, and preserves
  only the curated promoted subset until explicit deletion.

## Client State And Recovery Proof

- Physical and test triggers enter the same trigger-acceptance path, retain
  distinguishable source metadata, ignore overlap and use a fresh reference
  series after every failure. Late response, timeout and reconnect fixtures
  prove that stale work cannot replace the current advertising/result state.
- Camera list, preview, explicit selection, disconnect/reconnect/port-change
  and oversized-input fixtures prove recoverable reselection, no arbitrary
  substitution and downscale before ring-buffer/detector work.
- Named camera, sensor, model, optional-asset and central-service failures keep
  the loaded client on usable advertising. The server-communication notice is
  timed for 5–10 seconds and a newer notice may replace it immediately.
- Central roles are started and exercised without KDE, Chromium or the
  `display` login. Browser termination in advertising and active/result states
  proves user-service restart, reachable-origin reload, advertising and discard
  of prior personalized client state.
- An authorized operator follows only the linked recovery runbook from browser
  failure and intact-volume central restart and retains the named checks as
  evidence. The proof must not claim offline reload or recovery after sole-
  primary loss.

## Reference Search And Joint Correctness Proof

- Realtime startup with deterministic read-only model fixtures proves that only
  the committed selected validated revision is loaded and warmed. Missing,
  identity/hash-mismatched or other-pipeline assets keep readiness closed before
  Attempt admission, inference or processing-state mutation; no download or
  fallback occurs, and a serving-revision change takes effect only after the
  operator restart.
- Mixed revision, СПА, date, active/soft-deleted Photo, processing state and
  confirmed/unconfirmed time-window fixtures prove the exact scope before
  cosine comparison. Ordered/tied/repeated-person/low-quality crops prove
  server-authoritative at-most-five selection, independent native queries and
  every forbidden clustering/margin/cross-pipeline path.
- Candidate-pool fixtures retain each selected detection, every threshold-valid
  Photo match, pHash ranking decision, reserved Photo, four teaser IDs and the
  complete unique `session_result_photo_ids` union. The artifact reconciles
  `N` to the union and distinguishes weak-match, repeated-Photo, partial-ready
  inventory and fewer-than-four outcomes.
- The FT-004 implementation task runs a controlled 20-attempt corpus with
  stable attempt IDs and manually reviewed participant/detection ground truth.
  It retains a correctness row for all four teasers and every union member in
  each attempt; missing group-member coverage alone remains a pass.
- The final joint `19/20` feature verdict joins those same attempt IDs with the
  physical one-clock fully-visible/scannable QR evidence owned by FT-005. The
  FT-004 task may close after its server-owned correctness implementation and
  evidence pass, but FT-004 feature completion MUST NOT claim the joint verdict
  until that cross-feature evidence exists. This avoids a task dependency cycle
  without weakening the accepted shared-attempt criterion.
- A concurrency fixture holds the one inference slot, proves an admitted
  second Attempt returns `busy` before release with no waiter/inference call,
  and proves only a fresh later request can acquire the slot. Deadline and
  restart fixtures prove no late session, `accepted|searching -> interrupted`,
  no replay and fresh post-restart acquisition.
- Active-date/security fixtures prove the operator-only setting boundary,
  missing-date `503` with no admission/search, display-token-derived СПА,
  client override rejection, rate limiting, private topology and complete token
  redaction.

## Promo Presentation And Display Outcome Proof

- The server display-boundary proof covers display-token authentication,
  principal scope, rate limiting, redaction, private topology, configuration,
  authorized teaser media, acknowledgement and display-state integration
  defined by the [Promo Display API](../contracts/promo-display-api.md).
- Migration/repository proof fixes one positive result-display expiry for every
  newly issued result and records confirmed/failed receipt plus the client
  monotonic QR-visible offset. Duplicate same-status acknowledgement is
  idempotent; conflict and late acknowledgement change nothing; pending expiry
  derives terminal `unconfirmed` without scheduler or outbox. Every branch
  proves that session/ticket/first-open expiry/teasers/union/`N` remain unchanged.
- Display-media proof uses only the authenticated same-origin proxy, returns
  `no-store` low-quality no-watermark JPEGs for the four issued teasers and
  rejects unknown, foreign or hard-purged references without raw MinIO keys,
  presigned participant URLs, replacement selection or partial Promo.
- Client integration proof covers camera/stale/fresh retry, advertising and
  communication-notice behavior, managed restart, typed result/non-success,
  server-correctness rows, the display boundary, result-aware rendering, local
  QR, post-render acknowledgement, independent display/cooldown timers and
  optional-asset/non-success integration.
- Complete and malformed/incomplete result fixtures at the logical 1920x1080
  target prove exactly four unique decoded teasers, exact truthful copy, a
  fully visible high-contrast locally generated QR and no partial/stale Promo.
  Missing optional audio/animation is silent and does not block a valid result.
- A confirmed report is emitted only after all four JPEGs decode and the QR is
  fully visible. Render failure may report `failed`; duplicate, late, lost and
  conflicting report fixtures retain the server-authoritative terminal result
  while the client returns safely to advertising.
- Result-display and success-cooldown clocks use the two independent positive
  configuration values. Display expiry returns to advertising and emits no
  session invalidation; failure starts no success cooldown. The display-expiry
  evidence row is joinable to FT-006 continuation evidence, which owns the
  actual phone read and final independent-session-lifetime verdict.
- The controlled 20-attempt run reuses the stable FT-004 `attempt_id` set. An
  authorized pilot evaluator records, for every attempt, the server-correctness
  row, one-clock `qr_fully_visible_elapsed_ms`, `<10_000 ms` comparison,
  complete target-screen render, programmatic QR decode and representative-real-
  phone scan. The final joint result requires at least 19 of the same 20 rows
  to pass every conjunct; timeout/no-match rows remain failures.

## Phone Continuation And Expiry Proof

- FT-006 continuation proof treats independently accepted session/ticket
  issuance, immutable session truth, authorized no-store media, QR rendering
  and display expiry as prerequisites. Its own proof covers ticket exchange,
  shared browser fields, phone session/media/activity paths, local expiry
  handling and post-display phone-read integration.
- A controlled server clock and concurrent browser fixtures prove first open
  strictly before the 30-minute boundary, safe redirect at the exact/late
  boundary, repeated scans from multiple phones, one shared state row, atomic
  first/last timestamps and one 60-minute idle deadline. Explicit activity on
  either phone advances that deadline for both; passive session polling,
  media/asset requests and timers do not. Exact idle expiry is irreversible and
  survives a database restart without a scheduler or per-device grant.
- Same-session fixtures compare issued and phone `session_id`, СПА,
  authoritative `visit_date`, first available ordered teaser and historical
  `N`. Soft deletion keeps the issued media readable. Each combination of one,
  several and all hard-purged teaser objects proves ordered skip or `null`
  without union replacement, session rebuild, invalidation or `N`
  recalculation.
- Expiry fixtures independently vary result-display duration, success cooldown,
  QR first-open and browser idle clocks. The phone clears rendered personalized
  state and redirects with no teaser, `N`, session/ticket query or referrer
  data; later HTML/API/media/activity reads cannot revive or disclose it.
- Public-boundary fixtures prove the exact QR query is omitted from logs, the
  shared cookie has the required attributes, forged/foreign/late tickets and
  cookies remain non-disclosing, all personalized responses are `no-store` and
  `no-referrer`, rate limiting returns `429`, the purchase target cannot be
  request-overridden and PostgreSQL/MinIO/internal ports remain private.
- The feature-completion physical join scans the QR captured for the exact
  issued session in display-expiry evidence after the screen has returned to
  advertising. A representative phone must read that same still-active session
  and its expected content, closing the actual-phone conjunct without rerunning
  search, changing display status or claiming implementation of the target
  purchase page.

## Data-policy Checks

- If the implementation logs, caches, stores or delivers capture-derived
  media, verification must not require developer-only access solely because it
  contains image content. No such mechanism is required.
- Credentials, authentication state, infrastructure access, commercial Photo
  media, personalized session data, participant names/annotations and
  administrative actions retain their existing protection.

## Exclusions

- No full/downscaled reference-frame upload or proof/annotation of
  local-detector misses is required for ordinary requests, diagnostics,
  Calibration or acceptance.
- No distributed tracing, client/server clock subtraction, mandatory
  per-crop logging, public media endpoint or cache layer is required.
- No representative benchmark is required before FT-003 design or tasking.
  Site validation still proves the existing controlled performance acceptance.
- No bridge/WebSocket comparison, dual-detector benchmark, model OTA, sensor
  discovery/pairing or credential-rotation proof is required.
- Contract fixtures MUST use the exact endpoint paths, multipart part names,
  validation rules and compact outcomes in the linked subject contracts.

## Evidence Route

- Keep task-specific automated, UI and physical-site evidence under
  `.tasks/<TASK_ID>/`; feature/task records link only the concise result.
- Use the cheapest fixture, integration or UI proof that demonstrates each
  applicable contract.
