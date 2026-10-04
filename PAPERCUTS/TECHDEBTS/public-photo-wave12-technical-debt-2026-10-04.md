# Wave 12 — advisory technical debt

Проверен только завершённый TASK-136-T2-FT-015-W12: browser free download и фактическая интеграция с существующим выбором фото. Материальный технический долг в проверенной области не подтверждён.

## Область и evidence

- `client/public-photo-download.js:2` — controller: стабильный client_request_id, повтор POST при неопределённом create outcome, GET для известного заказа, подавление устаревшего результата и безопасные состояния preparing/failed/ready.
- `client/public-photo-download.js:33` — DOM integration: selection events, ручная проверка статуса, bearer fetch, проверка revision перед выдачей Blob и освобождение object URL.
- `client/public-photo-selection.js:32` и `:50` — события изменения выбора и передачи authoritative quote; существующий quote owner сохраняется.
- `client/site.html:64` и `:72` — download panel и подключение модуля; остальные накопленные изменения shell вне Wave 12.
- `tests/client/test_public_photo_download.mjs:5`, `tests/client/public_photo_download.spec.mjs`, `tests/client/public_photo_download_browser_fixture.py` — probes retry/concurrency/late state и served browser join с изолированными PG/MinIO/executor/signer, cleanup.
- `.tasks/TASK-136-T2-FT-015-W12/claim-evidence.md` — actual change surface и девять групп comparisons; `.protocols/TASK-136-T2-FT-015-W12/verification.md` — independent unit 99/99, browser 1/1 и отдельный late-state probe; `.tasks/FT-015/FT-015-S-RED-VERIFY-final-report-docs-01.md` — итоговый feature semantic PASS.
- Нормативная основа: `.memory-bank/contracts/photo-purchase-api.md`, `.memory-bank/domains/photo-orders.md`, `.memory-bank/features/FT-015.md#FT-015-AC-002` и текущая indexed task card.

## Подтверждённые findings

## Вывод и ограничения

Новый controller остаётся bounded consumer существующих quote/order API. В изученных изменениях не найдено подтверждённого механизма, существенно увеличивающего repeated change cost, coupling, regression risk или maintenance burden. Remediation и приоритет не требуются. Повторные tests и широкий аудит не выполнялись; runtime вывод опирается на уже сохранённую независимую verification, source проверен read-only.

TASK-137 остановлена на preflight без реализации из-за отсутствующих YooKassa TEST configuration и разрешения external test calls; TASK-138/139 dependency-blocked. Этот advisory не меняет halt, task/feature statuses, gates или resume route и не вводит новую работу. Существующие dirty изменения сохранены; создан только данный отчёт.
