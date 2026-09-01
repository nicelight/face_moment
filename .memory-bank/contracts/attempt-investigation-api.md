---
description: Exact role-scoped staff Attempt investigation page, filters, projections and failure contract.
status: active
last_updated: 2026-09-01
source_of_truth:
  - .memory-bank/contracts/attempt-investigation-api.md
---
# Attempt Investigation API

## Scope And Ownership

`diagnostics` owns the role-scoped investigation use case and staff-facing
projection. It reads the promo-owned core Attempt only through the accepted
`diagnostics -> promo` application boundary and reads diagnostics-owned
`DiagnosticEvidence` through its own repository. Its HTTP adapter obtains the
current principal through the registered `diagnostics -> staff_access` edge;
the diagnostics application then authorizes and projects the result.
`staff_access` authenticates only, and the backend composition root only
registers the adapter. Neither may own diagnostic authorization or query owner
tables directly.

This contract adds one internal diagnostics-owned ordinary-removal transition
on the existing evidence shape, but no HTTP mutation route, JSON endpoint,
table, migration, materialized read model, runtime role or diagnostic artifact.
FT-009 may link a correlated server event to this surface but does not change
its fields or authorization.

## Staff Routes And Filters

The same-origin read-only HTML routes are:

- `GET /staff/attempts` for the filter form and bounded table;
- `GET /staff/attempts/{attempt_id}` for one Attempt detail.

Both routes use the existing staff session, return `Cache-Control: no-store`
and evaluate the current principal on every request. Active `operator` and
`developer` principals may read them. A photographer receives `403`; a missing,
invalid, expired, revoked or downgraded session receives `401` or the current
role's `403`. A stale browser page or copied URL never retains prior authority.
Because both methods are safe reads, they add no CSRF mutation surface.

The list accepts only these optional query parameters:

| Parameter | Contract |
|---|---|
| `attempt_id` | Exact UUID of the promo-owned server `PromoAttempt.id`. |
| `correlation_id` | Exact UUID equal to existing `PromoAttempt.client_attempt_id`. |
| `from` | Inclusive RFC 3339 UTC lower bound over `created_at`. |
| `to` | Exclusive RFC 3339 UTC upper bound over `created_at`; when both bounds exist, `to` MUST be later than `from`. |
| `state` | Exact promo processing state: `accepted`, `searching`, `result_issued`, `no_success`, `interrupted`, `deadline` or `internal_failure`. |

Unknown, repeated or malformed parameters and invalid ranges return `422` and
perform no query. Multiple supplied filters are conjunctive. Results order by
`created_at DESC, attempt_id DESC` and contain at most the latest 100 matching
Attempts. No pagination, saved query, full-text search, export or live tail is
introduced.

## Promo Query Boundary

`promo` publishes one read-only application query that accepts the exact
identity/time/state filter set above and returns bounded immutable Attempt
projections. Each projection contains server `attempt_id`, client
`correlation_id`, immutable admission identity needed for investigation,
`created_at`, processing state/outcome and the existing
[core timeline projection](../domains/promo-attempt.md#core-timeline-projection).

The provider MUST apply the bound and deterministic ordering before returning
results. Exact server identity returns at most one row; client correlation is
resolved from `client_attempt_id` in the one-СПА pilot. The projection is not a
new persistence model. It MUST NOT expose ORM entities, accept arbitrary sort
or predicates, write core Attempt/result/session state, or let diagnostics read
`promo_attempts` directly.

## Role-Scoped HTML Projection

The list renders identifiers, creation time, processing state, outcome, bounded
stage/latency summary, issue tags and a detail link. The detail renders the
same core truth without subtracting client wall time from server time or
fabricating nullable stages.

For an operator, detail is limited to:

- server `attempt_id` and client `correlation_id`;
- processing state/outcome;
- client-local ready-series start, local-detection completion, request start
  and nullable response receipt;
- server admission/slot/search timestamps and derived durations;
- display state, nullable QR-visible elapsed value and bounded issue tags;
- the truthful ordinary-evidence state without its manifest, gap detail,
  promoted subset or protected related-feature data.

For a developer, detail adds the existing ordinary evidence schema version,
completeness, bounded gap reason, evidence issue tags and readable
`ordinary_manifest` when present. It MUST NOT add `promoted_subset`, participant
names/annotations, Calibration, structured server events, personalized session
data, commercial Photo media or a new artifact-navigation surface. Existing
capture-derived fields are not hidden solely because they are image-derived;
their actual delivery still follows the owning media boundary.

## Evidence Availability

The diagnostics projection uses exactly four ordinary-evidence states:

| State | Existing durable truth | Read behavior |
|---|---|---|
| `complete` | A row has readable `ordinary_manifest` and `completeness=complete`. | Developer may read the allowed manifest; operator sees only the state and merged issue tags. |
| `incomplete` | No evidence row exists, or a readable row is explicitly incomplete. | Show the bounded gap (`evidence_absent` for no row); never imply a full history. |
| `expired` | `ordinary_expired_at` is present and ordinary content is absent. | Show expiry and return no expired content through current or stale routes. |
| `removed` | The diagnostics-owned [explicit ordinary-removal transition](../domains/diagnostic-evidence.md#explicit-ordinary-removal-transition) retained provenance with `gap_reason=ordinary_removed`, cleared ordinary content and left the retention-expiry marker absent. | Show explicit removal and return no removed content through current or stale routes. |

A promoted subset never recreates ordinary detail. A missing core Attempt
returns `404`; the page MUST NOT reconstruct it from an evidence row, retained
subset, session or stale browser content.

## Failure Contract

Authentication failures remain `401` for a missing/invalid session and `403`
for a current authenticated role outside operator/developer. These outcomes are
covered by the role-isolation feature claims. The remaining public failures are
separate task-owned obligations below.

### Missing Attempt Response

An authorized detail request for a server `attempt_id` that does not exist MUST
return `404`, `Cache-Control: no-store` and no evidence-derived reconstruction
or identifier-existence detail beyond that result.

### Invalid Filter Response

Unknown, repeated, malformed or unsupported list filters and invalid time
ranges MUST return `422`, `Cache-Control: no-store` and MUST NOT call the promo
query provider.

### Sanitized Internal Failure Response

An unexpected provider, evidence-read or HTML-render failure MUST return a
sanitized `500` with `Cache-Control: no-store`. The response, logs and retained
task artifacts MUST NOT contain a traceback, session cookie, credential,
protected manifest or participant data.

Responses do not reveal whether a denied identifier exists. Logs and task
artifacts MUST NOT retain session cookies, credentials, protected manifests or
participant data.

## Verification Targets

- Seed bounded Attempts spanning both exact identities, every processing state
  and inside/outside UTC windows; prove conjunctive filtering, deterministic
  newest-first order, the 100-row cap and complete core timeline fields.
- Compare operator and developer list/detail HTML for the same Attempts and
  prove the exact field asymmetry, `no-store` and absence of FT-009, annotation,
  Calibration, promoted-subset and personalized-session data.
- Exercise photographer, unauthenticated and post-downgrade current/direct-link
  requests and prove `401|403` without existence or prior-page disclosure.
- Exercise complete, absent/partial, retention-expired and explicitly removed
  evidence plus stale URLs; create `removed` through the diagnostics owner
  transition, prove its idempotency/stale-write rejection, and prove each
  visible state is distinct with no expired or removed content recoverable.
- Inject a missing detail identity, every invalid-filter class and a protected
  internal read/render failure; prove exact `404`, no-query `422` and sanitized
  `500` responses with `no-store` and redacted logs/artifacts.
- Use `playwright cli` for the real-browser filter, table, detail and stale-role
  flow; retain transcript and screenshots under the owning task evidence path.
