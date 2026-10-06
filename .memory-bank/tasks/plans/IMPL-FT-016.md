---
description: Paid integration outcomes and bounded browser successor repairs consuming frozen orders and archive delivery.
status: active
last_updated: 2026-10-06
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
| TASK-144-T3-FT-016-W15 | promo browser `client/public-photo-download.js`: free-to-paid change between quote and new-order POST gives the accepted message and ordinary fresh selection | AC-001 repair; done TASK-129/136/138 and Foundation |
| TASK-145-T3-FT-016-W15 | promo browser `client/public-photo-download.js`: retry after pending provider return and new search refreshes retained owner order for empty `photo_ids`, and keeps `start()` for nonempty selection | AC-005 repair; done TASK-129/136/138 and Foundation |

Receipt/config/replay inseparable from create-payment command; authenticated GET,
webhook and entitlement publication form one confirmation outcome. Historical
TASK-139 combined the initial browser paid interaction and failed after its
allowed retries. Each newly evidenced browser repair is a separate change
result; tests/probes stay with implementation, with no proof-only or
production-only task. Foundation is direct for each card. Canonical suppliers
avoid reverse dependency/cycle.

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

The accepted [clarification](../../../.protocols/FT-016/clarification.md#task-139-принятый-kiss-repair-browser-continuation-2026-10-06)
and FT-016-AC-001/005 fix the successor scope. TASK-144 and TASK-145 are
independently executable browser corrections: changed free-to-paid order
admission and saved-order retry routing can each pass with the other still
broken. Their common file does not make one outcome. Both belong to the
existing promo public browser consumer; `client/public-photo-download.js` is
the expected source path, with focused unit and served Playwright regressions
at `tests/client/test_public_photo_payment.mjs` and
`tests/client/public_photo_payment.spec.mjs`. The existing isolated HTTPS
backend/fake-provider fixture may gain only the controls needed to reproduce
the two transitions. `promo` remains the server order/payment owner; browser
uses the accepted Purchase API and must not write server state, infer paid
entitlement or initiate a replacement purchase automatically. The accepted
[public search and delivery](../../contracts/boundary-map.md#public-search-and-delivery)
and [external browser boundary](../../contracts/boundary-map.md#external-and-runtime-boundaries)
stop propagation: no server, shared API, schema or graph change is required.

Both W15 tasks depend directly on done Foundation TASK-002 and the applicable
done selection/free-browser/paid-server suppliers TASK-129/136/138. Neither
depends on failed TASK-139 or on the other successor. W15 is a sequential
execution wave, not parallel file access. TASK-139 identity, T3 status,
attempt reports, evidence and retry budget remain historical. TASK-137/138
server proof is consumed without reproof. No production-only work is added;
the existing real-shop SBP release checkpoint remains outside development.
TASK-139's failed AC-001/005 mappings remain historical; TASK-144 owns the
fresh AC-001 browser verdict and TASK-145 the fresh AC-005 browser verdict.
Each successor rechecks already working browser branches needed for its whole
AC while limiting new production work to its own evidenced defect.
Both successors are T3 because they govern purchase continuation and the
browser-visible gate to paid originals; each card requires an isolated served
RED/GREEN probe and independent functional/semantic verification. The correction
does not raise any supplier's tier or transfer its payment proof.
Planning Revision 4, feature design complete and existing canonical links
remain unchanged. Fresh task-plan review APPROVE preceded W15 execution.
Root closed TASK-144/145 after independent functional PASS and semantic-pass
recorded in their indexed cards. With done TASK-137/138, these producers
cover FT-016 development AC-001..005; the [owner decision](../../../.protocols/AUTONOMOUS-RUN/decision-log.md#wave15-closure-owner-decision)
authorizes verified feature/epic/REQ reconciliation. TASK-139 and its reports
remain historical failed evidence. Production activation, fiscal issuance,
real-shop SBP, SMTP setup and deployment remain separately unproved.

Historical server tasks used mypy/relevant pytest; successors use client unit
and focused served browser gates. Inspect accepted ownership rather than invent
an architecture command. T3 harm probes follow each task's owned payment or
delivery outcome; upstream proof is consumed rather than copied. Secrets,
private keys and tokens are redacted. Production/deploy actions remain outside
these cards. The earlier `/review-tasks-plan FT-016` APPROVE at Revision 4
preceded TASK-137 execution; a separate fresh W15 review approved the
successor cards before their execution.
