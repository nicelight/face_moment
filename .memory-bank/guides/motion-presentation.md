---
description: Motion Atlas presentation ownership, local review routes and public selfie implementation limits.
status: active
last_updated: 2026-09-08
---
# Motion Atlas presentation

The operator authorized implementation of the visual direction and refined
upload/progress behavior in the [design brief](../../.design/motion-atlas-integration/DESIGN_BRIEF.md).
The goal is a coherent visitor and staff experience with atmospheric homepages
and stable operational controls. This presentation work does not close new
public search/payment requirements or change the accepted backend contracts.

## Routes and ownership

- `/site`: public homepage, Fluid hero, camera preview/capture/retake. The
  portrait frame is the clickable «Найти меня» entry to the selfie section on
  desktop and mobile; the former hero button and registration tagline were
  removed at the operator’s request. No login
  is required. Public search and payment are absent; the page says so and keeps
  the photo within the browser. Gallery upload and Google OAuth are deferred.
- `/staff`: authenticated homepage with actions for the current role. Existing
  capability handlers enforce authorization; navigation is presentation only.
- `/staff/login` and existing staff pages: shared typography, navigation,
  panels, accessible focus and local table scrolling.
- Authenticated staff navigation is a permanently visible horizontal top strip;
  links wrap on narrow screens. The username follows the links on the right and
  opens an account dropdown containing identity and logout. Escape and an
  outside click close this dropdown.
- Authenticated staff headers show the account name beside the closed menu.
  Photographers use regular text; operators (the administrative account) and
  developers use bold white text with a static radial white glow.
- `/` and `/display`: existing kiosk; the original entry remains available.
- `/phone`: existing QR continuation, with the shared palette and rolling count.

[staff_presentation.py](../../src/face_moment/platform/staff_presentation.py)
owns the shared server HTML decoration; capability handlers own their forms.
[motion-theme.css](../../client/motion-theme.css) and
[motion-ui.js](../../client/motion-ui.js) own the reusable visual primitives.
[staff-ui.js](../../client/staff-ui.js) owns identity, navigation visibility,
logout, token copy and counter enhancement.
[site-selfie.js](../../client/site-selfie.js) owns camera resources and clears
streams/previews when the document becomes hidden.

## Fluid reference fidelity

The operator explicitly requested the original Atlas Fluid appearance after
comparing screenshots. Preserve its repeated off-center radial gradients,
65% background size, original layer inset, 70 px drift and ±15° rotation.
The visible rectangular tile edges are part of the requested reference, not
a defect to smooth away. Do not replace them with centered non-repeating
spots or add a dark full-hero overlay. This applies to public and staff heroes.

Public `/site` includes a collapsible «Настроить Fluid» panel for live tuning
of spot size, drift, local speed, rotation and edge blur. Changes affect only
the public hero until reload; reset restores the reference preset. Zero speed
pauses at the current frame. System reduced-motion remains respected.
[fluid-controls.js](../../client/fluid-controls.js) owns this preview UI.

The «Найти меня» rectangular link hit area also triggers a 4-second Fluid zoom
on mouse hover or keyboard focus. CSS scales the existing painted layers by
`150 / selected spot size`, rather than animating gradient background-size.
This approximates 150% spot size while preserving the selected slider value;
leaving the link smoothly restores the original scale from its current position.
The link remains immediately clickable throughout the transition. It introduces no JS frame loop
or extra blur. Touch hover is disabled and reduced-motion removes the transition.
This is a rendering-cost choice, not a measured device-performance guarantee.

## Activity and result presentation

Upload perspective enters when file requests start and leaves after all
concurrent requests settle, including failures. Background face processing
continues independently. The form stays usable for additional files.
The upload date defaults to today's local browser date when the field is empty;
the photographer can change it before uploading.
The date field and upload result rows use explicit `DD.MM.YYYY` formatting.
The editable text field validates calendar dates and converts them to ISO for
the existing upload API, independently of the browser's date-control locale.

[signal-progress.js](../../client/signal-progress.js) observes existing local
capture/detection/request/preview boundaries from the kiosk composition. Its
outer strokes show approximate phase targets, not measured server progress.
Stale attempt events cannot advance or cancel a newer overlay. Errors clear
it; only decoded successful results reach the final target.

The existing [paper Promo presentation](promo-presentation.md) stays intact.
Result/QR insertion occurs above the fading signal layer; acknowledgement is
not delayed by its 450 ms cosmetic timer. No extra media request is added.
Reduced motion disables decorative motion; background/offscreen ambient
animations pause. Device performance has not been benchmarked by this change.

## Local review and evidence

Use `https://localhost:8443/site` and `https://localhost:8443/staff` on the
[local testing stand](local-development.md#persistent-local-testing-stand--2026-09-08).
Its ignored source overlay mounts current `src` and `client` into the backend:

```bash
docker compose --env-file .env.testing -f compose.yaml -f .protocols/local-testing/compose-source.yaml up -d --no-deps backend
```

Restart that backend after Python changes. Static assets are read from the
mount; the image itself has not been rebuilt for this visual iteration.

Validation: mypy passed for 95 source files; 52 client unit tests, 7 page tests
and 10 database-backed session/settings tests passed.
[Check record](../../.protocols/motion-atlas-qa/implementation-checks.md).
Browser evidence: [review](../../.protocols/motion-atlas-qa/REVIEW.md).
Role login, desktop/mobile layouts and menu were checked. Automated camera
success remains unverified. Real camera/sensor → search → Promo → phone and
measured performance remain outside this presentation verification.
