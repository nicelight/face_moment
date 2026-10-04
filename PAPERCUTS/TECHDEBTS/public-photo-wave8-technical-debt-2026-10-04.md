# Технический долг публичного фото-flow — Wave 8

Проверены только новые изменения TASK-126-T2-FT-013-W8 (галерея) и TASK-132-T3-FT-014-W8 (frozen order core). Существенный технический долг в этой границе не подтверждён. Отчёт advisory: задач и дополнительных gates не создаёт.

## Проверенная граница и evidence

- Галерея: `client/public-photo-gallery.js:2–40`, gallery integration в `client/public-photo-search.js:42–47,93,109`, gallery container в `client/site.html`, правила `.fm-photo-*` в `client/site.css`. Проверены server-granted состав/порядок/free flags, DOM watermark, последовательная загрузка preview и очистка прежнего результата; тексты создаются через textContent. Evidence: `tests/client/test_public_photo_gallery.mjs`, `.tasks/TASK-126-T2-FT-013-W8/claim-evidence.md`, `.protocols/TASK-126-T2-FT-013-W8/verification.md` (unit94, browser journey и независимый probe, QR60; private preview, retry429, clearing).
- Frozen order: `src/face_moment/promo/photo_orders.py:26–129`, `migrations/versions/0032_photo_orders.py`, регистрация модели в `migrations/env.py:26,47`, `tests/promo/test_photo_orders.py:51–218`. Core использует существующий authoritative quote; owner lookup, profile lock, unique request key и request digest обеспечивают replay/conflict. Order/profile сохраняются одной caller-owned транзакцией. Evidence: `.tasks/TASK-132-T3-FT-014-W8/claim-evidence.md`, `.protocols/TASK-132-T3-FT-014-W8/verification.md` (native16, independent12, mypy122) и `.tasks/TASK-132-T3-FT-014-W8/TASK-132-T3-FT-014-W8-S-RED-VERIFY-final-report-docs-01.md` (конкурентный retry после rollback).
- Основание границы: обе indexed task cards; `.memory-bank/contracts/public-photo-search-api.md`, `.memory-bank/contracts/photo-purchase-api.md`, `.memory-bank/domains/photo-orders.md`; Constitution KISS и accepted Planning Revision 4.

## Подтверждённые замечания

## Ограничения вывода

Это чтение реализации и существующих проверок; новые runtime/tests/deploy не запускались. Historical Wave 8 и полный FT-013 не проверялись. ZIP executor, order HTTP/UX, provider payment и mail принадлежат последующим задачам и не являются долгом рассмотренного core. Доказательств повторяющейся материальной стоимости сопровождения или регрессий в новом delta не найдено; дополнительных мер без такого основания не предлагается.
