---
description: Pre-design global SDD backbone candidate awaiting the mandatory full /spec-design gate.
status: active
last_updated: 2026-07-24
---
# SDD Spec Backbone

## Review Status
- Acceptance: pending
- State: not_ready
- Notes: Candidate architecture, boundary, lifecycle and Foundation specs exist,
  but the complete `/spec-design` cycle has never run. No global readiness or
  downstream task-planning approval is established. No working
  application/backend/runtime exists yet.

## Global Backbone Status
- Status: blocked
- Planning Revision: 0
- Mode: pending
- Architecture artifact strategy: pending
- Not applicable areas:
  - event_message_contracts: not_applicable - accepted runtime boundaries use direct in-process calls and PostgreSQL row state; no broker or event/message protocol exists.
  - agent_io_contracts: not_applicable - the product has no agent/tool/model-I/O boundary.
- Notes: Existing documents are candidate inputs. The mandatory full
  source/coverage/consequence review, artifact-strategy selection and
  Foundation decision validation have not run. All downstream design/task gates
  remain closed until `/spec-design` records `complete|minimal` with a positive
  Planning Revision.

## Candidate Source Roles

The future `/spec-design` run must apply target authority in this order:

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
| open_questions | blocked | [system architecture](architecture/system-architecture.md) | `/spec-design` has not yet validated that the recorded deferrals exhaust all material architecture questions. Affected scope: all product features and Foundation. Owner/resume route: operator decisions through `/spec-design`. |

## Candidate Canonical Design Bundle

- [System architecture](architecture/system-architecture.md): system shape,
  Architecture Spine, runtime, slice roots, ownership, HTTP/storage decisions,
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

The bundle is not yet accepted as sufficient. `/spec-design` must confirm
whether additional subject specs are needed before any downstream task design.

## Foundation Decision

- Foundation Decision Status: pending `/spec-design`
- Candidate Foundation Required: true
- Foundation Gate Task: not_assigned
- Candidate reason: no executable runtime, entrypoint, storage baseline,
  migration path or project-native build/test command exists.
- Scope guard: no Foundation task queue may be created until `/spec-design`
  accepts or replaces this candidate decision.

## Planning Revision Effect

Planning Revision is `0` because no successful full `/spec-design` run has
occurred. Existing candidate decisions do not establish a positive Planning
Revision. The first successful run must set Revision `1`; the task index is
empty, so no task status or task-plan review is invalidated by this correction.

## Handoff

- Global backbone is not ready.
- Run `/spec-design` next.
- Do not run `/foundation-to-tasks`, `/feature-to-tasks`, `/spec-auto` task
  generation or execution until the backbone has a ready positive Planning
  Revision and an accepted Foundation decision.
