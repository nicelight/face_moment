# Technical-debt review — wave W7

## Checked scope

`TASK-016-T3-FT-001-W7` only: the secured inventory Photo-upload HTTP
boundary, staff-session/CSRF access, configured principal-plus-IP limiter,
multipart dependency and task-owned verification evidence. This review does
not cover the repository outside that completed Wave W7 change surface.

## Evidence checked

- `.memory-bank/tasks/TASK-016-T3-FT-001-W7.task.json`: completed T3 scope,
  exact multipart, authenticated rate-limit, private-topology and standard
  failure constraints.
- `.tasks/TASK-016-T3-FT-001-W7/TASK-016-T3-FT-001-W7-S-EXECUTE-final-report-code-01.md`,
  `TASK-016-T3-FT-001-W7-S-VERIFY-final-report-docs-01.md` and
  `TASK-016-T3-FT-001-W7-S-RED-VERIFY-final-report-docs-01.md`: independent
  packaged functional PASS and semantic-pass evidence, including the
  response/auth/rate/redaction/topology matrix and isolated cleanup.
- `src/face_moment/inventory/http.py:51-59,128-161`: the route calls
  `_photo_upload_form()` before session/CSRF authentication; that helper calls
  `await request.form()` and then `await raw_photo.read()` before the later
  configured candidate validation.
- `src/face_moment/inventory/photo_upload.py:83-118` and
  `src/face_moment/infrastructure/settings.py:42-53`: authentication and the
  `PHOTO_UPLOAD_MAX_COMPRESSED_BYTES` check happen only after the complete
  multipart file has been read into `photo_bytes`.
- `deploy/Caddyfile:10-14,26-30`: the public inventory route has no
  `request_body` bound, whereas the separate realtime route explicitly uses
  `max_size 20MiB`.
- the packaged `starlette.formparsers.MultiPartParser` used by the current
  backend image: it spools file parts after 1 MiB but applies its
  `max_part_size` check only to non-file fields; it exposes no file-byte limit
  to this route's `request.form()` call.

## Confirmed material findings

### HIGH — unbounded public multipart intake precedes both authorization and the configured upload cap

An unauthenticated caller can send an arbitrarily large file part to
`POST /api/inventory/photos`. The application first parses and spools the full
file, then reads it fully into process memory, and only afterwards performs
the missing-session (`401`) branch or candidate-size (`413`) validation. Since
the public Caddy inventory route has no body-size bound, the configured
10 MiB candidate limit does not bound temporary-disk or process-memory use.
This makes the public upload boundary susceptible to resource exhaustion and
turns the accepted size configuration into a post-allocation check.

Smallest remediation direction: impose a finite body bound at the public
inventory edge that accommodates multipart overhead and is aligned with the
configured candidate cap, so oversized traffic is rejected before FastAPI
parses or reads it. Preserve the existing application-level JPEG validation
for the exact candidate contract.

## Assessment and uncertainty

The completed task otherwise stays within the accepted KISS single-backend
shape: Caddy overwrites the forwarded client IP, the limiter is deliberately
in-process, and execute/verify/red-verify evidence confirms authentication,
authorization, standard failures, redaction, private topology and cleanup.
No additional material debt was admitted.

This is an advisory finding only. It neither changes the task's completed
state nor questions the recorded functional or semantic verification verdicts.
