---
description: Router for canonical Face Moment boundary and API contracts.
status: active
---
# Contracts

- [Boundary Map](boundary-map.md): capability ownership, public boundaries and
  cross-slice write rules.
- [Attempt Investigation API](attempt-investigation-api.md): exact role-scoped
  Attempts filters, list/detail page, projections and failures.
- [Client Diagnostic API](client-diagnostic-api.md): authenticated best-effort
  browser response-receipt marker for one admitted core Attempt.
- [Diagnostic Retention API](diagnostic-retention-api.md): owner-ordered cleanup
  command and role-scoped latest-result read contract.
- [Ground-Truth Annotation API](ground-truth-annotation-api.md): developer-only
  Attempt annotation routes, mutations, authorization and failures.
- [Photo Admission API](photo-admission-api.md): authenticated staff uploader,
  per-file responses, standard failures and UI behavior.
- [Photo Inventory API](photo-inventory-api.md): role-scoped Photo selection,
  visibility, recent counters, restore-all and global hard-purge surfaces.
- [Photo Processing API](photo-processing-api.md): authenticated per-Photo
  processing status, controlled-interval SLO and primary-storage health.
- [Promo Display API](promo-display-api.md): authenticated display
  configuration, teaser delivery and post-render acknowledgement.
- [QR Continuation API](qr-continuation-api.md): public ticket exchange,
  session-wide browser access, protected phone reads and expiry redirects.
- [Realtime Attempt API](realtime-attempt-api.md): proposal-attempt multipart
  request, validation, idempotency and outcomes.
- [Server Event API](server-event-api.md): developer-only bounded structured
  server-event filters, HTML projection, FT-008 navigation and failures.
- [Sensor Passage API](sensor-passage-api.md): browser-to-ESP32 long-poll,
  authentication, CORS and event response.
