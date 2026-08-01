---
description: Лог изменений Memory Bank.
status: active
---
# Changelog

## [2026-08-01] FT-003 canonical contract design
- Completed the exact sensor long-poll and realtime multipart contracts plus
  central display-client and core Attempt data specifications without changing
  Global Planning Revision `4`.
- Advanced `FT-003.spec_design_status` from `blocked` to `complete` and closed
  the final unresolved `api_contracts` design row.
- Preserved the representative-benchmark and site-camera-dimension exclusions;
  no product behavior was changed.

## [2026-07-29] Client restart availability clarification
- Kept local advertising during transient server/network failure for an already
  loaded client.
- Removed the guarantee that tab reload or Chromium restart restores
  advertising while the central HTTPS origin is unavailable; normal automatic
  recovery resumes once that origin is reachable.

## [2026-07-28] Foundation current-state reconciliation
- Reconciled Product Brief, product, PRD, lifecycle and Architecture Spine
  wording with the verified Foundation: the executable server/storage substrate
  exists, while product behavior and the deployed pilot runtime remain target
  work.
- Preserved feature-level `not currently runnable` verification statements for
  product behavior that Foundation intentionally does not implement.

## [2026-07-24] Wave W0 — verified Foundation completion
- Reconciled scheduler-owned `done` closure for both indexed FT-000 tasks:
  TASK-001 has functional `PASS`, `semantic-pass` and
  `HUMAN_CHECKPOINT: done`; the TASK-002 final gate has independent
  `VERDICT: PASS`.
- Advanced only the already-decided `REQ-000` and FT-000 lifecycle surfaces
  from `planned` to `verified`; the global Planning Revision remains `2`.
- Linked the functional, semantic and final-gate verification reports plus the
  REQ-000/Foundation evidence map from the owning Foundation, feature and RTM
  surfaces. No findings, fixes, follow-ups or product tasks were created.

## [2026-07-24] Foundation executable-baseline queue
- Added `REQ-000` and the reserved `FT-000` pseudo-feature for the accepted
  greenfield executable baseline.
- Extended the existing testing spec with isolated build/typecheck/test,
  empty-database migration, private-storage, fake-engine, HTTPS and restart
  proof contracts without adding product behavior.
- Created the minimum two-task W0 queue: one T3 walking-skeleton
  implementation and one dependent T2 verification-only final gate.

## [2026-07-24] SDD verifier corrections
- Advanced Planning Revision once from `1` to `2` for three operator-approved
  corrections; the empty task queue made no plan stale.
- Fixed serving-revision recovery as an operator-owned manual action with no
  automatic rollback.
- Added the explicit Foundation `mypy` gate and an observable latest retention
  result.

## [2026-07-24] Global SDD backbone acceptance
- Completed the mandatory `/spec-design` gate with a
  `strict_architecture_scaffold`, `split-by-boundary-topic` strategy and
  Planning Revision `1`.
- Accepted the existing five-slice modular-monolith bundle without adding a
  new spec hub; fixed processing-projection reads, manual revision-switch
  orchestration and owner-ordered retention cleanup in the owning specs.
- Accepted `Foundation Required: true` because the greenfield repository has no
  executable release, entrypoints, migration/storage baseline or runnable
  build/start/test path.
- Kept product behavior outside Foundation and routed the next boundary to
  `/foundation-to-tasks`; the empty indexed task queue required no lifecycle
  invalidation.

## [2026-07-24] KISS session, offline-attempt and purge clarification
- Recorded explicit operator decisions as candidate `/spec-design` inputs; no
  successful global backbone run or positive Planning Revision was established.
- Clarified that soft delete blocks new search/result formation but does not
  invalidate an already issued Promo session.
- Simplified hard purge: it removes Photo-owned media/state while retaining
  existing Promo sessions, core Attempts and diagnostic evidence; UI/device
  loading skips unavailable media without rebuilding the session or `N`.
- Made client-only offline Attempt delivery best-effort and added the
  non-blocking 5–10-second server-communication failure notice.
- Fixed hard-purge concurrency by rejecting restore/restore-all for confirmed
  non-terminal snapshot members.
- Reconciled singleton realtime `busy` semantics, display acknowledgement,
  joint 19/20 acceptance, canonical feature links and supporting diagrams/docs.

## [2026-07-24] Photo Inventory Operations and SDD backbone
- Added role-scoped Photo soft delete/restore, project-wide restore-all and
  fixed-snapshot hard purge that retains core Attempts and diagnostic evidence.
- Added per-СПА 1/5/60-minute Photo processing counters with five-second Admin
  UI polling and traced the scope through `REQ-INV-*`, EP-001 and FT-012.
- Drafted the global SDD backbone and greenfield Foundation proposal; both
  remain candidate inputs until the first full `/spec-design` run.
- Drafted standard HTTP transport errors with typed capture/search outcomes and
  no custom error framework as candidate architecture input.
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
