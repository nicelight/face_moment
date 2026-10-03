---
description: Six accepted outcomes for combined selection, global quote, admin settings and frozen orders.
status: active
last_updated: 2026-10-03
---
# IMPL-FT-014

[FT-014](../../features/FT-014.md), [EP-004](../../epics/EP-004.md),
[PRD](../../prd.md#h-public-selfie-search-and-purchase--accepted-extension-2026-10-03)
и [requirements](../../requirements.md) определяют accepted scope.
Все пять existing feature canonical specs переиспользуются, включая уточнённый
Photo Purchase API; новых specs нет; Planning Revision 4 и completed Foundation TASK-002 сохранены.
Atomic AC-004/005/006 выделяют tariff backend/UI и frozen core из старых
AC-002/003; crossrefs сохраняют прежнее acceptance без нового product behavior.

## Accepted outcomes and order

| Task | Primary owner/root и результат | Prerequisite reason / owned AC |
|---|---|---|
| TASK-127-T3-FT-014-W3 | serving_control, `src/face_moment/serving_control/`: persistent global tariff/staff API | existing staff_access TASK-004; AC-004 |
| TASK-128-T3-FT-014-W7 | promo, `src/face_moment/promo/`: combined authoritative quote | TASK-127 tariff + TASK-123 current result/is_free/inventory projections; AC-002 |
| TASK-129-T2-FT-014-W9 | promo browser flow, `client/`: selection/sticky count/quote | TASK-128 quote + TASK-126 gallery; AC-001 |
| TASK-130-T2-FT-014-W4 | serving_control staff surface, `client/`: global tariff editor | TASK-127 staff API; AC-005 |
| TASK-131-T3-FT-014-W7 | serving_control, server + `client/`: venue create/settings free UX | TASK-123 is_free supplier + TASK-004 auth; AC-003 |
| TASK-132-T3-FT-014-W8 | promo, `src/face_moment/promo/`: frozen order core/profile transaction | TASK-128 validates authoritative composition/price; AC-006 |

Tariff persistence/API — одна owner command; selection/count/sticky — одна
browser interaction. Quote и order нужны разным consumers; два admin результата
меняют разные commands. Tests/proof не отдельные задачи. Все cards прямо зависят
от Foundation; waves отражают prerequisite, execution остаётся последовательным.
Expected subject paths/tests и native commands — advisory touched_files/cards.

## Boundaries and persistence

[Architecture](../../architecture/system-architecture.md#public-search-and-selected-delivery),
[boundary graph](../../contracts/boundary-map.md#public-search-and-delivery),
[Purchase API](../../contracts/photo-purchase-api.md),
[Photo Orders](../../domains/photo-orders.md#владельцы-и-данные) и
[lifecycle](../../states/lifecycle-map.md#public-visitor-flow) достаточны.
Staff authorization — accepted `serving_control -> staff_access` commands;
quote/order пересекают только `promo -> serving_control/inventory` public reads.
HTTP/composition не владеют business decisions, foreign direct writes запрещены.
TASK-127 пишет PostgreSQL face_moment.photo_tariff; TASK-131 читает/меняет
face_moment.spas.is_free через существующего provider TASK-123 без новой migration.
TASK-131 расширяет existing POST `/api/serving/spas` strict `is_free`, добавляет
PUT `/api/serving/spas/{spa_id}/is-free` и использует existing SSR `/staff/spas`
для initial/reload read; exact payload/errors — Purchase API. Browser/API/repository
proof закрывает только AC-003 integration delta, включая unchanged unrelated settings.
TASK-132 пишет face_moment.photo_orders и same-owner browser_search_profiles.
Все migrations используют [shared PostgreSQL contract](../../contracts/boundary-map.md#shared-postgresql-contract),
без exact mutable-head требования. Dependency proof остаётся supplier.

Frozen core принимает canonical profile/result/photo_ids/client_request_id и
paid email/method, revalidates accepted projections, atomically freezes полный
order и paid profile.email/last_visit. Все archive/payment fields сохраняются
с canonical initial requested/pending/not_required; provider не вызывается.
Это завершённая domain command/repository, не временный публичный endpoint.
FT-015 потребляет core в free POST/read/ZIP flow; FT-016 — в paid email form,
order HTTP/profile integration и provider/receipt. Snapshot/idempotence/atomicity
proof остаётся TASK-132; FT-016 доказывает consumer integration delta и свои
payment/delivery outcomes. Будущих/циклических dependencies нет.

## Verification and limits

Cards несут exact AC locators и claim-equivalent RED/GREEN; один probe различает
все owned assertions. Python mypy + relevant pytest; client unit/focused browser
и реальный bundle/API join. PostgreSQL owner read-after-new-session и disposable
migration roundtrip; T3 synthetic profiles/venues/private object prefixes,
unique state/rerun и cleanup. Staff role/CSRF and public foreign/forged scope
probes только isolated state. Boundary ownership inspection — без выдуманного
architecture-check command. Native checks не запускались при planning.

Constitution KISS/private originals/concise specs соблюдены. ZIP/provider/payment,
email delivery/receipt, production/deploy и Promo/QR changes вне feature; final
production-only task здесь не нужен. Следующий шаг — fresh
`/review-tasks-plan FT-014`, затем применимые workflow gates.
