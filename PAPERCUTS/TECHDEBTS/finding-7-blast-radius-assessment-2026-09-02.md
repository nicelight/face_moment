---
description: Blast-radius and change-volume assessment for technical-debt finding 7.
status: advisory
checked_scope:
  - src/face_moment/entrypoints/backend.py
  - src/face_moment/entrypoints/common.py
  - src/face_moment/platform/auth/http.py
  - src/face_moment/inventory/http.py
  - src/face_moment/serving_control/http.py
  - src/face_moment/diagnostics/http.py
  - src/face_moment/promo/http.py
  - backend integration tests and existing lifecycle precedents
---
# Finding 7 — blast radius and change volume

## Verdict

The finding is real. Its blast radius is **wide horizontally but medium in
code volume**: five HTTP capability packages and the backend composition/lifecycle
are involved, while endpoint contracts, database schema and business rules do
not need to change. It should be one focused implementation task, followed by
the final HTTP/integration verification pass.

## Evidence

The five HTTP adapters each define a private `_database_session` that calls
`create_engine(...)` and disposes that engine after one request:

- `platform/auth/http.py:131-137` — 3 request call sites;
- `inventory/http.py:214-220` — 6 call sites;
- `serving_control/http.py:160-166` — 4 call sites;
- `diagnostics/http.py:259-265` — 2 call sites;
- `promo/http.py:470-476` — 10 call sites.

That is **25 request-level call sites** over five packages. The backend is wired
from `entrypoints/backend.py:42-51`; its current shared lifecycle in
`entrypoints/common.py:44-60` only exposes the server-event emitter. By
contrast, `entrypoints/realtime.py:85-129` and `entrypoints/model_consumers.py:21-50`
already demonstrate a process-owned Engine plus short-lived `Session` factory.

Backend integration tests invoke the ASGI app directly (for example
`tests/staff_access/test_sessions.py:106-117` and
`tests/diagnostics/test_retention_api.py:180-215`) rather than entering the
FastAPI lifespan. Eight tests also monkeypatch the private HTTP helper, e.g.
`tests/promo/test_qr_continuation_api.py:254-258` and
`tests/inventory/test_processing_health_ui.py:20-30`.

## Expected blast radius

### Production

- **Must touch:** the backend lifecycle/composition root, one shared database
  binding or session-factory helper, and all five HTTP adapter modules.
- **Likely change shape:** replace 25 helper calls with a factory obtained from
  backend app state; create one Engine during backend startup and dispose it at
  shutdown. Each request still gets its own short-lived `Session`.
- **Should not touch:** migrations/models, public API payloads/statuses,
  Caddy, client code, worker runtime, or realtime behavior.
- **Important coupling:** `bind_server_events` in `common.py` is shared by
  backend and realtime and currently owns another Engine. Reusing that exact
  Engine would widen the change into realtime lifecycle/tests. The KISS scope
  should first share the Engine for backend HTTP sessions and leave the
  diagnostics emitter's independent writer binding intact, unless a strict
  one-Engine-per-process requirement is explicitly chosen.

### Tests and verification

The test impact is larger than the production diff. Backend tests currently
bypass lifespan, so they must either enter the app lifespan or explicitly
install/dispose the test session factory. Private-helper monkeypatches must be
rewired. Expect roughly **10–18 backend integration/support files** to be
reviewed, with fewer actually needing edits; the exact number depends on
whether a shared test helper is introduced. No new product test suite is
needed, but the final pass must prove startup binding, request-level Session
cleanup, pool reuse, and shutdown disposal.

## Volume estimate

- Production plumbing: approximately **6–8 files and 150–300 changed lines**
  (mostly wiring, imports, and call-site substitutions).
- Test adaptation and lifecycle proof: approximately **10–18 files and
  100–250 changed lines**, unless the existing request harness is centralized.
- No schema migration or data backfill.

This is a medium implementation effort with a high regression surface: a
mistake in the shared factory can break every authenticated, inventory,
serving-control, diagnostics, and Promo endpoint at once. The change remains
bounded if it is kept to backend lifecycle plumbing and does not introduce a
DI framework, hidden global cache, new pool variants, or transaction changes.

## Smallest safe remediation

Follow the existing `realtime`/`model_consumers` precedent: a backend-lifecycle
Engine and `Callable[[], Session]` factory, short sessions per request, and
explicit disposal at shutdown. Keep transaction ownership and `commit`/
`rollback` statements in the current handlers. Add one focused lifecycle/pool
probe, then run the existing backend integration tests in the final QA batch.

## Uncertainty

There is no production load or connection-budget measurement in the repository,
so the runtime gain is not quantified. The test-file range depends on whether
the current per-file ASGI request helpers are consolidated. The assessment
therefore supports fixing before deployment/long-running pilot load, but does
not claim that this finding blocks current feature implementation.
