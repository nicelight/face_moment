---
description: Reproducible verification contract for FT-002 processing, recovery, SLO and storage-health behavior.
status: active
last_updated: 2026-09-07
source_of_truth:
  - .memory-bank/testing/photo-processing.md
---
# Photo Processing Verification

## Scope And Authority

This specification defines deterministic proof for `REQ-ING-003..004`,
`REQ-SRCH-001`, `REQ-REL-002`, `REQ-SEC-001`, `REQ-ARCH-001` and
`FT-002-AC-001..012`. Product outcomes remain owned by the
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

Migration proof uses two isolated starting states. With an empty
`pipeline_revisions` table, upgrade/downgrade/re-upgrade adds the exact FT-002
shape while preserving unrelated prerequisite rows. With any legacy revision
row, including a referenced fixture, upgrade fails before the first schema or
data mutation. The proof confirms that no compatibility value is synthesized
and no reference is deleted or repointed.

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

The per-Photo API compatibility fixture admits one Photo under revision A and
adds a second B state. With A current, the API returns exact A state fields and
the ordinary A completeness/activity `searchable` truth. After current serving
changes to B, it still returns `200` with A's revision, pipeline, status,
attempts and timestamps but `searchable=false`. Repeat with a complete `ready`
B row and confirm it neither replaces the A response nor triggers
`MultipleResultsFound`. The read is mutation-free and a missing required A
state remains the existing owner-read `5xx` branch.

The ordinary serving-switch matrix starts with current validated A and target
validated B for one СПА. One A-admitted Photo in each of `pending` and
`processing` yields the audited rejection result, keeps A current, and changes
no Photo state, assets or model-consuming process. Each of `ready`, `no_faces`
and `failed` permits B to commit; the later restart/admission matrix then proves
the committed B binding separately. An interleaved admission and switch proves
one serial outcome only: the completed A admission blocks B, or the successful
B switch makes the admission snapshot B. Calibration/model-comparison fixtures
remain offline and cannot invoke or bypass the guard.

The transaction contract adds a read-only `SELECT 1` before a successful switch
and observes the committed B revision from a fresh session without a caller
commit. A rejection compares the complete serving and Photo snapshot before and
after the command. A failure injected after assignment and flush must leave A
durable; the same Session observes A after rollback and retries successfully to
B. The existing Calibration apply caller remains green with its explicit
surrounding commit/rollback handling.

The adapter matrix binds one synthetic image independently to the configured
SFace and Buffalo M adapters. It records revision identity, detector/recognizer
call path, embedding dimension and proof that neither path consumes the other
adapter's bbox, landmarks, crop or alignment result.

The runtime-admission matrix mounts deterministic model fixtures read-only and
starts against the one selected validated revision. The matching case proves
that only its direct adapter is loaded and warmed. Missing assets, a hash or
identity mismatch, an absent/ineligible selection or selected paths resolving
to the other pipeline's assets all keep the worker unavailable before startup
recovery, claim or Photo-state mutation. A serving-revision change remains
unavailable until a restart binds the process to matching assets; no fallback
or download is allowed.

The Buffalo native-readiness regression uses the actual local SCRFD and Buffalo
M ONNX files with an in-memory compatible revision. It records CPU detector
preparation at `(640, 640)`, detector inference, recognizer `get` on a
discarded BGR image with valid five-point landmarks, and a finite normalized
512-dimensional result. Readiness is false before warmup, remains false after
independent native detector/recognizer or invalid-embedding failures, and only
opens after both native calls succeed. The same dynamic detector then processes
a 320-by-320 synthetic Photo without the prior `input_size` assertion. Existing
serving and Calibration admission tests prove a `BuffaloAdapterError` remains
closed as `ModelAdmissionError`; no skip, fallback or model download is valid
evidence.

TASK-114 is closed with [independent native readiness verification](../../.protocols/TASK-114-T3-FT-002-W6/verification.md): the real native node, full 26-test adapter/admission gate and 16-case consumer failure matrix pass. [Task semantic verification](../../.protocols/TASK-114-T3-FT-002-W6/red-verification.md) and the current [FT-002 feature verdict](../../.tasks/FT-002/FT-002-S-RED-VERIFY-final-report-docs-01.md) support AC-009 closure.

## Idempotency And Restart Matrix

The EXIF regression starts at real admission and persistence, then uses real
orchestration, terminal publication and derivative creation with a deterministic
adapter in disposable PostgreSQL/MinIO state. An asymmetric 30-by-10 JPEG with
orientation 6 or 8 persists as 10-by-30, accepts bbox `(2, 15, 5, 5)` outside
the former unrotated height, and preserves the adapter's five landmarks.
Preview and thumbnail pixels prove the correct clockwise/anticlockwise order
after resizing; original bytes and SHA-256 remain exact. Repeat with no EXIF and
with genuinely out-of-bounds bbox values to prove ordinary success and unchanged
rejection without partial ready publication. Admission unit coverage includes
no EXIF, all orientations 1–8, and invalid orientation 9. These fixtures create
new Photos; they do not repair or assert the presence of historical bad metadata.

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

- one Photo exactly at inclusive `accepted_from` and one exactly at exclusive
  `accepted_before`;
- compatible searchable before 15 minutes;
- compatible ready exactly at or after 15 minutes;
- `no_faces`, `failed`, `pending` and `processing` at age at least 15 minutes;
- one still-open Photo younger than 15 minutes;
- one rejected candidate and one checksum duplicate as explicit exclusions.

For one accepted A-revision Photo, switch current serving to B and add an
explicit B state. The SLO row still joins only the Photo's persisted admission
revision A state and therefore remains one member of its original class. No
state/revision timestamp, status, attempt count or current serving selection
may choose the row. The lineage-migration matrix starts with an empty `photos`
table for upgrade/downgrade/re-upgrade and separately proves that any non-empty
Photo table aborts before schema/data mutation; it never backfills a guessed
revision.

Reconcile every Photo to exactly one `success`, `breach` or `open` class. The
retained evidence records acceptance/state/searchable times, interval bounds,
population and exclusion reason, all three counts, ratio and the rule that
`meets_95_percent` is null until `open=0`. A completed population passes only
when `success / population >= 0.95`; no-face, failure and late unfinished work
remain breaches.

Repeat with a valid half-open interval containing no Photos. Assert
`population=success_under_15_minutes=breach=open=0` and
`success_ratio=meets_95_percent=null`; the API and UI MUST NOT present that
result as zero percent or as a pass/fail verdict.

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
| `FT-002-AC-001` | Terminal/compatibility and ordinary-switch matrices prove only complete current-revision `ready` is searchable, `pending|processing` A rejects B before commit, and every terminal A state permits B. |
| `FT-002-AC-002` | Repeat and post-derivative interruption converge on one derivative/face set and terminal state. |
| `FT-002-AC-003` | Worker restart preserves pending/processing population, resets unfinished work and reaches idempotent terminals. |
| `FT-002-AC-004` | Controlled half-open full-population matrix reconciles successes, breaches, opens and explicit exclusions to the 95%/15-minute rule and proves the all-zero/null empty result. |
| `FT-002-AC-005` | Calibration-held singleton worker leaves backlog/SLO effect visible, then ordinary processing resumes without scheduler expansion. |
| `FT-002-AC-006` | Authenticated health matrix exposes failures/recovery plus independent normal/low/unavailable PostgreSQL and MinIO capacity, while `REQ-SEC-001` private-topology and redaction proof remains satisfied. |
| `FT-002-AC-007` | The configured SFace adapter records the YuNet plus `alignCrop`/SFace path, revision/dimension match and rejection of Buffalo-derived or mismatched input. |
| `FT-002-AC-008` | The configured Buffalo M adapter records the SCRFD/native alignment/`normed_embedding` path, revision/dimension match and rejection of SFace-derived or mismatched input. |
| `FT-002-AC-009` | The actual local dynamic-input Buffalo detector and recognizer complete native warmup, readiness stays closed on native failure, and existing serving/Calibration admissions fail closed with `ModelAdmissionError`. |

Project-native build/typecheck/tests and tier-routed verification remain owned
by the [testing index](index.md). This subject specification adds no lifecycle,
gate category or production-data permission.

## Photographer Scale Experiment

This method proves AC-010/011 under the accepted
[versioned preprocessing contract](../domains/photo-processing.md#versioned-photographer-preprocessing).
Use deterministic fixtures for actual resize ratios on non-square odd
sizes, EXIF orientations, images smaller than 640, 640..1280 images, duplicate
scales, the same face at two scales, neighbouring faces and partial edge faces.
Observe detector dimensions, original array passed to alignCrop, all five
mapped landmarks, native 112x112 crop, finite normalized embeddings, clipped
terminal bbox and absence of count/size filters. Prove legacy full-image behavior
and single-pass query calls under both new Photo identities; keep Buffalo and
serving/Calibration admission regressions scoped to compatibility.

Native sample inputs currently include five JPEGs under
`/tmp/!datasets/serg_1/me_1/`, `IMG_20230523_185218.jpg` at the dataset root
(EXIF 3), and groups `FansChildrenTJ.jpg` and `sirious-guys.jpg` at that root.
Verify paths and record a filename/hash/dimensions/orientation manifest before
measurement. Six portraits correspond to the existing local uploaded inventory.
The group images include partial, occluded and profile faces; results must name
which visible sample faces are recovered or missed, not claim that every pose
or every group of eight is supported.

Use the same configured YuNet/SFace read-only assets, CPU/thread conditions,
originals and query inputs for both variants. Warm up, then repeat each sample
at least three times and retain per-image median detection and full processing
time, pre/post-merge face counts and reviewable original-coordinate overlays.
Compare query cosine/matching observations under unchanged thresholds only
where corresponding evidence is actually available. Separate visually observed
detection counts from operator ground truth and distinguish sample/self-query
sanity from real camera accuracy. Store bounded metrics and local overlays in
task evidence, not model files, raw embeddings or commercial originals in Git.

Select 640 unless the additional scale recovers a visually verified real face
or improves an available corresponding match without introducing a known
sample regression that defeats that benefit. Record the concrete gain and
extra time; uncertain or absent benefit resolves to 640 under the accepted
simpler-selection policy. Missing camera Attempts or human ground truth is
reported as unavailable evidence, never fabricated Calibration data or an
unsupported universal accuracy verdict. The experiment is local task proof,
not a new persisted product experiment platform.

## Local Reprocessing Proof

AC-012 uses the authorized workstation runtime for a non-destructive final
application after disposable integration proof. Capture current revision,
selected Photo IDs, original hashes, admission/visibility fields, old terminal
states/faces/derivative references and effective Compose configuration. Prove
new-revision pending creation/repeated invocation, guarded selection, selected
worker/realtime binding, truthful terminals and compatible search through the
existing owner boundaries. Compare fresh-session before/after snapshots and
re-run the same recorded target to prove no extra revision/state/face rows.

Inject failure and restart only in disposable fixtures with unique database and
object-prefix cleanup; never erase or downgrade local operator inventory.
Retain deployed local outcomes for testing. Staff admission-revision status and
the admission-based SLO are intentionally unchanged after reprocessing and
must not be presented as new-revision completion evidence. A missing local
runtime/model/original is reported with its exact affected scope.


Local reprocessing implementation evidence uses
`tests/processing/test_photo_reprocessing.py`: preserved-A/new-B exact search,
create-only pending with rollback and all five existing statuses, and target
reuse after interrupted journaling through real processing/serving owner APIs.
Native admission remains covered by `test_model_asset_admission.py`; the local
procedure retry fixture substitutes only model loading. All databases are
fixture-owned and removed. The local application evidence belongs to
`.tasks/TASK-118-T3-FT-002-W8/` and retains user outcomes after application.
