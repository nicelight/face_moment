---
description: Pure SDD spec registry and planned-spec index.
status: active
last_updated: 2026-08-01
source_of_truth:
  - .memory-bank/spec-index.md
---
# SDD Spec Index

## Purpose
- Keep a concise registry of existing and planned SDD specs.
- Read this index before creating new specs or doing serious design-pressure work.
- Keep readiness, open design questions, backbone status, and routing handoffs in [.memory-bank/spec-backbone.md](spec-backbone.md).
- Feature `spec_design_status` lives in feature frontmatter, not in this index.

## Spec Registry
| Type | Path | Status | Scope | Change route |
|---|---|---|---|---|
| governance | [.memory-bank/constitution.md](constitution.md) | active | Top governing policy. | /constitution |
| invariants | [.memory-bank/invariants.md](invariants.md) | active | Global MUST/NEVER rules grounded in ratified governance decisions. | /constitution, /spec-init, or /spec-design |
| glossary | [.memory-bank/glossary.md](glossary.md) | active | Canonical Face Moment vocabulary and disambiguation rules. | /brief, /spec-init, or /spec-design |
| architecture | [.memory-bank/architecture/system-architecture.md](architecture/system-architecture.md) | active | Accepted greenfield system shape, capability ownership and Architecture Spine. | /spec-design |
| contract | [.memory-bank/contracts/boundary-map.md](contracts/boundary-map.md) | active | Canonical capability/application boundaries, write authority and cross-slice orchestration. | /spec-design or /feature-to-tasks |
| contract | [.memory-bank/contracts/sensor-passage-api.md](contracts/sensor-passage-api.md) | active | Exact central-origin browser to ESP32 long-poll, event, CORS and Bearer contract. | /feature-to-tasks |
| contract | [.memory-bank/contracts/realtime-attempt-api.md](contracts/realtime-attempt-api.md) | active | Exact proposal-attempt endpoint, multipart serialization, validation, idempotency and typed outcome contract. | /feature-to-tasks |
| data | [.memory-bank/domains/display-client-access.md](domains/display-client-access.md) | active | Serving-control display-client identity, token hash storage and authentication lifecycle. | /feature-to-tasks |
| data | [.memory-bank/domains/promo-attempt.md](domains/promo-attempt.md) | active | Promo-owned core Attempt persistence, snapshot, transitions and idempotency. | /feature-to-tasks |
| state | [.memory-bank/states/lifecycle-map.md](states/lifecycle-map.md) | active | Canonical pilot lifecycle and recovery rules. | /spec-design or /feature-to-tasks |
| foundation | [.memory-bank/foundation.md](foundation.md) | active | Explicit Foundation Dev Path decision and minimum substrate evidence. | /spec-design or /foundation-to-tasks |
| testing | [.memory-bank/testing/index.md](testing/index.md) | active | Bootstrap verification contract and project quality-gate router. | /spec-design or /foundation-to-tasks |
| testing | [.memory-bank/testing/client-realtime.md](testing/client-realtime.md) | active | Client proposal, one-clock latency, diagnostics and related media/retention verification. | /spec-auto or /feature-to-tasks |
| testing | [.memory-bank/testing/calibration.md](testing/calibration.md) | active | FT-011 threshold-profile oracle, one-dimensional quality analysis, manual apply, worker recovery and retention verification. | /spec-auto or /feature-to-tasks |

## Planned Specs
| Area | Expected path | Needed by | Notes |
|---|---|---|---|
| user_scenarios | .memory-bank/user-scenarios.md | /spec-design or decomposition repair | Current clarified PRD is sufficient for decomposition; create only if later scenario pressure needs a separate reviewed artifact. |
| core_domain | .memory-bank/domains/core-domain.md | Later feature design if proven necessary | Current PRD plus registered architecture/lifecycle specs are sufficient; do not create a duplicate domain hub without new shared pressure. |
| interface_contract_specs | .memory-bank/contracts/*, .memory-bank/testing/*, and .memory-bank/runbooks/* | /spec-design, /foundation-to-tasks, /feature-to-tasks | Generate/update only applicable Component/API/Event/Data contracts, protocol/agent/tool I/O, boundary compatibility, evidence/redaction, safety/security, testing, runbook, or verification contracts. A Data Contract defines payloads crossing a boundary. |
| data_specs | .memory-bank/domains/* and .memory-bank/states/* | /spec-design, /feature-to-tasks | Generate/update internal domain, storage, schema, migration, validation/serialization, lifecycle, retention, seed, or runtime-data specs only when applicable. |
| foundation_substrate_specs | .memory-bank/architecture/*, .memory-bank/contracts/*, .memory-bank/domains/*, .memory-bank/states/*, .memory-bank/testing/*, .memory-bank/runbooks/* | /foundation-to-tasks | Apply Architecture, Interfaces/Contracts, and Data lenses to the walking-skeleton proof path. Generate only applicable subject-based substrate contracts/specs. Product-level detail reuses or extends those paths later. |
| subject_feature_concerns | .memory-bank/contracts/*, .memory-bank/domains/*, .memory-bank/states/*, .memory-bank/testing/*, .memory-bank/runbooks/*, or .memory-bank/guides/* | /feature-to-tasks | Discover existing canonical specs first; create only missing subject-based concerns and link exact paths from features/tasks. |

## Broken / Missing Links
- None known.

## Update Rules
- Keep this file as index/registry only: types, canonical paths, statuses,
  scopes, change routes, and broken links.
- Canonical identity is the path. Do not add a separate spec key, feature owner,
  `used_by`, or reverse-usage copy; derive usage from feature/task links.
- Do not add global backbone status, backbone matrices, feature status maps, long hard rules, or open design question dumps here.
- Use [.memory-bank/spec-backbone.md](spec-backbone.md) for pre-PRD readiness, decomposition inputs, global backbone status, matrix, and handoffs.
- Use linked specs or ADRs for detailed decisions, rationale, contracts, state transitions, schemas, invariants, and testing rules.
