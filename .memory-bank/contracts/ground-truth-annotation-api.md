---
description: Exact developer-only HTML routes, mutation rules and failures for ground-truth annotation.
status: active
last_updated: 2026-09-04
source_of_truth:
  - .memory-bank/contracts/ground-truth-annotation-api.md
---
# Ground-Truth Annotation API

## Scope And Ownership

`diagnostics` owns the annotation use case, business authorization, projection
and writes. Its HTTP adapter obtains the current principal through the existing
`diagnostics -> staff_access` edge and reads the core Attempt through the
existing `diagnostics -> promo` edge. `staff_access` authenticates only; the
backend composition root registers routes and owns no annotation behavior.

This is a same-origin HTML feature. It adds no JSON API, participant registry,
dataset catalog, artifact upload, read model or new runtime role.

## Staff Routes

The minimal routes are:

- `GET /staff/attempts/{attempt_id}/annotations` — list current annotations and
  show the create/correction controls;
- `POST /staff/attempts/{attempt_id}/annotations` — create one annotation;
- `POST /staff/attempts/{attempt_id}/annotations/{annotation_id}` — apply
  exactly one form action, `update` or `delete`, to an annotation belonging to
  that Attempt.

The existing developer Attempt detail may show a link to the child page, but
its FT-008 base projection still contains no participant name or annotation.
Successful mutations return `303` to the annotation GET route. Every response,
including errors and redirects, carries `Cache-Control: no-store`.

## Authorization And Mutation Contract

Every request evaluates the current staff session. Only an active `developer`
may read or mutate annotations. An operator or photographer receives `403`; a
missing, invalid, expired or revoked session receives `401`. Denied responses
do not reveal whether the Attempt or annotation exists.

Every mutation uses the existing staff CSRF cookie/header-or-form contract.
Missing or invalid CSRF returns `403` without a write. Participant names are
HTML-escaped and MUST NOT appear in URLs, access logs, structured server events,
exception text or retained task artifacts.

Create/update accepts only the fields defined by
[Ground-Truth Annotations](../domains/ground-truth-annotations.md#postgresql-shape).
The application validates the Attempt and detection target through owner
boundaries before committing. Update preserves identity/target; delete removes
only the addressed diagnostics-owned ordinary row. The page shows absent
annotation as unlabelled, never as `missed`; person-level `missed` needs no
detection artifact.

## Failure Contract

- A well-formed authorized request for a missing Attempt or an annotation not
  owned by that Attempt returns `404` with no owner-state reconstruction.
- Malformed UUIDs, unknown/repeated fields, unsupported form actions, invalid
  target/outcome pairs, blank/oversized names and nonexistent detection targets
  return `422` and perform no write. An annotation write after ordinary
  evidence is `expired|removed` also returns `422` without recreating content.
- An unexpected provider, repository or render failure returns a sanitized
  `500`; the transaction rolls back and no protected value enters the response,
  logs or evidence artifact.

No custom error envelope or message registry is introduced.

## Verification Targets

- Focused HTML/application fixtures prove create, correction, deletion,
  `correct|false`, person-level `missed`, missing-versus-missed behavior and the
  resulting calculation projection.
- The current-role matrix covers developer success plus operator,
  photographer, unauthenticated, revoked and downgraded denial on list, direct
  link and every mutation.
- CSRF, validation, missing-owner and injected-failure fixtures prove no write,
  `no-store`, rollback and absence of names/annotations from URLs, logs,
  structured events and retained artifacts.
- One `playwright cli` smoke covers Attempt-detail navigation and one successful
  form submission using only disposable synthetic names and rows. Focused
  application fixtures above own correction/removal and stale-page denial after
  role downgrade; the browser smoke does not duplicate that matrix.
