# Technical-debt review — wave W1

## Result

One material, workflow-level debt was confirmed in the checked W1 surface. It
does not invalidate the completed task verdicts or change workflow state; this
is an advisory report only.

## Checked scope

The closed FT-004/W1 implementation surface:

- `TASK-068-T3-FT-004-W1` — operator active-search-date page/API;
- `TASK-069-T2-FT-004-W1` — native SFace/Buffalo reference-query preparation
  and deterministic selection;
- `TASK-074-T3-FT-004-W1` — startup interruption of stale realtime Attempts;
- their actual source/tests, task-local execution receipts, independent
  `/verify` reports, T3 `/red-verify` reports, and W1 Memory Bank gates.

The remaining FT-004 tasks, deferred/blocked runtime tasks, and a repo-wide
architecture or dependency audit are outside this review.

## Evidence checked

- Indexed gate declarations use bare packaged-image commands in
  `.memory-bank/tasks/TASK-068-T3-FT-004-W1.task.json:16-19` and
  `.memory-bank/tasks/TASK-069-T2-FT-004-W1.task.json:22-25`.
- The current W1 execution receipts instead require a read-only host-source
  mount and `PYTHONPATH=/workspace/src`, for example
  `.protocols/TASK-068-T3-FT-004-W1/progress.md:23-28` and
  `.protocols/TASK-069-T2-FT-004-W1/handoff.md:20-25`.
- TASK-068 Attempt 2 reproduced an invalid authenticated failure because the
  bare `docker compose run --rm backend ...` command used stale
  `face-moment:dev` contents without the current test-helper correction:
  `.tasks/TASK-068-T3-FT-004-W1/TASK-068-T3-FT-004-W1-S-DEBUG-final-report-docs-01.md:38-59`.
- The same diagnosis records a confirmed repeated mechanism in prior task
  evidence and recommends a source/image-congruence guardrail:
  `.tasks/TASK-068-T3-FT-004-W1/TASK-068-T3-FT-004-W1-S-DEBUG-final-report-docs-01.md:102-127`.
- The corrected current-source run passed `3` focused tests, and W1 closed
  only after fresh independent verification; this demonstrates the workaround
  but not a repository-owned prevention mechanism.

## Confirmed findings

### MEDIUM — Indexed container gates do not enforce source/image congruence

The task cards prescribe commands that run code from the packaged Compose image
without mounting the current workspace or recording a digest. In this wave the
mechanism caused a real retry to execute an older test snapshot, producing
misleading `401` failures and requiring a diagnostic route plus a bounded
resume. The mechanism is confirmed as repeated in the inspected prior task
history, so this is more than a one-off operator mistake.

Impact: future `/exe` receipts can appear to verify the current change while
actually exercising stale source. This increases retry time, makes failures
non-diagnostic, and weakens trust in the task gate until a verifier detects the
drift independently.

Smallest remediation direction: make the `/exe` gate runner accept only a
receipt that either mounts the current workspace read-only with an explicit
`PYTHONPATH`, or follows a successful rebuild after the last source/test change
and records the resulting image digest/source marker. Keep the task card's
semantic command intent unchanged; the guard belongs in the shared executor or
its receipt validation, not in each feature implementation.

## Uncertainty

This review did not change the executor, task-card gate schema, or image build
workflow, and it did not audit unrelated waves. The report does not determine
whether the cheapest durable guard is a wrapper, receipt validator, or schema
extension; that design choice belongs to the `/exe` workflow owner.
