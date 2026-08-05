---
description: Глобальные инварианты и запреты проекта (MUST/NEVER).
status: active
last_updated: 2026-08-05
source_of_truth:
  - .memory-bank/invariants.md
---
# Invariants

## MUST

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

## NEVER

- Не расширять pilot search/group semantics смешиванием pipeline revisions,
  cross-pipeline preprocessing, tracking, identity clustering, ensemble или
  top-1/top-2 margin.
- Не помещать в technical logs запрещённые sensitive payloads, перечисленные в
  PRD `FR-DEV-04` и `NFR-DATA-04`.
- Не применять serving threshold или quality-gate recommendation автоматически.
- Не разрешать `ON DELETE` cascade пересекать ownership boundary или удалять
  core Attempt/diagnostic evidence вместе с Photo.
