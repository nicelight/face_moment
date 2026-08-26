---
description: Exact authenticated client timing report contract for one admitted realtime Attempt.
status: active
last_updated: 2026-08-25
source_of_truth:
  - .memory-bank/contracts/client-diagnostic-api.md
---
# Client Diagnostic API

## Scope And Ownership

This contract reports the browser-local response-receipt marker after the
existing synchronous [Realtime Attempt API](realtime-attempt-api.md) returns.
`promo` owns the core Attempt and this timing transition. The route may notify
`diagnostics` through its accepted application boundary, but neither the HTTP
handler nor `diagnostics` may write `face_moment.promo_attempts` directly.

The report is best-effort. It adds no reliable outbox, replay queue or new
Attempt. A client-only failure before server admission may therefore leave no
durable server record.

## Endpoint And Authentication

- Method and path:
  `POST /api/realtime/attempts/{attempt_id}/client-timing`.
- `{attempt_id}` is the client-generated UUID returned by the realtime response.
- Authentication uses the same active display-client
  `Authorization: Bearer <spa-client-token>` principal as the realtime request.
- The server derives `spa_id` from the token hash and resolves only the unique
  `(spa_id, client_attempt_id)` Attempt. The body cannot supply or override
  `spa_id`.
- The route uses the configured display-client rate limit and returns
  `Cache-Control: no-store`. Token material, the request body and protected
  identifiers MUST NOT enter logs.

## Request Version 1

The JSON body contains exactly:

```json
{
  "schema_version": 1,
  "response_received_ms": 842
}
```

- `schema_version` MUST be integer `1`.
- `response_received_ms` MUST be a non-negative integer monotonic offset from
  the same `reference_series_ready` origin used by
  `local_detection_completed_ms` and `request_started_ms`.
- It MUST be greater than or equal to the stored `request_started_ms`.
- Unknown fields, booleans in place of integers and client/server wall-clock
  subtraction are forbidden.

## Idempotency And Response

The first valid report for the scoped Attempt atomically stores the marker
through the promo repository. A repeated equal value is idempotent. A different
later value conflicts and MUST NOT replace the first observation.

A successful first or equal repeat returns `200 application/json`:

```json
{
  "schema_version": 1,
  "attempt_id": "d7938b68-31e8-44ce-bdaa-32755a64b067",
  "response_received_ms": 842
}
```

The client does not wait for or retry this response as a participant-flow
prerequisite. Report failure never changes the already observed realtime
outcome, display state or session.

## Failures And Gaps

- `401`: missing or invalid display-client credentials.
- `404`: unknown or foreign-СПА Attempt, without disclosing which case applies.
- `409`: the Attempt is not terminal yet or a different marker was already
  accepted; owner state is unchanged.
- `422`: invalid UUID, version, shape, type, range or marker ordering.
- `429`: configured display-client rate limit exceeded.

If the report is missing, FT-007 read projections expose an explicit
`response_receipt_missing` gap rather than substituting server response time.
No core Attempt is upserted by this endpoint.

## Verification Targets

- Controlled-clock client/API/repository fixtures prove exact shape, marker
  ordering, first-write/equal-repeat idempotency and conflicting-repeat
  immutability.
- Success, zero-proposal, busy, deadline and admitted technical-failure fixtures
  retain the core Attempt and can accept a scoped terminal report.
- Pre-admission offline, foreign token, invalid payload and rate-limit fixtures
  create no Attempt and change no existing Attempt.
- Source and evidence scans prove no reliable outbox, cross-machine subtraction,
  token/body logging or diagnostics direct write to the core table.
