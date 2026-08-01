---
description: Accepted global SDD backbone, coverage matrix and Foundation routing for the Face Moment pilot.
status: active
last_updated: 2026-08-01
---
# SDD Spec Backbone

## Pre-PRD Spec Status

- Status: ready_for_prd
- Last updated: 2026-07-29
- Notes: The clarified [.memory-bank/prd.md](prd.md), including the accepted
  FT-003 browser-native client direction, is sufficient for meaningful L1-L3
  decomposition without a representative benchmark gate.

## Decomposition Inputs

- User scenarios: PRD `Users / Actors`, `UX / Interaction Flow`, `Edge Cases /
  Failure Handling` and `Acceptance Criteria`; no separate scenario artifact is
  needed.
- Domain model: PRD `Data / Domain Model`, with terms disambiguated by
  [.memory-bank/glossary.md](glossary.md).
- Constraints: PRD `FR-CAP-01..17`, `NFR-PERF-01`,
  `NFR-SEC-02`, `NFR-SEC-07` and `NFR-ARCH-06`.
- Non-goals: PRD `Non-goals` and `Downstream SDD Inputs`.
- Risks: PRD `Risks` and `Edge Cases / Failure Handling`, including the
  accepted first-20 traversal trade-off and site-dependent camera geometry.
- Boundary hints: PRD source precedence, `FR-CAP-03`, `FR-CAP-09..17` and
  `NFR-SEC-02/07`; the accepted client boundaries do not redefine
  server-internal ranking, selection, embeddings or search.
- Lifecycle hints: PRD `Participant Promo and continuation flow`,
  `FR-CAP-01..03`, `FR-CAP-10..17` and `FR-DIAG-01..02`.

## Open Design Questions

- No product/domain question blocks decomposition. Exact endpoint paths,
  serialization details and site-selected camera/input dimensions remain
  downstream choices under PRD `Downstream SDD Inputs`; they do not reopen the
  accepted FT-003 route or require a representative benchmark.

## Handoff To /prd-to-features

- Ready: yes
- Required reads: [.memory-bank/constitution.md](constitution.md), the current
  [.memory-bank/prd.md](prd.md), [.memory-bank/glossary.md](glossary.md), this
  decomposition framing and the pure
  [.memory-bank/spec-index.md](spec-index.md).
- Stop conditions: stop if reconciliation would change an actor, product
  outcome, non-goal or lifecycle without PRD authority. Do not reopen the
  accepted FT-003 route, detector, crop, request or structural bounds.

## Global Backbone Status
- Status: complete
- Planning Revision: 4
- Mode: strict_architecture_scaffold
- Architecture artifact strategy: split-by-boundary-topic
- Not applicable areas:
  - event_message_contracts: not_applicable - accepted runtime boundaries use direct in-process calls and PostgreSQL row state; no broker or event/message protocol exists.
  - agent_io_contracts: not_applicable - the product has no agent/tool/model-I/O boundary.
- Notes: The full source, coverage and consequence review is complete. Public
  HTTPS/security boundaries, retention, one migration stream and irreversible
  hard purge justify strict mode; the implementation remains a KISS modular
  monolith. The registered system, boundary and lifecycle subjects are the
  smallest useful split. The selected client transport/proposal contract
  changed the durable global boundary from Planning Revision `3` to `4`;
  Foundation remains accepted, verified and complete.

## Source Roles

Target authority was applied in this order:

1. [.memory-bank/constitution.md](constitution.md) and explicit accepted
   operator decisions, including the selected FT-003 directions recorded in
   [.memory-bank/analysis/brainstorming/BR-004.md](analysis/brainstorming/BR-004.md)
   and the compatible client/media decisions in
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
define product behavior or override the Planning Revision `4` target.

## Backbone Area Matrix

| Area | Status | Authoritative source | Notes |
|---|---|---|---|
| architecture_style | authoritative | [system architecture](architecture/system-architecture.md) | One greenfield Python/FastAPI modular monolith, one release and three server process entrypoints. |
| source_of_truth | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | PostgreSQL owns durable state in one application schema/migration stream; private MinIO owns stored binary bytes regardless of media classification; one capability owns every mutable invariant. |
| module_boundaries | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Five capability packages, public application boundaries, dependencies, orchestration, shared-schema ownership constraints and code discovery roots are explicit. |
| user_scenarios | authoritative | [.memory-bank/prd.md](prd.md) | Actors and scenario-sensitive flows are reviewed through clarified PRD behavior; no separate scenario document is required. |
| constraints | authoritative | [.memory-bank/constitution.md](constitution.md), [.memory-bank/prd.md](prd.md), [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | KISS, one server/СПА, client/sensor and proposal boundaries, one-clock performance, security and no-backup limits are explicit. |
| non_goals | authoritative | [.memory-bank/prd.md](prd.md), [system architecture](architecture/system-architecture.md) | Paid delivery, standalone selfie, local-detector miss proof/frame upload, speculative scale and extra lifecycle machinery are excluded. |
| domain_model | authoritative | [.memory-bank/prd.md](prd.md), [lifecycle map](states/lifecycle-map.md), [.memory-bank/glossary.md](glossary.md) | Product entities, face proposal occurrences, Photo visibility, purge, Attempt and session semantics are explicit. |
| data_flow | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Client proposals, existing server-owned search, Promo, diagnostics, inventory, revision recovery and retention have named owners and failure paths. |
| storage | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md), [lifecycle map](states/lifecycle-map.md) | Private PostgreSQL/MinIO authority, ownership-safe persistence, optional capture media, retention and restart semantics are explicit. |
| api_contracts | authoritative | [boundary map](contracts/boundary-map.md), [sensor passage API](contracts/sensor-passage-api.md), [realtime attempt API](contracts/realtime-attempt-api.md) | Global transport plus exact FT-003 sensor/realtime paths, multipart serialization/validation, structural bounds, zero-proposal behavior, standard HTTP failures and compact admitted outcomes are fixed. |
| event_message_contracts | not_applicable | [system architecture](architecture/system-architecture.md) | No event broker/message protocol is part of the accepted pilot. |
| agent_io_contracts | not_applicable | [.memory-bank/prd.md](prd.md) | No agent/tool I/O is a product or runtime boundary. |
| security_safety | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md), [.memory-bank/prd.md](prd.md) | Capture-derived media is not protected solely as media; credentials, infrastructure, commercial/personalized data, names/annotations and admin actions retain protection. |
| deployment | authoritative | [system architecture](architecture/system-architecture.md), [.memory-bank/foundation.md](foundation.md) | The verified Compose walking skeleton provides the explicit build, typecheck, start, test and smoke substrate; production deployment remains outside Foundation. |
| risks | authoritative | [.memory-bank/prd.md](prd.md), [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Client proposal-order and site-camera trade-offs plus accepted pilot/deferred-complexity risks are explicit. |
| open_questions | authoritative | [system architecture](architecture/system-architecture.md), [.memory-bank/prd.md](prd.md) | No global architecture or product-design question remains unresolved. Feature-level completion stays with the owning feature. |

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
- [Client realtime verification](testing/client-realtime.md): browser/ESP32
  transport, chronological first-at-most-20, crop/JPEG/manifest, zero-proposal,
  one-clock latency, diagnostics and related media/retention proof.
- [Sensor Passage API](contracts/sensor-passage-api.md) and
  [Realtime Attempt API](contracts/realtime-attempt-api.md): exact FT-003
  external paths, payloads, validation, authentication and typed outcomes.
- [Display Client Access](domains/display-client-access.md) and
  [Promo Attempt](domains/promo-attempt.md): authoritative credential and core
  Attempt persistence/state rules for FT-003.
- [.memory-bank/foundation.md](foundation.md): explicit greenfield Foundation
  Dev Path decision.

This bundle is sufficient at the global boundary.

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
