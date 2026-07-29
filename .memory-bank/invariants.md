---
description: Глобальные инварианты и запреты проекта (MUST/NEVER).
status: active
last_updated: 2026-07-29
source_of_truth:
  - .memory-bank/invariants.md
---
# Invariants

## MUST

- Для текущего закрытого pilot и следующих нескольких версий приоритизировать
  измеримые latency и стабильность контура Promo/QR.
- Подтверждать новые acceptance gates текущим Product Brief или явным решением
  владельца продукта.
- Считать выбранный фотографом и сохранённый с каждой accepted Photo
  `visit_date` authoritative business scope коммерческой фотографии; EXIF, имя
  файла и upload time не могут молча заменить его.
- Назначать каждой Photo effective `captured_at`: reliable EXIF time в timezone
  СПА, иначе server-side start time upload этого файла, иначе 01:00
  authoritative `visit_date`.
- Создавать Photo и её serving-pipeline `pending` state одним per-photo commit;
  PostgreSQL-backed очередь MUST сохранять свою `pending`/`processing`
  population при restart backend/worker, а незавершённая `processing` работа
  должна возвращаться в `pending`.
- Обрабатывать и сравнивать embeddings только внутри совместимой immutable
  `pipeline_revision`, сохраняя native detector/preprocessing/alignment каждого
  face pipeline.
- Загружать browser-native Chromium `SpaPromoClient` с центрального HTTPS
  origin и, пока client активен, держать ровно один authenticated 10-second
  HTTP long-poll к fixed-name mDNS ESP32, сразу продолжая после event/timeout.
- Обходить ready reference series хронологически через BlazeFace Full-range,
  останавливаться на occurrence 20 и передавать первые не более 20 crops плюс
  metadata одним synchronous multipart request; при нуле proposals отправлять
  manifest-only request. Сервер отклоняет request body больше `20 MiB` через
  HTTP `413` до domain admission, без oversize domain outcome и без
  client-side ranking/truncation.
- Измерять основной `<10 s` interval от начала local processing до полной
  видимости QR на одном client monotonic clock, включая local processing и
  request send; diagnostics показывает три client markers из PRD `FR-DIAG-02`.
- Сохранять result/session integrity и expired-data isolation, определённые в
  [.memory-bank/prd.md](prd.md) `FR-CAP-05..08` и `FR-UX-03..10`, не создавая
  здесь параллельную копию этих правил.
- Делать browser/server logging и diagnostic ingestion неблокирующими для
  capture, search, Promo и QR. Capture-derived media не является protected
  только из-за image content; credentials, private infrastructure, commercial
  Photo media, personalized data, names/annotations и admin actions сохраняют
  собственные protection boundaries.
- Сохранять core Attempt для каждого server-admitted request; delivery
  client-only offline attempt и detailed evidence остаются best-effort и не
  требуют durable-until-ack outbox.
- Исключать soft-deleted Photo из новых search/result formation и recent
  statistics, сохраняя Photo и связанные данные для restore без reprocessing.
  Уже выданная Promo/session продолжает использовать media, пока она существует.
- Выполнять hard purge по fixed project-wide snapshot через один resumable
  global run на shared worker без per-photo purge lifecycle или purge jobs
  table.
- Отклонять restore/restore-all для Photo из подтверждённого non-terminal
  hard-purge snapshot.
- Сохранять существующие Promo sessions, core Attempt и diagnostic evidence при
  hard purge Photo; UI/device loading пропускает отсутствующую media без
  invalidation session, replacement или пересчёта issued `N`.
- Выражать transport failures стандартными HTTP statuses (`401`, `403`, `413`,
  `422`, `429`, `5xx`), а результаты принятого capture/search request —
  `2xx` response с компактным typed domain outcome.
- Использовать одну PostgreSQL application schema, один SQLAlchemy
  `Base/MetaData`, одну Alembic configuration и один последовательный migration
  stream, сохраняя capability-level write ownership.

## NEVER

- Не добавлять speculative product gates для будущих версий в текущий pilot.
- Не расширять pilot search/group semantics смешиванием pipeline revisions,
  cross-pipeline preprocessing, tracking, identity clustering, ensemble или
  top-1/top-2 margin.
- Не выполнять на client proposals ranking/top-5, authoritative quality gating,
  tracking, clustering, deduplication, embeddings или search.
- Не добавлять для FT-003 local bridge/separate local client web server,
  WebSocket, sensor discovery service, pairing/PKI/rotation lifecycle,
  параллельный YuNet, generic detector/runtime abstraction или model OTA.
- Не требовать proof/annotation local-detector misses или diagnostic upload
  полных/downscaled reference frames.
- Не добавлять Redis/broker, ANN, distributed scheduling, extra workers,
  GPU-first или внешний observability stack без измеримого bottleneck либо
  требования текущего scope.
- Не помещать в technical logs запрещённые sensitive payloads, перечисленные в
  PRD `FR-DEV-04` и `NFR-DATA-04`.
- Не применять serving threshold или quality-gate recommendation автоматически.
- Не добавлять собственный HTTP error framework/envelope и не принимать
  client decisions по тексту `5xx` response.
- Не добавлять realtime waiter queue: singleton slot возвращает typed `busy`.
- Не создавать PostgreSQL schemas/users/ACLs или независимые migration streams
  per capability slice; не разрешать `ON DELETE` cascade пересекать ownership
  boundary или удалять core Attempt/diagnostic evidence вместе с Photo.

## Notes

- Эти правила основаны на ratified
  [.memory-bank/constitution.md](constitution.md), clarified
  [.memory-bank/prd.md](prd.md), зарегистрированных
  [system architecture](architecture/system-architecture.md) и
  [boundary contracts](contracts/boundary-map.md), а также
  [IDEA_APP.md](../IDEA_APP.md), [IDEA_DEBUG.md](../IDEA_DEBUG.md) и явных
  client/media решений [IDEA_CLIENT.md](../IDEA_CLIENT.md);
  `IDEA_INGEST.md` сохраняется как historical evidence, а при конфликте
  действует precedence из
  [.memory-bank/spec-backbone.md](spec-backbone.md).
- Ссылайся на этот файл из архитектурных, контрактных и execution docs, если
  правило является cross-cutting.
