---
description: Скрытый профиль посетителя, фиксированные образцы А/Б и результаты публичного поиска.
status: active
last_updated: 2026-10-03
source_of_truth:
  - .memory-bank/domains/browser-search-profile.md
---
# Browser Search Profile

## Данные и владелец

`promo` единолично пишет профиль, образцы и результат; PostgreSQL и миграции
следуют [общему контракту](../contracts/boundary-map.md#shared-postgresql-contract).
Продуктовая приёмка: [FT-013](../features/FT-013.md).

| Запись | Поля и ограничения |
|---|---|
| `browser_search_profiles` | UUID, уникальный SHA-256 digest случайного 256-bit cookie token, nullable email, last_visit_at, reset_used=false. Автоматического удаления нет. |
| Образцы профиля | Nullable A/B embedding и immutable pipeline_revision_id; B требует A. По совпадению не обновляются. |
| `public_search_results` | UUID, profile_id, выбранные venue IDs, pipeline_revision_id, created_at; личные photo IDs и similarity, общие photo IDs с venue/visit_date. Только последний успешно сформированный результат профиля используется для нового выбора. |

Selfie bytes сервер не сохраняет в профиле или diagnostics. А/Б — ограничение
допустимости, а не запрос: поиск использует embedding текущего снимка.
Profile cookie `fm_browser_profile`: HttpOnly, Secure, SameSite=Lax, Path=/,
без Domain; persistent Max-Age=31536000 обновляется при явном действии.
Неизвестная cookie создаёт новый профиль только при поиске. Потеря cookie
не восстанавливает заказы. Last visit обновляется явными действиями, не media reads.

## А/Б

Сначала `processing` проверяет ровно одно лицо и configured quality gate.
Затем `promo` блокирует строку профиля и выполняет переход атомарно.
Cosine similarity >= отдельного `profile_similarity_threshold` означает совпадение.

| Пригодное селфи | Изменение / ответ |
|---|---|
| A отсутствует | Сохранить A; поиск разрешён. |
| Совпало с A или B | Ничего не заменять; поиск разрешён. |
| Не совпало с A, B отсутствует | Сохранить B; поиск разрешён, в том числе после reset. |
| Не совпало с обоими, reset_used=false | Не искать; `confirmation_required`, предупреждение о чужом лице и «Это я» / «Переснять». |
| Явное подтверждение того же снимка | A=current, B=null, reset_used=true; поиск разрешён. |
| Не совпало с обоими, reset_used=true | `face_denied`; текст из FR-PUB-05, пересъёмка доступна. |
| Нет/несколько лиц или качество ниже gate | `retake_required`; A/B/reset не меняются. |

«Это я» повторно отправляет текущий JPEG с `confirm_reset=true`. Сервер заново
проверяет качество/совпадения и выполняет reset только при несовпадении с А и Б
и reset_used=false под lock. Повтор уже выполненного подтверждения проходит
обычным совпадением с новым A; отдельного challenge state нет.
Несовместимая сохранённая revision возвращает `503` без сброса/расходования
образцов; embeddings разных revisions не сравниваются.

## Проверка

Одновременные запросы одного профиля не заполняют дополнительные образцы и не
делают два reset. Fixtures проходят все строки таблицы, replay подтверждения,
непригодный снимок, смену revision, cookie loss и независимое изменение порога
А/Б без изменения профессионального search threshold.
