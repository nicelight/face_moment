---
description: Accepted global SDD backbone, coverage matrix and Foundation routing for the Face Moment pilot.
status: active
last_updated: 2026-07-28
---
# SDD Spec Backbone

## Pre-PRD Spec Status

- Status: ready_for_prd
- Last updated: 2026-07-28
- Notes: The clarified [.memory-bank/prd.md](prd.md) is sufficient for
  meaningful L1-L3 decomposition.

## Decomposition Inputs

- User scenarios: PRD `Users / Actors`, `UX / Interaction Flow`, `Edge Cases /
  Failure Handling` and `Acceptance Criteria`; no separate scenario artifact is
  needed.
- Domain model: PRD `Data / Domain Model`, with terms disambiguated by
  [.memory-bank/glossary.md](glossary.md).
- Constraints: PRD `FR-CAP-03`, `NFR-PERF-01` and `NFR-SEC-06`.
- Non-goals: PRD `Non-goals` and `Deferred Technical Decisions`.
- Risks: PRD `Edge Cases / Failure Handling` and `FR-CAP-09..10`.
- Boundary hints: PRD source precedence and `FR-CAP-03`; the client submission
  contract does not define server-internal processing.
- Lifecycle hints: PRD `FR-DIAG-02`, `FR-CAP-10` and `NFR-DATA-01..03`.

## Open Design Questions

- See PRD `Deferred Technical Decisions` and `Feature Design Blockers` below;
  they do not change the accepted L1-L3 cut.

## Handoff To /prd-to-features

- Ready: yes
- Required reads: [.memory-bank/constitution.md](constitution.md), the current
  [.memory-bank/prd.md](prd.md), [.memory-bank/glossary.md](glossary.md), this
  decomposition framing and the pure
  [.memory-bank/spec-index.md](spec-index.md).
- Stop conditions: stop if decomposition requires selecting a deferred
  technical alternative or if the PRD becomes unclear or contradictory.

## Handoff To /spec-design

- Global Backbone Status: `complete` at Planning Revision `3`; see below.
- Downstream readiness: see `Feature Design Blockers` and `Handoff`.

## Global Backbone Status
- Status: complete
- Planning Revision: 3
- Mode: strict_architecture_scaffold
- Architecture artifact strategy: split-by-boundary-topic
- Not applicable areas:
  - event_message_contracts: not_applicable - accepted runtime boundaries use direct in-process calls and PostgreSQL row state; no broker or event/message protocol exists.
  - agent_io_contracts: not_applicable - the product has no agent/tool/model-I/O boundary.
- Notes: The full source, coverage and consequence review is complete. Public
  HTTPS/security boundaries, retention, one migration stream and irreversible
  hard purge justify strict mode; the implementation remains a KISS modular
  monolith. The registered system, boundary and lifecycle subjects are the
  smallest useful split. The client proposal/media boundary changed durably;
  Foundation remains accepted, verified and complete.

## Source Roles

Target authority was applied in this order:

1. [.memory-bank/constitution.md](constitution.md) and explicit accepted
   operator decisions, including the client/media decisions in
   [IDEA_CLIENT.md](../IDEA_CLIENT.md);
2. the registered [system architecture](architecture/system-architecture.md),
   [boundary map](contracts/boundary-map.md),
   [lifecycle map](states/lifecycle-map.md) and
   [Foundation decision](foundation.md) for the accepted technical target;
3. [.memory-bank/prd.md](prd.md), [.memory-bank/requirements.md](requirements.md)
   and feature/epic composition for product behavior and acceptance;
4. Remaining `IDEA_*` files as overview/discovery evidence under the precedence
   declared in the PRD.

The verified Foundation is as-is evidence for substrate only. It does not
define product behavior or override the Planning Revision `3` target.

## Backbone Area Matrix

| Area | Status | Authoritative source | Notes |
|---|---|---|---|
| architecture_style | authoritative | [system architecture](architecture/system-architecture.md) | One greenfield Python/FastAPI modular monolith, one release and three server process entrypoints. |
| source_of_truth | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | PostgreSQL owns durable state in one application schema/migration stream; private MinIO owns stored binary bytes regardless of media classification; one capability owns every mutable invariant. |
| module_boundaries | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Five capability packages, public application boundaries, dependencies, orchestration, shared-schema ownership constraints and code discovery roots are explicit. |
| user_scenarios | authoritative | [.memory-bank/prd.md](prd.md) | Actors and scenario-sensitive flows are reviewed through clarified PRD behavior; no separate scenario document is required. |
| constraints | authoritative | [.memory-bank/constitution.md](constitution.md), [.memory-bank/prd.md](prd.md), [system architecture](architecture/system-architecture.md) | KISS, one server/СПА, all-occurrence client submission, one-clock performance, security and no-backup limits are explicit. |
| non_goals | authoritative | [.memory-bank/prd.md](prd.md), [system architecture](architecture/system-architecture.md) | Paid delivery, standalone selfie, local-detector miss proof/frame upload, speculative scale and extra lifecycle machinery are excluded. |
| domain_model | authoritative | [.memory-bank/prd.md](prd.md), [lifecycle map](states/lifecycle-map.md), [.memory-bank/glossary.md](glossary.md) | Product entities, face proposal occurrences, Photo visibility, purge, Attempt and session semantics are explicit. |
| data_flow | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Client proposals, existing server-owned search, Promo, diagnostics, inventory, revision recovery and retention have named owners and failure paths. |
| storage | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md), [lifecycle map](states/lifecycle-map.md) | Private PostgreSQL/MinIO authority, ownership-safe persistence, optional capture media, retention and restart semantics are explicit. |
| api_contracts | authoritative | [boundary map](contracts/boundary-map.md) | All-occurrence, zero-proposal and oversize client semantics, standard HTTP failures and typed admitted outcomes are fixed; exact schema/bounds remain feature-owned. |
| event_message_contracts | not_applicable | [system architecture](architecture/system-architecture.md) | No event broker/message protocol is part of the accepted pilot. |
| agent_io_contracts | not_applicable | [.memory-bank/prd.md](prd.md) | No agent/tool I/O is a product or runtime boundary. |
| security_safety | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md), [.memory-bank/prd.md](prd.md) | Capture-derived media is not protected solely as media; credentials, infrastructure, commercial/personalized data, names/annotations and admin actions retain protection. |
| deployment | authoritative | [system architecture](architecture/system-architecture.md), [.memory-bank/foundation.md](foundation.md) | The verified Compose walking skeleton provides the explicit build, typecheck, start, test and smoke substrate; production deployment remains outside Foundation. |
| risks | authoritative | [system architecture](architecture/system-architecture.md), [.memory-bank/prd.md](prd.md) | Oversize fails visibly without a hidden subset; accepted pilot risks and deferred-complexity triggers are explicit. |
| open_questions | authoritative | [system architecture](architecture/system-architecture.md), [.memory-bank/prd.md](prd.md) | No global blocker remains. FT-003 runtime/transport/detector/crop/schema/bounds and FT-011 `Balance` are unresolved feature decisions with named owners. |

## Canonical Design Bundle

- [System architecture](architecture/system-architecture.md): system shape,
  Architecture Spine, runtime, slice roots, ownership, HTTP/storage decisions,
  recovery, extension seams, deferred decisions, accepted risks and Foundation
  proof pressure.
- [Boundary map](contracts/boundary-map.md): application boundaries, write
  authority, PostgreSQL/MinIO convergence, data-specific delivery,
  HTTP/realtime semantics, cross-slice orchestration, revision switch,
  retention, statistics and hard-purge contracts.
- [Lifecycle map](states/lifecycle-map.md): Photo admission/processing/
  visibility, global purge, Promo/QR, Attempt/display, client-restart,
  evidence and Calibration states.
- [Client realtime verification](testing/client-realtime.md): all-occurrence,
  zero-proposal, oversize, one-clock latency, diagnostics and related
  media/retention proof.
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
Foundation decision or Planning Revision `3`. They prevent only the affected
feature from reaching an executable task handoff.

### FT-003 — Client runtime and site integration

- Exact question: Which single client runtime route and ESP32-to-client
  transport will implement FT-003?
- Alternatives and impact: browser-native and narrow-bridge routes remain
  candidates; neither is accepted. Existing feasibility observations do not
  select a route. Exact camera/sensor models remain site-validation choices,
  not this blocker. Detector/runtime/model/update, crop, schema and hard-bound
  choices remain unresolved pending the route and representative benchmark.
- Affected artifacts/features: FT-003 and its request interface with FT-004;
  the all-occurrence client contract and existing server search authority stay
  fixed.
- Decision owner and repair route: operator/site technical owner selects one
  route and transport through `/feature-doctor FT-003`, then reruns
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

- Global backbone is ready at Planning Revision `3`.
- The minimum FT-000 queue is complete and
  `TASK-002-T2-FT-000-W0` is the scheduler-closed final gate with independent
  `VERDICT: PASS`.
- Planning Revision `3` is the baseline for future product task plans; none
  currently exist. The completed FT-000 queue is unchanged.
- `/spec-auto --all` leaves FT-003 and FT-011 blocked and confirms
  FT-001..FT-002, FT-004..FT-010 and FT-012 complete against their direct
  canonical links.
- Product-wide task handoff remains blocked by FT-003 and FT-011. Run
  `/feature-doctor FT-003`, then `/feature-doctor FT-011`; after both decisions,
  rerun `/spec-auto --all`, then `/feature-to-tasks --all` and
  `/review-tasks-plan --all`.
- The top-level scheduler runs `node scripts/mb-lint.mjs` and then
  `/mb-doctor --strict` before any product-task promotion or next success
  handoff.
