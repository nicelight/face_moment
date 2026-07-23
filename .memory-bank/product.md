---
description: Product definition (C4 L1) for the Face Moment one-СПА pilot.
status: draft
last_updated: 2026-07-23
---
# Face Moment Product

## Product Identity

Face Moment is a controlled one-СПА smoke pilot that turns fresh professional
JPEG photographs into an automatic personalized Promo at the participant's
exit. A sensor-triggered display finds four valid low-quality teaser photos and
continues the same short-lived result on the participant's phone through QR,
without a new selfie.

The pilot also gives the application developer a protected diagnostic and
calibration contour for explaining attempts and preparing manual face-match and
input-quality setting changes.

## Core Value

- A participant discovers relevant photographs at the moment of leaving and
  continues the result with one QR scan.
- A photographer gets a timely path from fresh JPEG upload to searchable
  inventory and potential buyer attention.
- An operator can observe readiness and Promo outcomes without receiving access
  to sensitive developer diagnostics.
- A developer can correlate failures, latency and face-search decisions and
  derive explainable, manually applied calibration recommendations.

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
-> exact scoped face search and result assembly
-> four-teaser Promo with QR
-> same-session phone continuation
```

Every accepted attempt produces one core Attempt/correlation timeline. Detailed
diagnostic evidence is attached best-effort and remains visibly `incomplete`
when absent or unfinished. Authorized developers may annotate collected
evidence and use it for explainable Calibration; recommendations never update
serving settings automatically.

## Success Contract

- At least 19 of 20 controlled attempts show four correct unique teasers and a
  fully visible, scannable QR in less than 10 seconds from
  `reference_series_ready_at`.
- The same accepted attempts contain no unrelated teaser or `photo_id` in `N`.
- At least 95% of independently accepted unique JPEGs become searchable in less
  than 15 minutes from their server-side `photo.accepted_at`.
- Valid phone continuation preserves the same СПА, authoritative `visit_date`,
  teaser and `N`; expired sessions disclose no personalized result data.
- Each accepted attempt retains a core correlation identity and stage timestamps
  sufficient to localize its outcome and latency; missing detailed evidence is
  explicit.

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
- Infrastructure complexity is added only after evidence of a current
  requirement failure or measured bottleneck.
- Diagnostic logging is non-blocking and excludes images, embeddings, secrets,
  request bodies and session replay.

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
