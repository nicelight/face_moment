---
description: Frozen выбор, тариф, ZIP и право выдачи выбранных originals.
status: active
last_updated: 2026-10-03
source_of_truth:
  - .memory-bank/domains/photo-orders.md
---
# Photo Orders

## Владельцы и данные

`promo` пишет заказы/ZIP/payment entitlement. `serving_control` пишет free venue,
global tariff и отдельный profile threshold. `inventory` предоставляет только
active выбранные Photo/original projections; foreign state не изменяется.
[API](../contracts/photo-purchase-api.md) задаёт транспорт и provider.

| Запись | Поля |
|---|---|
| Venue extension | `is_free` (existing venues default false); создание требует explicit bool. |
| Global tariff | Один Base в integer kopecks >0, decimal d1/d2/d3: 1>=d1>=d2>=d3>0, каждая округлённая paid unit >=1 копейки; updated_at. Provision до первой paid quote, без выдуманных цен. |
| `photo_orders` | UUID, profile_id, client_request_id unique/profile, frozen items[{photo_id,venue_id,visit_date,is_free,unit_kopecks}], total_kopecks, email для paid, выбранный bank_card/sbp, created_at. |
| Archive fields | `requested|preparing|ready|failed`, private key, nullable ready_at, safe failure reason. |
| Payment fields | Nullable unique provider_payment_id, stable creation idempotence key, nullable payment_requested_at, `not_required|pending|succeeded|canceled`; paid_at. |

Quote считает только платные личные фото n по всему выбору. Цена первого Base,
каждого 2–5 round(Base*d1), 6–20 round(Base*d2), 21+ round(Base*d3), округление
half-up до копейки на единицу. Бесплатные строки =0. Платные строки назначаются
ступеням в stable photo_id order; сумма равна сумме frozen строк. Изменение
настроек влияет только на новые заказы. Quote/order проверяют принадлежность
текущей галерее, active Photo и availability оригинала; duplicate IDs →422.

## Исполнение и выдача

Создание заказа фиксирует состав/стоимость/free flags транзакционно, archive=requested.
Paid order в той же транзакции обновляет profile.email и last_visit_at; email
заказа фиксируется для чека. Free order email не требует и не заменяет.
Один ограниченный backend исполнитель берёт старейший requested, ставит preparing,
читает originals через inventory, пишет ZIP во временный private key и публикует
ready/key/ready_at только после успешного завершения. Его IO/compression вне event
loop; модель и shared Photo worker не используются. После restart preparing
возвращаются requested и собираются заново; final key детерминирован по order_id,
повторное завершение не сдвигает уже сохранённый ready_at. Нет отдельной job table.

ZIP содержит только frozen выбранные originals с именами `{photo_id}.jpg`.
Missing source/ошибка сборки → failed; попытка admin email через настроенный mail
adapter на `sergiosandroid2@gmail.com`, safe user error, provider не вызывается.
Mail failure не скрывает archive failure; записывается bounded operational error.
Повторного надёжного mail outbox нет.

Ready free заказ (`total=0`) разрешает выдачу; paid — только payment=succeeded.
Bearer link — `/api/public/archives/{id}?token=<HMAC>`; HMAC-SHA256 отдельным
server secret связывает order_id и неизменный ready_at. Access требует valid
signature, entitlement, существующий ZIP и `now < ready_at+3 days`.
Token не зависит от cookie; verification constant-time. Прямого original route нет.
Expiry derived, не новый scheduler. Metadata/profile автоматически не удаляются;
эта спецификация не добавляет archive shielding, foreign cascades или purge.
Недоступная выдача — понятная ошибка и ручная поддержка/возврат.

## Проверка

Изолированные DB/object-store fixtures проверяют round/bands 0,1,2,5,6,20,21,
frozen quote при изменении настроек, конкурентный duplicate order, состав ZIP,
restart preparing и неизменный ready_at, unavailable originals, fake admin mail,
free/paid entitlement, bearer без cookie и точную границу 3 дней.
