---
description: Глобальные инварианты и запреты проекта (MUST/NEVER).
status: active
last_updated: 2026-07-20
source_of_truth:
  - .memory-bank/invariants.md
---
# Invariants

## MUST

- Для текущего закрытого pilot и следующих нескольких версий приоритизировать
  измеримые latency и стабильность контура Promo/QR.
- Подтверждать новые acceptance gates текущим Product Brief или явным решением
  владельца продукта.
- Считать подтверждённый фотографом batch `visit_date` authoritative business
  scope коммерческих фотографий; EXIF, имя файла и upload time не могут
  молча заменить его.
- Обрабатывать и сравнивать embeddings только внутри совместимой immutable
  `pipeline_revision`, сохраняя native detector/preprocessing/alignment каждого
  face pipeline.
- Сохранять result/session integrity и expired-data isolation, определённые в
  [.memory-bank/prd.md](prd.md) `FR-CAP-05..08` и `FR-UX-03..10`, не создавая
  здесь параллельную копию этих правил.
- Делать browser/server logging и diagnostic ingestion неблокирующими для
  capture, search, Promo и QR; protected artifacts и technical logs остаются
  разными data classes согласно PRD `FR-DIAG-04..05` и `FR-DEV-04`.

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

## Notes

- Эти правила основаны на ratified
  [.memory-bank/constitution.md](constitution.md), clarified
  [.memory-bank/prd.md](prd.md), [IDEA_APP.md](../IDEA_APP.md),
  [IDEA_INGEST.md](../IDEA_INGEST.md) и [IDEA_DEBUG.md](../IDEA_DEBUG.md); при
  конфликте действует precedence из
  [.memory-bank/spec-backbone.md](spec-backbone.md).
- Ссылайся на этот файл из архитектурных, контрактных и execution docs, если
  правило является cross-cutting.
