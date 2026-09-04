---
description: Diagnostics-owned ground-truth annotation shape, calculation input and retention boundary.
status: active
last_updated: 2026-09-04
source_of_truth:
  - .memory-bank/domains/ground-truth-annotations.md
---
# Ground-Truth Annotations

## Scope And Owner

`diagnostics` owns ordinary ground-truth annotations and their calculation
projection. An annotation is protected diagnostic data linked logically to one
promo-owned core Attempt. Diagnostics reads the Attempt only through the
accepted `diagnostics -> promo` application boundary and MUST NOT mutate or
reconstruct it.

The runtime persistence path is PostgreSQL table
`face_moment.ground_truth_annotations` through a diagnostics-owned repository.
Annotations do not enter `ordinary_manifest`: that evidence shape retains its
existing rejection of names and annotation fields.

## PostgreSQL Shape

One next-linear Alembic revision creates:

| Field | Contract |
|---|---|
| `annotation_id` | UUID primary key. |
| `attempt_id` | Required promo-owned server Attempt UUID used as a logical cross-owner reference; no foreign key or ownership-crossing cascade. |
| `target_kind` | Exactly `detection` or `person`. |
| `detection_occurrence_index` | Non-negative integer only for a detection target; null for a person target. |
| `participant_name` | Trimmed non-empty Unicode text of at most 200 characters. |
| `outcome` | Exactly `correct`, `false` or `missed`. |

The valid pairs are deliberately small:

- `detection` requires an existing evidence `occurrence_index` and permits
  `correct|false`;
- `person` has no detection index and permits only `missed`.

At most one ordinary annotation may target the same
`(attempt_id, detection_occurrence_index)`. Multiple person-level `missed` rows
are allowed because the pilot may contain several missed participants and has
no participant registry. Annotation identity, Attempt identity and target are
immutable; a correction may replace only the participant name or outcome, and
a wrong target is removed and created again.

## Calculation-Ready Owner Boundary

For an existing readable Attempt, diagnostics can create, correct, remove and
list validated annotation rows, then return an immutable calculation snapshot
ordered by `annotation_id`. A detection target is accepted only when its
occurrence exists in the current readable ordinary evidence. A person-level
`missed` row needs no local-detector occurrence, frame upload or detector-miss
proof.

The calculation projection contains only persisted annotations. No row means
missing ground truth and is excluded rather than synthesized as an outcome.
Writes reject an Attempt whose diagnostics evidence is already `expired` or
`removed`; an absent evidence row still permits a person-level `missed` row.
FT-011 may compose this projection with the Attempt snapshot, scores and
parameters already owned by promo/diagnostics, but it MUST NOT infer an
annotation from result or evidence absence.

## Promoted Annotation Snapshot

When a later authorized Calibration flow selects annotations for promotion,
diagnostics copies only the selected immutable annotation fields into the
existing `promoted_subset.annotations` array:

- `annotation_id`, `attempt_id` and target fields;
- `participant_name`;
- `outcome`.

The snapshot is validated against current diagnostics-owned rows before it is
stored. Promotion does not prolong the ordinary rows or copy the whole evidence
bundle. One diagnostics-owned whole-subset deletion operation clears the
retained subset and its timestamp; repeating it after the subset is absent is a
no-op success. No annotation-specific deletion route, archive or history is
added.

## Ordinary Annotation Removal

Ordinary retention and the existing explicit ordinary-evidence removal
transition delete every ordinary annotation for the supplied Attempt through
the diagnostics repository. Scheduled retention does so before promo may delete
its core Attempt; explicit removal does so before the transition returns. An
absent annotation set is an idempotent owner-local no-op. Retention uses the
promo-selected Attempt cutoff; annotation creation time does not extend it.

## Verification Targets

- The next-linear migration upgrades/downgrades a disposable database and
  proves the exact checks, partial detection-target uniqueness and absence of a
  cross-owner foreign key/cascade.
- Repository/application fixtures prove valid create/correct/remove/list,
  rejection of invalid target/outcome pairs, detection existence checks,
  expired/removed write rejection, multiple person-level misses and immutable
  ordered calculation snapshots.
- Missing annotation yields no calculation row; explicit `missed` remains a
  row without any local-detector proof or frame upload.
- Disposable promotion fixtures prove selection validation, exact snapshot
  fields and idempotent whole-subset deletion.
- Disposable fixtures prove both scheduled and explicit ordinary removal,
  promoted snapshot preservation and one safe repeat per path without mutating
  promo-owned state.
