---
description: Lightweight responsibility and scope boundary notes for decomposition, implementation, and verification.
status: draft
last_updated: 2026-07-20
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
- [IDEA_INGEST.md](../../IDEA_INGEST.md): pilot ingest and immutable batch
  boundary.
- [IDEA_DEBUG.md](../../IDEA_DEBUG.md): attempt/log/artifact/annotation/
  calibration boundary.

## Boundary Notes
| Boundary | Purpose | Direction | Responsibility owner | Known constraints | Later design question |
|---|---|---|---|---|---|
| Photographer -> ingest application | Turn validated JPEG uploads into an immutable commercial-photo batch. | Photographer submits; backend validates and confirms. | Backend owns authentication, authoritative `visit_date`, checksum handling, manifest freeze, and visible state. | Direct HTTPS JPEG upload only; Yandex/external ingest is post-pilot. | Exact component/API/data contracts. |
| Backend/PostgreSQL -> `BackgroundPhotoWorker` -> private object storage/PostgreSQL | Make confirmed commercial photos searchable. | Backend creates idempotent work; one sequential worker consumes and publishes results. | Worker owns pipeline processing; PostgreSQL owns job/state records; object storage owns binaries. | No external broker; `photo_pipeline_states.status = ready` is searchable truth; at-least-once work must not duplicate final faces. | Transaction, retry/recovery, object-key, and failure contracts. |
| `SpaPromoClient` -> `RealtimeFaceService` | Convert one fresh sensor-triggered reference series into one short-lived result. | Client submits fresh reference context; service returns teasers and continuation context. | Client owns capture/display freshness; service owns compatible pipeline processing, exact scoped search, result construction, and session issue. | SPA binding and freshness are mandatory; stale work cannot be replayed. | Transport, request/response, deadline, error, and authorization contracts. |
| Realtime search -> commercial inventory | Match selected detections only against compatible searchable photos. | Service queries filtered PostgreSQL/pgvector state and resolves protected previews. | `RealtimeFaceService` owns query gates and aggregation; persistent stores own records/artifacts. | Same pipeline revision, SPA, authoritative `visit_date`, query quality, calibrated threshold; `pHash` is ranking-only. | Canonical query/data and artifact-access contracts. |
| Promo session -> phone continuation | Continue the same personalized result without another selfie. | Display exposes QR; phone opens the issued session through the backend. | Backend owns session validity/data isolation; clients render the allowed view. | Display, QR first-open, and browser-idle lifetimes are independent; expired data must not leak; payment/original delivery is out of scope. | Token/session representation, expiry, redirect, and compatibility contracts. |
| Browser/server runtime -> diagnostic attempt | Correlate critical-flow evidence without blocking it. | Runtime emits structured events and protected artifact references to the existing backend. | Backend/PostgreSQL owns searchable events; private object storage owns images; application authorization owns access split. | One correlation ID per attempt; no images/secrets/request bodies/session replay in logs; operator view is sanitized. | Event schema, ingestion/failure, redaction, access, and retention contracts. |
| Annotation/calibration -> serving settings | Explain threshold/quality alternatives while keeping serving changes controlled. | Developer annotates and requests analysis; Calibration recommends; developer applies separately. | Diagnostic/calibration contour owns evidence and recommendations; serving configuration owner applies accepted changes. | Per-person/per-detection evidence; one-dimensional quality-gate analysis; never auto-apply. | Exact formulas, audit, configuration-change, and rollback contracts. |

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
