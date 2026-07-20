---
description: Pre-PRD spec framing and global SDD backbone state.
status: active
last_updated: 2026-07-20
---
# SDD Spec Backbone

## Pre-PRD Spec Status
- Status: ready_for_prd
- Last updated: 2026-07-20
- Notes: The clarified PRD and its governing inputs provide sufficient
  evidence for meaningful L1-L3 decomposition. This status does not approve
  architecture, Foundation Dev Path, or implementation tasking.

## Framing Sources

- [.memory-bank/constitution.md](constitution.md): governing project policy and
  KISS/bounded-autonomy constraints.
- [.memory-bank/analysis/product-brief.md](analysis/product-brief.md): accepted
  one-SPA pilot scope and outcome contract.
- [.memory-bank/prd.md](prd.md): clarified actors, requirements, domain model,
  scenarios, lifecycles, constraints, risks, and acceptance criteria.
- [.memory-bank/invariants.md](invariants.md): current cross-cutting Promo/QR
  and decomposition invariants.
- [IDEA_APP.md](../IDEA_APP.md): evidence for accepted application topology,
  pipeline compatibility, exact-search/group semantics, process boundaries, and
  separation of requirements from recommendations and future candidates.
- [IDEA_INGEST.md](../IDEA_INGEST.md): authoritative pilot batch boundary,
  `visit_date`, manifest, idempotency, searchable-state, and SLO semantics.
- [IDEA_DEBUG.md](../IDEA_DEBUG.md): authoritative first-version Attempts,
  Log Explorer, annotation, calibration, retention, and sensitive-log boundary.

## Source Precedence

- Apply the precedence already defined in the PRD `Source Inputs` and
  `Clarifications` sections. `IDEA_*` requirements and accepted decisions are
  evidence; recommendations and future candidates are not pilot gates.
- When wording differs, the clarified PRD controls. Known superseded defaults
  concern Promo copy, QR/browser TTL, absence of a separate pilot selfie,
  cross-batch duplicate scope, and curated calibration retention.

## Decomposition Inputs
- User scenarios: authoritative in PRD `Users / Actors` and `UX / Interaction
  Flow`; no separate scenario artifact is needed for decomposition.
- Domain model: PRD `Data / Domain Model` is sufficient; the three `IDEA_*`
  inputs add evidence without replacing later canonical design.
- Constraints: sufficient in the Constitution, PRD non-functional requirements,
  and [.memory-bank/invariants.md](invariants.md).
- Non-goals: authoritative in the PRD `Non-goals` section.
- Risks: sufficient in Product Brief `Risks`, PRD `Edge Cases / Failure
  Handling`, and acceptance criteria.
- Boundary hints: sufficient in
  [.memory-bank/contracts/boundary-map.md](contracts/boundary-map.md); exact
  interfaces remain for `/spec-design`.
- Lifecycle hints: sufficient in
  [.memory-bank/states/lifecycle-map.md](states/lifecycle-map.md); exact states
  and transition contracts remain for `/spec-design`.

## Open Design Questions

- Canonical component ownership and interfaces for the accepted high-level
  application/process split.
- Persistence ownership, schemas, detailed lifecycles, transaction boundaries,
  and cross-boundary data contracts.
- Security/redaction/error contracts, exact `Balance` formula, and audited
  manual serving-setting application.
- Global architecture mode, Foundation Dev Path, deployment/recovery proof, and
  canonical verification contract.

These questions are intentionally deferred to `/spec-design`; none requires a
new product assumption to derive requirements, epics, or features.

## Backbone Area Matrix
| Area | Status | Authoritative source | Notes |
|---|---|---|---|
| architecture_style | blocked | - | Decide in `/spec-design`; KISS and single-server constraints are already fixed. |
| source_of_truth | blocked | [.memory-bank/prd.md](prd.md), [IDEA_APP.md](../IDEA_APP.md), [IDEA_INGEST.md](../IDEA_INGEST.md) | Accepted truth hints exist; canonical ownership and transaction rules remain pending. |
| module_boundaries | blocked | [IDEA_APP.md](../IDEA_APP.md), [.memory-bank/contracts/boundary-map.md](contracts/boundary-map.md) | The high-level process split is accepted; canonical component/interface boundaries remain pending. |
| user_scenarios | authoritative | [.memory-bank/prd.md](prd.md) | `Users / Actors` and `UX / Interaction Flow` are sufficient for decomposition. |
| constraints | authoritative | [.memory-bank/constitution.md](constitution.md), [.memory-bank/prd.md](prd.md) | Pilot, security, performance, and KISS constraints are explicit. |
| non_goals | authoritative | [.memory-bank/prd.md](prd.md) | Pilot exclusions and post-pilot context are explicit. |
| domain_model | blocked | [.memory-bank/prd.md](prd.md), [IDEA_APP.md](../IDEA_APP.md), [IDEA_INGEST.md](../IDEA_INGEST.md), [IDEA_DEBUG.md](../IDEA_DEBUG.md) | Product concepts and accepted semantics are framed; formal domain/data design remains pending. |
| data_flow | blocked | [.memory-bank/prd.md](prd.md), [IDEA_APP.md](../IDEA_APP.md) | End-to-end and process flows are known; canonical runtime/data-flow design remains pending. |
| storage | blocked | [.memory-bank/prd.md](prd.md), [IDEA_APP.md](../IDEA_APP.md), [IDEA_DEBUG.md](../IDEA_DEBUG.md) | Product storage/retention constraints and accepted roles are known; exact ownership/schema remain pending. |
| api_contracts | blocked | - | Decide applicable contracts in `/spec-design`. |
| event_message_contracts | blocked | - | Decide applicability in `/spec-design`; do not infer a broker or event architecture. |
| agent_io_contracts | blocked | - | Decide applicability in `/spec-design`. |
| security_safety | blocked | [.memory-bank/prd.md](prd.md), [IDEA_APP.md](../IDEA_APP.md), [IDEA_DEBUG.md](../IDEA_DEBUG.md) | Product security/privacy and log-redaction rules are fixed; canonical enforcement contracts remain pending. |
| testing_strategy | blocked | [.memory-bank/prd.md](prd.md), [.memory-bank/testing/index.md](testing/index.md) | Product verification outcomes are known; canonical strategy remains pending. |
| deployment | blocked | [.memory-bank/prd.md](prd.md) | Single-server constraints are fixed; deployment/recovery design remains pending. |
| risks | authoritative | [.memory-bank/analysis/product-brief.md](analysis/product-brief.md), [.memory-bank/prd.md](prd.md) | Decomposition-affecting risks and failure semantics are explicit. |
| open_questions | blocked | [.memory-bank/spec-backbone.md](spec-backbone.md) | Design-only questions above remain for `/spec-design`. |

## Handoff To /prd-to-features
- Ready: yes
- Required reads: `.memory-bank/constitution.md`, `.memory-bank/prd.md`,
  `.memory-bank/invariants.md`, `.memory-bank/spec-backbone.md`,
  `.memory-bank/spec-index.md`, `.memory-bank/contracts/boundary-map.md`, and
  `.memory-bank/states/lifecycle-map.md`.
- Stop conditions: required PRD clarification markers regress; governing sources
  conflict; or a new product/domain decision would materially change actors,
  scenarios, non-goals, lifecycles, boundaries, or L1-L3 cuts.

## Handoff To /spec-design
- Global Backbone Status: intentionally pending until /spec-design
- Downstream readiness: tasking and autonomous execution wait for /spec-design
- Backbone areas to revisit: every `blocked` row in the Backbone Area Matrix.
- Candidate specs: use the Planned Specs registry in
  [.memory-bank/spec-index.md](spec-index.md); discover existing canonical paths
  before creating any subject spec.

## Global Backbone Status
- Status: pending
- Mode: pending
- Architecture artifact strategy: pending
- Not applicable areas:
  - Classification is intentionally pending `/spec-design`.
- Notes: `/spec-init` approved product decomposition only. `/spec-design` still
  owns global architecture, Foundation Dev Path, canonical SDD coverage, and
  downstream tasking readiness.
