---
description: Exhausted-retry failure history for TASK-101 Calibration missing-original terminalization.
status: active
last_updated: 2026-09-05
---
# TASK-101 Calibration Missing-Original Terminalization

## Failure

`TASK-101-T3-FT-011-W2` exhausted its initial attempt plus two bounded retries.
The final semantic verifier reproduced a supported `PrivateObjectStore` S3
`NoSuchKey` path: it escapes offline Calibration input handling, releases the
singleton worker, and leaves the durable Calibration run `running` instead of
recording the required terminal `dataset_unavailable` failure. This violates
`FT-011-AC-005`; TASK-101 remains immutable failed evidence.

## Evidence

- [Final semantic verification](../../.protocols/TASK-101-T3-FT-011-W2/red-verification.md)
- [Final semantic report](../../.tasks/TASK-101-T3-FT-011-W2/TASK-101-T3-FT-011-W2-S-RED-VERIFY-final-report-docs-01.md)
- [Authoritative failed task](../tasks/TASK-101-T3-FT-011-W2.task.json)

## Follow-up Route

Any repair must use the normal FT-011 planning, review and readiness route.
It must preserve the selected direct-adapter, singleton-worker, manual-rerun
and serving-boundary constraints already proven by TASK-101.
