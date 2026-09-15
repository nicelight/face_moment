---
description: Motion Atlas presentation ownership, local review routes and public selfie implementation limits.
status: active
last_updated: 2026-09-13
---
# Motion Atlas presentation

## Search animation identity

The signal animation displays the server-generated `Attempt ID` above its
phase caption after the realtime response supplies `X-Face-Moment-Attempt-Id`.
Before that response the identity line is hidden. The client correlation UUID
is not displayed. A new capture clears the label and stale responses cannot
replace it. Owners: `client/app.js`, `client/signal-progress.js`,
`client/signal-progress.css` and `entrypoints/realtime.py`.
Existing loaded pages require a reload; server header delivery requires the
updated realtime process.

Capture completion retains the request-to-capture identity binding until the
JPEG settings snapshot is released. A successful Promo or render failure can
complete by request UUID; pre-request failure completes by capture ID. Late
completion from a previous request cannot finish the new capture. Regression:
`tests/client/test_capture_completion_identity.mjs` exercises the actual app
handlers with the real JPEG quality controller and a subsequent search.

Implementation of the operator-approved [design brief](../../.design/motion-atlas-integration/DESIGN_BRIEF.md).
This document covers presentation only; public search, payment and backend
contracts are unchanged.

## Routes and ownership

- `/site`: public Fluid hero and camera preview/capture/retake. The portrait
  frame is the «Найти меня» entry to the selfie section. No public search,
  payment, gallery upload or OAuth is implemented; the photo stays in-browser.
- `/staff`, `/staff/login`: role-scoped actions, shared typography/navigation,
  accessible focus and local table scrolling. The horizontal navigation wraps;
  the account dropdown closes on Escape or outside click. Photographer names
  are regular; operator/developer names are bold white with a static glow.
- `/` and `/display`: existing kiosk. `/phone`: existing QR continuation.
- `/staff/attempts`: «Анализ Захватов» in navigation, dashboard cards and the
  page title, using the operator-selected capture terminology.
- Attempt detail: «Диагностика распознаний захвата(JSON)» has a «Копировать»
  button that copies the complete displayed JSON through `staff-ui.js`.
- Library uses one venue list with Media and per-venue statistics buttons.
  Statistics appear after selection, with an 18px venue heading (list: 14px),
  and refresh every five seconds for that venue only. Stale responses are ignored.

[staff_presentation.py](../../src/face_moment/platform/staff_presentation.py)
owns shared HTML decoration. `motion-theme.css`/`motion-ui.js` own reusable
visuals; `staff-ui.js` owns identity/navigation/logout; `site-selfie.js` owns
camera resources and clears streams when the document is hidden.

## Fluid reference fidelity

Preserve the requested Atlas Fluid reference: repeated off-center radial
gradients, 65% background size, original layer inset, 70 px drift and ±15°
rotation. Rectangular tile edges are intentional; do not replace them with
centered spots or add a dark hero overlay. This applies to public and staff.

`/site` has a collapsible «Настроить Fluid» panel for spot size, drift, speed,
rotation and edge blur. Changes are public-page local until reload; reset restores
the preset, zero speed pauses, and reduced-motion is respected. `fluid-controls.js`
owns the panel.

The «Найти меня» hit area zooms Fluid for 4 seconds on mouse hover/focus.
CSS scales existing layers by `150 / selected spot size`; touch hover and the
transition are disabled for reduced motion. The link remains clickable.

## Activity and result presentation

Venue parameters (name, camera search dates and detector thresholds) live in a
collapsed «Настройки площадки» disclosure. Detector hints use native `title`
tooltips only; hovering does not insert explanatory text into the layout.

Capture configuration fetch failures report a server connection/access problem
and finish with `configuration_failure`, without emitting a detector failure.
Successful configuration loading clears that status; successful face detection
clears the persistent detector warning, including its existing DOM notice.
Regression: `tests/client/test_capture_configuration_failure.mjs`.

Upload perspective covers all concurrent requests, including failures; face
processing continues and the form remains usable. Empty dates default to the
local browser date. The field and result rows use `DD.MM.YYYY`, while the API
receives validated ISO dates.

[signal-progress.js](../../client/signal-progress.js) observes existing
capture/detection/request/preview boundaries. Its strokes are phase targets, not
server progress. Stale events cannot affect a newer overlay; errors clear it;
only decoded results reach the final target.

The [paper Promo presentation](promo-presentation.md) stays intact. Result/QR
insertion is above the signal layer and ACK is not delayed by its cosmetic
timer. No extra media request is added; reduced motion disables decoration.

## Local review and evidence

Use `https://localhost:8443/site` and `/staff` on the
[local testing stand](local-development.md#persistent-local-testing-stand--2026-09-08).
The source overlay mounts current `src` and `client`:

```bash
docker compose --env-file .env.testing -f compose.yaml -f .protocols/local-testing/compose-source.yaml up -d --no-deps backend
```

Restart after Python changes. Validation: mypy (95 files), 52 client tests,
7 page tests and 10 session/settings tests passed. See [checks](../../.protocols/motion-atlas-qa/implementation-checks.md)
and [browser review](../../.protocols/motion-atlas-qa/REVIEW.md). Camera success,
full camera→search→Promo→phone flow and measured performance remain unverified.
