---
description: Preliminary decomposition-level lifecycle hints for the Face Moment one-СПА pilot.
status: draft
last_updated: 2026-07-20
---
# Lifecycle Map

## Purpose

Record only lifecycle transitions that affect L1-L3 decomposition. Exact state
schemas, persistence, concurrency, recovery, and transition contracts remain
owned by `/spec-design`.

## Commercial Batch

- Before confirmation, uploaded candidates may be validated, accepted,
  rejected, or classified as duplicates.
- Confirmation freezes the accepted manifest and `confirmed_at` for one СПА and
  authoritative `visit_date`.
- Pre-confirmation rejects and same-СПА/date checksum duplicates never enter the
  confirmed population or downstream photo/job/search result lifecycle.

Sources: [IDEA_INGEST.md](../../IDEA_INGEST.md) and
[.memory-bank/prd.md](../prd.md) `FR-ING-01..08`.

## Photo Pipeline State

```text
pending -> processing -> ready | no_faces | failed
```

- The lifecycle is scoped by `(photo_id, pipeline_revision_id)`.
- Only `ready` is searchable for the compatible serving revision.
- `no_faces` is a distinct terminal processing outcome but remains an
  `ingest_to_searchable` SLO breach for the accepted-JPEG population.
- Retry/recovery details are intentionally deferred; execution must remain
  idempotent and must not duplicate final face records.

Sources: [IDEA_APP.md](../../IDEA_APP.md),
[IDEA_INGEST.md](../../IDEA_INGEST.md), and
[.memory-bank/prd.md](../prd.md) `FR-ING-07..08`.

## Automatic Attempt And Display

```text
advertising -> capturing -> searching -> result -> cooldown -> advertising
                              +-> unsuccessful -> advertising
```

- New sensor events are ignored while capture/search or successful cooldown is
  active.
- `result` is entered only after four unique threshold-valid teaser photos are
  available; otherwise no final Promo/Chime or success cooldown occurs.
- A stale response cannot replace a newer display state, and retry requires a
  fresh reference capture.

Sources: [IDEA_APP.md](../../IDEA_APP.md) and
[.memory-bank/prd.md](../prd.md) `FR-CAP-01..08`, `FR-UX-01..09`.

## Promo, QR, And Browser Session

- Issuing a Promo result binds СПА, authoritative `visit_date`, four teaser IDs,
  `session_result_photo_ids`, `N`, and QR expiry context.
- Result-display expiry returns the display to advertising without expiring the
  personalized session.
- First QR open is allowed for 30 minutes from `qr_issued_at`; after successful
  open, browser access expires after 60 minutes without activity.
- Expiry makes personalized data unavailable and redirects to the separate main
  Face Moment page without passing teaser, `N`, or other expired-session data.

Source: clarified [.memory-bank/prd.md](../prd.md) `FR-UX-03..10`; these values
supersede older configurable defaults in `IDEA_APP.md`.

## Diagnostic And Calibration Retention

- Technical browser/server logs expire after 30 days.
- Ordinary attempts, manifests, and diagnostic artifacts expire after 90 days
  and do not enter long-lived backup.
- Manual promotion preserves only the curated calibration subset named by PRD
  `NFR-DATA-03` until explicit deletion; it does not extend the whole ordinary
  bundle or its Promo screenshot.
- Recommendations never transition serving settings automatically; an explicit
  developer action is a separate boundary requiring later audit design.

Sources: [IDEA_DEBUG.md](../../IDEA_DEBUG.md) and clarified
[.memory-bank/prd.md](../prd.md) `NFR-DATA-01..04`.

## Deferred To /spec-design

- Canonical state names/fields and persistence ownership.
- Transition guards, concurrency/idempotency contracts, retry/recovery, and
  failure normalization.
- Session-token representation, expiry enforcement, cleanup, and audit events.
- Calibration-case promotion/deletion and serving-setting change contracts.
