---
description: Accepted global SDD backbone and Foundation routing state for the greenfield Face Moment pilot.
status: active
last_updated: 2026-07-24
---
# SDD Spec Backbone

## Review Status
- Acceptance: accepted
- State: ready
- Notes: Reconciled through `/spec-design` into the canonical architecture,
  boundary, lifecycle and Foundation specs from accepted operator decisions,
  clarified product sources and the KISS session/offline-attempt/purge
  decisions of 2026-07-24. No working application/backend/runtime exists yet.

## Global Backbone Status
- Status: complete
- Planning Revision: 3
- Mode: standard_architecture_scaffold
- Architecture artifact strategy: split-core-docs
- Not applicable areas:
  - event_message_contracts: not_applicable - accepted runtime boundaries use direct in-process calls and PostgreSQL row state; no broker or event/message protocol exists.
  - agent_io_contracts: not_applicable - the product has no agent/tool/model-I/O boundary.
- Notes: The global architecture, ownership, lifecycle, storage, security,
  standard HTTP failure semantics, single-schema migration boundary and
  Foundation decisions are explicit. Issued sessions survive Photo soft/hard
  deletion with missing-media skip, client-only offline attempts are
  best-effort, and restore of non-terminal purge snapshot members is rejected.
  Feature-level table/payload detail remains owned by `/feature-to-tasks` and
  does not block the backbone.

## Accepted Source Roles

Target authority is applied in this order:

1. [.memory-bank/constitution.md](constitution.md) and explicit accepted
   operator decisions;
2. the registered [system architecture](architecture/system-architecture.md),
   [boundary map](contracts/boundary-map.md),
   [lifecycle map](states/lifecycle-map.md) and
   [Foundation decision](foundation.md) for the accepted technical target;
3. [.memory-bank/prd.md](prd.md), [.memory-bank/requirements.md](requirements.md)
   and feature/epic composition for product behavior and acceptance;
4. `IDEA_*` files as overview/discovery evidence under the precedence declared
   in the PRD.

There is no as-is runtime/code authority because the repository contains no
working application, backend, worker or deployed runtime.

## Backbone Area Matrix

| Area | Status | Authoritative source | Notes |
|---|---|---|---|
| architecture_style | authoritative | [system architecture](architecture/system-architecture.md) | One greenfield Python/FastAPI modular monolith, one release and three server process entrypoints. |
| source_of_truth | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | PostgreSQL owns durable state in one application schema/migration stream; private MinIO owns binary bytes; one capability owns every mutable invariant. |
| module_boundaries | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Five capability packages, public application boundaries, dependencies, orchestration, shared-schema ownership constraints and code discovery roots are explicit. |
| user_scenarios | authoritative | [.memory-bank/prd.md](prd.md) | Actors and scenario-sensitive flows are reviewed through clarified PRD behavior; no separate scenario document is required. |
| constraints | authoritative | [.memory-bank/constitution.md](constitution.md), [.memory-bank/prd.md](prd.md), [system architecture](architecture/system-architecture.md) | KISS, one server/СПА, performance, security and no-backup limits are explicit. |
| non_goals | authoritative | [.memory-bank/prd.md](prd.md), [system architecture](architecture/system-architecture.md) | Paid delivery, standalone selfie, distribution, speculative scale and extra lifecycle machinery are excluded. |
| domain_model | authoritative | [.memory-bank/prd.md](prd.md), [lifecycle map](states/lifecycle-map.md), [.memory-bank/glossary.md](glossary.md) | Product entities, effective capture time, Photo visibility, purge, Attempt and session semantics are explicit. |
| data_flow | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Admission, search, Promo, Calibration and Photo Inventory orchestration have named owners. |
| storage | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md), [lifecycle map](states/lifecycle-map.md) | PostgreSQL/MinIO authority, one schema/Base/Alembic stream, ownership-safe foreign-key/cascade limits, transaction limits, issued-session media behavior, visibility, retention and restart semantics are explicit. |
| api_contracts | authoritative | [boundary map](contracts/boundary-map.md) | Standard HTTP failure statuses, typed admitted-request outcomes, client control inputs and external HTTPS boundaries are fixed; concrete endpoint success payloads remain feature-owned. |
| event_message_contracts | not_applicable | [system architecture](architecture/system-architecture.md) | No event broker/message protocol is part of the accepted pilot. |
| agent_io_contracts | not_applicable | [.memory-bank/prd.md](prd.md) | No agent/tool I/O is a product or runtime boundary. |
| security_safety | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md), [.memory-bank/prd.md](prd.md) | Private stores, HTTPS, greenfield staff roles, owner-scoped deletion and protected evidence are fixed. |
| testing_strategy | authoritative | [.memory-bank/testing/index.md](testing/index.md), [system architecture](architecture/system-architecture.md) | Bootstrap policy routes gates; Architecture Spine names required Foundation/feature proofs that are not runnable before code exists. |
| deployment | authoritative | [system architecture](architecture/system-architecture.md), [.memory-bank/foundation.md](foundation.md) | One future Compose deployment and minimum executable walking skeleton are explicit. |
| risks | authoritative | [system architecture](architecture/system-architecture.md), [.memory-bank/prd.md](prd.md) | Accepted pilot risks and deferred-complexity triggers are explicit. |
| open_questions | authoritative | [system architecture](architecture/system-architecture.md) | Remaining hardware/scale/media-delivery choices are explicitly deferred with triggers; none blocks current task planning. |

## Canonical Design Bundle

- [System architecture](architecture/system-architecture.md): system shape,
  Architecture Spine, runtime, slice roots, ownership, HTTP/storage decisions
  recovery, extension seams, deferred decisions, accepted risks and Foundation
  proof pressure.
- [Boundary map](contracts/boundary-map.md): application boundaries, write
  authority, PostgreSQL/MinIO convergence, authentication/protected delivery,
  HTTP/realtime semantics, cross-slice orchestration, statistics and hard-purge
  contracts.
- [Lifecycle map](states/lifecycle-map.md): Photo admission/processing/
  visibility, global purge, Promo/QR, Attempt/display, client-restart,
  evidence and Calibration states.
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

Planning Revision advanced from `1` to `2` for the standard HTTP
failure/domain-outcome contract and single-schema migration/foreign-key rules.
It advanced from `2` to `3` for the operator-accepted KISS rules: soft delete
does not invalidate an issued session, hard-purged media is skipped without
rebuilding the session or `N`, client-only offline attempts are best-effort,
and restore of non-terminal hard-purge snapshot members is rejected. These
rules affect feature/task planning. The task index is empty, so no existing task
status or task-plan review is made stale.

Consolidating the already accepted target into registered canonical specs does
not change the target and therefore does not advance Planning Revision `3`.

## Handoff

- Global backbone is ready.
- Run `/foundation-to-tasks` next because Foundation is required.
- Do not create product task records until the Foundation route and normal
  feature task-design gates are satisfied.
