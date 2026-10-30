# Главная: информация покупателям — deployment acceptance

- Разрешение владельца: «делай» после вопроса о push/deploy.
- Application commit: `8f55e69`, pushed в `origin/main`; server base: `47f9a19`.
- Delta к server base: только `client/site.html`, `client/site.css` и документация.
  Schema/ORM, миграции, зависимости, Compose, env и модели не менялись.
- На странице: 350 ₽ за платное фото по прямому решению владельца; это
  публикационный текст, серверный тариф не менялся. Контакты вымышленные и
  явно помечены, оферта/политика остаются проектами до реальных данных.

## Сборка и проверки

`npm run test:unit`: 110/110 PASS. Проверены уникальность HTML IDs,
все внутренние якоря и `git diff --check`.
Локальный packaged smoke не стартовал: Docker daemon недоступен в обоих
локальных contexts. Exact Git archive проверен на facecentral в отдельном
временном окружении `/tmp/face-moment-purchase-8f55e69-uPu2wh`.

Обычная Dockerfile-сборка была отменена во время затянувшейся загрузки GCC
из Debian: mutable base tag вызвал загрузку новой базы и системных пакетов.
Для static-only release собран производный образ от сохранённого рабочего
`face-moment:rollback-before-purchase-8f55e69`, с COPY только двух целевых
HTML/CSS и владельцем app:app. Остальные 436 runtime-файлов сверены с target
по SHA-256. После сборки сверены все 438 файлов (src, migrations, tests,
client, pyproject.toml, alembic.ini, storage probe и Caddyfile).

Существующий fallback `SMOKE_PREBUILT_IMAGE=face-moment:release-8f55e69`
в `scripts/smoke-runtime.sh` завершился `runtime_smoke=ok`. Подтверждены
миграции в disposable DB до 0033, native model, initializer/no-op retry,
две площадки, readiness, HTTPS/auth routes и storage persistence после restart.
Очистка только test-owned resources: `owned_cleanup_status=0`,
`owned_image_cleanup_status=0`. Новый dependency build не заявляется.
Полный redacted log: `/tmp/face-moment-purchase-smoke-prebuilt.log` на facecentral.

## Production rollout

Серверный checkout обновлён fast-forward, без сброса локальных изменений.
Проверенный release image назначен `face-moment:dev`; application roles и edge
перезапущены по narrow static-only path. Production migrate/initializer не
запускались; PostgreSQL и MinIO не перезапускались. Конфигурация Caddy валидна.

- Old application image: `sha256:e81993f1e6bf66f616e92ba7465a635bd894cfde625c05da89ae9d95c5b201fc`.
- New application image: `sha256:9941fbed50334a213a03b062ed620a24265c7f8c7282ad965ed3c8d1561a1f33`.
- Release tag: `face-moment:release-8f55e69`; rollback tag сохранён.
- Backend, worker, realtime healthy; worker/realtime production_model_loaded
  и recovery_completed=true.
- Production volume names до/после совпали; `.env` остался mode600/facemoment.
- Retention timer enabled/active, следующий запуск 2026-10-31 00:00 +07;
  таймер не останавливали.

Внешние HTTP-проверки: [public-checks.txt](public-checks.txt), 10/10 PASS.
HTML `/` и `/site`, CSS `/client/site.css` побайтово совпадают с целевыми
файлами. Публичные search/payment/email операции не выполнялись.
Payment credentials, SMTP и реальный тариф не менялись.
