---
description: Настройки тарифа, публичный заказ, ЮKassa и архивная выдача.
status: active
last_updated: 2026-10-03
source_of_truth:
  - .memory-bank/contracts/photo-purchase-api.md
---
# Photo Purchase API

[Photo Orders](../domains/photo-orders.md) — единственный владелец schema/formula/state;
product acceptance — [FT-014](../features/FT-014.md), [FT-015](../features/FT-015.md),
[FT-016](../features/FT-016.md). Browser не присылает authoritative цену/free flags.

| Endpoint | Контракт |
|---|---|
| `GET|PUT /api/serving/photo-tariff` | operator/developer, existing staff session/CSRF; `{base_kopecks,d1,d2,d3}`. Invalid →422 без изменения. |
| `POST /api/serving/spas` (existing create) | К existing request добавляется обязательный strict boolean `is_free`; existing `201` response также возвращает `is_free`. Прежние поля и create errors сохраняются. |
| `PUT /api/serving/spas/{spa_id}/is-free` | Strict `{is_free:boolean}` → `200 {spa_id,is_free}`. operator/developer, existing staff session/CSRF; 401/403/404/422, invalid input не меняет state. Изменяется только free mode. |
| `POST /api/public/quote` | Profile cookie + `{result_id,photo_ids}` → `{items,selected_count,paid_count,total_kopecks,currency:"RUB"}`. |
| `POST /api/public/orders` | То же + `client_request_id`, paid email (атомарно profile.email + frozen order.email) и method `bank_card|sbp` → `{id,archive_status,total_kopecks}`; повтор того же request возвращает тот же order, conflicting payload→409. |
| `GET /api/public/orders/{id}` | Только owner profile → archive/payment statuses, safe error, ready бесплатного/оплаченного заказа `download_url`; preparing → retry_after_seconds=30. |
| `POST /api/public/orders/{id}/payment` | Owner profile, ready ZIP, total>0 и не expired → confirmation_url. До ready →409, никаких provider calls. |
| `POST /api/public/payments/yookassa` | JSON `{type:"notification",event:"payment.succeeded"|"payment.canceled",object:{id}}`: проверить payment через authenticated server GET, затем idempotent transition; browser cookies не требуются. |
| `GET /api/public/archives/{id}?token=...` | Проверки Photo Orders → streamed application/zip attachment; invalid/unentitled/unavailable→404, expired→410. |

Staff free-mode initial value и reload читает existing server-rendered `/staff/spas`
через serving_control projection; дополнительный GET не нужен. Переход false→true
требует popup подтверждения, cancel не отправляет mutation. Staff responses no-store.

Public mutations требуют matching Origin и profile cookie; HTTPS/no-store/no-referrer
и configured IP/profile limits — [Public Search](public-photo-search-api.md#защита-и-проверка).
Webhook исключён из browser Origin check. Download logs не содержат query/token;
JSON не содержит private keys. Free choice не вызывает provider и не требует email.

## ЮKassa и email

После ZIP ready: `POST https://api.yookassa.ru/v3/payments`, HTTP Basic shop_id/key,
`Idempotence-Key` заказа, `capture:true`, frozen amount/RUB,
`payment_method_data.type=bank_card|sbp`, confirmation redirect с server-owned
return_url, metadata.order_id. Browser получает только confirmation_url;
return navigation не открывает entitlement. СБП одностадийная, поэтому deferred
capture для задержки списания не используется.

Перед paid transition сервер читает `GET /v3/payments/{id}` и сверяет provider id,
metadata.order_id, amount/RUB, `status=succeeded` и `paid=true`. Pending/canceled
доступ не дают. Duplicate webhook/refresh не создаёт второй заказ; обработанный
webhook получает `200`, временная техническая ошибка `5xx` допускает provider redelivery.
Неопределённый create outcome повторяется с тем же idempotence key, не новым платежом;
после provider idempotency window нужна ручная сверка, а не blind retry.

Receipt использует frozen email и paid строки, сгруппированные по unit price
(не более четырёх групп), quantity/amount sum=payment; free zero строки исключены.
Налоговые поля/тип предмета расчёта — explicit merchant deployment configuration,
не выдуманные налоговые значения. Missing credentials/fiscal config→503 до payment.
Manual refunds через кабинет ЮKassa, отдельного API возвратов приложение не создаёт.
Mail adapter обслуживает automatic ZIP failure уведомление, указанное в Photo Orders;
секреты provider/mail — runtime config, не profile/logs.

Официальные источники: [карта](https://yookassa.ru/developers/payment-acceptance/integration-scenarios/manual-integration/bank-card),
[СБП](https://yookassa.ru/developers/payment-acceptance/integration-scenarios/manual-integration/other/sbp),
[webhooks](https://yookassa.ru/developers/using-api/webhooks),
[receipt](https://yookassa.ru/developers/payment-acceptance/receipts/54fz/yoomoney/payments).

## Проверка

Provider/mail fakes доказывают отсутствие payment до ZIP ready, правильный frozen
amount/receipt/email, оба метода, server GET authentication и поддельный/duplicate
webhook, browser-return bypass, canceled/pending без выдачи. Staff tests проверяют
обе разрешённые роли/CSRF, popup cancel и atomic invalid-setting rejection.
Внешний test-mode join проверяет реальный card/СБП redirect и receipt payload;
реальные payment/email не нужны для unit verification.
