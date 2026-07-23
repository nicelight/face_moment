---
description: Preliminary decomposition-level lifecycle hints for the Face Moment one-СПА pilot.
status: draft
last_updated: 2026-07-23
---
# Lifecycle Map

## Purpose

Record only lifecycle transitions that affect L1-L3 decomposition. Exact state
schemas, persistence, concurrency, recovery, and transition contracts remain
owned by `/spec-design`.

## Independent Photo Admission

- The photographer selects one СПА and authoritative `visit_date`; each uploaded
  JPEG is validated and admitted independently.
- Invalid files are rejected. A duplicate under
  `(spa_id, visit_date, checksum_sha256)` is reported, its new object is deleted,
  and no new Photo or pipeline state is created.
- For a valid unique object, one per-photo PostgreSQL commit creates Photo,
  server-side `accepted_at` and serving-pipeline `pending` state together.
- A crash before that commit may leave an orphan object and lose one admission;
  re-upload is the accepted recovery. No group-level confirmation exists.

Source: [.memory-bank/prd.md](../prd.md) `FR-ING-01..08`; the grouping model in
[IDEA_INGEST.md](../../IDEA_INGEST.md) is historical.

## Photo Pipeline State

```text
pending -> processing -> ready | no_faces | failed
```

- The lifecycle is scoped by `(photo_id, pipeline_revision_id)`.
- Only `ready` is searchable for the compatible serving revision.
- `no_faces` is a distinct terminal processing outcome but remains an
  `ingest_to_searchable` SLO breach for the accepted-JPEG population.
- `pending` and `processing` records are durable. Worker startup returns
  unfinished `processing` work to `pending` and restarts it from the beginning.
- At-least-once execution must remain idempotent and must not duplicate final
  face records.

Sources: [IDEA_APP.md](../../IDEA_APP.md),
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
  `session_result_photo_ids`, `N`, QR expiry context, and one session-wide
  browser access state without per-device grant records.
- Result-display expiry returns the display to advertising without expiring the
  personalized session.
- A QR scan may open or reuse the same browser access context for 30 minutes
  from `qr_issued_at`; after successful first open, the shared context expires
  after 60 minutes without explicit participant activity on any opened phone.
- Expiry makes personalized data unavailable and redirects to the separate main
  Face Moment page without passing teaser, `N`, or other expired-session data.

Source: clarified [.memory-bank/prd.md](../prd.md) `FR-UX-03..10`; these values
supersede older configurable defaults in `IDEA_APP.md`.

## Core Attempt And Diagnostic Evidence

- Every accepted capture/search execution creates one core Attempt with its
  correlation identity before inference.
- Detailed diagnostic evidence is attached best-effort and is not a prerequisite
  for completing the participant-facing flow.
- A terminal Attempt whose evidence is absent or failed to finalize remains
  visible as `incomplete`.

Source: [.memory-bank/prd.md](../prd.md) `FR-DIAG-01..05`.

## Diagnostic And Calibration Retention

- Technical browser/server logs expire after 30 days.
- Ordinary attempts and diagnostic evidence expire after 90 days.
- Manual promotion preserves only the curated calibration subset named by PRD
  `NFR-DATA-03` until explicit deletion; it does not extend the whole ordinary
  bundle or its Promo screenshot.
- Recommendations never transition serving settings automatically; an explicit
  developer action is a separate boundary requiring later audit design.

Sources: [IDEA_DEBUG.md](../../IDEA_DEBUG.md) and clarified
[.memory-bank/prd.md](../prd.md) `NFR-DATA-01..04`.

## Calibration Run

- A developer-triggered Calibration run may use the same sequential
  `BackgroundPhotoWorker` and delay photo processing during debugging.
- Worker restart makes an interrupted run visibly `failed` or `interrupted`;
  photo processing resumes and the developer may rerun Calibration manually.
- No preemption, priority scheduler or separate Calibration worker is part of
  the pilot requirement.

Source: [.memory-bank/prd.md](../prd.md) `FR-DEV-11` and `NFR-PERF-03`.

## Deferred To /spec-design

- Canonical state names/fields and persistence ownership.
- Detailed transition guards, concurrency/idempotency contracts, bounded retry
  policy and failure normalization beyond the restart behavior fixed above.
- Session-token representation, expiry enforcement, cleanup, and audit events.
- Calibration-case promotion/deletion and serving-setting change contracts.
