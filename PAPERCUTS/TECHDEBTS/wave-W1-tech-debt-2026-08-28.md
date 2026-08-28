# Technical-debt review — wave W1 (TASK-080 and TASK-083)

## Result

CONCERNS. В проверенной W1 surface подтверждены два материальных механизма
technical debt, оба в реализации TASK-083. Они не отменяют финальные PASS и
semantic-pass, не блокируют завершённые задачи и не меняют workflow state;
отчёт носит только advisory-характер.

В TASK-080 материального maintainability или operational debt по проверенным
изменениям и evidence не подтверждено.

## Checked scope

Проверена только фактическая implementation surface двух завершённых задач:

- `TASK-080-T3-FT-006-W1`: migration
  `migrations/versions/0014_promo_browser_access.py`, browser-access model и
  repository в `src/face_moment/promo/session.py`, package export и focused
  `tests/promo/test_qr_browser_access.py`;
- `TASK-083-T3-FT-007-W1`: migration
  `migrations/versions/0015_promo_attempt_client_timing.py`, client sender и
  wiring, Promo Attempt/timing model, repository и projections, realtime HTTP
  adapter, `deploy/Caddyfile`, package export и focused Python/Node tests;
- indexed task cards, прямые canonical specs, execution reports, независимые
  `/verify` reports, T3 `/red-verify` reports и task-local edge/projection
  evidence этих двух задач.

Вне scope: другие W1-задачи, FT-003, TASK-075, Production acceptance records,
feature/task lifecycle, scheduler, unrelated FRP/server-parameter dirt и
repo-wide audit.

## Evidence checked

- TASK-080 final adversarial evidence подтверждает одну durable shared row,
  strict 30/60-minute boundaries, atomic monotonic updates, restart durability
  и отсутствие второго state store или scheduler:
  `.tasks/TASK-080-T3-FT-006-W1/TASK-080-T3-FT-006-W1-S-RED-VERIFY-final-report-docs-01.md:10-39`.
- Existing display projection уже выводит `pending -> unconfirmed` в
  `src/face_moment/promo/display_outcome.py:193-216`; TASK-083 повторяет это
  правило отдельно в `src/face_moment/promo/client_timing.py:146-153` и
  возвращает его из второй projection в строках `160-175`.
- Первое adversarial review TASK-083 воспроизвело именно divergence этих
  значений: tag был `display_unconfirmed`, а projection всё ещё возвращала raw
  `pending`:
  `.tasks/TASK-083-T3-FT-007-W1/TASK-083-T3-FT-007-W1-S-RED-VERIFY-final-report-docs-01.md:14-21`.
- Исправление добавило local derived value и отдельный regression, после чего
  финальные functional и semantic checks прошли:
  `.tasks/TASK-083-T3-FT-007-W1/TASK-083-T3-FT-007-W1-S-EXECUTE-final-report-code-03.md:9-29`
  и
  `.tasks/TASK-083-T3-FT-007-W1/TASK-083-T3-FT-007-W1-S-VERIFY-final-report-docs-03.md:16-27`.
- Public timing route объявлен в
  `src/face_moment/entrypoints/realtime.py:250-333`, а Caddy независимо
  перечисляет exact root и child shape в `deploy/Caddyfile:16-44`.
- Verify Attempt 1 доказал реальный operational consequence рассинхронизации:
  child path ушёл в backend fallback и вернул пустой Caddy `200` вместо
  realtime `401 no-store`, поэтому timing write вообще не выполнялся:
  `.tasks/TASK-083-T3-FT-007-W1/TASK-083-T3-FT-007-W1-S-VERIFY-final-report-docs-01.md:14-24`.
- Постоянный focused test проверяет Caddy как текст, затем отдельно вызывает
  realtime ASGI app (`tests/promo/test_client_diagnostic_timing.py:144-169`);
  task evidence прямо фиксирует это разделение, а фактический HTTPS edge
  проверялся отдельным live probe:
  `.tasks/TASK-083-T3-FT-007-W1/attempt-2-edge-routing-evidence.md:15-27,40-65`.

## Confirmed findings

### MEDIUM / Priority 1 — Effective display state имеет два владельца вычисления

`DisplayOutcomeRepository` и `project_core_timeline()` независимо реализуют
одинаковую temporal rule `pending -> unconfirmed`. Это уже вызвало не
гипотетический, а воспроизведённый semantic divergence в первой завершённой
попытке TASK-083. Наличие regression на второй projection фиксирует текущий
case, но не устраняет необходимость синхронно менять обе реализации при любом
следующем изменении display semantics.

Практический impact: repeated change cost и риск противоречивых operator/read
projections остаются повышенными; один и тот же Attempt может снова получить
разные effective states в разных Promo reads.

Минимальное направление remediation: вынести только pure derivation effective
display status в одну Promo-owned функцию и переиспользовать её в обеих
projections. Новый service, class или abstraction layer не нужен; stored state
и текущие no-mutation tests должны остаться без изменений.

### MEDIUM / Priority 2 — Public realtime route вручную дублируется в edge config

FastAPI владеет timing path, но доступность через центральный origin зависит от
отдельного exact Caddy matcher. Рассинхронизация уже сделала корректный ASGI
endpoint недоступным в реальном client path и потребовала отдельной retry.
Текущий regression сопоставляет config-текст и ASGI behavior раздельно, поэтому
обычный test path не исполняет тот самый Caddy -> realtime handoff, который
сломался.

Практический impact: добавление или изменение realtime child route требует
ручной синхронизации source, Caddy matcher и text assertion; ошибка проявляется
как misleading fallback response и может дойти до operational edge probe.

Минимальное направление remediation: передать стабильный capability prefix
`/api/realtime/*` одному Caddy `handle` с существующим body limit и оставить
дочернюю маршрутизацию FastAPI. Это убирает второй registry paths без нового
router или deployment machinery; exact API behavior продолжает проверяться в
application tests.

## Uncertainty

- Review не расширялся на прочие Caddy routes, поэтому второй finding не
  утверждает repo-wide edge problem.
- Prefix remediation предполагает, что все пути под публичным
  `/api/realtime/*` принадлежат текущему realtime capability, как показывает
  проверенная architecture/source surface. Если explicit allow-list является
  отдельным незафиксированным security requirement, сначала требуется owner
  confirmation; тогда минимальной альтернативой будет executable disposable
  Caddy edge smoke вместо text-only assertion.
- Report не выбирает отдельную lifecycle-задачу и не оценивает priority
  относительно непросмотренных waves.
