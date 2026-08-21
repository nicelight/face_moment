# Технический долг wave W5 — 2026-08-21

## Проверенная область

Проверена wave `W5` по индексированным task cards и фактическим implementation/verification artifacts:

- `TASK-012-T2-FT-001-W5`;
- `TASK-026-T3-FT-002-W5`;
- `TASK-028-T2-FT-002-W5`;
- `TASK-030-T3-FT-002-W5`;
- `TASK-037-T2-FT-002-W5`;
- `TASK-053-T2-FT-003-W5`;
- `TASK-054-T3-FT-003-W5`;
- `TASK-066-T2-FT-003-W5`.

В scope вошли изменённые W5 code/tests/scripts/service unit, task-local reports и independent verification evidence. Отчёт advisory-only: workflow state и task statuses не изменялись.

## Подтверждённые findings

### MEDIUM — Browser-recovery regression test не имеет переносимого project-owned запуска

**Evidence**

- `tests/client/test_browser_recovery.spec.mjs:7-8` загружает `playwright/test` через bare package resolution.
- Из корня репозитория `require.resolve("playwright/test")` возвращает `MODULE_NOT_FOUND`; repository-owned Node manifest, lockfile или Playwright test-runner configuration отсутствуют.
- Фактические RED/GREEN и functional verification команды требуют machine-specific `NODE_PATH=/usr/local/lib/node_modules`: `.protocols/TASK-054-T3-FT-003-W5/progress.md:30`, `:44`, `:48` и `.protocols/TASK-054-T3-FT-003-W5/verification.md:107`.
- Эта friction уже потребовала отдельного resolution workaround: `PAPERCUTS/gpt-5 __ 08-21-2026 13.59.md:8-10`.
- Required gates task card проверяют только shell syntax и Memory Bank lint: `.memory-bank/tasks/TASK-054-T3-FT-003-W5.task.json:11`. `scripts/check-ft003-recovery.sh:7-10` передаёт `--browser` в `scripts/check-kiosk-browser.sh`, который проверяет service declaration и доступный live process, но не запускает три persistent-profile state scenarios.
- Принятый project-default browser driver — установленный `playwright cli`: `.memory-bank/testing/index.md:53-61`; постоянный test использует другой, неразрешимый без внешней настройки runner entrypoint.

**Impact**

Постоянная regression coverage для recovery из `advertising`, `active` и `result` может не запускаться обычными task/recovery gates и не воспроизводится в чистом checkout без знания локального global-module path. Изменения в restart/profile-state semantics поэтому могут пройти существующие проверки без этой regression, а следующий исполнитель снова платит стоимость восстановления неявной команды запуска.

**Минимальная remediation**

Дать этому test один repository-owned переносимый entrypoint на уже принятом Playwright runtime и включить его в релевантный recovery gate. Entry point должен сам разрешать установленный driver без hard-coded `NODE_PATH`; полный frontend toolchain не нужен, если достаточно тонкого checked wrapper или переноса сценария на принятый `playwright cli`.

### MEDIUM — Проверка сохранения sensor configuration допускает false positive

**Evidence**

- Fixture сохраняет `sensor_id`: `tests/client/test_browser_recovery.spec.mjs:17-25`.
- Production schema ожидает `sensorId`, а невалидный persisted value превращает в `null`: `client/sensor-config.js:14-29`, `:32-40`.
- После relaunch test сравнивает только raw `localStorage` с исходной строкой: `tests/client/test_browser_recovery.spec.mjs:154-167`; usability через production reader не проверяется.
- Independent verifier явно обнаружил несовпадение и отказался считать raw comparison доказательством: `.protocols/TASK-054-T3-FT-003-W5/verification.md:53-54`.
- Для доказательства verifier создал отдельный probe с корректным `sensorId` и application-level read: `.tasks/TASK-054-T3-FT-003-W5/verifier-recovery-probe.mjs:12-20`, `:132-150`. Adversarial probe повторяет тот же обход: `.tasks/TASK-054-T3-FT-003-W5/red-crash-recovery-probe.mjs:19`, `:178`.

**Impact**

Постоянный regression test проходит, даже когда «сохранённая» sensor configuration непригодна для приложения. Надёжность результата сейчас обеспечивают task-local verifier probes, поэтому будущая проверка требует дублирования логики и может утратить application-level assertion после завершения operational artifacts.

**Минимальная remediation**

В постоянном test сохранять sensor configuration через production `saveSensorConfig()` (или как минимум использовать точный `sensorId`) и после relaunch проверять результат через production `readSensorConfig()`. Уже работающий verifier probe показывает достаточный минимальный assertion; отдельная новая abstraction не требуется.

## Проверенный прежний долг

Finding из `PAPERCUTS/TECHDEBTS/wave-W5-tech-debt-2026-08-14.md` о неуточнённом `photo_id` lookup больше не актуален:

- status path передаёт immutable admission revision: `src/face_moment/inventory/photo_processing_status.py:82-86`;
- projection query фильтрует точную пару `photo_id + pipeline_revision_id`: `src/face_moment/processing/searchable_projection.py:57-68`, `:107-110`;
- regression покрывает смену serving revision после admission: `tests/inventory/test_photo_processing_api.py:293-357`.

Повторно в debt он не принят.

## Не принятые как debt наблюдения

- Предыдущие RED/FAIL попытки TASK-026, TASK-028 и TASK-053 устранены до финальных PASS/semantic-pass и получили regression evidence; отдельного действующего cost mechanism не найдено.
- Deferred real pilot-host evidence для TASK-054 — явно принятое ограничение local-development verification, а не подтверждённый defect текущей реализации.
- Размер отдельных scripts/functions, исторический объём task artifacts и отсутствие дополнительных необязательных test levels сами по себе findings не образуют.

## Неопределённости

- Реальная user-service замена Chromium на pilot host не перепроверялась: evidence остаётся отложенным по принятому решению.
- В рамках read-only debt-аудита gates не перезапускались; использованы сохранённые functional и adversarial verification artifacts плюс статическая проверка текущих source/tests.

## Итог

Подтверждены два material findings уровня `MEDIUM`, оба в permanent browser-recovery regression surface TASK-054. Они не отменяют закрытие TASK-054: functional verifier и red verifier отдельно доказали нужную семантику. Долг состоит в том, что это доказательство пока не закреплено переносимым и schema-valid постоянным regression gate.
