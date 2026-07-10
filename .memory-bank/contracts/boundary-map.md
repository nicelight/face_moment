---
description: Lightweight responsibility and scope boundary notes for decomposition, implementation, and verification.
status: draft
---
# Boundary Map

## Purpose
- Keep lightweight boundary notes that help agents avoid crossing ownership, responsibility, or write-scope lines during decomposition and task execution.
- Use this file as an existing contract/spec input when task records need `purpose`, `success_outcome`, `anti_goals`, `runtime_context.allowed_write_scope`, `runtime_context.forbidden_scope`, or `runtime_context.stop_conditions`.

## Boundary Notes
| Boundary | Purpose | Direction | Owner | Known Constraints | Questions |
|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD | TBD |

## Boundary: <producer> -> <consumer>

- Owner:
- Consumers:
- Allowed calls:
- Forbidden calls:
- Data owner:
- Compatibility rule:
- Verification:
- Linked ADs:

## Runtime Context Hints
- Allowed write scope hints: TBD
- Forbidden scope hints: TBD
- Stop condition hints: TBD

## Update Rules
- Keep entries evidence-backed and short.
- Do not add endpoint lists, OpenAPI details, request/response schemas, auth policy, error-code design, or implementation pseudocode here.
- Do not create new task fields for boundaries; link this file through existing task fields such as `source_artifacts`, `normative_inputs`, `constraints`, `invariants`, or `verification_targets`, and copy executable scope into `runtime_context` when needed.
