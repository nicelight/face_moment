---
description: Project Constitution — governing principles for AI-first development.
status: active
version: 4
project_principles: ratified
ratified: 2026-07-17
last_updated: 2026-08-04
---
# Project Constitution

## Purpose

This Constitution defines the project-level, non-negotiable rules for planning,
implementation, verification, and synchronization. Concrete product and
technical rules remain in their owning normative artifacts.

## Core Principles

### I. Medium Project, KISS, and DO NOT Overengineering

Face Moment is a `medium` project and KISS is its architecture priority. Agents
MUST choose the simplest solution that satisfies accepted requirements and
preserves required correctness. They MUST NOT add enterprise architecture,
speculative scale, abstraction, distribution, redundancy, recovery machinery,
or process unless a current requirement, constraint, measured bottleneck,
demonstrated duplication, or evidenced material risk justifies its total cost.

### II. Performance and Promo/QR Continuity Lead the Current Phase

Promo/QR latency and stable end-to-end continuation are the leading product
priorities for the current phase. Acceptance and planning MUST focus on the
measurable ingest, display, QR, and continuation outcomes defined by the active
Product Brief, PRD, and testing specifications.

### III. AI-First Spec-Driven Development

Agents MUST derive work from accepted product, requirement, feature, spec, task,
and workflow artifacts. They MUST NOT invent or change product scope without
authoritative evidence or explicit operator instruction. `.memory-bank/`
remains durable project knowledge; chat context is temporary.

### IV. Schema-Backed, Tier-Routed, Proportionate Completion

Tasks MUST use the current schema-backed JSON task model and route through
`tier: T0|T1|T2|T3`. Agents MUST NOT use legacy task formats, deprecated risk
models, a second tier model, or undocumented assumptions. Baseline code
Definition of Done is successful configured build/typecheck plus relevant unit
tests. Tier policy owns additional protocol, verification, red-verification,
and human-checkpoint gates. Every completed task MUST retain evidence
appropriate to its tier and scope.

### V. Bounded Agent Autonomy

Agents MAY independently make routine, reversible, in-scope changes. They MUST
stop for a human checkpoint before production or deploy actions, destructive
or data-loss-capable actions, and material public-contract changes, as well as
wherever the T3 workflow requires one.

### VI. Synchronization and Context Discipline

Agents SHOULD read the smallest sufficient normative context. After meaningful
changes they MUST update affected Memory Bank knowledge and follow the current
wave-boundary synchronization policy.

## Governance

- This Constitution has precedence over workflow habits and generated plans.
- MBB, spec-index, spec-backbone, invariants, contracts, states, testing, and
  workflow docs refine this Constitution and MUST NOT contradict it.
- Amendments require evidence or explicit user instruction and must update
  affected durable docs.
- Keep this document short; concrete rules belong in invariants, contracts,
  states, testing, or workflow policies.
