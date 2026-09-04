---
description: Reproducible verification contract for FT-011 threshold profiles, one-dimensional quality analysis and Calibration boundaries.
status: active
last_updated: 2026-09-04
source_of_truth:
  - .memory-bank/testing/calibration.md
---
# Calibration Verification

## Scope And Authority

This specification defines the reproducible proof for `REQ-CAL-001..003` and
`FT-011-AC-001..008`. Product outcomes remain owned by the
[PRD](../prd.md) and [FT-011](../features/FT-011.md); this document supplies the
fixed evaluation method and evidence shape needed to verify them.

`diagnostics` owns annotated-sample selection, Calibration recommendations and
their drill-down. It calls `processing` through its offline-evaluation boundary.
Only `serving_control` may apply an explicitly developer-confirmed setting by
the audited command in the [boundary map](../contracts/boundary-map.md).
The persisted ground truth comes only from the immutable calculation projection
in [Ground-Truth Annotations](../domains/ground-truth-annotations.md#calculation-ready-owner-boundary);
absence is not synthesized as an outcome.

## Fixed Evaluation Input

Each verification run uses one immutable fixture snapshot containing:

- unique selected existing Photo UUIDs plus the SHA-256 identity of each
  inventory-owned original JPEG;
- the selected applicable annotated Attempts, their required available input
  evidence and their `correct`, `false` and `missed` ground truth;
- pipeline code/revision, release and parameter-set identities;
- the finite candidate threshold or quality-gate values under evaluation;
- the current serving value and the score/outcome evidence needed to reproduce
  every aggregate count;
- stable Attempt locators for drill-down.

All profiles in one threshold comparison use the same snapshot and candidate
set. Processing loads each selected original once, verifies its frozen digest
and gives those same bytes plus the same selected Attempt snapshot to every
selected SFace/Buffalo M revision without reupload. SFace and Buffalo M retain
separate native pipeline evaluation and result rows; the proof never combines
embeddings or participant-facing results across pipeline revisions. A missing
or changed original or required Attempt input fails the run visibly instead of
shrinking or rebuilding the dataset.

## Threshold Profile Oracle

For every candidate threshold, the independent oracle derives aggregate
`correct`, `false` and `missed` counts from the fixed annotation snapshot, then
calculates:

```text
precision = correct / (correct + false)
recall    = correct / (correct + missed)
F1        = 2 * correct / (2 * correct + false + missed)
```

An undefined denominator is shown as unavailable rather than `NaN` or infinity.
When every candidate has undefined F1, `Balance` produces no proposed value and
the result visibly reports insufficient annotated evidence with the sample
size. No such result can mutate serving state.

Candidates are ranked deterministically:

1. `Best face match`: fewer `false`, then more `correct`, then the higher
   (stricter) threshold.
2. `Balance`: higher aggregate F1, then fewer `false`, then fewer `missed`, then
   the higher (stricter) threshold.
3. `Minimum missed faces`: fewer `missed`, then fewer `false`, then the higher
   (stricter) threshold.

The higher-threshold final tie-break only chooses a stable numeric proposal
when all governing counts/metrics are already equal. Implementations may
generate finite candidates by any deterministic local tactic, but the candidate
list used by a run MUST be retained in its reproducibility evidence; this spec
does not introduce a new product-level search grid or weighted cost.

For each winning profile, verification compares the proposed threshold, counts,
precision, recall and sample size to the oracle and reconciles the aggregate to
the linked contributing Attempts.

## One-Dimensional Quality Analysis

Quality-gate verification changes exactly one gate per scenario while holding
the annotated snapshot, pipeline/revision, face threshold and all other quality
gates fixed:

- face size and detection confidence use minimum cutoffs;
- brightness uses one allowed range;
- pose uses maximum absolute yaw, pitch and roll;
- blur cutoff direction follows the named score's actual documented semantics.

Each result exposes current/proposed value, sample size, kept/rejected detection
counts and the expected `correct`/`false`/`missed` changes. The retained run
evidence names the deterministic candidate policy used. It MUST NOT apply a
joint multidimensional search or invent an unaccepted weighted product
objective.

## Before/After And Manual-Apply Proof

- A before/after fixture selects two stored release or parameter-set snapshots
  over the same dataset hash, verified Photo original JPEG bytes and applicable
  annotations. Aggregate differences MUST reconcile to the contributing
  Attempts and stored versions/parameters/outcomes. A different dataset hash is
  rejected rather than presented as a comparable delta.
- Generating or viewing any recommendation MUST leave the current serving
  settings and revision unchanged.
- Only a separate authenticated developer action through `serving_control` may
  apply the chosen setting. Success and failure are audited; failure preserves
  the previously committed setting. A pipeline-revision change also follows the
  manual revision-switch contract.

No separate experimentation platform, automatic apply path or serving fallback
is part of this proof.

## Worker, Recovery And Retention Proof

The worker scenario starts from isolated test state with queued Photo work and
one developer-triggered Calibration run:

1. Let Calibration occupy the shared `BackgroundPhotoWorker` and demonstrate
   that Photo processing may be delayed.
2. Restart the worker during the run.
3. Verify the run is visibly terminal as `failed` or `interrupted`, queued Photo
   processing resumes, and no replacement Calibration run starts automatically.
4. Verify an explicit developer rerun is required and uses fresh run evidence.

The ordinary-run retention scenario applies the existing 90-day cutoff to
isolated old/equal/new terminal and active Calibration rows. It proves only old
terminal rows are deleted, the public latest-result shape is unchanged and one
repeat is safe.

The separate promoted-case scenario proves that confirmed manual promotion
preserves only the curated PRD `NFR-DATA-03` subset until confirmed explicit
deletion; other diagnostic media, Promo screenshots and technical logs retain
their ordinary expiry. Whole-subset deletion remains safe to repeat.

## Acceptance Evidence Map

| Feature criterion | Required proof |
|---|---|
| `FT-011-AC-001` | Fixed-snapshot oracle for all three profiles, accepted F1/tie-break ordering, exact metrics and Attempt drill-down. |
| `FT-011-AC-002` | One-gate-at-a-time fixtures with unchanged peer gates and required current/proposed/count deltas. |
| `FT-011-AC-003` | Two stored release/configuration snapshots consume identical verified Photo original JPEG bytes and applicable Attempt selection without reupload, remain separate by run/dataset/revision and reconcile to annotated Attempts. |
| `FT-011-AC-004` | Recommendation generation leaves serving state unchanged; only the separate audited command may mutate it. |
| `FT-011-AC-005` | Shared-worker restart yields visible terminal Calibration, resumed Photo work and no automatic rerun. |
| `FT-011-AC-006` | An all-candidates-undefined output exposes selected/applicable sample counts, produces no proposal and leaves serving state unchanged. |
| `FT-011-AC-007` | Fixed-cutoff terminal ordinary Calibration expiry, active/equal/new preservation, safe rerun and unchanged public cleanup result. |
| `FT-011-AC-008` | Confirmed selected-only promotion, ordinary-cleanup preservation and idempotent explicit whole-subset deletion. |

All fixtures must be isolated, deterministic and safe to rerun. Project-native
build/typecheck and relevant unit/integration tests remain routed by the
[testing index](index.md); this document does not create a new quality-gate
category.
