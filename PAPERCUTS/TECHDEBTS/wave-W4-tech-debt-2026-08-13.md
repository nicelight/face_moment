---
description: Advisory technical-debt review for the actual W4 processing surface and the carried W3 import finding.
status: active
---
# Technical-debt review — wave W4

## Checked scope

Actual `TASK-024-T2-FT-002-W4` single-Photo orchestration,
`TASK-027-T2-FT-002-W4` compatible searchable-truth projection, and
`TASK-032-T2-FT-002-W4` queue/recovery-health projection, including the
`processing` package seam changed as the bounded prerequisite correction for
the W3 import finding. This is not a repository-wide review.

## Verdict

`APPROVE` — no material technical debt is confirmed in the checked W4 surface.

## Evidence checked

- Indexed records and independent `PASS` reports for TASK-024, TASK-027 and
  TASK-032; their scoped tests cover claimed-revision terminal outcomes,
  complete/current/active searchability, and repeatable read-only queue health.
- `src/face_moment/processing/photo_orchestration.py:59-177` composes one
  claimed Photo through existing adapter, derivative, terminal-publication and
  bounded-failure owners; no worker loop, scheduler or duplicate lifecycle is
  present.
- `src/face_moment/processing/searchable_projection.py:45-103` and
  `health_projection.py:48-90` are direct current-state reads. The former
  derives all required searchability facts; the latter derives the five
  counts, nullable oldest pending time and singleton runtime facts without a
  history or metrics store.
- Fresh current-image check on
  `face-moment@sha256:74d272f5b64c43a705cd3e80aa67a2b3afc290512d69d78ded4046e7ab41a4c8`:
  host/image hashes matched for the three W4 modules and their three focused
  tests; packaged pytest for those tests exited `0` (`6 passed`).

## Material findings

None.

## Prior W3 HIGH — resolved

The prior order-dependent cycle is not carried forward. The current
`processing/__init__.py:3-22` no longer eagerly exports `worker_claims` or
terminal-publication symbols; the two former cycle consumers import concrete
submodules at `inventory/admission.py:13-14` and
`serving_control/ingest_target.py:11-15`.

On the exact current image, each fresh process succeeded:

```text
import face_moment.serving_control.ingest_target
import face_moment.serving_control.ingest_target; import face_moment.processing
```

Packaged collection also succeeded for the affected terminal and health
consumers (`5` and `1` tests). This directly disproves the W3 HIGH mechanism
on the packaged source seam; no new reliability concern was observed.

## Scheduler implication

This advisory report changes no status, gate or promotion. It admits no W4
debt finding and records the W3 HIGH as resolved; ordinary scheduler/owner
handling of the three existing T2 `PASS` results remains the only route.
