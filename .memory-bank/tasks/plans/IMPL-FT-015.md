---
description: Four accepted free-delivery outcomes consuming frozen order core.
status: active
last_updated: 2026-10-03
---
# IMPL-FT-015

[FT-015](../../features/FT-015.md), [EP-004](../../epics/EP-004.md),
[PRD](../../prd.md#h-public-selfie-search-and-purchase--accepted-extension-2026-10-03)
and [requirements](../../requirements.md) own scope. All five existing canonical
specs reused; no spec created/extended. Planning Revision 4, Foundation TASK-002
and TASK-132 frozen core/profile transaction preserved.

## Outcomes and supplier order

| Task | Primary owner/root and outcome | Dependencies / exact claim |
|---|---|---|
| TASK-133-T3-FT-015-W9 | promo `src/face_moment/promo/`: bounded backend ZIP executor/recovery/failure-mail | TASK-132 frozen orders; AC-004 |
| TASK-134-T3-FT-015-W10 | promo: HMAC bearer streaming/TTL/private entitlement | TASK-133 complete private archive; AC-003 |
| TASK-135-T3-FT-015-W11 | promo: public order POST/read transport integration | TASK-132 core + TASK-134 ready link; AC-001 |
| TASK-136-T2-FT-015-W12 | promo browser `client/`: free download/preparation/error interaction | TASK-135 HTTP + TASK-129 selected quote; AC-002 |

ZIP assembly/recovery/failure/mail belong one executor lifecycle. Preparation/error
render belong one browser download interaction. HTTP admission/status and bearer
streaming independently complete. Proof/tests remain with implementation; no
proof-only/production-only tasks. Every task directly depends on Foundation.

## Ownership and runtime

[Architecture](../../architecture/system-architecture.md#public-search-and-selected-delivery),
[graph](../../contracts/boundary-map.md#public-search-and-delivery),
[Photo Orders](../../domains/photo-orders.md), [Purchase API](../../contracts/photo-purchase-api.md)
and [lifecycle](../../states/lifecycle-map.md#public-visitor-flow) sufficient.
`promo` alone changes PostgreSQL face_moment.photo_orders. Inventory supplies
existing verified original reads/projection; no Photo or foreign writes. Backend
composition binds bounded executor, private storage, configured mail and separate
HMAC secret; compression/IO outside event loop. Real mail adapter with fake
transport is implemented in executor outcome, no real delivery at planning/proof.
No Photo worker, new queue/job table/service, outbox or retention guarantee.

TASK-132 owns full frozen snapshot/atomic paid profile/idempotence; order HTTP
consumes this command and proves only free HTTP integration. Canonical paid request
shape is retained; FT-016 supplies paid browser/provider integration without a
cycle. Executor produces free/paid ZIP; bearer reads stored payment entitlement,
including pending/canceled denial and succeeded acceptance. FT-016 proves only
provider-confirmation-to-delivery delta, not supplier TTL/ZIP claims.

Advisory subject paths and native commands are in cards; no hard file allow-list.
HTTP/composition adapt, business orchestration remains promo. Backend lifecycle
startup/shutdown/restart registration and real served client script are required.
Direct original access remains private; logs/JSON never expose private keys/token.

## Verification and constraints

Exact AC locators/RED/GREEN in cards. PostgreSQL read after independent session,
private-store ZIP member read, deterministic clock and isolated synthetic inputs;
unique DB/object prefixes and cleanup finally make rerun safe. Executor tested via
actual backend lifecycle, not only manually called helper; fake mail captures
configured transport target and failures. Bearer actual HTTP streams ZIP without
cookie, with precise expiry/signature/entitlement checks. Browser served shell uses
actual routes; relevant unit tests + focused browser/API join. mypy and relevant
pytest; native client unit/browser commands. Boundary inspection, no fabricated
architecture command. Planning runs only schema/link/dependency checks, not code
checks or live email/payment. Constitution KISS, private originals and Promo/QR
preserved. Next fresh `/review-tasks-plan FT-015` then applicable workflow gates.
