---
description: Canonical accepted module/change-unit dependency graph and boundary contracts.
status: draft
---
# Boundary Map

## Purpose
- Keep one accepted inventory of project modules/change units and every allowed significant dependency between them.
- Treat `Consumer -> Provider` as the direction of dependency. Observed imports or calls are evidence, not accepted edges by themselves.

## Modules
| Module / Change Unit | Parent Architecture Unit | Code Root | Responsibility |
|---|---|---|---|

## Dependency Graph

`Consumer -> Provider` means Consumer depends on Provider through the linked contract.

| Consumer | Provider | Contract |
|---|---|---|

## Inline Contracts

Add a `### <Contract>` block here only for a simple internal boundary. Use an exact heading link from the graph. A contract with independent complexity, multiple consumers, reuse, or its own compatibility surface belongs in a subject contract.

Each contract block defines only the applicable public surface, allowed interaction, state/data authority, failure and compatibility rules, forbidden bypasses, and verification. Topology remains exclusively in `Dependency Graph`.

## Update Rules
- `Module / Change Unit` is the unique graph key. Use stable functional responsibility names, not feature/task IDs, current paths, or generic technical layers.
- Every graph row names registered modules and links to one exact contract heading. The graph row alone owns consumer, provider, and direction.
- Include every accepted significant inter-module dependency. An absent edge is not authorized.
- Keep the detailed module inventory here. `system-architecture.md` owns only larger architecture units and links to `#modules`.
- Plans and tasks link relevant graph/contract blocks through existing fields; they do not copy the subgraph or introduce graph-specific task fields.
