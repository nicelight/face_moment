# Technical-debt review — final wave W8 / FT-001

## Checked scope

Final FT-001 change surface only: TASK-016 Attempt 3 correction of the public
Photo-upload edge bound and its execution/verification history; TASK-017
authenticated same-origin uploader page and its exact Caddy route. This review
does not widen to the repository outside those completed task surfaces.

## Evidence checked

- `PAPERCUTS/TECHDEBTS/wave-W7-tech-debt-2026-08-11.md`: the prior HIGH was
  the unbounded public multipart intake before authorization and the configured
  candidate cap.
- `deploy/Caddyfile:4-33,47-50`: the exact upload path rejects missing length
  and only evaluates the numeric over-cap expression after a non-empty length;
  it also has the finite `11MiB` proxy body bound. The authenticated uploader
  has one exact backend route and no direct internal-service route.
- `.tasks/TASK-016-T3-FT-001-W7/TASK-016-T3-FT-001-W7-S-EXECUTE-final-report-code-03.md`,
  `TASK-016-T3-FT-001-W7-S-VERIFY-final-report-docs-03.md`,
  `TASK-016-T3-FT-001-W7-S-RED-VERIFY-final-report-docs-02.md` and
  `red_verify_attempt3_edge_probe-output.txt`: current packaged evidence shows
  the old absent-length failure is gone, all previously affected routes remain
  routable, unsafe upload framings are rejected before backend receipt, and an
  exact 10 MiB multipart candidate reaches the backend.
- `src/face_moment/inventory/http.py:37-51,203-330` and
  `.tasks/TASK-017-T2-FT-001-W8/TASK-017-T2-FT-001-W8-S-VERIFY-final-report-docs-01.md`:
  the page is session-protected, uses only same-origin inventory endpoints,
  allocates one persistent visible row per selected file, and maps the existing
  response contract without browser-side storage or admission ownership.
- `.tasks/TASK-017-T2-FT-001-W8/browser-verifier-transcript.md`: independent
  Playwright CLI verification proved real reordered completion, accepted,
  rejected, duplicate and mixed-EXIF outcomes, authoritative selected-date
  projection, redaction and cleanup.

## Prior W7 finding

Resolved. The guarded Caddy expression prevents the former `int("")` route
failure, while the pre-proxy responders and request-body limit bound the public
upload before FastAPI parses it. Final functional and adversarial verification
both passed the absent, malformed, oversized and lengthless framing probes
without regressing unrelated routes.

## Confirmed material findings

None.

The inspected evidence does not demonstrate a remaining debt mechanism with
material reliability, coupling, regression-risk or maintenance impact in this
final change surface.

## Assessment and uncertainty

This is advisory only. It does not alter task or feature lifecycle state. No
blocker to terminal scheduler completion is identified by this review.
