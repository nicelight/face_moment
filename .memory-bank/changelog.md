---
description: Compact current Memory Bank state; historical task evidence stays in task records.
status: active
---
# Changelog

## [2026-09-02] FT-008 closure and FT-009 producer slice

- Verified: FT-008 is complete. TASK-088 and TASK-089 are `done`, the
  feature-level adversarial review is `semantic-pass`, and `REQ-DIAG-003` is
  verified.
- Implemented: FT-009's isolated redacted persistence slice
  (`FT-009-AC-002`) is closed by TASK-094 with functional PASS and
  task-scoped semantic-pass.
- Reconciled: TASK-090 remains failed historical evidence and its resolved bug
  note is archived. TASK-091 and TASK-093 no longer carry the obsolete failed-
  dependency block; TASK-091 is `in_progress`, while TASK-093 remains `planned`.
- Clarified: one explicit bounded Promo-owned QR correlation query after commit
  is accepted ordinary owner access, not diagnostics writer latency. No global
  zero-SQL requirement was introduced.
- Local development now runs current editable Python source through locked
  `uv`; only PostgreSQL/pgvector and MinIO stay in the daily Compose overlay.
  The unchanged base Compose topology remains the packaged-runtime smoke.
- Backend HTTP adapters now reuse one composition-owned SQLAlchemy Engine and
  open a short Session per request. The Engine is disposed at backend shutdown;
  the diagnostics writer keeps its contract-required independent Session path.
  API, transaction ownership, schema and capability ownership are unchanged.

## [2026-08-29] Development baseline after FT-001…FT-007

- All development work for `FT-001` through `FT-007` is terminal. Their
  completed task records are historical evidence, not active work or blockers.
- `TASK-075-T3-FT-004-W5` is `done_for_prod`. Its development evidence is
  accepted; `FT-004-AC-004` remains production-only and does not block
  development scheduling.
- `TASK-078-T3-FT-005-W2`, `TASK-081-T3-FT-006-W2` and
  `TASK-086-T3-FT-007-W3` are `done`. Their earlier failures, retry limits and
  halted-run records are superseded historical checkpoints.
- The remaining non-terminal `FT-001`…`FT-007` records are title-prefixed
  `Production acceptance:` tasks. They remain deferred until production and
  are excluded from development autopilot.
- No active bug or development blocker remains for `FT-001`…`FT-007`.

Current lifecycle authority is `.memory-bank/tasks/*.task.json`. Historical
verification entries inside terminal task records preserve provenance but do
not override the record's top-level status.
