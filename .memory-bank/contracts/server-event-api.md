---
description: Exact developer-only bounded structured server-event search page and failure contract.
status: active
last_updated: 2026-09-01
source_of_truth:
  - .memory-bank/contracts/server-event-api.md
---
# Server Event API

## Scope And Ownership

`diagnostics` owns the server-event search use case, filtering, business
authorization and HTML projection over its
[Structured Server Events](../domains/structured-server-events.md) repository.
Its HTTP adapter obtains the current principal through the accepted
`diagnostics -> staff_access` edge. `staff_access` authenticates only, and the
backend composition root only registers the adapter.

This contract adds no JSON API, detail route, read-model table, arbitrary query
surface or separate frontend. FT-008 remains the owner of Attempt investigation;
this page only links to its existing routes.

## Staff Route And Filters

The only route is `GET /staff/server-events`. It uses the existing staff
session, returns `Cache-Control: no-store` and reevaluates the current principal
on every request. Only an active `developer` may read it. An authenticated
operator or photographer receives `403`; a missing, invalid, expired or revoked
session receives `401`.

The route accepts each of these optional parameters at most once:

| Parameter | Contract |
|---|---|
| `from` and `to` | Both omitted selects `[now - 24 hours, now)`. When used, both are required RFC 3339 UTC values, `from` is inclusive, `to` is exclusive, `to` is later and the interval is at most seven days. |
| `severity` | Exact `info \| warning \| error`. |
| `component` | Exact `runtime \| realtime \| promo \| qr`. |
| `event_code` | Exact code from the canonical event catalog. |
| `attempt_id` | Exact server Attempt UUID. |
| `correlation_id` | Exact client correlation UUID. |

Unknown, repeated, malformed or unsupported parameters, a lone time bound and
an invalid/oversized range return `422` before a repository call. Supplied
filters are conjunctive. Results order by `occurred_at DESC, event_id DESC` and
contain at most the latest `100` rows. There is no pagination, arbitrary sort,
message/full-text query, saved query, live tail, export or dashboard.

## HTML Projection And FT-008 Navigation

The page renders only event time, severity, component, event code, release ID
and nullable Attempt/correlation IDs. It renders no arbitrary message/payload,
traceback, media or protected value.

- An event with `attempt_id` links to
  `GET /staff/attempts/{attempt_id}`.
- An event without `attempt_id` but with `correlation_id` links to
  `GET /staff/attempts?correlation_id={correlation_id}`.
- An event with neither identity renders no Attempt link and MUST NOT invent an
  association.

The target route applies its own current authorization and missing-state rules.
FT-009 neither reads promo tables to validate the link nor embeds FT-008 detail.
Because there is no event detail route, a bookmarked search after 30-day cleanup
renders only currently retained matches and cannot recover deleted event data.

## Failure Contract

### Invalid Filter Response

Every invalid filter class defined above returns `422`, `Cache-Control:
no-store` and performs zero repository calls.

### Sanitized Internal Failure Response

An unexpected repository or HTML-render failure returns a sanitized `500` with
`Cache-Control: no-store`. The response, server output and retained task
artifacts MUST NOT contain a traceback, session cookie, credential, protected
value, arbitrary failed payload or participant data.

Denied responses reveal neither matching-row existence nor correlation state.
All responses remain server-rendered HTML; no shared custom error envelope is
introduced.

## Verification Targets

- Seed every catalog code and filter field across default, exact and
  outside-window fixtures; prove conjunctive filtering, deterministic ties, the
  seven-day validation and 100-row cap.
- Compare developer, operator, photographer, unauthenticated, revoked and
  downgraded requests, including copied URLs and browser history; prove current
  `401|403`, no-store and no retained protected page content.
- Prove detail-link, correlation-query link and no-link behavior for the three
  identity shapes without a promo-table read or invented Attempt.
- Exercise every invalid-filter class and injected repository/render failures;
  prove no-query `422`, sanitized `500` and redacted artifacts.
- Use `playwright cli` for the real browser filter/table/navigation and stale-
  role/stale-retention journey, retaining only redacted synthetic evidence.
