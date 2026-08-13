---
description: Advisory technical-debt review for actual FT-002 Wave W3 changes and carried import drift.
status: active
---
# Technical-debt review — wave W3

## SCOPE

- Actual W3 surface: `TASK-023-T3-FT-002-W3` terminal publication,
  `TASK-025-T2-FT-002-W3` startup recovery, and their changed processing
  package seam at `src/face_moment/processing/__init__.py`.
- Evidenced carried drift: the `WorkerClaimRepository` eager export introduced
  by `TASK-022-T2-FT-002-W2`, which remains part of that package seam.
- This is not a repository-wide review.

## VERDICT

One material finding is confirmed. `TASK-023` and `TASK-025` retain their
task-scoped functional evidence; the finding is a package-import reliability
defect outside their accepted terminal/recovery outcomes.

## MATERIAL FINDINGS

### HIGH — `serving_control.ingest_target` has an order-dependent circular import

- Reproduction on the current packaged image:

  ```text
  docker compose run --rm --no-deps backend python -c \
    'import face_moment.serving_control.ingest_target'
  # exit 1: ImportError: cannot import name 'IngestTarget' from partially initialized module
  ```

- Chain: `serving_control/ingest_target.py:11` imports the processing package;
  `processing/__init__.py:30-34` eagerly imports `worker_claims` and terminal
  publication; `worker_claims.py:9-12` imports inventory and serving-control
  models; package initialization of `inventory/__init__.py:1-14` imports
  `admission.py:13-14`, which imports the partially initialized
  `serving_control` package.
- The defect is persistent, not historical: the same fresh import failed now.
  The W3 task gates, `import face_moment.processing`,
  `import face_moment.entrypoints.backend`, and
  `import face_moment.inventory.ingest_targets` pass only because those paths
  initialize the packages in a favorable order.
- Impact/blast radius: any direct consumer of the serving-control ingest-target
  module can fail before application logic starts; a harmless import ordering
  change can expose the same failure in backend, worker, tests, or maintenance
  commands. No persistent state is mutated; restart with a favorable import
  order is recoverable, but it is not a reliable remedy.

## OWNER / REQUIRED ACTION

- Owner: the processing package export boundary; the carried mechanism entered
  with `TASK-022` and remains on the W3 package seam.
- Smallest bounded fix target: `src/face_moment/processing/__init__.py`.
  Stop eagerly re-exporting repository modules that import `inventory` or
  `serving_control` (`WorkerClaimRepository`, `TerminalFace`, and
  `TerminalPublicationRepository`); consumers use their concrete processing
  submodules. Prove the correction with the exact fresh direct import above.
- No product, architecture, contract, state, or scheduler redesign is needed.

## REPORT SCHEDULER IMPLICATION

This advisory report neither blocks nor promotes W4 and does not change any
task status. Under the `/tech-debt` policy, W4 promotion may proceed only by
the scheduler's ordinary gate process. The scheduler should retain this HIGH
finding as the bounded correction basis before relying on a direct
serving-control import; this report itself makes no lifecycle or promotion
decision.
