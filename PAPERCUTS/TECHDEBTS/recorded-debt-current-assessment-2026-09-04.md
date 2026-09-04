---
description: Current evidence-backed assessment of technical debt already recorded for Face Moment.
status: advisory
---
# Текущая оценка уже записанного технического долга

## Проверенная область

Проверены все восемь доступных отчётов в `PAPERCUTS/TECHDEBTS/`, связанные
записи Memory Bank и текущее состояние затронутого кода и tests. Отдельно
проверены исторические debt-ссылки из task cards. Папка
`PAPERCUTS/TECHDEBTS/` является реальным реестром advisory findings;
`.memory-bank/` хранит задачи, решения и ссылки на этот реестр, но не отдельный
полный список долга.

Плановый out-of-scope и deferred physical-pilot evidence не считаются
техническим долгом: это явно отложенные продуктовые обязательства, а не
дефекты текущей реализации. Session papercuts вне `TECHDEBTS/` также не
повышены до долга без отдельного материального impact.

## Итог

В текущем коде остаются четыре открытых findings. Один естественно закрывать до
или внутри FT-011, три можно оставить после FT-011. Закрытые и superseded
записи перечислены отдельно и не включены в число открытых.

| Приоритет | Finding | Существенность | Решение относительно FT-011 |
|---|---|---|---|
| MEDIUM / P1 | Ненадёжный browser recovery test | Test не запускается и способен принять нечитабельную production-конфигурацию | Закрыть до или вместе с TASK-104 |
| MEDIUM / P2 | Realtime routes вручную повторены в Caddy | Сейчас синхронны, но прежний child route уже выпадал из edge surface | Можно после FT-011 |
| MEDIUM / P2 | Revision switch требует чистую Session | Латентный transaction-owner defect; production caller пока отсутствует | Можно после FT-011, до появления caller переключения pipeline revision |
| LOW / P2 | Disposable PostgreSQL lifecycle всё ещё продублирован | Maintenance-only: после локального исправления остаётся 9 diagnostics modules | Исправлять постепенно после FT-011 |

## Подтверждённые открытые findings

### MEDIUM / P1 — browser recovery proof фактически отсутствует

`node --test tests/client/test_browser_recovery.spec.mjs` завершается
`MODULE_NOT_FOUND: playwright/test`; repository не содержит
`package.json`/lockfile. Fixture по-прежнему сохраняет `sensor_id`, тогда как
`client/sensor-config.js` читает `sensorId`, и assertion сравнивает raw
`localStorage`, а не результат production reader. Та же неуправляемая test
dependency используется degraded-advertising spec.

Это не доказанная browser regression, а существенный пробел в постоянном
доказательстве recovery. Он особенно релевантен TASK-104, где FT-011 требует
реальный Playwright smoke. Минимальный repair — один project-managed runner и
assertion через production config/behavior boundary.

### MEDIUM / P2 — edge routes имеют второй ручной registry

`deploy/Caddyfile` вручную перечисляет `/api/realtime/attempts` и
`/api/realtime/attempts/*/client-timing` отдельно от FastAPI routes. Сейчас
matcher синхронизирован, но ранее child route уже был реализован в приложении
и забыт на edge. Текущий impact латентный; FT-011 не расширяет realtime
namespace. Минимальный repair — namespace matcher с сохранением body cap и
FastAPI 404 для неизвестных paths, если отдельный строгий allow-list не
является контрактом.

### MEDIUM / P2 — revision switch неявно владеет outer transaction

`IngestTargetRepository.switch_serving_revision()` по-прежнему открывает
`with self._session.begin()`. После обычного pre-read SQLAlchemy уже запускает
autobegin, поэтому method падает вместо переключения. Tests обходят механизм,
создавая свежую Session непосредственно перед вызовом.

FT-011 manual apply меняет settings, но явно не меняет pipeline revision,
поэтому этот finding не блокирует TASK-104. Он должен быть закрыт до появления
реального caller именно для pipeline revision switch: назначить явного
transaction owner и проверить pre-read, commit и rollback semantics.

### LOW / P2 — общий PostgreSQL test primitive принят только частично

Локально закрыты три FT-010 Wave 2 копии, и общий
`tests/disposable_postgresql.py` уже существует. Однако `CREATE DATABASE`
остаётся в девяти diagnostics test modules, включая annotations, retention,
server-events и investigation families. Это не влияет на production и не
делает tests неверными, но сохраняет drift setup/teardown и повторную цену
изменений. Достаточна постепенная миграция на существующий helper при касании
этих modules; отдельный большой refactor не нужен.

## Закрытые или superseded записи

- Finding 1 (Docker мог проверять устаревший image), finding 5 (двойной расчёт
  effective display state) и finding 7 (Engine на каждый HTTP request) явно
  отмечены закрытыми в основном отчёте и подтверждаются текущим кодом/историей.
- Три findings отчёта TASK-090 относятся к исчерпанной неудачной реализации;
  их outcome заменён и закрыт TASK-094. Активный frontmatter старого advisory
  report не означает открытый product defect.
- FT-010 Wave 2 duplicate-fixture finding закрыт текущим helper и focused
  tests; в открытом списке осталась только более широкая соседняя duplication
  family.
- Исторический W5 finding о неоднозначном Photo state selector был превращён
  в TASK-038 и закрыт. Ссылка на удалённый advisory report ещё присутствует в
  `source_artifacts`, но текущего implementation debt за ней нет.

## Выполненные проверки

- Browser recovery reproduction: module resolution failure до запуска tests.
- Source inspection: Caddy matcher, transaction boundary and 9 remaining
  disposable-database copies.

Отчёт advisory-only. Код, Memory Bank, task lifecycle, gates и уже существующие
debt reports не изменялись.
