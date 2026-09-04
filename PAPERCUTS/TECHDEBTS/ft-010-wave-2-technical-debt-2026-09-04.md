---
description: Advisory technical-debt review of FT-010 Wave 2 closed by TASK-097, TASK-098 and TASK-099.
status: resolved
---
# FT-010 Wave 2 — technical-debt review

## Проверенная область

Запрос `/tech-debt wave 2` разрешён только в текущей FT-010 границе как
закрытые `TASK-097-T3-FT-010-W2`, `TASK-098-T3-FT-010-W2` и
`TASK-099-T3-FT-010-W2`. `TASK-096-T3-FT-010-W1`, одноимённые Wave 2 других
features и repository-wide surface не входили в checked scope; Wave 1
использовалась только как read-only dependency context.

Проверены:

- индексированные task cards и их фактические execute/verify/red-verify
  evidence в `.memory-bank/tasks/TASK-097-T3-FT-010-W2.task.json`,
  `.memory-bank/tasks/TASK-098-T3-FT-010-W2.task.json`,
  `.memory-bank/tasks/TASK-099-T3-FT-010-W2.task.json` и соответствующих
  `.tasks/TASK-097-T3-FT-010-W2/`, `.tasks/TASK-098-T3-FT-010-W2/`,
  `.tasks/TASK-099-T3-FT-010-W2/`;
- TASK-097 application surface:
  `src/face_moment/diagnostics/ground_truth_annotation_http.py`,
  `src/face_moment/diagnostics/attempt_investigation.py`,
  `src/face_moment/diagnostics/http.py`,
  `src/face_moment/entrypoints/backend.py` и
  `tests/diagnostics/test_ground_truth_annotation_http.py`;
- TASK-098 promotion surface:
  `src/face_moment/diagnostics/evidence.py`,
  `tests/diagnostics/test_ground_truth_annotation_promotion.py`,
  `tests/diagnostics/test_evidence_persistence.py` и связанные retry probes;
- TASK-099 retention surface:
  `src/face_moment/diagnostics/ground_truth_annotations.py`,
  `src/face_moment/diagnostics/evidence.py`,
  `src/face_moment/diagnostics/retention.py`,
  `tests/diagnostics/test_ground_truth_annotation_retention.py`,
  `tests/diagnostics/test_retention_cleanup.py` и связанные retry probes;
- текущая Attempt 2 correction для TASK-099. SHA-256 трёх production/test
  файлов и verifier probe совпали с хешами, записанными в
  `.tasks/TASK-099-T3-FT-010-W2/TASK-099-T3-FT-010-W2-S-RED-VERIFY-targeted-probe-02.md`.

`touched_files` использовался только как ориентир и был сопоставлен с execute
reports, commit `ef3d6c6`, текущим working-tree diff и retained evidence.

## Итог

Подтверждён один материальный технический долг низкого приоритета в test
infrastructure. Подтверждённого production debt в проверенной Wave 2 surface
не найдено. Это не меняет functional `PASS`, task-scoped `semantic-pass` или
closure любого из трёх tasks; отчёт advisory-only.

## Resolution

Resolved on 2026-09-04 before FT-011 implementation. The shared
`tests/disposable_postgresql.py` context manager now owns database creation,
head migration, `DATABASE_URL` restoration and forced teardown. The three
FT-010 Wave 2 modules retain only their subject-specific fixtures and tests.

Verification: the shared-helper failure-path regression plus the three migrated
modules passed (`23 passed`); the full `tests/diagnostics` suite, source and
helper mypy checks, Memory Bank lint and `git diff --check` also passed.

## Подтверждённые findings

### LOW / P2 — Wave 2 содержит три копии lifecycle disposable PostgreSQL database

Каждый новый task-specific test module самостоятельно реализует один и тот же
infrastructure primitive: получает base URL, создаёт UUID-named database через
AUTOCOMMIT admin engine, вручную меняет process-wide `DATABASE_URL`, выполняет
Alembic upgrade, создаёт рабочий Engine, затем восстанавливает environment и
делает forced drop:

- `tests/diagnostics/test_ground_truth_annotation_http.py:48-119`;
- `tests/diagnostics/test_ground_truth_annotation_promotion.py:30-58`;
- `tests/diagnostics/test_ground_truth_annotation_retention.py:32-60`.

TASK-097 дополнительно наполняет базу staff/session/application fixtures, но
create/migrate/environment/teardown primitive остаётся тем же. TASK-098 и
TASK-099 повторяют его почти построчно. Следовательно, изменение общего
database bootstrap, admin connection options, URL switching, migration setup
или cleanup требует синхронной правки как минимум в трёх новых Wave 2 местах.
Это наблюдаемый механизм повторной стоимости поддержки, а не замечание о стиле
или размере функций.

Практический impact ограничен test infrastructure: возможный drift между
копиями повышает maintenance burden и regression risk вокруг гарантированного
teardown, особенно при дальнейшем добавлении PostgreSQL-backed task tests.
Поэтому relative priority — LOW / P2.

Минимальное направление: вынести только общий context manager/fixture primitive
для создания, migration bootstrap и гарантированного удаления случайной test
database с безопасным восстановлением `DATABASE_URL`. Task-specific seed,
fixture scope, application wiring и concurrency orchestration оставить в
текущих modules; новый generic test framework не требуется.

## Неопределённость и исключённые кандидаты

- Dynamic gates в рамках этого advisory review повторно не запускались:
  PostgreSQL-dependent verification уже сохранена для каждого task, а текущие
  хеши TASK-099 Attempt 2 совпадают с red-verification evidence. Поэтому review
  не делает новых runtime или performance утверждений.
- Blanket failure sanitization и минимальный HTML/JavaScript в TASK-097 не
  записаны как debt: текущая evidence подтверждает требуемые authorization,
  CSRF, rollback, no-store и privacy outcomes, а отдельного наблюдаемого
  maintenance/reliability механизма поверх этих требований не установлено.
- Function-local imports между `evidence.py` и
  `ground_truth_annotations.py` показывают реальную owner-local coupling, но
  она непосредственно обслуживает promotion/removal transactions. Данных о
  самостоятельном материальном impact сверх принятой границы недостаточно,
  поэтому finding не создан.
- Для TASK-098 и TASK-099 Attempt 1 были доказаны semantic failures, но Attempt
  2 исправления и свежие adversarial probes закрыли конкретные stale promotion
  и late-commit orphan механизмы. Исторически исправленные defects не выданы за
  текущий technical debt.
- Возможные advisory-lock collision/performance эффекты не измерялись; текущая
  evidence доказывает только требуемую per-Attempt serialization. Оснований для
  уверенного finding здесь нет.
