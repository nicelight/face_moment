---
description: Product definition (C4 L1) for the Face Moment one-СПА pilot.
status: draft
last_updated: 2026-07-28
---
# Face Moment Product

## Product Identity

Face Moment is a controlled one-СПА smoke pilot that turns fresh professional
JPEG photographs into an automatic personalized Promo at the participant's
exit. A sensor-triggered display finds four valid low-quality teaser photos and
continues the same short-lived result on the participant's phone through QR,
without a new selfie.

The pilot also gives the application developer a role-scoped diagnostic and
calibration contour for explaining attempts and preparing manual face-match and
input-quality setting changes.

The repository is no longer documentation-only: the verified Foundation
supplies runnable backend, background-worker and realtime entrypoints plus the
non-production Compose/storage substrate. Product behavior and a deployed pilot
runtime do not exist yet; the capabilities below remain the product to be built.

## Core Value

- A participant discovers relevant photographs at the moment of leaving and
  continues the result with one QR scan.
- A photographer gets a timely path from fresh JPEG upload to searchable
  inventory and potential buyer attention, plus control to hide or restore their
  own uploaded Photos.
- An operator can observe recent per-СПА photo activity, manage authorized
  inventory and Promo outcomes without receiving access to sensitive developer
  diagnostics.
- A developer can correlate failures, latency and face-search decisions and
  derive explainable, manually applied calibration recommendations, while
  retaining project-wide inventory administration.

## Audience

- Pilot participant.
- Authenticated photographer.
- Face Moment / СПА operator.
- Authorized application developer.

The economic buyer of a future commercial product remains a post-pilot
hypothesis and is not a current actor.

## Primary Flow

```text
authenticated independent JPEG upload for selected СПА/date
-> compatible background processing
-> searchable inventory
-> automatic sensor-triggered reference series
-> client-side face proposals and bounded request
-> exact scoped face search and result assembly
-> four-teaser Promo with QR
-> same-session phone continuation
```

In parallel, authorized users can select Photos by СПА, authoritative
`visit_date` and effective capture-time range, soft-delete or restore them, and
observe per-СПА 1/5/60-minute processing statistics. Authorized
operator/developer settings also provide project-wide restore-all and confirmed
hard-purge operations.

Every request admitted by the server produces one core Attempt/correlation
timeline. Client-only offline metadata and detailed diagnostic evidence are
attached best-effort; an offline trigger may have no durable Attempt, while
missing evidence for a server Attempt remains visibly `incomplete`. Authorized
developers may annotate collected evidence and use it for explainable
Calibration; recommendations never update serving settings automatically.

## Success Contract

- At least 19 of 20 controlled attempts show four correct unique teasers and a
  fully visible, scannable QR in less than 10 seconds from
  `reference_series_ready_at`, measured on one client monotonic clock and
  including local reference-series processing and request sending.
- The same accepted attempts contain no unrelated teaser or `photo_id` in `N`.
- At least 95% of independently accepted unique JPEGs become searchable in less
  than 15 minutes from their server-side `photo.accepted_at`.
- Valid phone continuation preserves the same СПА, authoritative `visit_date`,
  available teaser and issued `N`; hard-purged media is skipped without session
  invalidation or `N` recalculation, and expired sessions disclose no
  personalized result data.
- Each server-admitted request retains a core correlation identity and stage
  timestamps sufficient to localize its outcome and latency; missing detailed
  evidence is explicit and client-only offline attempts remain best-effort.
- Soft-deleted Photos immediately leave new search/result formation and queue
  statistics but remain usable by already issued sessions. They can be restored
  without reprocessing and removed by one confirmed resumable project-wide purge
  that retains sessions, core Attempts and diagnostic evidence; existing clients
  skip missing hard-purged media.
- Per-СПА `new`, `unprocessed`, `processed` and transition-based `failed`
  counters for 1, 5 and 60 minutes refresh by five-second polling.

## Constraints

- One selected СПА, one central CPU-only server in the Russian Federation and
  one configured `SpaPromoClient`.
- One pre-warmed participant-facing pipeline; pipeline revisions and native
  preprocessing/alignment paths remain isolated.
- Exact PostgreSQL/pgvector search scoped by pipeline revision, СПА and the
  operator-selected authoritative `visit_date`.
- Private object storage; HTTPS public boundary; PostgreSQL, object storage and
  internal service ports are not public.
- KISS baseline: backend, one sequential `BackgroundPhotoWorker`, one
  synchronous `RealtimeFaceService`, PostgreSQL/pgvector and private
  MinIO/S3-compatible storage.
- Each unique Photo and serving `pending` state are committed atomically per
  photo; the PostgreSQL-backed queue retains unfinished work across restart.
- Developer Calibration may occupy the shared `BackgroundPhotoWorker`; an
  interrupted run is rerun manually after photo processing resumes.
- Photo Inventory Operations reuse that shared worker and durable Photo data:
  hard purge waits for the current operation, reports completed/total progress
  and resumes after restart without per-photo purge state, a purge jobs table,
  another worker, WebSocket or SSE.
- Infrastructure complexity is added only after evidence of a current
  requirement failure or measured bottleneck.
- Diagnostic logging is non-blocking. Capture-derived media is not protected
  solely by its content; credentials, infrastructure, commercial Photo media,
  personalized data, participant names and administrative actions remain
  protected by their own boundaries.

## Non-goals

- Public rollout, 10-15-СПА deployment or production-readiness claims.
- Payment, receipt/refund, original delivery or implementation of the main
  selfie-search/purchase page.
- Standalone or repeated selfie search in the pilot.
- External ingest, RAW processing or photographer cloud OAuth.
- Full group-member coverage, tracking, identity clustering, cross-pipeline
  person linking or participant-facing model ensembles.
- ANN, brokers, Redis, distributed scheduling, extra workers, Kubernetes,
  GPU-first deployment or an external observability stack without evidence.
- Automatic application of Calibration recommendations or a general-purpose
  experimentation platform.
- Backup, replication or recovery after irreversible loss of the only primary
  disk/server; the controlled pilot accepts that data-loss risk.

## Canonical Inputs

- [.memory-bank/prd.md](prd.md): clarified product contract and acceptance.
- [.memory-bank/constitution.md](constitution.md): governing priorities and
  bounded-autonomy rules.
- [.memory-bank/invariants.md](invariants.md): cross-cutting MUST/NEVER rules.
- [.memory-bank/requirements.md](requirements.md): stable requirements and RTM.
