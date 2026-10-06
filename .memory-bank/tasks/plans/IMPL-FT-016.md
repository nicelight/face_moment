---
description: Three paid integration outcomes consuming frozen orders and archive delivery.
status: active
last_updated: 2026-10-05
---
# IMPL-FT-016

[FT-016](../../features/FT-016.md), [EP-004](../../epics/EP-004.md),
[PRD](../../prd.md#h-public-selfie-search-and-purchase--accepted-extension-2026-10-03)
and [requirements](../../requirements.md) own scope. Reuse all six feature-linked
canonical specs, plus existing public security boundary. No spec extension or
creation. Planning Revision 4 and verified Foundation TASK-002 unchanged.

## Outcomes and supplier order

| Task | Primary owner/root and implementation result | Exact claim / supplier |
|---|---|---|
| TASK-137-T3-FT-016-W12 | promo `src/face_moment/promo/`: ready-paid-order initiation, real YooKassa adapter, frozen receipt | AC-002; TASK-135 public orders |
| TASK-138-T3-FT-016-W13 | promo: server confirmation/webhook and stored paid entitlement→existing bearer delivery | AC-003/004; TASK-137 + TASK-134 bearer |
| TASK-139-T3-FT-016-W14 | promo browser `client/`: paid email/order/method/preparing/redirect/return/download | AC-001/005; TASK-138 + TASK-136 free browser + TASK-129 selection |

Receipt/config/replay inseparable from create-payment command; authenticated GET,
webhook and entitlement publication form one confirmation outcome. Browser email,
method and all continuation states form one paid interaction. Tests/probes stay
with implementation, no proof-only or production-only task. Foundation is direct
for each card. Canonical supplier paid shape eliminates reverse dependency/cycle.

## Ownership and canonical coverage

[Architecture](../../architecture/system-architecture.md#public-search-and-selected-delivery),
[graph/contract](../../contracts/boundary-map.md#public-search-and-delivery),
[external boundary](../../contracts/boundary-map.md#external-and-runtime-boundaries),
[Purchase API](../../contracts/photo-purchase-api.md),
[Photo Orders](../../domains/photo-orders.md),
[Browser Profile](../../domains/browser-search-profile.md),
[lifecycle](../../states/lifecycle-map.md#public-visitor-flow) and
[public security](../../contracts/public-photo-search-api.md#защита-и-проверка)
are reused. Exact shapes/state/errors/verification already accepted.
`promo` owns orders/payment entitlement in PostgreSQL face_moment.photo_orders;
profile/last visit supplied by TASK-132 same transaction. Inventory original
projection, serving tariff/free snapshot and processing results remain read-only
consumers through accepted public-search-and-delivery edge. Existing core/HTTP
commands are consumed, no foreign writes. HTTP/composition adapt only; provider
HTTP adapter and credentials/fiscal config bind in existing backend runtime,
blocking IO outside event loop. Client script must be served by actual shell.
No new module/service/queue/payment platform/outbox/refund API or shielding.

TASK-132 keeps frozen quote/profile transaction/idempotence proof; TASK-133 keeps
ZIP/recovery/failure-mail; TASK-134 keeps bearer/HMAC/TTL; TASK-135 keeps HTTP
admission/status; TASK-136 keeps free browser. FT-016 proves only paid consumer
integration and provider/confirmation delta. AC-002 server and new AC-005 browser
atomic split preserve accepted behavior and stable older AC crossreferences.

## Verification and execution boundaries

Cards carry literal exact AC locators, governing REQs, RED/GREEN and advisory
subject paths. Real registered backend/provider HTTP adapter against fake provider,
disposable PostgreSQL/private objects, synthetic multi-venue inputs, read-after-new
session/restart and deterministic clock prove claims. Unique namespace and finally
cleanup permit safe rerun. Real served Playwright flow joins backend rather than
mock-only assertions. Provider/mail tests use fakes; no real money/email.
TASK-137 owns external YooKassa TEST `bank_card` redirect and frozen receipt
payload join. Its real application route and HTTP adapter also prove `sbp` with
an isolated fake HTTP provider: method payload, frozen receipt, idempotence and
errors. TASK-139 proves browser continuation for both choices against the fake
provider. The TEST shop exposes `bank_card,yoo_money` but no `sbp`; its receipt
check mode has not been confirmed. The authorized external card join returned
HTTP 200/pending with matching frozen amount/order metadata, a redirect and
the transmitted frozen receipt payload, as recorded in
`.tasks/TASK-137-T3-FT-016-W12/claim-evidence.md`. This proves the accepted
TEST claim; actual merchant receipt mode and fiscal receipt issuance remain
unproven and are not TASK-137 closure criteria. Merchant inputs are ИП, УСН
«доходы», без НДС, service description «Оказание цифровых услуг»; credentials
stay in ignored `.env.yookassa.local`, never in logs or task evidence.

Before production SBP enablement, separate external redirect/receipt proof in
the real shop remains mandatory with explicit operator authorization for real
calls/payment. It is a release checkpoint, not TASK-137 TEST evidence; no
production call is part of this plan. The existing three task boundaries,
tiers, waves and dependencies remain unchanged. TASK-137 subsequently closed
done after independent functional PASS and semantic-pass. TASK-138 also closed
done after attempt 2 independent functional PASS and separate semantic-pass;
TASK-139 was blocked pending scheduler promotion at the Wave 13 boundary.
After promotion it exhausted the initial attempt and two retries; the final
independent [functional FAIL](../../../.protocols/TASK-139-T3-FT-016-W14/verification.md)
and [failed task record](../TASK-139-T3-FT-016-W14.task.json) supersede that
execution handoff. The existing plan and review remain historical; the
[BUG](../../bugs/public-photo-purchase-browser-continuation.md) routes
normal FT-016 successor planning and separate review after operator resume.

Native mypy/relevant pytest and client unit/focused browser gates; inspect accepted
ownership rather than invent missing architecture command. T3 isolated harm probes
cover premature charge, forged server truth, duplicates, privacy and paid delivery
bypass. Upstream proof is consumed rather than copied. Secrets/private keys/tokens
redacted. Production/deploy actions prohibited, human checkpoints
remain with execution workflow. This planning correction executed no code or tests.
The fresh `/review-tasks-plan FT-016` returned APPROVE at Revision 4 before
TASK-137 verification and closure.
