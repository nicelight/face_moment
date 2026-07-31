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
- [IDEA_INGEST.md](../IDEA_INGEST.md): per-photo ingest и processing-концепция;
  при расхождении product contract и acceptance определяет PRD.
- [IDEA_DEBUG.md](../IDEA_DEBUG.md): Developer-only browser/server logging,
  investigation attempts и KISS-подбор face threshold/quality gates.
- [IDEA_CLIENT.md](../IDEA_CLIENT.md): принятые client behavior, timing и
  capture-derived media-policy decisions с явно отложенными technical choices.

## Architecture decision authority

- [.memory-bank/spec-backbone.md](spec-backbone.md): authority order, coverage
  matrix and current Planning Revision.
- [.memory-bank/architecture/system-architecture.md](architecture/system-architecture.md)
  and [.memory-bank/contracts/boundary-map.md](contracts/boundary-map.md):
  accepted architecture decisions and boundary contracts.

## Навигация

- [.memory-bank/constitution.md](constitution.md): Project Constitution — top governing policy for agents.
- [.memory-bank/mbb/index.md](mbb/index.md): Правила ведения Memory Bank (MBB).
- [.memory-bank/roles/index.md](roles/index.md): Router for agent role contracts.
- [.memory-bank/roles/orchestrator.md](roles/orchestrator.md): Orchestrator role contract.
- [.memory-bank/roles/general.md](roles/general.md): General role contract for one-agent execution.
- [.memory-bank/roles/architect.md](roles/architect.md): Architect role contract.
- [.memory-bank/roles/explorer.md](roles/explorer.md): Explorer role contract.
- [.memory-bank/roles/implementer.md](roles/implementer.md): Implementer role contract.
- [.memory-bank/roles/reviewer.md](roles/reviewer.md): Reviewer role contract.
- [.memory-bank/prd.md](prd.md): Clarified Product Requirements Document for the current one-СПА pilot.
- [.memory-bank/product.md](product.md): Face Moment one-СПА pilot product
  identity, value, flow, constraints and non-goals (C4 L1).
- [.memory-bank/requirements.md](requirements.md): stable `REQ-*` requirements
  and `REQ -> Epic -> Feature -> Test` traceability.
- [.memory-bank/epics/index.md](epics/index.md): router for the three product
  epics (C4 L2).
- [.memory-bank/features/index.md](features/index.md): router for the twelve product
  features (C4 L3).
- [.memory-bank/behavior-specs/](behavior-specs/): Optional JSON behavior examples linked from feature docs and task `source_artifacts`.
- [.memory-bank/tasks/index.json](tasks/index.json): Authoritative JSON task record index.
- [.memory-bank/schemas/task.schema.json](schemas/task.schema.json): JSON schema for task records.
- [.memory-bank/workflows/index.md](workflows/index.md): Workflow router and tier/execution/sync policies.

- [.memory-bank/spec-index.md](spec-index.md): Pure SDD spec registry and planned-spec index.
- [.memory-bank/spec-backbone.md](spec-backbone.md): accepted complete global
  SDD backbone at Planning Revision 4, feature blockers and verified Foundation
  handoff.
- [.memory-bank/foundation.md](foundation.md): Accepted Foundation Dev Path,
  verified substrate scope, concrete Foundation gate and completion evidence.
- [.memory-bank/features/FT-000-foundation.md](features/FT-000-foundation.md):
  verified reserved executable-baseline pseudo-feature, tasking and evidence
  links.
- `.memory-bank/user-scenarios.md`: optional user scenarios and architecture implications when created by `/spec-init` or `/spec-design`.
- [.memory-bank/glossary.md](glossary.md): Общий словарь терминов и доменных значений.
- [.memory-bank/invariants.md](invariants.md): Глобальные MUST/NEVER правила.
- [.memory-bank/architecture/](architecture/): Duo + boundaries (WHAT/WHY).
- [.memory-bank/architecture/system-architecture.md](architecture/system-architecture.md):
  canonical greenfield system shape, capability ownership and Architecture
  Spine.
- [.memory-bank/guides/](guides/): Valid HOW docs для использования, запуска и troubleshooting.
- [.memory-bank/adrs/](adrs/): ADR решения.

- [.memory-bank/domains/](domains/): Subject-based domain models, storage, schemas, migrations, and persistence rules.
- [.memory-bank/contracts/](contracts/): Контракты и boundary specs (prefer when present).
- [.memory-bank/contracts/boundary-map.md](contracts/boundary-map.md): Canonical
  capability ownership, cross-store/auth/media contracts, application
  boundaries and cross-slice write rules.
- [.memory-bank/states/](states/): Lifecycle/state rules (prefer when present).
- [.memory-bank/states/lifecycle-map.md](states/lifecycle-map.md): Canonical
  Photo, processing, inventory, purge, Promo and diagnostics lifecycles.
- [.memory-bank/runbooks/](runbooks/): Runbooks и operational procedures.
- [.memory-bank/testing/index.md](testing/index.md): Testing strategy.
- [.memory-bank/skills/index.md](skills/index.md): Skill registry.
- [mermaids/README.md](../mermaids/README.md): обзорные diagrams of the accepted
  product, runtime, lifecycle, Promo and diagnostics contracts.

## Product Decomposition

- [.memory-bank/epics/EP-001.md](epics/EP-001.md): fresh searchable
  commercial-photo inventory, role-scoped inventory operations and recent
  per-СПА processing statistics.
- [.memory-bank/epics/EP-002.md](epics/EP-002.md): automatic participant Promo
  and QR continuation.
- [.memory-bank/epics/EP-003.md](epics/EP-003.md): explainable diagnostics,
  annotation and Calibration.
- [.memory-bank/features/index.md](features/index.md): feature-level outcomes,
  stable `FT-<NNN>-AC-<NNN>` acceptance closure, failure behavior,
  requirement traceability and SDD gate routing.
