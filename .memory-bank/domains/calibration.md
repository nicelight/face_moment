---
description: Minimal diagnostics-owned Calibration run, evaluation, staff flow and retention contract.
status: active
last_updated: 2026-09-04
source_of_truth:
  - .memory-bank/domains/calibration.md
---
# Calibration

## Scope And Ownership

`diagnostics` owns Calibration selection, run state, recommendations,
drill-down and promoted subsets. It reads its immutable annotation projection
and the accepted Attempt projection, then calls `processing` for offline
evaluation. `processing` alone resolves inventory-owned Photo originals and
uses the two existing direct SFace and Buffalo M adapters.

Only `serving_control` may change serving settings after a separate explicit
developer action. The flow adds no model registry, experiment platform,
generic job system, second worker or automatic apply.

## Immutable Input And Evaluation

One run freezes:

- one SPA and unique selected Photo UUIDs with their immutable SHA-256 values;
- unique selected Attempt UUIDs with current persisted annotations and
  available required diagnostic input;
- exactly one eligible SFace revision and one eligible Buffalo M revision;
- current serving values, release/parameter identities and the finite candidate
  values used by the run.

All selected data must belong to the same SPA. Missing ground truth is excluded,
not invented. An Attempt without required available input remains an explicit
exclusion in the selected/applicable sample counts.

For each Photo, `processing` loads and verifies the original JPEG bytes once and
passes those same bytes and the same frozen applicable-Attempt selection to both
direct adapters without reupload. Missing or checksum-mismatched required input
fails the run as `dataset_unavailable`; the run must not silently shrink or
rebuild its dataset. Results remain separate by run, dataset hash and pipeline
revision, and no Photo, Attempt, annotation or serving state is mutated.

## Persistence And Run State

The next linear Alembic revision creates one diagnostics-owned table,
`face_moment.calibration_runs`, with:

| Field | Contract |
|---|---|
| `id` | UUID primary key and Calibration locator. |
| `requested_by_staff_id` | Developer UUID recorded as a logical reference without cross-owner cascade. |
| `status` | `requested | running | complete | failed | interrupted`. |
| `dataset_snapshot`, `dataset_sha256` | Required bounded immutable JSONB input and its canonical SHA-256. |
| `result_bundle` | Nullable bounded JSONB, present only for `complete`, with separate per-revision results. |
| `error_code` | Nullable bounded safe code, required for `failed | interrupted`. |
| `created_at`, `started_at`, `finished_at` | UTC timestamps consistent with state. |

Each JSON value is at most `1 MiB`, contains only finite numbers and excludes
embeddings, credentials, tokens, arbitrary request bodies and object-store
keys. Dataset input and terminal result are immutable.

```text
requested -> running -> complete | failed
running -- worker restart --> interrupted
```

The existing singleton `BackgroundPhotoWorker` claims one requested run only
while idle, publishes `current_operation=calibration`, executes it, then
releases the worker for Photo processing. Startup marks stale `running` rows
`interrupted`, restores the existing worker to `idle` and never creates a
replacement run. Rerun is a new explicit developer request.

## Recommendation Result

Threshold profiles and one-dimensional quality recommendations follow
[Calibration Verification](../testing/calibration.md). When accepted metrics
are undefined for every candidate, the result produces no proposal and shows
selected/applicable counts. Before/after comparison is allowed only between
complete stored results with the same dataset hash; otherwise it reports
`dataset_mismatch`.

## Minimal Developer Surface

The existing same-origin staff application exposes only:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/staff/calibrations` | Bounded recent list and explicit selection form. |
| `POST` | `/staff/calibrations` | Create one immutable requested run and redirect to detail. |
| `GET` | `/staff/calibrations/{calibration_id}` | Show state, comparison, profiles, quality results and Attempt links. |
| `POST` | `/staff/calibrations/{calibration_id}` | Perform exactly one confirmed `apply`, `promote` or `delete_promoted` action. |

Only an active `developer` may use these routes. Reads and redirects are
`no-store`; each POST requires the existing CSRF cookie/header pair. The create
form accepts only Photo, Attempt and the two pipeline-revision UUID selections.
The action form accepts an exact action, stored recommendation/selection key and
matching confirmation. It cannot submit replacement scores, thresholds,
quality values, annotations, media paths or result data.

Invalid form/confirmation returns `422`; a missing run or selected entity
returns `404`; ineligible, stale, cross-SPA or wrong-state input returns `409`;
unexpected failures return an empty sanitized `500` and roll back. Missing or
invalid session returns `401`, and another staff role returns `403`.

## Manual Apply

For `apply`, diagnostics resolves one exact recommendation from a complete run
and asks `serving_control` to update the existing
`reference_search_settings` row. Success increments the existing
`settings_revision`, updates `updated_at` and stores `calibration_id`; rejection
returns a bounded reason and preserves the row. These existing fields and the
command result are the pilot audit evidence; no settings-history or audit table
is added. Calibration never changes the selected pipeline revision.

## Ordinary And Promoted Retention

The existing owner-ordered cleanup also deletes terminal ordinary Calibration
runs strictly before its 90-day cutoff. Equal/newer terminal rows and active
`requested | running` rows are ineligible. The public latest-result shape is
unchanged, and the run deletion is verified as diagnostics-owned convergence
like annotation deletion.

Promotion reuses the existing `diagnostic_evidence.promoted_subset` seam. It
copies only selected currently available media/crops, parameters, scores and
immutable annotations needed for reproduction; it does not retain the whole
run, unselected data, screenshot, logs, credentials or session state. Ordinary
cleanup preserves that subset. The confirmed `delete_promoted` action reuses
the existing idempotent whole-subset deletion and does not restore ordinary
data.

## Verification Targets

- Disposable migration/repository fixtures prove the one table, immutable
  bounded data, transitions and no cross-owner cascade.
- Cross-slice fixtures prove identical verified JPEG bytes and Attempt selection
  across the two direct adapters without reupload or foreign writes.
- Fixed oracle and UI fixtures prove all profiles, one-gate-at-a-time analysis,
  same-dataset before/after, drill-down and honest unavailable recommendations.
- Worker restart proves `running -> interrupted`, no automatic replacement and
  resumed Photo processing.
- Role/CSRF/apply fixtures prove developer-only access, stored-value apply,
  unchanged state before confirmation and existing-field provenance.
- Fixed-time cleanup/promotion fixtures prove ordinary expiry, curated-only
  preservation and safe repeated whole-subset deletion.
