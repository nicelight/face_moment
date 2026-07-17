---
description: Project Constitution — governing principles for AI-first development.
status: active
version: 3
project_principles: ratified
ratified: 2026-07-17
last_updated: 2026-07-17
---
# Project Constitution

## Purpose

This Constitution defines the non-negotiable principles that guide AI agents
when planning, implementing, verifying, and synchronizing Face Moment work.

## Core Principles

### I. Medium Project and DO NOT Overengineering

Face Moment is governed as a `medium` project. Agents MUST use the simplest
solution that satisfies current requirements and evidence. They MUST NOT add
enterprise architecture, speculative scale mechanisms, abstraction layers, or
process that is not justified by a current requirement, constraint, measured
bottleneck, or demonstrated duplication.

### II. KISS Before Up-front Stability Machinery

KISS is the architecture priority. Correctness required by current scope MUST
be preserved, but redundancy, distribution, recovery machinery, and other
stability complexity are added only after concrete evidence demonstrates the
need.

### III. Performance and Promo/QR Continuity Lead the Current Phase

Promo/QR latency and stable end-to-end continuation are the leading product
priorities for the current phase. Acceptance and planning MUST focus on the
measurable ingest, display, QR, and continuation outcomes defined by the active
Product Brief.

### IV. AI-First Spec-Driven Development

Agents MUST derive implementation work from explicit product, requirement,
feature, spec, task, and workflow artifacts. Agents MUST NOT invent product
scope without evidence or user instruction. `.memory-bank/` remains the
durable source of project knowledge; chat context is temporary.

### V. Schema-Backed, Tier-Routed Execution

Tasks MUST use the current schema-backed JSON task model and route through
`tier: T0|T1|T2|T3`. Agents MUST NOT use legacy task formats, deprecated risk
models, or undocumented assumptions.

### VI. Proportionate Definition of Done

The baseline code Definition of Done is a successful configured build/typecheck
plus relevant unit tests. Existing tier policy remains authoritative for any
additional protocol, verification, red-verification, or human-checkpoint gate.
Every completed task MUST retain evidence appropriate to its tier and scope.

### VII. Bounded Agent Autonomy

Agents MAY independently make routine, reversible, in-scope changes. They MUST
stop for a human checkpoint before production or deploy actions, destructive
or data-loss-capable actions, and material public-contract changes, as well as
wherever the T3 workflow requires one.

### VIII. Synchronization and Context Discipline

Agents SHOULD read the smallest sufficient normative context. After meaningful
changes they MUST update affected Memory Bank knowledge and follow the current
wave-boundary synchronization policy.

## Governance Decisions

- Project level: `medium`.
- Architecture priority: KISS.
- Baseline code DoD: build/typecheck and relevant unit tests; tier gates remain
  additive.
- Agent mode: bounded autonomy with critical human checkpoints.
- Highest current product non-negotiable: performance and stable Promo/QR.

## Governance

- This Constitution has precedence over workflow habits and generated plans.
- MBB, spec-index, spec-backbone, invariants, contracts, states, testing, and
  workflow docs refine this Constitution and MUST NOT contradict it.
- Amendments require evidence or explicit user instruction and must update
  affected durable docs.
- Keep this document short; concrete rules belong in invariants, contracts,
  states, testing, or workflow policies.

**Version**: 3 | **Ratified**: 2026-07-17 | **Last updated**: 2026-07-17
