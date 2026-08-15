---
description: Server-authoritative reference-query selection and compatible exact realtime search contract.
status: active
last_updated: 2026-08-16
source_of_truth:
  - .memory-bank/domains/realtime-search.md
---
# Realtime Reference Search

## Scope And Ownership

This specification owns the `processing` part of one admitted automatic
reference search: immutable context consumption, server-authoritative proposal
selection, native query preparation and exact compatible Photo search.

`serving_control` owns active date and search settings, `inventory` owns Photo
identity/visibility, and `promo` owns the inference-slot orchestration,
candidate union, teaser selection, `N`, core Attempt and result session.
`processing` returns typed search observations through its application
boundary and writes none of those foreign states. HTTP handlers, generic
helpers, infrastructure and the composition root MUST NOT implement selection,
query preparation or search rules.

## Active-Search Context Persistence

The `serving_control`-owned persistence extends `face_moment.spas` with nullable
`active_visit_date`, positive `settings_revision` and `settings_updated_at`.
One `face_moment.reference_search_settings` row per
`(spa_id, pipeline_code, query_source)` stores the threshold,
`min_query_face_quality`, bounded JSON quality settings, nullable
`calibration_id` and update timestamp. `query_source` is `reference` in this
pilot. Threshold identity is deliberately tied to pipeline code and query
source, not to one immutable pipeline revision.

An isolated provision/update path supplies deterministic test settings. The
active-date staff API is defined by the
[Boundary Map](../contracts/boundary-map.md#active-search-date). No automatic
date rollover, automatic threshold change, settings history or generic
configuration platform is introduced.

## Immutable Active-Search Context

Before domain admission, `serving_control` resolves one immutable context from
the owner stores above and the accepted serving revision:

| Value | Contract |
|---|---|
| `settings_revision` | Positive owner revision copied into the core Attempt. |
| `spa_id` | Authoritative UUID from the authenticated display-client principal. |
| `visit_date` | Nullable owner setting before readiness; required for an admitted search and never supplied by the client. |
| `pipeline_revision_id`, `pipeline_code` | One validated selected serving revision. |
| `query_source` | Exactly `reference`. |
| `reference_threshold` | Finite configured cosine-similarity threshold for `(spa_id, pipeline_code, reference)`. |
| `min_query_face_quality`, `quality_settings` | Finite configured query gate and its bounded versioned parameters. |
| `calibration_id` | Nullable accepted Calibration provenance. |
| `release_id` | Current server release identity. |

If the active date or another required context value is absent, serving
readiness is closed: the realtime boundary returns `503` before `promo`
admission, performs no query preparation/search and creates no core Attempt or
session. A bounded operational event may name the missing field but contains no
token, credential or personalized payload.

An optional capture-time filter is absent by default. It may be supplied in the
immutable context only when deployment evidence explicitly marks its clock and
timezone quality as confirmed. Without that fact, search MUST NOT infer a time
window from client/server clocks or Photo upload order.

## Reference Query Boundary

The owner-local `FaceEngine` implementations from
[Photo Processing](photo-processing.md) expose the smallest additional
reference-query operations needed here:

- inspect one admitted occurrence crop and return a deterministic finite
  `reference_quality_score` plus bounded gate observations under the immutable
  quality settings;
- prepare a selected crop through that revision's native detector,
  preprocessing, alignment, normalization and embedding path.

Before realtime readiness opens, the composition root follows the shared
[model-asset admission](photo-processing.md#model-asset-admission) contract:
resolve the committed selected validated revision, load and warm only its
direct adapter from the operator-managed read-only mount, and verify the full
configured identity plus computed `weights_sha256`. Missing or mismatched
assets keep readiness closed before Attempt admission or processing-state
mutation. Search MUST NOT load a model on first request, fall back to the other
pipeline, mix pipeline-native preparation, reuse another revision's embedding
or silently switch revisions.

For one request, `processing`:

1. inspects every admitted occurrence independently;
2. sorts by descending `reference_quality_score`, then ascending request-local
   `occurrence_index` as the deterministic tie-break;
3. selects at most five occurrences;
4. applies the configured query-quality gate and prepares/searches every
   selected acceptable occurrence independently.

Repeated occurrences of one physical person remain valid and may occupy all
five slots. No tracking, identity clustering, cross-frame deduplication,
embedding merge, client ranking, top-1/top-2 margin or cross-pipeline person
link exists.

If none of the selected occurrences passes the query gate, the owner returns a
typed unacceptable-query result to `promo`; it does not weaken the gate to
manufacture a result.

## Exact Compatible Search

Each accepted selected detection runs one exact pgvector cosine search. Before
distance comparison, the query filters to:

- the immutable `pipeline_revision_id`;
- authoritative token-bound `spa_id` and owner-selected `visit_date`;
- active Photos only;
- complete `ready` state with ready private preview for that same revision;
- the optional confirmed capture-time window, when one is explicitly present.

No ANN index or fallback scope is used. A Photo with multiple compatible face
rows contributes its best cosine similarity once to that detection. A match is
returned only when query quality passes and cosine similarity is greater than
or equal to the immutable calibrated threshold. Results are ordered by
descending similarity and then ascending `photo_id` for deterministic ties.

For every unique threshold-valid Photo needed by result assembly, `processing`
loads its private ready preview and computes one deterministic 64-bit pHash
with the owner-local `opencv_phash64_v1` adapter. The hash is returned only for
Hamming-distance ranking; it is not a match gate, identity, persisted
lifecycle or reason to admit a weak candidate. On-demand computation is the
initial KISS path; persistence/caching requires measured latency evidence.

The typed result returned to `promo` contains, in selected-detection order:

- request-local occurrence index, rank, quality score and gate result;
- for every gate-passing detection, all unique threshold-valid Photo matches
  with `photo_id`, cosine similarity, private preview reference and pHash.

It does not contain a session, global candidate union, selected teaser set,
`N`, QR ticket or display state. Those are `promo`-owned outcomes.

## Failure And Deadline Behavior

- Incompatible/unvalidated revision or closed pre-warm/readiness returns `503`
  before admission and starts no search.
- A selected crop that cannot produce an acceptable query contributes an
  explicit rejected detection; if none remain, the domain outcome is
  `unacceptable_query`.
- An admitted native engine, PostgreSQL, pgvector or private-preview technical
  failure becomes the existing `5xx`/`internal_failure` path; partial matches
  MUST NOT publish a session.
- `promo` owns one request deadline and checks it before/after each processing
  call. A late result is discarded and MUST NOT publish a session or replace a
  terminal Attempt outcome. The pilot adds no killable subprocess or waiter
  queue.

## Verification Targets

- Mixed revision, СПА, date, visibility, readiness and optional-time fixtures
  prove all scope filters occur before exact distance comparison and that an
  unconfirmed clock adds no time filter.
- Ordered, tied, repeated-person and low-quality proposal fixtures prove
  server-authoritative at-most-five selection, deterministic ties, independent
  native query preparation and no forbidden grouping/margin behavior.
- Separate SFace and Buffalo M traces prove pre-warmed immutable revision
  identity and native processing/alignment paths without cross-revision reuse.
- Startup fixtures prove the selected matching read-only assets open readiness,
  while missing/mismatched or other-pipeline assets keep readiness closed with
  no Attempt, inference or processing-state mutation until an operator restart.
- Candidate fixtures prove threshold inclusion, per-Photo best-match grouping,
  deterministic ordering and on-demand pHash output without pHash admission.
- Ownership proof locates the implementation under `processing`, follows only
  accepted `inventory`/`serving_control` projections and finds no transport,
  generic-util, infrastructure, composition-root or foreign-write bypass.
