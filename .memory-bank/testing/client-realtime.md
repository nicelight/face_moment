---
description: Canonical verification contract for client proposal submission, one-clock Promo latency and related diagnostics.
status: active
last_updated: 2026-08-06
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
