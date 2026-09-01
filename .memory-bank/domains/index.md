---
description: Router for canonical Face Moment domain and persistence specifications.
status: active
---
# Domain Specifications

- [Display Client Access](display-client-access.md): SpaPromoClient identity,
  Admin-visible current token, manual kiosk handoff, authentication hash and
  lifecycle.
- [Diagnostic Evidence](diagnostic-evidence.md): versioned best-effort evidence,
  completeness gaps, explicit ordinary removal, promoted subset and
  diagnostics-owned retention.
- [Promo Attempt](promo-attempt.md): core Attempt persistence, immutable
  serving snapshot, result assembly/session, display and shared QR browser
  access transitions.
- [Realtime Reference Search](realtime-search.md): server-authoritative query
  selection, native query preparation and exact compatible Photo search.
- [Photo Admission](photo-admission.md): Photo/original/pending data,
  transaction, duplicate arbitration and crash recovery.
- [Photo Processing](photo-processing.md): compatible pipeline revisions,
  processing states, derivatives/faces, searchable truth and worker recovery.
- [Staff Access](staff-access.md): staff principals, roles, password hashes,
  server sessions and CSRF.
- [Structured Server Events](structured-server-events.md): fixed event shape,
  catalog, non-blocking diagnostics persistence, redaction and 30-day expiry.
