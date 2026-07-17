---
description: Pure SDD spec registry and planned-spec index.
status: active
last_updated: 2026-07-17
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
| glossary | [.memory-bank/glossary.md](glossary.md) | planned | Shared vocabulary when needed. | /spec-init or /spec-design |
| contract | [.memory-bank/contracts/boundary-map.md](contracts/boundary-map.md) | draft | Lightweight responsibility/scope notes for task boundaries. | /spec-init or /spec-design |
| testing | [.memory-bank/testing/index.md](testing/index.md) | planned | Verification strategy and quality gates. | /prd or /spec-design |

## Planned Specs
| Area | Expected path | Needed by | Notes |
|---|---|---|---|
| user_scenarios | .memory-bank/user-scenarios.md | /prd, /spec-design | Create only when scenario evidence exists or gaps must be explicit. |
| core_domain | .memory-bank/domains/core-domain.md | /prd, /spec-design | Create only when domain model affects decomposition or shared design. |
| boundary_hints | .memory-bank/contracts/boundary-map.md | /prd, /spec-design | Seeded lightweight template; fill only evidence-backed responsibility/scope notes, no endpoint/OpenAPI details. |
| lifecycle_hints | .memory-bank/states/lifecycle-map.md | /prd, /spec-design | Create only when lifecycles affect feature boundaries. |
| system_architecture | .memory-bank/architecture/system-architecture.md | /spec-design | Candidate architecture hub; fill only when selected or needed by /spec-design. |
| interface_contract_specs | .memory-bank/contracts/*, .memory-bank/testing/*, and .memory-bank/runbooks/* | /spec-design, /foundation-to-tasks, /prd-to-tasks | Generate/update Interface Specification and only applicable Component/API/Event/Data contracts, protocol/agent/tool I/O, boundary compatibility, evidence/redaction, safety/security, testing, runbook, or verification contracts. Data Contract defines payloads crossing a boundary. |
| data_specs | .memory-bank/domains/* and .memory-bank/states/* | /spec-design, /prd-to-tasks | Generate/update Data Specification for internal models, DB schemas, storage/persistence/migrations, internal data formats, validation/serialization rules, lifecycle, retention, seed, or runtime data paths. |
| foundation_substrate_specs | .memory-bank/architecture/*, .memory-bank/contracts/*, .memory-bank/domains/*, .memory-bank/states/*, .memory-bank/testing/*, .memory-bank/runbooks/* | /foundation-to-tasks | Apply Architecture, Interfaces/Contracts, and Data lenses to the walking-skeleton proof path. Generate only applicable subject-based substrate contracts/specs. Product-level detail reuses or extends those paths later. |
| subject_feature_concerns | .memory-bank/contracts/*, .memory-bank/domains/*, .memory-bank/states/*, .memory-bank/testing/*, .memory-bank/runbooks/*, or .memory-bank/guides/* | /prd-to-tasks | Discover existing canonical specs first; create only missing subject-based concerns and link exact paths from features/tasks. |

## Broken / Missing Links
- TBD

## Update Rules
- Keep this file as index/registry only: types, canonical paths, statuses,
  scopes, change routes, and broken links.
- Canonical identity is the path. Do not add a separate spec key, feature owner,
  `used_by`, or reverse-usage copy; derive usage from feature/task links.
- Do not add global backbone status, backbone matrices, feature status maps, long hard rules, or open design question dumps here.
- Use [.memory-bank/spec-backbone.md](spec-backbone.md) for pre-PRD readiness, decomposition inputs, global backbone status, matrix, and handoffs.
- Use linked specs or ADRs for detailed decisions, rationale, contracts, state transitions, schemas, invariants, and testing rules.
