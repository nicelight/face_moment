---
description: Лог изменений Memory Bank.
status: active
---
# Changelog

## [2026-07-24] Photo Inventory Operations and SDD backbone
- Added role-scoped Photo soft delete/restore, project-wide restore-all and
  fixed-snapshot hard purge that retains core Attempts and diagnostic evidence.
- Added per-СПА 1/5/60-minute Photo processing counters with five-second Admin
  UI polling and traced the scope through `REQ-INV-*`, EP-001 and FT-012.
- Accepted the initial global SDD backbone at Planning Revision 1 and recorded
  the required greenfield Foundation Dev Path with its task gate still pending.
- Advanced the backbone to Planning Revision 2 for standard HTTP transport
  errors with typed capture/search outcomes and no custom error framework.
- Fixed one PostgreSQL application schema, shared SQLAlchemy `Base/MetaData`,
  one Alembic configuration/stream and ownership-safe foreign-key/cascade
  constraints across capability slices.
- Clarified that all application, backend, worker and deployment descriptions
  are target design; no working runtime or code exists yet.

## [2026-07-22] Pilot durability and QR-session simplification
- Removed backup as a pilot requirement and recorded accepted data loss after
  irreversible loss of the only primary disk/server.
- Corrected the greenfield boundary: the backend/admin application is delivered
  by this project; no existing backend or external IdP is assumed.
- Simplified QR continuation to one session-wide browser access state with no
  per-device grant records while retaining the 30-minute first-open and
  60-minute shared idle limits.
- Clarified that browser JPEG upload crosses the HTTPS backend boundary and
  private MinIO is never a browser endpoint.

## [2026-07-20] СПА terminology synchronization
- Updated the human-readable venue term from Latin spelling to Cyrillic `СПА`
  across current project Markdown documents.
- Preserved ASCII machine identifiers such as `spa_id`, `spa_client_token` and
  `SpaPromoClient`; changed the illustrative folder placeholder to `spa_code`.
- Reconciled PRD, Product Brief, requirements, epics, features, supporting
  discovery records and Memory Bank routers without changing product meaning.

## [2026-07-18] One-СПА pilot PRD clarification
- Completed the one-СПА pilot PRD clarification against the ratified
  Constitution and current Product Brief.
- Recorded the final Promo/QR, ingest-deduplication, diagnostics, retention,
  access and acceptance decisions directly in the normative PRD sections.
- Updated `mb-lint` so a complete PRD is validated by the absence of unresolved
  markers/blockers rather than by requiring a historical Clarifications section.

## [2026-07-17] Project Constitution ratification
- Ratified project governance as `medium` with KISS and an explicit
  `DO NOT Overengineering` principle.
- Set performance and stable Promo/QR as the current leading product priority.
- Simplified current product risks, gates, and open questions to the concerns
  that matter for the pilot.
- Aligned Product Brief, discovery inputs, invariants, testing guidance, and
  spec routing with the ratified priorities.

## [2026-07-11] Discovery input refinement
- Linked `IDEA_APP.md` and `IDEA_OS.md` as non-normative pre-PRD inputs.
- Preserved blocked SDD readiness until the formal brief/PRD/spec workflow runs.
- Split the central host into administrative `facemoment` and unprivileged
  autologin `display` users; required the standard Chromium sandbox.

## [2026-07-09] Initial setup
- Created Memory Bank skeleton
- Seeded core docs (product, requirements, testing, task registry)
