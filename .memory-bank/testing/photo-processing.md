---
description: Reproducible verification contract for FT-002 processing, recovery, SLO and storage-health behavior.
status: active
last_updated: 2026-08-06
source_of_truth:
  - .memory-bank/testing/photo-processing.md
---
# Photo Processing Verification

## Scope And Authority

This specification defines deterministic proof for `REQ-ING-003..004`,
`REQ-SRCH-001`, `REQ-REL-002`, `REQ-SEC-001`, `REQ-ARCH-001` and
`FT-002-AC-001..006`. Product outcomes remain owned by the
[PRD](../prd.md) and [FT-002](../features/FT-002.md); the persisted/worker rules
come from [Photo Processing](../domains/photo-processing.md), and the staff
surface comes from the [Photo Processing API](../contracts/photo-processing-api.md).

Every integration scenario uses unique disposable PostgreSQL/MinIO state,
explicit model/derivative fixtures, a controlled clock, a task-owned object
prefix and owned cleanup. Fake engines are allowed for deterministic lifecycle
and failure injection; adapter-contract fixtures still prove that the two real
engine implementations preserve their separate native paths and revision
checks.

## Terminal And Compatibility Matrix

Start with independently admitted Photos whose serving `pending` row and
pipeline revision are fixed. Drive:

- one compatible face result to complete private derivatives, one face set and
  `ready`/`searchable_at`;
- zero faces to `no_faces` with no searchable face set;
- a retryable fault through two returns to `pending`, then success on claim
  three;
- a repeated fault through terminal `failed` on claim three.

For every case, compare persisted state, state timestamps, attempts,
derivative/object counts, face rows and the staff-visible status. Negative
fixtures use an incompatible revision, invalid embedding dimension, incomplete
derivative publication and inactive Photo. Only complete active `ready` for the
current serving revision may produce `searchable=true`.

The adapter matrix binds one synthetic image independently to the configured
SFace and Buffalo M adapters. It records revision identity, detector/recognizer
call path, embedding dimension and proof that neither path consumes the other
adapter's bbox, landmarks, crop or alignment result.

## Idempotency And Restart Matrix

Use one deterministic face/derivative fixture for
`(photo_id, pipeline_revision_id)`:

1. Run to a normal terminal result and retain object checksums plus face rows.
2. Repeat delivery and confirm terminal no-op with the same rows/objects.
3. In a fresh state, interrupt after deterministic derivative publication but
   before terminal database commit, restart the worker, and run from the
   immutable original.
4. Restart once with active `processing` plus queued `pending` rows and compare
   the complete before/after population.

The final result MUST contain one face set keyed by stable `face_index`, one
deterministic preview/thumbnail per artifact kind, one terminal state, no lost
queued Photo and no duplicated face. Recovery evidence records
`worker_started_at`, `last_recovery_at` and `last_recovered_count`. Repeating the
whole fixture is safe and cleans only its own rows/objects.

## Full-Population SLO Matrix

Use one controlled accepted interval and at least these independently admitted
Photos:

- compatible searchable before 15 minutes;
- compatible ready exactly at or after 15 minutes;
- `no_faces`, `failed`, `pending` and `processing` at age at least 15 minutes;
- one still-open Photo younger than 15 minutes;
- one rejected candidate, one checksum duplicate and one non-serving revision
  state as explicit exclusions.

Reconcile every Photo to exactly one `success`, `breach` or `open` class. The
retained evidence records acceptance/state/searchable times, interval bounds,
population and exclusion reason, all three counts, ratio and the rule that
`meets_95_percent` is null until `open=0`. A completed population passes only
when `success / population >= 0.95`; no-face, failure and late unfinished work
remain breaches.

Repeat the calculation while a controlled Calibration operation occupies the
shared worker. New accepted Photos remain visible as ordinary pending/open or
aged breach, their SLO effect is not excluded, and processing resumes when the
operation releases the singleton worker. The fixture proves there is no
priority/preemption scheduler or second worker; it does not implement the
FT-011 Calibration calculation.

## Processing And Storage Health Matrix

The health scenario records queue counts, oldest pending time, current
operation and recovery projection from persisted disposable state. Then bind
explicit test capacity thresholds and independently exercise:

- both PostgreSQL and MinIO above threshold;
- PostgreSQL below threshold while MinIO remains normal;
- MinIO below threshold while PostgreSQL remains normal;
- each probe unavailable while the other stays observable.

Compare status, available bytes, configured threshold and observation time.
Probe evidence contains no mounted data-file content, path, credentials,
authentication state, object keys, embeddings, model paths or commercial
media. Effective topology evidence also proves the capacity views are
read-only and PostgreSQL, MinIO and internal service ports remain private.

## Acceptance Evidence Map

| Feature criterion | Required proof |
|---|---|
| `FT-002-AC-001` | Terminal/compatibility matrix plus exact staff-visible state proves only complete current-revision `ready` is searchable. |
| `FT-002-AC-002` | Repeat and post-derivative interruption converge on one derivative/face set and terminal state. |
| `FT-002-AC-003` | Worker restart preserves pending/processing population, resets unfinished work and reaches idempotent terminals. |
| `FT-002-AC-004` | Controlled full-population matrix reconciles successes, breaches, opens and explicit exclusions to the 95%/15-minute rule. |
| `FT-002-AC-005` | Calibration-held singleton worker leaves backlog/SLO effect visible, then ordinary processing resumes without scheduler expansion. |
| `FT-002-AC-006` | Authenticated health matrix exposes failures/recovery plus independent normal/low/unavailable PostgreSQL and MinIO capacity, while `REQ-SEC-001` private-topology and redaction proof remains satisfied. |

Project-native build/typecheck/tests and tier-routed verification remain owned
by the [testing index](index.md). This subject specification adds no lifecycle,
gate category or production-data permission.
