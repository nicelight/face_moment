---
description: Accepted global SDD backbone, coverage matrix and Foundation routing for the Face Moment pilot.
status: active
last_updated: 2026-07-24
---
# SDD Spec Backbone

## Global Backbone Status
- Status: complete
- Planning Revision: 2
- Mode: strict_architecture_scaffold
- Architecture artifact strategy: split-by-boundary-topic
- Not applicable areas:
  - event_message_contracts: not_applicable - accepted runtime boundaries use direct in-process calls and PostgreSQL row state; no broker or event/message protocol exists.
  - agent_io_contracts: not_applicable - the product has no agent/tool/model-I/O boundary.
- Notes: The full source, coverage and consequence review is complete. Public
  HTTPS/security boundaries, retention, one migration stream and irreversible
  hard purge justify strict mode; the implementation remains a KISS modular
  monolith. The registered system, boundary and lifecycle subjects are the
  smallest useful split. Manual revision recovery, observable retention outcome
  and the Foundation typecheck gate are explicit. Foundation is required before
  product task design.

## Source Roles

Target authority was applied in this order:

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

At Planning Revision `2` there was no as-is runtime/code authority. The
subsequent verified Foundation implements that accepted design but does not
revise its planning authority or advance the Planning Revision.

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
| data_flow | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Admission, search, Promo, Calibration, inventory, manual serving-revision recovery and observable retention orchestration have named owners and failure paths. |
| storage | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md), [lifecycle map](states/lifecycle-map.md) | PostgreSQL/MinIO authority, one schema/Base/Alembic stream, ownership-safe foreign-key/cascade limits, transaction limits, issued-session media behavior, visibility, retention result and restart semantics are explicit. |
| api_contracts | authoritative | [boundary map](contracts/boundary-map.md) | Standard HTTP failure statuses, typed admitted-request outcomes, client control inputs and external HTTPS boundaries are fixed; concrete endpoint success payloads remain feature-owned. |
| event_message_contracts | not_applicable | [system architecture](architecture/system-architecture.md) | No event broker/message protocol is part of the accepted pilot. |
| agent_io_contracts | not_applicable | [.memory-bank/prd.md](prd.md) | No agent/tool I/O is a product or runtime boundary. |
| security_safety | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md), [.memory-bank/prd.md](prd.md) | Private stores, HTTPS, greenfield staff roles, owner-scoped deletion and protected evidence are fixed. |
| deployment | authoritative | [system architecture](architecture/system-architecture.md), [.memory-bank/foundation.md](foundation.md) | The verified Compose walking skeleton provides the explicit build, typecheck, start, test and smoke substrate; production deployment remains outside Foundation. |
| risks | authoritative | [system architecture](architecture/system-architecture.md), [.memory-bank/prd.md](prd.md) | Accepted pilot risks and deferred-complexity triggers are explicit. |
| open_questions | authoritative | [system architecture](architecture/system-architecture.md), [.memory-bank/prd.md](prd.md) | No material global question remains. Site hardware/client transport and the `Balance` formula are explicitly routed feature-level deferrals with named revisit points. |

## Canonical Design Bundle

- [System architecture](architecture/system-architecture.md): system shape,
  Architecture Spine, runtime, slice roots, ownership, HTTP/storage decisions,
  recovery, extension seams, deferred decisions, accepted risks and Foundation
  proof pressure.
- [Boundary map](contracts/boundary-map.md): application boundaries, write
  authority, PostgreSQL/MinIO convergence, authentication/protected delivery,
  HTTP/realtime semantics, cross-slice orchestration, revision switch,
  retention, statistics and hard-purge contracts.
- [Lifecycle map](states/lifecycle-map.md): Photo admission/processing/
  visibility, global purge, Promo/QR, Attempt/display, client-restart,
  evidence and Calibration states.
- [.memory-bank/foundation.md](foundation.md): explicit greenfield Foundation
  Dev Path decision.

This bundle is sufficient at the global boundary. Concrete endpoint payloads,
feature schemas and feature-owned verification detail remain routed to
`/feature-to-tasks`; they do not justify another global or feature-owned spec
hub.

## Foundation Decision

- Foundation Decision Status: accepted
- Foundation Required: true
- Foundation Gate Task: TASK-002-T2-FT-000-W0
- Foundation Gate Status: done
- Foundation Lifecycle: verified
- Reason: at the decision boundary, the accepted target needed one executable
  release, three server roles, one storage/migration baseline and a
  project-native build/typecheck/start/test path, while none existed.
- Scope guard: Foundation establishes substrate only. Product Photo, Attempt,
  Promo, diagnostics and inventory behavior remains in FT-001..FT-012.

## Feature Design Blockers

These feature-level questions do not reopen the accepted global architecture,
Foundation decision or Planning Revision `2`. They prevent only the affected
feature from reaching an executable task handoff.

### FT-003 — Site device integration

- Exact question: Which single site-selected camera/sensor integration and
  client app-shell route implements the accepted logical `SpaPromoClient`
  contract?
- Alternatives and impact: browser-native device access uses a versioned
  Service Worker app shell; bridge-only hardware uses one narrow client adapter
  serving the same bundle. Building both routes or a generic device-plugin
  framework is forbidden. The selected hardware also fixes the concrete
  camera/sensor transport and physical proof path.
- Affected artifacts/features: FT-003 and its capture-interface tasks; the
  logical realtime boundary and FT-004..FT-006 behavior remain unchanged.
- Decision owner and repair route: operator/site technical owner selects the
  pilot hardware and one route through `/feature-doctor FT-003`, then reruns
  `/spec-auto FT-003`.

### FT-011 — `Balance` calibration objective

- Exact question: What deterministic objective and tie-break order defines the
  `Balance` threshold profile across correct, false and missed outcomes?
- Alternatives and impact: an accepted balanced score or an explicit weighted
  error objective may satisfy the named trade-off, but they can recommend
  different thresholds on the same annotated sample. The choice fixes the
  calculation and its repeatable verification; no agent default is
  authoritative.
- Affected artifacts/features: FT-011 threshold recommendation calculation and
  verification only; annotation semantics, other two named profiles and
  manual-only setting application remain fixed.
- Decision owner and repair route: product owner/operator, informed by the
  application developer's calibration needs, decides through
  `/feature-doctor FT-011`, then reruns `/spec-auto FT-011`.

## Handoff

- Global backbone is ready at Planning Revision `2`.
- The minimum FT-000 queue is complete and
  `TASK-002-T2-FT-000-W0` is the scheduler-closed final gate with independent
  `VERDICT: PASS`.
- Product-wide task handoff remains blocked by FT-003 and FT-011. Run
  `/feature-doctor FT-003`, then `/feature-doctor FT-011`, and rerun
  `/spec-auto` for the repaired features; do not run
  `/feature-to-tasks --all` until both feature statuses are `complete`.
- The top-level scheduler runs `node scripts/mb-lint.mjs` and then
  `/mb-doctor --strict` before any product-task promotion or next success
  handoff.
