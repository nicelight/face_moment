---
description: Lightweight responsibility and scope boundary notes for decomposition, implementation, and verification.
status: draft
last_updated: 2026-07-23
---
# Boundary Map

## Purpose
- Preserve evidence-backed responsibility and direction hints without deciding
  exact APIs, schemas, auth policy, or implementation structure before
  `/spec-design`.
- Help `/prd-to-features` avoid merging independent user flows or cutting across
  accepted application/process boundaries.

## Evidence Scope

- [.memory-bank/prd.md](../prd.md): current pilot product contract and source
  precedence.
- [IDEA_APP.md](../../IDEA_APP.md): accepted high-level topology, processing,
  realtime, search, Promo/QR, and session boundaries.
- [IDEA_INGEST.md](../../IDEA_INGEST.md): historical ingest evidence superseded
  by the PRD where it requires Batch/manifest/confirmation.
- [IDEA_DEBUG.md](../../IDEA_DEBUG.md): attempt/log/artifact/annotation/
  calibration boundary.

## Boundary Notes
| Boundary | Purpose | Direction | Responsibility owner | Known constraints | Later design question |
|---|---|---|---|---|---|
| Photographer -> ingest application | Admit each validated JPEG independently under one selected СПА/`visit_date`. | Photographer submits through HTTPS; backend validates each file and reports accepted/rejected/duplicate. | Backend owns authentication, selected `visit_date`, SHA-256 duplicate arbitration and the per-photo Photo + `pending` commit. | Direct HTTPS JPEG upload only; uniqueness is `(spa_id, visit_date, checksum_sha256)`; no Batch/manifest/confirmation. | Exact component/API/data contracts. |
| Backend/PostgreSQL -> `BackgroundPhotoWorker` -> private object storage/PostgreSQL | Make independently accepted commercial photos searchable. | Backend durably creates `pending` work with the Photo; one sequential worker consumes and publishes results. | Worker owns pipeline processing; PostgreSQL owns durable job/state records; object storage owns binaries. | No external broker; `ready` is searchable truth; restart returns unfinished `processing` work to `pending`; at-least-once work must not duplicate final faces. | Exact retry/recovery, object-key, and failure contracts. |
| `SpaPromoClient` -> `RealtimeFaceService` | Convert one fresh sensor-triggered reference series into one short-lived result. | Client submits fresh reference context; service returns teasers and continuation context. | Client owns capture/display freshness; service owns compatible pipeline processing, exact scoped search, result construction, and session issue. | СПА binding and freshness are mandatory; stale work cannot be replayed. | Transport, request/response, deadline, error, and authorization contracts. |
| Realtime search -> commercial inventory | Match selected detections against all currently `ready` compatible photos for the active СПА/`visit_date`. | Service queries filtered PostgreSQL/pgvector state and resolves protected previews. | `RealtimeFaceService` owns query gates and aggregation; persistent stores own records/artifacts. | Readers may see a partial current-day set while upload continues; query quality and calibrated threshold remain mandatory; `pHash` is ranking-only. | Canonical query/data and artifact-access contracts. |
| Promo session -> phone continuation | Continue the same personalized result without another selfie. | Display exposes QR; scans within the first-open window reuse one session-wide browser access context through the backend. | Backend owns session validity/data isolation; clients render the allowed view. | No per-device grant records; display, QR first-open, and session-wide browser-idle lifetimes are independent; expired data must not leak; payment/original delivery is out of scope. | Ticket/cookie representation, expiry, redirect, and compatibility contracts. |
| Browser/server runtime -> core Attempt and diagnostic evidence | Persist the attempt correlation/timeline while collecting detailed evidence without blocking the critical flow. | Runtime creates one core Attempt before inference and attaches structured events/protected artifact references best-effort through the project backend. | Backend/PostgreSQL owns core Attempts and searchable events; private object storage owns images; application authorization owns access split. | Terminal Attempt remains visible as `incomplete` when evidence finalization fails; no images/secrets/request bodies/session replay in logs; operator view is sanitized. | Event schema, ingestion/failure, redaction, access, and retention contracts. |
| Annotation/calibration -> serving settings | Explain threshold/quality alternatives while keeping serving changes controlled. | Developer annotates and requests analysis; Calibration may occupy `BackgroundPhotoWorker`, recommends, and developer applies separately. | Diagnostic/calibration contour owns evidence and recommendations; serving configuration owner applies accepted changes. | Per-person/per-detection evidence; one-dimensional quality-gate analysis; never auto-apply; interrupted run is visible and manually rerunnable while photo processing resumes. | Exact formulas, audit, configuration-change, and rollback contracts. |

## Runtime Context Hints
- Allowed write scope hints: not assigned at this pre-PRD boundary; task cards
  must bind writes to the canonical components/specs selected later.
- Forbidden scope hints: post-pilot payment/original delivery, standalone selfie
  search, external ingest, tracking/clustering, and speculative infrastructure
  cannot enter pilot tasks implicitly.
- Stop condition hints: stop when a task would change the accepted high-level
  process split, public/session behavior, searchable truth, security/privacy,
  or retention semantics without an owning canonical design decision.

## Update Rules
- Keep entries evidence-backed and short.
- Do not add endpoint lists, OpenAPI details, request/response schemas, auth
  policy, error-code design, or implementation pseudocode here.
- `/spec-design` may refine or replace hints with canonical subject specs; task
  records must link those exact specs rather than relying on this router alone.
