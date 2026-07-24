---
description: Accepted global SDD backbone and Foundation routing state for the greenfield Face Moment pilot.
status: active
last_updated: 2026-07-24
---
# SDD Spec Backbone

## Review Status
- Acceptance: accepted
- State: ready
- Notes: Reconciled through `/spec-design` from the operator-accepted
  [architecture source](../arch_vision.md) and clarified product sources. No
  working application/backend/runtime exists yet.

## Global Backbone Status
- Status: complete
- Planning Revision: 1
- Mode: standard_architecture_scaffold
- Architecture artifact strategy: split-core-docs
- Not applicable areas:
  - event_message_contracts: not_applicable - accepted runtime boundaries use direct in-process calls and PostgreSQL row state; no broker or event/message protocol exists.
  - agent_io_contracts: not_applicable - the product has no agent/tool/model-I/O boundary.
- Notes: The global architecture, ownership, lifecycle, storage, security and
  Foundation decisions are explicit. Feature-level schemas and concrete API
  payloads remain owned by `/feature-to-tasks` and do not block the backbone.

## Accepted Source Roles

Target authority is applied in this order:

1. [.memory-bank/constitution.md](constitution.md) and explicit accepted
   operator decisions;
2. [arch_vision.md](../arch_vision.md) for accepted target architecture;
3. [.memory-bank/prd.md](prd.md), [.memory-bank/requirements.md](requirements.md)
   and feature/epic composition for product behavior and acceptance;
4. the canonical architecture, boundary and lifecycle projections registered
   in [.memory-bank/spec-index.md](spec-index.md);
5. `IDEA_*` files as overview/discovery evidence under the precedence declared
   in the PRD.

There is no as-is runtime/code authority because the repository contains no
working application, backend, worker or deployed runtime.

## Backbone Area Matrix

| Area | Status | Authoritative source | Notes |
|---|---|---|---|
| architecture_style | authoritative | [arch_vision.md](../arch_vision.md), [system architecture](architecture/system-architecture.md) | One greenfield Python/FastAPI modular monolith, one release and three server process entrypoints. |
| source_of_truth | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | PostgreSQL owns durable state; private MinIO owns binary bytes; one capability owns every mutable invariant. |
| module_boundaries | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Five capability packages, public application boundaries, dependencies, orchestration and code discovery roots are explicit. |
| user_scenarios | authoritative | [.memory-bank/prd.md](prd.md) | Actors and scenario-sensitive flows are reviewed through clarified PRD behavior; no separate scenario document is required. |
| constraints | authoritative | [.memory-bank/constitution.md](constitution.md), [.memory-bank/prd.md](prd.md), [system architecture](architecture/system-architecture.md) | KISS, one server/СПА, performance, security and no-backup limits are explicit. |
| non_goals | authoritative | [.memory-bank/prd.md](prd.md), [system architecture](architecture/system-architecture.md) | Paid delivery, standalone selfie, distribution, speculative scale and extra lifecycle machinery are excluded. |
| domain_model | authoritative | [.memory-bank/prd.md](prd.md), [lifecycle map](states/lifecycle-map.md), [.memory-bank/glossary.md](glossary.md) | Product entities, effective capture time, Photo visibility, purge, Attempt and session semantics are explicit. |
| data_flow | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Admission, search, Promo, Calibration and Photo Inventory orchestration have named owners. |
| storage | authoritative | [system architecture](architecture/system-architecture.md), [lifecycle map](states/lifecycle-map.md) | PostgreSQL/MinIO authority, transaction limits, visibility, retention and restart semantics are explicit. |
| api_contracts | authoritative | [boundary map](contracts/boundary-map.md) | Applicable component/application contracts and external HTTPS boundaries are fixed; endpoint payload detail is feature-owned. |
| event_message_contracts | not_applicable | [system architecture](architecture/system-architecture.md) | No event broker/message protocol is part of the accepted pilot. |
| agent_io_contracts | not_applicable | [.memory-bank/prd.md](prd.md) | No agent/tool I/O is a product or runtime boundary. |
| security_safety | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md), [.memory-bank/prd.md](prd.md) | Private stores, HTTPS, greenfield staff roles, owner-scoped deletion and protected evidence are fixed. |
| testing_strategy | authoritative | [.memory-bank/testing/index.md](testing/index.md), [system architecture](architecture/system-architecture.md) | Bootstrap policy routes gates; Architecture Spine names required Foundation/feature proofs that are not runnable before code exists. |
| deployment | authoritative | [system architecture](architecture/system-architecture.md), [.memory-bank/foundation.md](foundation.md) | One future Compose deployment and minimum executable walking skeleton are explicit. |
| risks | authoritative | [arch_vision.md](../arch_vision.md), [.memory-bank/prd.md](prd.md) | Accepted pilot risks and deferred-complexity triggers are explicit. |
| open_questions | authoritative | [system architecture](architecture/system-architecture.md) | Remaining hardware/scale/media-delivery choices are explicitly deferred with triggers; none blocks current task planning. |

## Canonical Design Bundle

- [System architecture](architecture/system-architecture.md): system shape,
  Architecture Spine, runtime, slice roots, ownership and Foundation proof
  pressure.
- [Boundary map](contracts/boundary-map.md): application boundaries, write
  authority, cross-slice orchestration, statistics and hard-purge contracts.
- [Lifecycle map](states/lifecycle-map.md): Photo admission/processing/
  visibility, global purge, Promo/QR, Attempt/evidence and Calibration states.
- [.memory-bank/foundation.md](foundation.md): explicit greenfield Foundation
  Dev Path decision.

No new domain, API, event, security or runbook spec is needed at this global
boundary. Concrete payload/schema and feature-specific verification detail must
reuse these subject paths or be added later only when
`/feature-to-tasks` proves a missing concern.

## Foundation Decision

- Foundation Required: true
- Foundation Gate Task: pending_foundation_to_tasks
- Reason: no executable runtime, entrypoint, storage baseline, migration path
  or project-native build/test command exists. Product feature execution needs
  one minimal walking skeleton first.
- Scope guard: Foundation contains only shared runtime/storage/native-
  compatibility proof; Photo Inventory behavior remains product work.

## Planning Revision Effect

Planning Revision advanced once from `0` to `1` because accepted global
architecture, ownership, lifecycle and Foundation rules became canonical. The
task index is empty, so no existing task status or task-plan review is made
stale.

## Handoff

- Global backbone is ready.
- Run `/foundation-to-tasks` next because Foundation is required.
- Do not create product task records until the Foundation route and normal
  feature task-design gates are satisfied.
