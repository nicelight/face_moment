---
description: Pre-PRD spec framing and global SDD backbone state.
status: active
---
# SDD Spec Backbone

## Pre-PRD Spec Status
- Status: blocked
- Last updated: 2026-07-09
- Notes: Run /spec-init after /write-prd to determine whether PRD decomposition is safe.

## Decomposition Inputs
- User scenarios: not_started
- Domain model: not_started
- Constraints: not_started
- Non-goals: not_started
- Risks: not_started
- Boundary hints: not_started
- Lifecycle hints: not_started

## Open Design Questions
- TBD

## Backbone Area Matrix
| Area | Status | Authoritative source | Notes |
|---|---|---|---|
| architecture_style | blocked | - | Decide in /spec-design after /prd. |
| source_of_truth | blocked | - | Decide in /spec-design after /prd. |
| module_boundaries | blocked | .memory-bank/contracts/boundary-map.md | Fill only evidence-backed responsibility/scope notes; decide in /spec-design after /prd. |
| user_scenarios | blocked | .memory-bank/user-scenarios.md | Create/review when scenarios affect decomposition or architecture. |
| constraints | blocked | - | Capture in /spec-init and refine in /spec-design. |
| non_goals | blocked | - | Capture in /spec-init and refine in /spec-design. |
| domain_model | blocked | .memory-bank/domains/core-domain.md | Create only when domain model affects decomposition or shared design. |
| data_flow | blocked | - | Decide in /spec-design after /prd. |
| storage | blocked | - | Decide in /spec-design after /prd. |
| api_contracts | blocked | - | Decide authoritative/needed/not_applicable/blocked in /spec-design. |
| event_message_contracts | blocked | - | Decide authoritative/needed/not_applicable/blocked in /spec-design. |
| agent_io_contracts | blocked | - | Decide authoritative/needed/not_applicable/blocked in /spec-design. |
| security_safety | blocked | - | Decide in /spec-design after /prd. |
| testing_strategy | blocked | .memory-bank/testing/index.md | Decide in /spec-design after /prd. |
| deployment | blocked | - | Decide in /spec-design after /prd. |
| risks | blocked | - | Capture in /spec-init and refine in /spec-design. |
| open_questions | blocked | - | Resolve or keep blocked. |

## Handoff To /prd
- Ready: no
- Required reads: .memory-bank/prd.md, .memory-bank/spec-index.md, this file, and linked pre-PRD specs.
- Stop conditions: Pre-PRD Spec Status is missing, stale, or blocked.

## Handoff To /spec-design
- Global Backbone Status: intentionally pending until /spec-design
- Downstream readiness: /prd-to-tasks, /autopilot, and autonomous scheduler mode must wait for /spec-design.
- Backbone areas to revisit: all
- Candidate specs: see .memory-bank/spec-index.md Planned Specs.

## Global Backbone Status
- Status: blocked
- Mode: pending
- Architecture artifact strategy: pending
- Not applicable areas:
  - TBD
- Notes: /spec-design has not completed the global architecture scaffold yet.
