---
description: Глобальные инварианты и запреты проекта (MUST/NEVER).
status: active
last_updated: 2026-07-24
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
- Сохранять result/session integrity и expired-data isolation, определённые в
  [.memory-bank/prd.md](prd.md) `FR-CAP-05..08` и `FR-UX-03..10`, не создавая
  здесь параллельную копию этих правил.
- Делать browser/server logging и diagnostic ingestion неблокирующими для
  capture, search, Promo и QR; protected artifacts и technical logs остаются
  разными data classes согласно PRD `FR-DIAG-04..05` и `FR-DEV-04`.
- Исключать soft-deleted Photo из search, participant media access и recent
  statistics, сохраняя Photo и связанные данные для restore без reprocessing.
- Выполнять hard purge по fixed project-wide snapshot через один resumable
  global run на shared worker без per-photo purge lifecycle или purge jobs
  table.
- Сохранять core Attempt и diagnostic evidence при hard purge Photo, даже когда
  удаляются связанные Promo result/session.
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
- Не добавлять Redis/broker, ANN, distributed scheduling, extra workers,
  GPU-first или внешний observability stack без измеримого bottleneck либо
  требования текущего scope.
- Не помещать в technical logs запрещённые sensitive payloads, перечисленные в
  PRD `FR-DEV-04` и `NFR-DATA-04`.
- Не применять serving threshold или quality-gate recommendation автоматически.
- Не добавлять собственный HTTP error framework/envelope и не принимать
  client decisions по тексту `5xx` response.
- Не создавать PostgreSQL schemas/users/ACLs или независимые migration streams
  per capability slice; не разрешать `ON DELETE` cascade пересекать ownership
  boundary или удалять core Attempt/diagnostic evidence вместе с Photo.

## Notes

- Эти правила основаны на ratified
  [.memory-bank/constitution.md](constitution.md), clarified
  [.memory-bank/prd.md](prd.md), принятых улучшениях
  [arch_impr1.md](../arch_impr1.md), [IDEA_APP.md](../IDEA_APP.md) и
  [IDEA_DEBUG.md](../IDEA_DEBUG.md); `IDEA_INGEST.md` сохраняется как
  historical evidence, а при конфликте действует precedence из
  [.memory-bank/spec-backbone.md](spec-backbone.md).
- Ссылайся на этот файл из архитектурных, контрактных и execution docs, если
  правило является cross-cutting.
