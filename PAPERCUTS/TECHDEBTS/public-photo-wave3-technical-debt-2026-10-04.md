# Public photo Wave 3: advisory technical-debt review

Дата: 2026-10-04. Существенный технический долг в проверенном scope не подтверждён.
Отчёт информационный: он не меняет статусы, verdicts или очередь задач.

## Проверенный scope

Только текущие изменения нового public photo сценария в
`TASK-121-T3-FT-013-W3`, `TASK-122-T2-FT-013-W3`,
`TASK-127-T3-FT-014-W3`. Исторические W3 других features исключены.

- Profile/A/B/reset: `src/face_moment/promo/browser_search_profile.py`,
  `src/face_moment/serving_control/public_search_settings.py`, migration
  `migrations/versions/0028_browser_search_profiles.py`.
- Native query и exact all-date search: `src/face_moment/processing/public_selfie_search.py`,
  добавление `PublicExactSearchRepository` в `processing/persistence.py:308`,
  `inventory/public_photo_projection.py`, `serving_control/public_search_context.py`.
- Persistent tariff: `src/face_moment/serving_control/photo_tariff.py`, migration
  `migrations/versions/0029_global_photo_tariff.py`.
- Связанные additions в `serving_control/http.py:633`, `entrypoints/backend.py`,
  `migrations/env.py`, canonical routes в `deploy/Caddyfile:26`; соответствующие
  task-owned tests и `tests/infrastructure/test_proxy_forwarding.py:142`.

Принятая основа: `.memory-bank/contracts/public-photo-search-api.md`,
`domains/browser-search-profile.md`, `contracts/photo-purchase-api.md`,
`domains/photo-orders.md`, public sections в `domains/realtime-search.md`,
`architecture/system-architecture.md`, `contracts/boundary-map.md`.
Пути сокращены относительно `.memory-bank/` и `src/face_moment/` соответственно.

## Доказательства и результат

- TASK-121: final verification attempt 3 и semantic-pass в `.protocols/TASK-121-T3-FT-013-W3/{verification,red-verification}.md`; regression tests в `tests/promo/test_browser_search_profile.py:172,199`. Исправления cosine endpoints находятся в `promo/browser_search_profile.py:119–124`; прежние FAIL не являются открытым долгом.
- TASK-122: `.protocols/TASK-122-T2-FT-013-W3/verification.md`, `.tasks/TASK-122-T2-FT-013-W3/{claim-evidence.md,verifier-outcome.json,verifier-native-sface-comparison.json,verifier-native-buffalo-comparison.json}` подтверждают native pairs, eligibility, best-face uniqueness, all-date scope и сохранение Promo SQL правил.
- TASK-127: `.protocols/TASK-127-T3-FT-014-W3/{verification,red-verification}.md`, `.tasks/TASK-127-T3-FT-014-W3/{verify2-edge.txt,red-concurrency.txt}` подтверждают исправленный HTTPS route, atomic singleton writes, immutable snapshot, rollback и сохранение unrelated state. Дефект маршрутизации устранён и не включён в открытые findings.

Текущие owner boundaries, транзакции, projections и миграции не показали подтверждённого механизма существенной maintenance burden или regression risk сверх принятого scope.

## Подтверждённые findings

## Ограничения уверенности

Это чтение текущего кода/diff и сохранённых независимых доказательств; тесты, native inference и deploy повторно не запускались. Compression evidence относится к одной representative portrait fixture: SFace large original/JPEG дают 0/0 лиц, поэтому общая точность на пользовательских снимках из него не следует. HTTP/slot/gallery integration и quote/order/payment принадлежат последующим задачам; их незавершённость не классифицирована как технический долг этой волны.
