---
description: Task-local media-reference status defect found after final TASK-081 verification.
status: active
---
# TASK-081 non-ASCII media reference status defect

## Evidence

Fresh independent verification of `TASK-081-T3-FT-006-W2` Attempt 3/3 passed
all four task gates, the current-tree browser flow, default Caddy IPAM safety,
malformed purchase-target fail-closed handling and query-log redaction. Its
negative current-image probe then observed:

- an unknown ASCII `media_ref` returns the required empty `404`;
- a percent-encoded non-ASCII unknown `media_ref` returns an empty `500`;
- `src/face_moment/promo/qr_continuation.py` passes the decoded non-ASCII
  string to `hmac.compare_digest`, which raises `TypeError` before the existing
  `PhoneMediaNotFoundError` mapping in `src/face_moment/promo/http.py`.

Decisive evidence:

- `.tasks/TASK-081-T3-FT-006-W2/TASK-081-T3-FT-006-W2-S-VERIFY-final-report-docs-03.md`
- `.tasks/TASK-081-T3-FT-006-W2/verify_attempt_3_media_ref_probe.py`
- `.tasks/TASK-081-T3-FT-006-W2/verify-attempt-3-media-ref-output.json`
- `.tasks/TASK-081-T3-FT-006-W2/verify-attempt-3-results.json`

## Disposition

The defect is implementation-local with fixed accepted semantics, but it was
found on the third unsuccessful attempt. The final preserved-Judge assessment
is `REDIRECT`; per the operator-directed disposition,
`TASK-081-T3-FT-006-W2` remains authoritatively `in_progress` while this
`/autopilot` run halts with `HALT_FAILURE_BUDGET`. No fourth executor attempt,
T3 red verification, closure, promotion or later-task selection is authorized
in this run.

The excluded direct dependent `TASK-082-T3-FT-006-W3` remains `planned`
because its title starts exactly `Production acceptance:`. It cannot become
runnable while this failed dependency remains unresolved.

## Owner / exact resume route

There is no further action inside the current run. Resume only under an
explicitly authorized follow-up/retry route that preserves the three
unsuccessful boundaries and supplies a reviewed budget for the bounded
non-ASCII unknown-media `404` correction and focused regression. It must not be
treated as Attempt 4 within this exhausted run. Fresh functional `/verify` and
required T3 `/red-verify` remain due only under that future authorized route.

FT-003 remains ignored, TASK-075 remains blocked on external AC-004 evidence,
and every `Production acceptance:` record remains excluded and planned.

## Separately authorized follow-up

The operator later authorized overall Execution Attempt 4 as a separate
follow-up Attempt 1 of 5, without resetting or relabelling the preserved
original Attempts 1..3 or their `HALT_FAILURE_BUDGET` checkpoint. Execute
code-04 now records the bounded production correction, focused RED/GREEN,
fresh current-image empty-`404` probe and all four passing task gates.

The bug record remains active until fresh independent
`/verify TASK-081-T3-FT-006-W2`. Required T3 `/red-verify`, lifecycle closure,
dependent promotion and Production acceptance remain downstream and were not
performed by the follow-up executor.
