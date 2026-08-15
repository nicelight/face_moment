---
description: Advisory technical-debt report for the explicit FT-002 W7 change surface.
status: active
---
# Технический долг — wave W7 / FT-002

## Проверенная область

Только explicit `/tech-debt wave W7` в заданном FT-002-контексте:
`TASK-040-T2-FT-002-W7`, его фактическая serving-control/admission change
surface и durable FT-002 semantic-completion evidence. Исторический
`TASK-016-T3-FT-001-W7` и существующий отчёт W7 исключены.

Проверены task card и feature completion:

- `.memory-bank/tasks/TASK-040-T2-FT-002-W7.task.json:1-119`;
- `.memory-bank/features/FT-002.md:144-227`;
- `.tasks/FT-002/FT-002-S-RED-VERIFY-final-report-docs-01.md:1-64`;
- `.protocols/TASK-040-T2-FT-002-W7/{context,plan,progress,verification,handoff}.md`;
- `.tasks/TASK-040-T2-FT-002-W7/*` — executor RED/GREEN/final evidence.

Нормативная база: `.memory-bank/architecture/system-architecture.md:212-238`,
`.memory-bank/contracts/boundary-map.md:209-239`,
`.memory-bank/domains/photo-admission.md:142-160`,
`.memory-bank/domains/photo-processing.md:240-256`,
`.memory-bank/states/lifecycle-map.md:61-76`,
`.memory-bank/testing/photo-processing.md:60-68` и
`.memory-bank/tasks/plans/IMPL-FT-002.md:116-125,152-164,211-219`.

## Фактическая change surface

- `src/face_moment/serving_control/ingest_target.py:41-175,177-262` — audited
  switch result, SPA row lock, target-B validation, exact-A guard and commit/
  reject transaction;
- `src/face_moment/serving_control/__init__.py:3-20` — public owner export;
- `src/face_moment/inventory/admission.py:47-88` — admission re-lock and
  current-target resolution;
- `tests/serving_control/test_serving_revision_switch.py:244-510` — focused
  disposable integration and admission/switch interleaving proof.

`src/face_moment/processing/serving_revision_guard.py` and its test are
TASK-039 dependency output, not TASK-040 implementation; they were checked
only as the processing boundary consumed by W7. Other dirty worktree paths
were excluded.

## Evidence и precise locations

- `.protocols/TASK-040-T2-FT-002-W7/verification.md:39-77,96-115` records the
  fresh focused PASS, target-validation/guard ordering, unchanged rejection
  snapshots, clear B commit and serial admission outcome.
- `.tasks/TASK-040-T2-FT-002-W7/TASK-040-T2-FT-002-W7-S-EXECUTE-final-report-code-01.md:6-47`
  lists the changed source and the same fresh-session focused proof.
- `tests/serving_control/test_serving_revision_switch.py:313-405,443-458`
  invokes each switch through a newly created `Session`; it does not exercise
  an already-used request session.
- `src/face_moment/serving_control/ingest_target.py:116-124` unconditionally
  enters `with self._session.begin()` for the owner command.
- `src/face_moment/inventory/photo_upload.py:83-121` demonstrates the existing
  session behavior: authentication and target reads begin SQLAlchemy's
  implicit read transaction, so the established admission flow explicitly
  calls `database_session.rollback()` before opening its short write boundary.
- A disposable probe in the existing verification image
  `05d9971f503b` (SQLAlchemy `2.0.41`) confirmed that after
  `session.execute(select 1)` / implicit autobegin, `session.begin()` raises
  `InvalidRequestError: A transaction is already begun on this Session`.
  The probe created no project artifact.

## Подтверждённые findings

### MEDIUM — owner switch has an implicit clean-Session precondition

`switch_serving_revision()` owns its transaction with `Session.begin()`, but
the boundary accepts a `Session` and the canonical input is an authenticated
operator command. If a future handler authenticates or reads request data on
the same request-scoped session and then calls this method without first
ending that read-only transaction, the method raises before it can return the
audited commit/reject result. The existing upload flow already has to encode
the same hidden sequencing rule with an explicit rollback, while all W7 tests
start the command with a fresh session.

Impact: the manual switch is coupled to undocumented caller-side transaction
state, so integrating the accepted owner command into an authenticated
transport/service path can fail deterministically and leave the command
without its promised result. This is a reliability and repeated-integration
cost, not a challenge to the task's serving-control semantics.

Smallest remediation direction: make transaction ownership explicit at the
composition boundary—either invoke the switch through a fresh short-lived
write session after read-only authentication, or explicitly end the
read-only transaction before calling the owner command—and add one integration
case that calls the switch after an authenticated/read transaction. Do not add
an unconditional rollback inside the repository, because that could discard
caller-owned pending work.

## Оценка и неопределённость

The task and FT-002 semantic verdict remain PASS/`semantic-pass`; the finding
is an integration reliability debt outside the task's explicitly forbidden
transport/auth implementation. No current W7 transport handler exists, so
the evidence establishes a latent boundary failure rather than a currently
reachable production endpoint failure. No separate stale-identity-map finding
was admitted because the reviewed production upload path expires state with
its explicit rollback and no current W7 caller exercises that path.

## Ограничения отчёта

Это bounded advisory review, не repository-wide audit и не повторный запуск
всех FT-002 gates. Отчёт не изменяет code, specs, requirements, task status,
lifecycle, gates, blockers, scheduler state, semantic verdict или debt
lifecycle.
