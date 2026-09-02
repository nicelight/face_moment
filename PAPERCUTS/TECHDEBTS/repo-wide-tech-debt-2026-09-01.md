---
description: Repository-wide advisory technical-debt review of the current implementation tree.
status: active
---
# Repository-wide technical-debt review — 2026-09-01

## Проверенная область

Проверен текущий рабочий tree целиком, включая незакоммиченные FT-008/FT-009
изменения:

- 82 Python source files (`15 218` строк) под `src/face_moment/`;
- 19 first-party client files (`4 495` строк) под `client/`, без vendored
  MediaPipe/WASM и model assets;
- 18 Alembic migrations, HTTP/entrypoint composition, `Dockerfile`,
  `compose.yaml`, Caddy и project scripts;
- 72 Python test files / 280 collected tests и 20 Node test files;
- существующие task verification reports, bug evidence и ранее выпущенные
  bounded technical-debt reports, после чего каждый перенесённый finding был
  повторно сопоставлен с текущим source.

Это advisory review. Он не меняет implementation, specs, tasks, statuses,
gates или workflow state.

## Итог

Точечный рефакторинг нужен. Полная переработка архитектуры не обоснована.
Подтверждены девять механизмов долга: один текущий HIGH correctness/reliability
дефект, три приоритетных repo-wide seam проблемы и пять более узких механизмов
повторной стоимости и regression risk.

Размер файлов сам по себе finding не образует. Несмотря на крупные
`client/app.js`, `diagnostics/evidence.py`, HTTP adapters и realtime
composition, проверка не показала необходимости делить их только ради длины.

## Проверки и наблюдения

- Current-source `mypy --strict` прошёл: `Success: no issues found in 82 source
  files`.
- Current-source Python suite собрал 280 tests. Штатный Compose run завершился
  с 30 failures; часть относится к текущему failed/in-progress FT-009 surface,
  поэтому количество failures не трактуется как 30 findings.
- Изолированные reruns подтвердили stale Alembic assertions и Foundation
  metadata assertion независимо от test order.
- `caddy validate` подтвердил `Valid configuration`, хотя два Python tests
  отвергают тот же файл из-за literal indentation comparison.
- `node --test tests/client/test_*.mjs` дал 42 pass и 2 setup failures: оба
  Playwright specs не могут разрешить `playwright/test` из repository root.
- Import probe для одного leaf
  `face_moment.diagnostics.server_events` загрузил 45 project modules, а также
  `cv2`, NumPy и boto3; cold import занял около 1.36 s в project image.

## Подтверждённые findings

### HIGH / P0 — best-effort event emission зависит от commit-expired ORM row

В `src/face_moment/entrypoints/realtime.py:211-222` owner Attempt создаётся и
commit-ится, после чего `emit_attempt_admitted(..., attempt)` читает ORM object.
SQLAlchemy expire-on-commit превращает такой read в implicit PostgreSQL refresh.
Независимый real-database latch воспроизвёл блокировку participant path до
снятия SQL latch; это зафиксировано в
`.tasks/TASK-090-T3-FT-009-W1/TASK-090-T3-FT-009-W1-S-VERIFY-final-report-docs-03.md`
и durable bug evidence
`.memory-bank/bugs/task-090-realtime-event-post-commit-sql.md`.

Механизм уже пережил несколько correction attempts, поэтому это не единичная
ошибка строки, а подтверждённое ORM-lifecycle coupling. Он нарушает обещание,
что logging-only работа не задерживает participant path.

Практический impact: diagnostics sink способен добавить PostgreSQL wait в
критический realtime request даже до фактической постановки события в
non-waiting queue.

Минимальное направление: пока owner row загружен, снять immutable primitives
(`attempt_id`, `correlation_id` и first-event decision), выполнить owner commit,
затем передать в emitter только snapshot. После commit producer не должен
читать ORM state или выполнять SQL. Такой же инвариант следует проверить для
terminal producer, не вводя outbox или новый broker.

### MEDIUM / P1 — пять HTTP adapters создают и уничтожают Engine на каждый request

Одинаковый `_database_session()` присутствует в:

- `src/face_moment/platform/auth/http.py:131-137`;
- `src/face_moment/inventory/http.py:214-220`;
- `src/face_moment/serving_control/http.py:160-166`;
- `src/face_moment/diagnostics/http.py:259-265`;
- `src/face_moment/promo/http.py:469-476`.

Каждый handler call выполняет `create_engine(...)`, открывает одну Session и
сразу `engine.dispose()`. Таким образом backend не переиспользует SQLAlchemy
pool и повторяет lifecycle/connection setup во всех capability adapters.

Практический impact: лишний connection churn на каждом HTTP request,
пять копий настройки DB lifecycle и пять monkeypatch seams в tests. Изменение
pooling, credentials или connection policy приходится синхронизировать вручную.

Минимальное направление: backend composition root владеет одним process-local
Engine/session factory и передаёт narrow session factory route registrars.
Diagnostics event writer сохраняет отдельный изолированный Engine/Session,
поскольку это его принятый non-blocking isolation contract.

### MEDIUM / P1 — eager package re-exports превращают leaf import в широкую загрузку системы

`diagnostics/__init__.py:3-39`, `promo/__init__.py:3-69`,
`processing/__init__.py:3-29`, `inventory/__init__.py:1-14` и
`serving_control/__init__.py:3-40` eager-import почти всех public symbols.
При импорте только `diagnostics.server_events` Python сначала выполняет
`diagnostics/__init__.py`, затем через investigation/Promo/Processing втягивает
45 project modules и тяжёлые cv2, NumPy и boto3.

Практический impact: startup/tooling/tests для лёгкого leaf boundary зависят от
неотносящихся ML/object-store modules; import side effects регистрируют 15
SQLAlchemy tables и уже ломают изолированный
`tests/test_foundation.py::test_one_empty_metadata_owns_the_foundation_schema`.
Ранее в этом проекте тот же класс механизма уже создавал order-dependent
circular import; конкретный прежний cycle был исправлен, но eager cascade снова
расширился.

Минимальное направление: сделать capability `__init__.py` тонкими и перевести
production consumers на concrete-module imports. Оставить только действительно
стабильные dependency-neutral exports; lazy export framework не нужен.

### MEDIUM / P1 — repo-wide regression suite содержит исторические и text-shape assertions, которые ломаются от допустимой эволюции

Подтверждены три независимых варианта:

1. `tests/inventory/test_admission_lineage.py:204-209` после upgrade до `head`
   требует, чтобы global head всё ещё был migration `0009`.
   `tests/processing/test_processing_persistence.py:138-143` требует, чтобы
   current head непосредственно зависел от `0007`. Оба tests отдельно падают
   при корректном единственном head `0018`.
2. `tests/staff_access/test_sessions.py:156-162` и
   `tests/inventory/test_ingest_targets_api.py:151-158` сравнивают literal
   Caddy block с фиксированным количеством tabs. Текущий Caddyfile семантически
   валиден, но дополнительный `route` nesting делает assertions красными.
3. `tests/test_foundation.py:3-12` сначала импортирует все composition roots, а
   затем требует пустой shared `Base.metadata`. Test падает даже отдельно,
   поскольку реальные model imports закономерно регистрируют tables.

Практический impact: добавление следующей migration, безопасная перегруппировка
Caddy directives или новый model import делает full gate красным без product
regression. Реальные failures смешиваются с ложными и теряют диагностичность.

Минимальное направление: historical migration tests проверяют named revision и
его собственный predecessor; отдельный invariant проверяет ровно один global
head. Caddy проверяется через `caddy validate/adapt` и executable route smoke,
а не whitespace. Foundation test должен проверять один shared schema/Base и
отсутствие второго metadata owner, а не вечную пустоту metadata после product
imports.

### MEDIUM / P2 — container gates не гарантируют соответствие image текущему source, а rebuild плохо кэширует dependencies

Текущий `face-moment:dev` не содержит новые FT-008/FT-009 modules: pytest без
`PYTHONPATH=/workspace/src` импортировал installed wheel и завершился
`ModuleNotFoundError` для `diagnostics.attempt_investigation`; тот же run с
explicit current-source path собрал все 280 tests. Аналогичный механизм уже
зафиксирован в
`PAPERCUTS/TECHDEBTS/wave-W1-tech-debt-2026-08-22.md`.

При этом `Dockerfile:8-10` копирует `src/` перед `pip wheel .`, а команда wheel
собирает также полный dependency set. Любое source-only изменение инвалидирует
слой и повторно разрешает/скачивает тяжёлые ML wheels; механизм повторно
зафиксирован в `PAPERCUTS/gpt-5 __ 09-01-2026 13.40.md` и
`PAPERCUTS/gpt-5.6-sol __ 08-28-2026 03.13.md`.

Практический impact: быстрый gate может незаметно тестировать stale code, а
надёжный rebuild делает малое изменение многоминутным и зависит от сети.

Минимальное направление: executor receipt должен доказывать либо current-source
read-only mount + `PYTHONPATH`, либо successful post-change image build с
digest/source marker. Docker build отдельно кэширует pinned dependency wheels,
а application wheel строит `--no-deps`; новый build system не нужен.

### MEDIUM / P2 — effective display status вычисляется в двух местах

`src/face_moment/promo/display_outcome.py:213-221` и
`src/face_moment/promo/client_timing.py:144-153` отдельно реализуют temporal
rule `pending -> unconfirmed`. Этот механизм уже вызвал semantic divergence в
TASK-083 и остаётся в current source.

Практический impact: изменение display expiry semantics требует синхронно
править две projections; при рассинхронизации operator views получают разные
effective states одного Attempt.

Минимальное направление: одна pure Promo-owned функция вычисляет effective
display status и используется обеими projections. Stored state и service layer
не меняются.

### MEDIUM / P2 — public realtime routes вручную перечислены второй раз в Caddy

FastAPI routes находятся в `src/face_moment/entrypoints/realtime.py:146-294`,
но central-origin ownership отдельно перечислено matcher-ом
`deploy/Caddyfile:16,38-45`. Ранее пропущенный child path реально ушёл в backend
fallback вместо realtime; текущий exact matcher устраняет тот случай, но
оставляет второй ручной registry.

Практический impact: каждый новый realtime child route требует синхронного
изменения application, Caddy и text assertions; ошибка обнаруживается только
на edge path.

Минимальное направление: если security contract не требует exact allow-list,
один bounded `/api/realtime/*` capability prefix с существующим body limit.
Если allow-list обязателен, сохранить exact matcher, но заменить text assertion
на disposable executable Caddy routing smoke.

### MEDIUM / P3 — permanent browser-recovery regression остаётся непереносимым и допускает false positive

`tests/client/test_browser_recovery.spec.mjs:7-8` требует bare
`playwright/test`, но в repository нет Node manifest/lock/config или
project-owned resolver. Обычный Node run воспроизвёл два setup failures для
Playwright specs.

В том же test `MANAGED_CONFIG` сохраняет `sensor_id`
(`:17-25`), тогда как production reader принимает `sensorId`
(`client/sensor-config.js:14-29`). После restart test сравнивает только raw
localStorage (`:154-167`), поэтому непригодная для приложения конфигурация
считается сохранённой.

Практический impact: clean checkout не имеет очевидного постоянного recovery
gate, а успешно запущенный test может пропустить невозможность прочитать sensor
configuration production-кодом.

Минимальное направление: один переносимый project-owned entrypoint на уже
принятом Playwright runtime; seed через `saveSensorConfig()` и assertion через
`readSensorConfig()` после relaunch. Полный frontend toolchain не требуется.

### MEDIUM / P3 — serving revision switch имеет скрытое требование к чистой Session

`src/face_moment/serving_control/ingest_target.py:124-132` принимает Session и
безусловно открывает `with self._session.begin()`. После любого preceding read
SQLAlchemy autobegin уже активен, и второй `begin()` детерминированно выбрасывает
`InvalidRequestError`. Текущие callers/tests используют свежую Session; HTTP
transport для switch пока отсутствует, поэтому defect латентный, но mechanism
сохраняется.

Практический impact: будущая authenticated handler integration сломается, если
authentication/read и command разделят одну request Session без явного конца
read transaction.

Минимальное направление: composition boundary вызывает switch в отдельной
короткой write Session либо явно завершает read transaction до owner command;
добавить integration case после authenticated read. Безусловный rollback внутри
repository не нужен, поскольку может потерять caller-owned work.

## Не принятые как debt наблюдения

- Крупные файлы и функции без воспроизведённого change/reliability mechanism.
- Production `type: ignore` в ORM-to-Literal projections: strict mypy зелёный,
  а отдельная runtime ошибка этими строками не подтверждена.
- Отсутствие coverage percentage, Ruff/complexity gate или дополнительной
  документации само по себе.
- Уже исправленный multi-revision Photo status lookup и прежний unbounded
  upload intake: current source передаёт admission revision, а Caddy имеет
  pre-application upload bounds.

## Практический порядок

1. Устранить P0 ORM read после commit и вернуть точный non-blocking proof.
2. Восстановить диагностичный repo-wide gate: migration/Caddy/Foundation tests.
3. Сузить eager package exports и дать backend один process-owned DB
   session-factory lifecycle.
4. Закрыть source/image congruence и dependency cache invalidation.
5. Выполнить три малых семантических/test refactors: effective display state,
   realtime edge ownership и browser-recovery test; clean-Session switch seam
   закрыть до появления transport caller.

## Неопределённость

- Production load/profile не запускался, поэтому per-request Engine finding
  основан на подтверждённом lifecycle/connection mechanism, а не на измеренном
  latency percentile.
- Полный browser UAT и pilot-host restart не повторялись; browser finding
  ограничен permanent test source и воспроизведённым module-resolution failure.
- Worktree содержит `TASK-090` в `failed`, `TASK-089` в `in_progress` и
  заблокированные dependents. Поэтому общий pytest result — честный снимок
  текущего tree, но не утверждение, что все 30 failures являются накопленным
  debt завершённых задач.
- Report не назначает lifecycle tasks и не меняет уже записанные verdicts.
