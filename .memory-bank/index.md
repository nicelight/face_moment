---
description: Главная карта знаний проекта (table of contents) для агентов.
status: active
---
# Memory Bank Index

## Pre-PRD discovery inputs

- [IDEA_APP.md](../IDEA_APP.md): Концепция приложения, обязательные MVP-границы
  и явно отмеченные рекомендации.
- [IDEA_OS.md](../IDEA_OS.md): Инфраструктурная концепция, topology display
  clients и deployment-рекомендации.
- [IDEA_INGEST.md](../IDEA_INGEST.md): Batch-first поступление фотографий,
  direct upload и импорт публичных ссылок Яндекс Диска из произвольных
  аккаунтов фотографов.
- [IDEA_DEBUG.md](../IDEA_DEBUG.md): Developer-only browser/server logging,
  investigation attempts и KISS-подбор face threshold/quality gates.

## Навигация

- [.memory-bank/constitution.md](constitution.md): Project Constitution — top governing policy for agents.
- [.memory-bank/mbb/index.md](mbb/index.md): Правила ведения Memory Bank (MBB).
- [.memory-bank/roles/orchestrator.md](roles/orchestrator.md): Orchestrator role contract.
- [.memory-bank/roles/general.md](roles/general.md): General role contract for one-agent execution.
- [.memory-bank/roles/worker.md](roles/worker.md): Worker role contracts.
- [.memory-bank/prd.md](prd.md): Clarified Product Requirements Document for the current one-СПА pilot.
- [.memory-bank/product.md](product.md): Face Moment one-СПА pilot product
  identity, value, flow, constraints and non-goals (C4 L1).
- [.memory-bank/requirements.md](requirements.md): stable `REQ-*` requirements
  and `REQ -> Epic -> Feature -> Test` traceability.
- [.memory-bank/epics/index.md](epics/index.md): router for the three product
  epics (C4 L2).
- [.memory-bank/features/index.md](features/index.md): router for the eleven product
  features (C4 L3).
- [.memory-bank/behavior-specs/](behavior-specs/): Optional JSON behavior examples linked from feature docs and task `source_artifacts`.
- [.memory-bank/tasks/index.json](tasks/index.json): Authoritative JSON task record index.
- [.memory-bank/schemas/task.schema.json](schemas/task.schema.json): JSON schema for task records.
- [.memory-bank/workflows/index.md](workflows/index.md): Workflow router and tier/execution/sync policies.

- [.memory-bank/spec-index.md](spec-index.md): Pure SDD spec registry and planned-spec index.
- [.memory-bank/spec-backbone.md](spec-backbone.md): Pre-PRD framing status and global backbone state for `/write-prd` and `/spec-design`.
- `.memory-bank/user-scenarios.md`: optional user scenarios and architecture implications when created by `/spec-init` or `/spec-design`.
- [.memory-bank/glossary.md](glossary.md): Общий словарь терминов и доменных значений.
- [.memory-bank/invariants.md](invariants.md): Глобальные MUST/NEVER правила.
- [.memory-bank/architecture/](architecture/): Duo + boundaries (WHAT/WHY).
- [.memory-bank/guides/](guides/): Valid HOW docs для использования, запуска и troubleshooting.
- [.memory-bank/adrs/](adrs/): ADR решения.

- [.memory-bank/domains/](domains/): Subject-based domain models, storage, schemas, migrations, and persistence rules.
- [.memory-bank/contracts/](contracts/): Контракты и boundary specs (prefer when present).
- [.memory-bank/contracts/boundary-map.md](contracts/boundary-map.md): Lightweight responsibility/scope boundary notes for decomposition and task runtime context.
- [.memory-bank/states/](states/): Lifecycle/state rules (prefer when present).
- [.memory-bank/runbooks/](runbooks/): Runbooks и operational procedures.
- [.memory-bank/testing/index.md](testing/index.md): Testing strategy.
- [.memory-bank/skills/index.md](skills/index.md): Skill registry.

## Product Decomposition

- [.memory-bank/epics/EP-001.md](epics/EP-001.md): fresh searchable
  commercial-photo inventory.
- [.memory-bank/epics/EP-002.md](epics/EP-002.md): automatic participant Promo
  and QR continuation.
- [.memory-bank/epics/EP-003.md](epics/EP-003.md): explainable diagnostics,
  annotation and Calibration.
- [.memory-bank/features/index.md](features/index.md): feature-level outcomes,
  acceptance, failure behavior and SDD gate routing.
