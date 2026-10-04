# Public photo Wave 6: advisory technical-debt review

Дата: 2026-10-04. Существенный технический долг в проверенных изменениях не подтверждён. Отчёт информационный и не блокирует очередь задач.

## Проверенный scope

Только фактические изменения `TASK-123-T3-FT-013-W6`: public search/current result и persistent paid/free supplier. Другие исторические W6, ранее выполненный native/exact search и незавершённые preview/UI/order/payment не включены в оценку долга.

- `src/face_moment/promo/public_photo_search.py:26,49,61,80`: result model, current-only authority, active projection, atomic profile/result orchestration.
- `src/face_moment/promo/public_search_http.py:37,76,105,125`: transport validation, venues/current routes, Origin/HTTPS, IP/profile limits и private cookie.
- `src/face_moment/serving_control/ingest_target.py:36,148,160` и `src/face_moment/serving_control/public_search_context.py:52`: owner free flag, explicit creation, mutation и immutable public projection.
- `src/face_moment/inventory/public_photo_projection.py:24` и `src/face_moment/processing/public_selfie_search.py:75`: active photo references и matched-date common read.
- `migrations/versions/0030_venue_free_mode.py`, `migrations/versions/0031_public_search_results.py`, result metadata registration в `migrations/env.py`; public composition в `src/face_moment/entrypoints/backend.py`, `src/face_moment/entrypoints/realtime.py` и `deploy/Caddyfile:24,66`.
- Task-owned assertions: `tests/promo/test_public_search_api.py:153,206,238,284,297,335` и `tests/serving_control/test_venue_free_mode.py:18,45`.

Проверены текущий source и соответствующий diff; общий dirty diff не принят за изменения одной задачи. Принятая основа: `.memory-bank/contracts/public-photo-search-api.md`, `.memory-bank/domains/browser-search-profile.md`, venue extension в `.memory-bank/domains/photo-orders.md`, public sections `.memory-bank/architecture/system-architecture.md` и `.memory-bank/contracts/boundary-map.md`.

## Доказательства и результат

- `.protocols/TASK-123-T3-FT-013-W6/verification.md`, `.tasks/TASK-123-T3-FT-013-W6/verify-fresh-gates.txt` и `verify-typecheck.txt`: независимые 8 scoped tests и mypy для 118 файлов; assertions просмотрены. Scope/privacy/current-only, paid/free persistence, migration roundtrip и failure/deadline rollback подтверждены.
- `.tasks/TASK-123-T3-FT-013-W6/verify-native-https-observations.json` и test `test_real_https_edge_warmed_native_cookie_origin_and_private_store`: фактический loopback HTTPS через Caddy и production apps с warmed SFace; own current read, cookie replay, foreign Origin и неизменённый private original.
- `.protocols/TASK-123-T3-FT-013-W6/red-verification.md` и `.tasks/TASK-123-T3-FT-013-W6/red-atomicity-probe.{py,txt}`: поздняя ошибка после flush откатывает новый profile/result, сохраняет существующий профиль/last visit/current result; slot освобождается и следующий поиск проходит.
- `.tasks/TASK-123-T3-FT-013-W6/competing-promo-failure.md` и `public_photo_search.py:95–102`: первоначальное удержание venue locks во время native исправлено короткой snapshot transaction. Неизменённая concurrency assertion в `tests/promo/test_public_search_api.py:297` подтверждена независимой проверкой. Исправленный дефект не является открытым долгом.

Текущий код не показал подтверждённого механизма существенного роста стоимости изменений, нарушения owner boundaries или открытого regression risk в этом scope. Profile/result остаются в одной транзакции, foreign owners предоставляют projections, migrations идут в принятом linear stream. Общий slot и существующие adapters переиспользованы без дополнительной runtime модели.

## Подтверждённые findings

## Ограничения уверенности

Проведено чтение кода, diff, assertions и сохранённых независимых доказательств; новые tests, native inference, deployment и изменения workflow не выполнялись. Материальность долга за пределами проверенного scope этим отчётом не оценивалась. Concurrency proof использует held native boundary double; warmed SFace проверен отдельным HTTPS flow. Перезаписанный ранний expanded log раскрыт в executor evidence и не использован как самостоятельное доказательство. Deprecation warnings сами по себе не доказывают существенный долг. При отсутствии подтверждённых findings приоритет и remediation не назначаются.
