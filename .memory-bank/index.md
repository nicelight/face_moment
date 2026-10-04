---
description: Главная карта знаний проекта (table of contents) для агентов.
status: active
---
# Memory Bank Index

## Pre-PRD discovery inputs

- [PAYMENS_TS.md](../PAYMENS_TS.md): принятые требования публичного поиска и
  покупки; согласованный [PRD](prd.md) декомпозирован в [EP-004](epics/EP-004.md),
  readiness/design route — [spec-backbone](spec-backbone.md).

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

## Public extension contracts

- [Public Search](contracts/public-photo-search-api.md): endpoints, scope и gallery bytes.
- [Browser profile](domains/browser-search-profile.md): А/Б и серверные результаты.
- [Purchase API](contracts/photo-purchase-api.md): tariff/admin, ЮKassa и download.
- [Photo Orders](domains/photo-orders.md): frozen quote, ZIP и entitlement.

## Architecture decision authority

- [.memory-bank/spec-backbone.md](spec-backbone.md): authority order, coverage
  matrix and current Planning Revision.
- [.memory-bank/architecture/system-architecture.md](architecture/system-architecture.md)
  and [.memory-bank/contracts/boundary-map.md](contracts/boundary-map.md):
  accepted architecture decisions and boundary contracts.

## Навигация

- [Advertising playlists](contracts/advertising-playlists.md): реклама площадок,
  воспроизведение, Cache Storage и обновления.

- [Первичная площадка](runbooks/server-deployment.md): одноразовое создание
  «СПА Сибирь 1» после migrations, проверка SFace assets и defaults; существующие
  площадки не меняются. API использует тот же сценарий создания.

- [.memory-bank/constitution.md](constitution.md): Project Constitution — top governing policy for agents.
- [.memory-bank/mbb/index.md](mbb/index.md): Правила ведения Memory Bank (MBB).
- [.memory-bank/roles/index.md](roles/index.md): Router for agent role contracts.
- [.memory-bank/roles/orchestrator.md](roles/orchestrator.md): Orchestrator role contract.
- [.memory-bank/roles/general.md](roles/general.md): General role contract for one-agent execution.
- [.memory-bank/roles/architect.md](roles/architect.md): Architect role contract.
- [.memory-bank/roles/explorer.md](roles/explorer.md): Explorer role contract.
- [.memory-bank/roles/implementer.md](roles/implementer.md): Implementer role contract.
- [.memory-bank/roles/reviewer.md](roles/reviewer.md): Reviewer role contract.
- [.memory-bank/roles/judge.md](roles/judge.md): Fresh read-only orchestration trajectory reviewer.
- [.memory-bank/prd.md](prd.md): Product requirements, including functional multi-venue operation.
- [.memory-bank/product.md](product.md): Face Moment shared multi-venue product
  identity, value, flow, constraints and non-goals (C4 L1).
- [.memory-bank/requirements.md](requirements.md): stable `REQ-*` requirements
  and `REQ -> Epic -> Feature -> Test` traceability.
- [.memory-bank/changelog.md](changelog.md): durable Memory Bank change history
  and wave-boundary reconciliation record.
- [.memory-bank/bugs/task-090-realtime-event-post-commit-sql.md](bugs/task-090-realtime-event-post-commit-sql.md):
  archived TASK-090 failure evidence and verified TASK-094 resolution.
- [.memory-bank/bugs/task-101-calibration-missing-original-terminalization.md](bugs/task-101-calibration-missing-original-terminalization.md):
  immutable TASK-101 failure evidence and verified TASK-111 successor
  resolution.
- [.memory-bank/epics/index.md](epics/index.md): router for the four product
  epics (C4 L2).
- [.memory-bank/features/index.md](features/index.md): router for the sixteen product
  features (C4 L3).
- [.memory-bank/behavior-specs/](behavior-specs/): Optional JSON behavior examples linked from feature docs and task `source_artifacts`.
- [.memory-bank/tasks/index.json](tasks/index.json): Authoritative JSON task record index.
- [.memory-bank/schemas/task.schema.json](schemas/task.schema.json): JSON schema for task records.
- [.memory-bank/workflows/index.md](workflows/index.md): Workflow router and tier/execution/sync policies.

- [.memory-bank/spec-index.md](spec-index.md): Pure SDD spec registry and planned-spec index.
- [.memory-bank/spec-backbone.md](spec-backbone.md): accepted complete global
  SDD baseline at Planning Revision 4, Foundation decision и завершённые
  design/task-plan routes публичного поиска и покупки.
- [.memory-bank/foundation.md](foundation.md): Accepted Foundation Dev Path,
  minimum substrate path, feature pressure map and exit criteria.
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
- [Multi-venue verification](testing/index.md#functional-multi-venue-operation-ac-27):
  shared revision, native two-venue processing/search, restart and isolation evidence.
- [.memory-bank/adrs/](adrs/): ADR решения.
- [opencv5_Migration.md](../opencv5_Migration.md): операторский стратегический
  план перехода runtime на OpenCV 5.

- [.memory-bank/domains/index.md](domains/index.md): subject-based domain
  models, storage, schemas, migrations and persistence rules.
- [.memory-bank/domains/calibration.md](domains/calibration.md): immutable
  Calibration datasets/runs/results, offline evaluation, manual apply and
  retention.
- [.memory-bank/contracts/index.md](contracts/index.md): canonical boundary and
  API contract router.
- [.memory-bank/contracts/boundary-map.md](contracts/boundary-map.md): Canonical
  capability ownership, cross-store/auth/media contracts, application
  boundaries and cross-slice write rules.
- [.memory-bank/states/](states/): Lifecycle/state rules (prefer when present).
- [.memory-bank/states/lifecycle-map.md](states/lifecycle-map.md): Canonical
  Photo, processing, inventory, purge, Promo and diagnostics lifecycles.
- [.memory-bank/runbooks/](runbooks/): Runbooks и operational procedures.
- [.memory-bank/runbooks/app_guide_ru.md](runbooks/app_guide_ru.md):
  краткое руководство пользователя по приложению и средам.
- [.memory-bank/runbooks/server-deployment.md](runbooks/server-deployment.md):
  canonical non-destructive deploy на facecentral и public acceptance.
- [.memory-bank/runbooks/vps-caddy.md](runbooks/vps-caddy.md): VPS Caddy,
  FRP-backhaul, ACME certificate и доверенный visitor IP.
- [.memory-bank/runbooks/local-test-deployment.md](runbooks/local-test-deployment.md):
  локальный stack и packaged smoke.
- [.memory-bank/runbooks/diagnostic-retention.md](runbooks/diagnostic-retention.md):
  pilot-host daily retention timer activation, observation and recovery.
- [.memory-bank/runbooks/display-and-central-restart.md](runbooks/display-and-central-restart.md):
  verified browser and intact-volume central-runtime recovery procedure.
- [.memory-bank/testing/index.md](testing/index.md): Testing strategy.
- [.memory-bank/skills/index.md](skills/index.md): Skill registry.
- [mermaids/README.md](../mermaids/README.md): обзорные diagrams of the accepted
  product, runtime, lifecycle, Promo, diagnostics and Feature-to-runtime
  allocation contracts.

## Product Decomposition

- [EP-004](epics/EP-004.md): accepted public camera discovery, combined quote
  and independently deliverable free/paid originals; [FT-013](features/FT-013.md),
  [FT-014](features/FT-014.md), [FT-015](features/FT-015.md),
  [FT-016](features/FT-016.md): design complete; [20 задач](tasks/plans/index.md)
  получили task-plan APPROVE при Revision 4. В Wave 1 scheduler закрыл
  [TASK-120](tasks/TASK-120-T2-FT-013-W1.task.json) после independent PASS
  камеры/IndexedDB. В Wave 3 закрыты
  [TASK-121](tasks/TASK-121-T3-FT-013-W3.task.json): profile/A/B,
  [TASK-122](tasks/TASK-122-T2-FT-013-W3.task.json): native selected-venue search
  и [TASK-127](tasks/TASK-127-T3-FT-014-W3.task.json): persistent tariff/API;
  в Wave 4 [TASK-130](tasks/TASK-130-T2-FT-014-W4.task.json): staff tariff editor
  закрыт scheduler после independent functional PASS обеих ролей.
  В Wave 6 [TASK-123](tasks/TASK-123-T3-FT-013-W6.task.json): public API/current
  result и paid/free supplier закрыт после independent functional PASS и
  semantic-pass. В Wave 7 scheduler закрыл
  [TASK-124](tasks/TASK-124-T3-FT-013-W7.task.json): private preview bytes,
  [TASK-125](tasks/TASK-125-T2-FT-013-W7.task.json): browser search/progress,
  [TASK-128](tasks/TASK-128-T3-FT-014-W7.task.json): authoritative quote и
  [TASK-131](tasks/TASK-131-T3-FT-014-W7.task.json): staff paid/free mode.
  В Wave 8 закрыты [TASK-126](tasks/TASK-126-T2-FT-013-W8.task.json): gallery
  и [TASK-132](tasks/TASK-132-T3-FT-014-W8.task.json): frozen order core.
  FT-013 завершена (verified) после [feature semantic-pass](../.tasks/FT-013/FT-013-S-RED-VERIFY-final-report-docs-01.md);
  REQ-PUB-002 verified. В Wave 9 закрыты [TASK-129](tasks/TASK-129-T2-FT-014-W9.task.json): combined
  selection/sticky quote и [TASK-133](tasks/TASK-133-T3-FT-015-W9.task.json): ZIP
  runtime/recovery/failure mail. FT-014 verified после всех шести done и
  [feature semantic-pass](../.tasks/FT-014/FT-014-S-RED-VERIFY-final-report-docs-01.md);
  REQ-PUB-003/004 verified. В Wave 10 закрыта
  [TASK-134](tasks/TASK-134-T3-FT-015-W10.task.json): private bearer ZIP/expiry
  после independent functional PASS и semantic-pass. В Wave 11 закрыта
  [TASK-135](tasks/TASK-135-T3-FT-015-W11.task.json): public order HTTP/free
  integration после independent functional PASS и semantic-pass. В Wave 12
  закрыта [TASK-136](tasks/TASK-136-T2-FT-015-W12.task.json): free browser download
  после independent [functional PASS](../.protocols/TASK-136-T2-FT-015-W12/verification.md).
  FT-015 active/verified после всех TASK-133..136 done,
  [feature semantic-pass](../.tasks/FT-015/FT-015-S-RED-VERIFY-final-report-docs-01.md)
  и явного owner completion. Terminal queue: 17/20 done (TASK-120..136),
  TASK-137..139 blocked. YooKassa TEST merchant/fiscal configuration и разрешение
  external test calls отсутствуют на preflight TASK-137;
  [stop evidence](../.tasks/TASK-137-T3-FT-016-W12/TASK-137-T3-FT-016-W12-S-EXECUTE-final-report-docs-01.md).
  [Checkpoint](../.protocols/AUTONOMOUS-RUN/status.md): HALT_BLOCKING_QUESTIONS;
  после local TEST config и authorization продолжить `/autopilot` и fresh
  `/exe TASK-137-T3-FT-016-W12`. FT-016/EP-004 lifecycle planned;
  REQ-PUB-002/003/004 verified, shared REQ-PUB-001/005..008 planned из-за paid
  integration. [changelog](changelog.md) и feature evidence содержат verification links.

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

- [Application guide](runbooks/app_guide_ru.md): staff, kiosk, Promo, QR and
  current public-site limits.
- [Motion Atlas design brief](../.design/motion-atlas-integration/DESIGN_BRIEF.md):
  operator presets, original discussion and implementation decisions.

- [Optional second Promo slide](contracts/promo-display-api.md#optional-second-slide):
  accepted fullscreen gallery; [FT-004](features/FT-004.md) selection/persistence verified,
  [FT-005](features/FT-005.md) authenticated media and client settings/grid/replay verified.
  [Kiosk guide](runbooks/app_guide_ru.md#киоск-promo-и-qr) explains local enablement.
