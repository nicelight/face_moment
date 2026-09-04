---
description: Canonical pilot lifecycles for Photo admission, processing, inventory visibility, purge, Promo and diagnostics.
status: active
last_updated: 2026-09-03
source_of_truth:
  - .memory-bank/states/lifecycle-map.md
---
# Lifecycle Map

## Purpose

Record the accepted lifecycle and recovery rules that constrain later feature
design. The verified Foundation supplies runnable infrastructure and server-role
entrypoints, but no product lifecycle below is implemented; every state remains
target design rather than observed product behavior.

## Independent Photo Admission

- The photographer selects one СПА and authoritative `visit_date`; each uploaded
  JPEG is validated and admitted independently.
- Invalid files are rejected. A duplicate under
  `(spa_id, visit_date, checksum_sha256)` is reported, its new object is deleted,
  and no new Photo or pipeline state is created.
- For a valid unique object, one per-photo PostgreSQL commit creates Photo,
  server-side `accepted_at`, immutable admission-time serving revision and the
  matching serving-pipeline `pending` state together.
- Effective `captured_at` uses reliable EXIF interpreted in the СПА timezone,
  otherwise that file's server-side upload-start time, otherwise 01:00 on the
  authoritative `visit_date`.
- A crash before that commit may leave an orphan object and lose one admission;
  re-upload is the accepted recovery. No group-level confirmation exists.

Source: [.memory-bank/prd.md](../prd.md) `FR-ING-01..08`; the grouping model in
[IDEA_INGEST.md](../../IDEA_INGEST.md) is historical.

## Photo Pipeline State

```text
pending -> processing -> ready | no_faces | failed
```

- The lifecycle is scoped by `(photo_id, pipeline_revision_id)`.
- The Photo's immutable admission-time revision selects exactly one state for
  its ingest-to-searchable SLO; another revision state neither replaces nor
  duplicates that population member.
- Only `ready` is searchable for the compatible serving revision.
- `no_faces` is a distinct terminal processing outcome but remains an
  `ingest_to_searchable` SLO breach for the accepted-JPEG population.
- `pending` and `processing` records are durable. Worker startup returns
  unfinished `processing` work to `pending` and restarts it from the beginning.
- Claiming work is one atomic `pending -> processing` transition that increments
  the persisted attempt counter.
- Processing retries are bounded to three attempts initially; exhaustion
  publishes terminal `failed` rather than looping forever.
- At-least-once execution must remain idempotent and must not duplicate final
  face records.

Sources: [IDEA_APP.md](../../IDEA_APP.md),
[.memory-bank/prd.md](../prd.md) `FR-ING-07..08`.

## Ordinary Serving-Revision Change Guard

An authenticated manual command may change one СПА from current revision A to
validated B, but it introduces no new revision-switch lifecycle or job state.
Before B commits, `serving_control` serializes the serving-context update with
admission and consults the processing-owned A-state guard. Any Photo admitted
against A with exact A state `pending` or `processing` rejects the command and
leaves A committed; `ready`, `no_faces` and `failed` are terminal and permit
the change. The rejection changes no Photo state and does not start the B
maintenance/restart path. Calibration/model comparison is test-only and never
creates an exception to this guard.

Source: accepted operator decision in
[FT-002](../features/FT-002.md#clarifications); application ownership and
transaction boundary are canonical in the
[Boundary Map](../contracts/boundary-map.md#manual-serving-revision-switch).

## Photo Inventory Visibility

```text
active <-> soft_deleted
soft_deleted -- confirmed global hard purge --> physically removed
```

- A photographer may transition only Photos with their own `uploader_id`; an
  operator/developer may transition any Photo in an accessible СПА.
- Selection uses one СПА, authoritative `visit_date` and effective
  `captured_at` range.
- `soft_deleted` is one inventory-owned visibility marker. All Photo/media,
  faces, pipeline state and related data remain stored, but new search/result
  formation and recent-statistics reads exclude the Photo. An already issued
  Promo/session keeps using its referenced media while it exists.
- Restore returns the Photo to `active` with its preserved processing state and
  timestamps; it does not upload or process the Photo again.
- Project-wide restore-all moves every currently `soft_deleted` Photo to
  `active` except members of a confirmed non-terminal hard-purge snapshot;
  restore of those members is rejected until completion.
- Hard purge physically removes snapshot Photo/media/face/pipeline data.
  Existing Promo results/sessions, the core Attempt and diagnostic evidence do
  not transition. UI/device loading skips an unavailable item without
  invalidating or rebuilding the session or recalculating issued `N`.
- There is no per-photo `purge_pending` or purge-job lifecycle.

Source: [.memory-bank/prd.md](../prd.md) `FR-INV-01..08`.

## Global Hard-Purge Run

```text
confirmed_waiting -> running -> completed
             restart ↘ resume same fixed snapshot ↗
```

- Explicit confirmation fixes every Photo that is soft-deleted across the
  project at that moment. Later soft deletes are not added.
- `confirmed_waiting` persists while the shared worker completes its current
  Photo-processing, Calibration or maintenance operation. No preemption occurs.
- The waiting UI displays `Начну удаление, как только закончится процесс
  {human-readable process name}`.
- `running` exposes completed/total progress and replaces the destructive
  settings surface.
- One durable global run retains enough snapshot/progress identity to resume
  idempotent cleanup after backend/worker restart. It is not a generic jobs
  subsystem.
- Restore and restore-all reject snapshot members until the run reaches
  `completed`; the fixed target set does not change.
- An upload already in progress is never interrupted. Ordinary upload may
  continue and create normal `pending` Photo work while purge occupies the
  worker.

Source: [.memory-bank/prd.md](../prd.md) `FR-INV-05..09`,
`NFR-REL-06`.

## Automatic Attempt And Display

```text
advertising -> capturing -> searching -> result -> cooldown -> advertising
                              +-> unsuccessful -> advertising
```

- While active in `advertising`, the client awaits a passage event through the
  ESP32 boundary. Poll continuation is transport behavior and creates no
  sensor queue or additional lifecycle.
- When the capture window ends, the ready reference series enters local
  proposal preparation and then crosses one realtime request boundary; this
  local work creates no intermediate server-visible state.
- Client configuration changes apply from the next Attempt and do not mutate
  an active Attempt or add a server-side settings lifecycle.
- Zero proposals follow the same admission boundary. Once admitted, the server
  creates the core Attempt and returns a typed non-success whose machine name
  belongs to the API contract.
- Transport rejection occurs before domain admission and creates no core
  Attempt or domain transition. Exact proposal, payload and failure contracts
  are defined in the [boundary map](../contracts/boundary-map.md).
- A server-admitted core Attempt uses:

  ```text
  processing_status: accepted -> searching
                     -> result_issued | no_success | interrupted
                        | deadline | internal_failure

  display_status: not_applicable | pending
                  pending -> confirmed | failed | unconfirmed
  ```

  `client_offline` is a client-side diagnostic outcome and may never become a
  durable server Attempt.
- While serving maintenance/readiness is closed, capture/search is rejected
  with `503` before `promo` admission. It creates no core Attempt, session or
  display transition; the client remains/returns to local advertising.
- New sensor events are ignored while capture/search or successful cooldown is
  active.
- `result` is entered only after four unique threshold-valid teaser photos are
  available; otherwise no final Promo/Chime or success cooldown occurs.
- A stale response cannot replace a newer display state, and retry requires a
  fresh reference capture.
- A server-communication failure returns to advertising and shows
  `Попытка связи с сервером была не успешна в hh:mm:ss` non-blockingly for
  5–10 seconds. A newer notice may replace the current one immediately.
- For a server-issued result, display state is `pending` until an idempotent
  post-render acknowledgement makes it `confirmed`; render failure may report
  `failed`, and absence of confirmation after the result-display window is
  derived as `unconfirmed` on read without scheduler machinery.
- `result_issued` is not Promo success. `confirmed` requires all four teasers
  decoded and the QR fully visible. A late acknowledgement cannot replace
  terminal derived `unconfirmed`.
- Realtime startup closes old server Attempts still in `accepted|searching` as
  `interrupted`; it never replays their reference work.
- Acceptance latency uses only client monotonic elapsed values:
  `qr_fully_visible_elapsed_ms - reference_series_ready_elapsed_ms`. Server
  stages record their own monotonic durations. This interval includes local
  detection, crop extraction/encoding, request upload, server processing,
  response receipt and Promo/QR render; cross-machine clock subtraction and
  distributed tracing are not required.

Sources: [IDEA_APP.md](../../IDEA_APP.md), [IDEA_CLIENT.md](../../IDEA_CLIENT.md)
and [.memory-bank/prd.md](../prd.md) `FR-CAP-01..17`, `FR-UX-01..09`.

## Client Restart And Offline Metadata

- After Chromium restart, SpaPromoClient reloads and enters `advertising` once
  the central HTTPS origin is reachable; it discards personalized
  result/frame/token state and does not replay search.
- A bounded local outbox may retain only diagnostic metadata and
  `cooldown_until` until acknowledgement or short expiry. Client-only offline
  delivery is best-effort and may be lost on expiry or restart.
- A currently loaded client keeps local advertising available through
  network/server failure. Reload or restart while the central HTTPS origin is
  unavailable is not required to restore advertising.

## Promo, QR, And Browser Session

- Issuing a Promo result binds СПА, authoritative `visit_date`, four teaser IDs,
  `session_result_photo_ids`, `N`, QR expiry context, and one session-wide
  browser access state without per-device grant records.
- Result-display expiry returns the display to advertising without expiring the
  personalized session.
- A QR scan may open or reuse the same browser access context for 30 minutes
  from `qr_issued_at`; after successful first open, the shared context expires
  after 60 minutes without explicit participant activity on any opened phone.
- A local phone timer clears rendered personal state at expiry; the server
  remains authoritative for every later read.
- Soft delete does not invalidate an issued session. If a referenced Photo is
  later hard-purged, UI/device loading skips that media item and continues with
  the session's historical `N`.
- Expiry makes personalized data unavailable and redirects to the separate main
  Face Moment page without passing teaser, `N`, or other expired-session data.

Source: clarified [.memory-bank/prd.md](../prd.md) `FR-UX-03..10`; these values
supersede older configurable defaults in `IDEA_OS.md`.

## Core Attempt And Diagnostic Evidence

- Every capture/search request admitted by the server creates one core Attempt
  with its correlation identity before inference.
- The correlated timeline retains client-local markers for ready-series
  processing start, request-send start and response receipt.
- A client-only offline trigger is delivered best-effort and may have no durable
  server Attempt.
- Detailed diagnostic evidence is attached best-effort and is not a prerequisite
  for completing the participant-facing flow.
- A terminal Attempt whose evidence is absent or failed to finalize remains
  visible as `incomplete`.
- Evidence completeness requires neither a full/downscaled reference-frame
  upload nor proof or annotation of occurrences missed by the local detector.

Sources: [IDEA_CLIENT.md](../../IDEA_CLIENT.md) and
[.memory-bank/prd.md](../prd.md) `FR-CAP-10`, `FR-DIAG-01..05`, `AC-22`.

## Diagnostic And Calibration Retention

```text
collecting -> complete | incomplete
complete | incomplete -- ordinary retention --> expired
complete | incomplete -- explicit diagnostics removal --> removed
```

- An incomplete bundle retains an explicit gap reason. Participant flow and the
  core Attempt/outcome/snapshot do not depend on detailed evidence completion.
- Structured server events expire after 30 days.
- Ordinary Attempts and diagnostic evidence, including persisted
  capture-derived media, expire after 90 days.
- Ordinary ground-truth annotation rows follow the same Attempt-selected
  90-day cutoff. Diagnostics deletes them before promo deletes the core Attempt;
  annotation creation or correction never extends the Attempt lifetime.
- `diagnostics` alone may create `removed` through the irreversible owner
  transition in
  [Diagnostic Evidence](../domains/diagnostic-evidence.md#explicit-ordinary-removal-transition).
  The transition retains provenance, exposes no public FT-008 mutation route,
  rejects stale ordinary writes and never aliases explicit removal to expiry.
  Later ordinary retention may delete the old core Attempt through `promo`, but
  cannot restore removed content.
- Manual promotion preserves only the curated calibration subset named by PRD
  `NFR-DATA-03` until explicit deletion; it does not extend the whole ordinary
  bundle, ordinary annotations or its Promo screenshot. Promoted annotation
  fields are an immutable selected snapshot and disappear with explicit
  promoted-subset deletion.
- Capture-derived media adds no separate retention lifecycle and is not
  protected solely because it contains an image. Other data keeps its
  data-specific authorization and delivery rules from the boundary contract.
- Recommendations never transition serving settings automatically; an explicit
  developer action uses the audited `serving_control` command defined in the
  [boundary map](../contracts/boundary-map.md).
- Retention cleanup adds no separate lifecycle. Its ownership, observable
  result and safe-rerun contract are defined in the
  [boundary map](../contracts/boundary-map.md).
- Structured server events have no per-row lifecycle beyond retained versus
  deleted: the diagnostics owner deletes rows strictly before the fixed cutoff,
  including uncorrelated rows, and current/stale search cannot reconstruct
  them. Exact shape and deletion proof are defined by
  [Structured Server Events](../domains/structured-server-events.md#retention-boundary).

Sources: [IDEA_DEBUG.md](../../IDEA_DEBUG.md),
[IDEA_CLIENT.md](../../IDEA_CLIENT.md) and clarified
[.memory-bank/prd.md](../prd.md) `NFR-DATA-01..04`.

## Calibration Run

- A developer-triggered Calibration run may use the same sequential
  `BackgroundPhotoWorker` and delay photo processing during debugging.
- Worker restart makes an interrupted run visibly `failed` or `interrupted`;
  photo processing resumes and the developer may rerun Calibration manually.
- No preemption, priority scheduler or separate Calibration worker is part of
  the pilot requirement.
- A confirmed hard purge waits for an active Calibration run. After the current
  operation ends, the shared worker executes the purge before returning to
  ordinary Photo processing.

Source: [.memory-bank/prd.md](../prd.md) `FR-DEV-11` and `NFR-PERF-03`.

## Deliberate Non-lifecycles

- No Batch/manifest/confirmation lifecycle.
- No resumable-upload lifecycle.
- No per-photo hard-purge state or purge jobs table.
- No realtime waiter/replay queue.
- No per-device QR access-grant lifecycle.
- No serving-revision switch lifecycle, queue or history beyond the atomic
  manual-change guard above.
- No local-detector-miss proof or diagnostic reference-frame-upload lifecycle.
- No separate capture-media retention lifecycle.
- No separate sensor transport/configuration lifecycle.
- No admitted proposal-request rejection lifecycle; transport rejection occurs
  before domain admission.
