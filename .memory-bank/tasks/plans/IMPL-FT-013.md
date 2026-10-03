---
description: Seven accepted implementation outcomes for public selfie search and private gallery.
status: active
last_updated: 2026-10-03
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
