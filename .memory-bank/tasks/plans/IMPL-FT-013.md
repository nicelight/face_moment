---
description: Public selfie search, private gallery and bounded capture/retry successors.
status: active
last_updated: 2026-10-07
---
# IMPL-FT-013

Посетитель снимает селфи, явно ищет в 1–3 площадках и видит разрешённую галерею.
Оператор принял семь результатов; Planning Revision 4 сохраняется.

## Authority and coverage

[FT-013](../../features/FT-013.md), [EP-004](../../epics/EP-004.md),
[PRD public extension](../../prd.md#h-public-selfie-search-and-purchase--accepted-extension-2026-10-03)
и [REQ-PUB-001/002/003/008](../../requirements.md) определяют acceptance.
Все восемь existing canonical feature links переиспользуются; новых specs нет.
[Public API](../../contracts/public-photo-search-api.md),
[Profile](../../domains/browser-search-profile.md),
[Photo Orders venue extension](../../domains/photo-orders.md#владельцы-и-данные),
[Realtime search](../../domains/realtime-search.md#public-selfie-search),
[Photo rendering](../../domains/photo-processing.md#public-gallery-rendering)
и [boundary graph](../../contracts/boundary-map.md#public-search-and-delivery)
задают contracts. [Architecture](../../architecture/system-architecture.md#public-search-and-selected-delivery),
[lifecycle](../../states/lifecycle-map.md) и
[Foundation](../../foundation.md) сохраняются.

AC-002 владеет server scope, explicit Submit перенесён в UI AC-003;
AC-007/008 уточняют independent processing/result outcomes уже принятого API;
AC-009 выделяет backend media proof из AC-005. AC-005 сохраняет gallery гарантию
через ссылку на AC-009; UI не доказывает backend повторно.

## Accepted implementation order

| Task | Result and primary owner | Prerequisite reason |
|---|---|---|
| TASK-120-T2-FT-013-W1 | Capture/history, `promo` browser flow, `client/` | Foundation достаточен для камеры/IndexedDB. |
| TASK-121-T3-FT-013-W3 | Profile А/Б, `promo/`; threshold `serving_control/` | Existing staff sessions защищают Developer setting. |
| TASK-122-T2-FT-013-W3 | Public native/exact search, `processing/` | Existing exact search/native adapters предоставляют baseline; TASK-120 даёт реальные compressed пары для native comparison. |
| TASK-123-T3-FT-013-W6 | Public API/current result, `promo/` | Использует завершённые profile/search и singleton realtime runtime; включает serving_control-owned is_free persistence/migration/read projection своего результата. |
| TASK-124-T3-FT-013-W7 | Authorized preview bytes, `promo/` orchestration | Membership требует current result; rendering у `processing/`. |
| TASK-125-T2-FT-013-W7 | Explicit search/status/summary, `promo` browser flow | Использует capture и public API. |
| TASK-126-T2-FT-013-W8 | Ordered watermarked gallery, `promo` browser flow | Использует завершённые browser search и protected previews. |

Code roots: `src/face_moment/{promo,processing,inventory,serving_control}/` и
`client/`; expected subject filenames и tests находятся в advisory touched_files
карточек. HTTP/composition не принимают business decisions; `promo` не пишет
Photo/processing/settings. Crossed edges только из accepted graph:
`promo -> processing/inventory/serving_control`, processing read projections.
Foundation final gate TASK-002-T2-FT-000-W0 включён непосредственно во все cards.
Очередь выполняется последовательно; W отражает prerequisites, не parallel policy.

## Proof and limits

Каждая карточка хранит owned AC, claim-linked RED/GREEN и дешёвые native checks.
Python: mypy + relevant pytest; client: native unit/browser runners.
Persistence использует реальный PostgreSQL owner storage и disposable migration
round-trip; privacy probes — synthetic DB/MinIO state с cleanup. Existing
Promo/QR regression проверяет только current integration delta.
TASK-122 владеет native original→960/q0.85 face count/gate/embedding/matches по AC-007/REQ-PUB-001; TASK-120 — browser encoding/history AC-001. TASK-123 владеет AC-008 supplier proof: face_moment.spas.is_free, existing default false, paid/free personal и always-free common; admin UX остаётся FT-014.
Human UX review для engaged progress/понятных отказов включён в TASK-125.
Native ownership inspection вместо отсутствующего architecture-check command.
T3 требует independent verify/red-verify; feature completion — semantic review.

Quote/selection/payment/ZIP принадлежат FT-014..016; нет production-only task,
backfill/no_faces rewrite, extra workers/queues, новой accuracy/latency гарантии.
Constitution KISS, private stores и concise canonical links обязательны.
Следующий шаг: отдельный свежий `/review-tasks-plan FT-013`, затем применимые
workflow gates. Task planning не выполняет implementation/deploy.

## 2026-10-07 capture/retry reconciliation

[PRD clarification](../../prd.md#2026-10-07--capture-flash-post-capture-selection-and-empty-search-retry),
[FT-013 AC-010..014](../../features/FT-013.md#acceptance-criteria) и
[REQ-PUB-001/002/008/009](../../requirements.md) задают пять результатов;
[Public Search API](../../contracts/public-photo-search-api.md#browser-и-media)
и [Browser Search Profile](../../domains/browser-search-profile.md#данные-и-владелец)
сохраняют прежние owners и Planning Revision 4.

| Successor | Самостоятельный результат; owner/root | Основание порядка |
|---|---|---|
| TASK-146-T1-FT-013-W16 | White capture flash; public browser, `client/` | TASK-120 даёт работающий capture. |
| TASK-147-T2-FT-013-W16 | Площадки только после capture; public browser, `client/` | TASK-120 и TASK-125 дают capture и явный submit. |
| TASK-148-T2-FT-013-W16 | Точный empty-result screen и действие повтора, AC-012; public browser, `client/` | TASK-125 даёт typed `no_matches`. |
| TASK-149-T3-FT-013-W16 | Success-only profile/A/result/cookie persistence; `promo`, `src/face_moment/promo/` | TASK-121/123 дают А/Б и search/result; TASK-138 даёт сохранённую paid purchase для проверки сохранности. |
| TASK-150-T2-FT-013-W16 | Browser-cookie счётчик и cooldown, AC-014; public browser, `client/` | TASK-125 даёт typed outcomes; экран TASK-148 не является prerequisite. |

[Boundary graph](../../contracts/boundary-map.md#public-search-and-delivery):
browser использует только public API; `promo` владеет profile/result,
`processing` — matches, `serving_control` — venue/settings projection.
Ожидаемые пути: `client/site-selfie.js`, `client/public-photo-search.js`,
`client/site.html`, `client/site.css`, `tests/client/`; для TASK-149 —
`src/face_moment/promo/browser_search_profile.py`,
`src/face_moment/promo/public_photo_search.py`,
`src/face_moment/promo/public_search_http.py`, `tests/promo/`.

RED/GREEN и тесты находятся в карточках реализации. Browser fixture проверяет
AC-012 на completed `no_matches` без паузы; TASK-150 проверяет cookie AC-014
на пяти исходах, reload/venue, expiry/success reset, исключениях и запрете
нового search POST. Непрерывность order refresh/payment проверяет TASK-151.
Временный context и управляемое
browser time обеспечивают rerun/cleanup. TASK-149 использует disposable
PostgreSQL для read/write, сохранности существующих заказов и отсутствия новой
profile cookie на первом пустом поиске. После TASK-148 и TASK-150 feature
verification проверяет путь четырёх экранов/повторов, пятой паузы и нового
поиска после expiry. Никакой production-only task нет.

## Preparing-order continuity successor

[FT-013-AC-014](../../features/FT-013.md#preparing-order-continuity) требует,
чтобы cooldown останавливал новый поиск, сохраняя доступ к созданному заказу.
[Feature semantic-fail](../../../.tasks/FT-013/FT-013-S-RED-VERIFY-final-report-docs-01.md)
и [triage](../../../.protocols/capture-retry-2026-10-07/order-continuity-triage-report.md)
показали два связанных client gap: пустой выбор удаляет `preparing` attempt до
redirect, а refresh идёт по post-redirect status-only пути. Один новый
[TASK-151-T3-FT-013-W16](../TASK-151-T3-FT-013-W16.task.json) владеет только
непрерывностью уже созданного заказа. Он зависит от done TASK-150 (cooldown) и
TASK-145 (платёжный browser flow); их cookie и post-redirect proof не переназначены.
Foundation gate TASK-002 остаётся прямой зависимостью. W16 сохраняется.

Primary owner — public browser `client/public-photo-download.js`; он использует
только [Public Search API](../../contracts/public-photo-search-api.md#browser-и-media)
и [Purchase API](../../contracts/photo-purchase-api.md), без server/profile/
processing writes. [Photo Orders](../../domains/photo-orders.md#исполнение-и-выдача)
остаётся authority для ZIP и payment. Hard write boundary содержит только
`client/public-photo-download.js`, `tests/client/test_public_photo_payment.mjs`
и `tests/client/public_photo_payment.spec.mjs`; дополнительный файл требует
маршрутизации до исполнения. Отсутствуют новая история, восстановление до
redirect после reload, server/financial/production actions и смена Revision 4.

Proof: honest RED/GREEN в существующем HTTPS fixture с изолированным состоянием,
реальными пятью `no_matches` и заглушками order/payment. Сравнить одинаковый
order ID, owner GET, один `POST /orders`, сохранённую панель и доступный refresh;
после ZIP `ready` продолжить оплату того же заказа. Pending после redirect
держит paid link закрытым до server-confirmed success; новый непустой выбор
использует обычный start. Native gates: `npm run test:unit`, focused payment
browser и search browser regression. T3 требует отдельные functional verify и
task red-verify; feature completion — новый semantic verdict и owner closure.
Design/behavior impact: none; используются существующие canonical specs.
