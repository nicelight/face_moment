---
description: Canonical verification contract for client proposal submission, one-clock Promo latency and related diagnostics.
status: active
last_updated: 2026-07-28
source_of_truth:
  - .memory-bank/testing/client-realtime.md
---
# Client Realtime Verification

## Required Proof

- An occurrence fixture proves that one bounded request contains one crop and
  its metadata for every local-detector occurrence, including repeated
  occurrences of one person. The outbound client path performs no ranking,
  top-5 selection, authoritative quality gate, tracking, clustering or
  deduplication.
- A zero-occurrence fixture proves a metadata-only request with the same
  correlation and client timings. If admitted, it creates the core Attempt and
  a typed non-success without requiring a particular machine outcome name.
- An oversize fixture proves explicit non-success and that no ranked or
  arbitrary subset is sent. Exact byte/pixel bounds and wire response remain
  deferred with FT-003.
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
- Client route, hardware, detector/runtime/model/update choice, crop contract,
  request schema and exact bounds remain FT-003 decisions; verification must
  not select them.

## Evidence Route

- Keep task-specific automated, UI and physical-site evidence under
  `.tasks/<TASK_ID>/`; feature/task records link only the concise result.
- Use the cheapest fixture, integration or UI proof that demonstrates each
  applicable contract. Browser-versus-bridge comparison is not an acceptance
  gate.
