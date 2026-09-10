---
description: Operator-approved adaptive Promo card presentation and verification.
status: active
---
# Promo presentation

Accepted by the operator on 2026-09-07. This supersedes the six equal cells,
animated cursor and growing/breathing QR presentation in IDEA_APP.md.

Four cream paper cards use wide lower margins, soft shadows and small distinct
tilts on a warm graphite background, inspired by frontend/past_forward_example.
Images retain their entire frame with object-fit: contain; no color filters.
Operator update, 2026-09-10: enlarge the paper cards to 125% of their grid
cells, producing roughly 20% overlap relative to card size. Small outer-screen
bleed and occlusion by neighboring cards are intentional; contain still avoids
cropping inside each image element. Reduce paper margins and outer whitespace.
Text and QR remain fully visible above the collage. The QR fills the largest
square within its remaining allocated slot, preserving its white quiet zone.
Cards appear with a short stagger and gently drift. Reduced motion disables
animation. QR is fully sized from insertion and remains stationary with its
existing white quiet zone. Existing result validation, acknowledgement,
expiry, media authorization and phone continuation remain unchanged.

Copy: «Ваши фото можно скачать по QR коду или на сайте face-momet.ru».
This operator-supplied wording replaces the previous copy requirement; it does
not implement downloading or change the issued QR destination.

Wide viewports show a 2x2 photo area and a right-hand text/QR column.
Square/moderately portrait viewports place text and QR below the cards;
tall portrait viewports stack text and QR. Dimensions use viewport width AND
height; there is no physical diagonal requirement or fixed 16:9 canvas.

Implementation: client/styles.css and client/promo-display.js.
Browser regression: tests/client/test_promo_layout.spec.mjs covers 1920x1080,
1280x1024, 1080x1080, 1080x1920, 2560x1080 and 390x844, image containment,
card enlargement/overlap, visible text/QR bounds, maximum QR slot sizing,
stationary QR and reduced motion. Synthetic
fixtures establish layout only; physical scan distance needs on-site checking.

2026-09-10 follow-up QA: the full browser suite passed 17/17. After correcting
the wide-screen text clearance, all six layout cases and an additional
1450x833 check passed. The served `/client/styles.css` matches the working
file. Existing open tabs need a reload to receive the updated presentation.

Sources: [PRD](../prd.md), [FT-005](../features/FT-005.md),
[display contract](../contracts/promo-display-api.md).

## Local composition editor

Operator request, 2026-09-10: Configuration → «Поправить расположение фоток»
opens a full-screen composition editor with four numbered sample cards, the
approved copy and a sample QR. Drag any of the six objects to move it; the
corner handle resizes and the upper handle rotates it. The object selector
also selects overlapped cards. Expand «Размер и поворот выбранного объекта»
for width, height and rotation sliders, including when handles lie beyond
the screen edge. Text uses small/medium/huge presets (0.75×, 1×,
1.4×); its box is independently movable, resizable and rotatable. QR resizing
preserves a square and the existing white quiet zone.

«Сохранить дизайн» at bottom right persists geometry and text scale in this
browser's localStorage, then returns to Configuration. Cancel/Escape discards
the draft; a storage error keeps the editor open with an explanation. No image,
session media reference or QR ticket is stored. Sample QR is not a participant
session. Sensor triggers are ignored while editing.

Saved positions and dimensions are relative to the viewport and apply to
subsequent real Promo results through the same card renderer. Custom layouts
disable card drift so authored positions remain stable. Without a saved valid
layout, the existing responsive collage remains the default. Tune the design
on the target screen; a custom composition is not a separate layout per aspect
ratio. Storage belongs to the current origin/browser profile, not the server.

Ownership: `client/promo-layout-editor.js` (interactions),
`client/promo-layout.js` (safe local geometry and application),
`client/promo-display.js` (shared card rendering), `client/styles.css` (visuals).

Validation: 55 client unit checks passed. The existing 17 browser tests
and the new `tests/client/test_promo_editor.spec.mjs` passed. Isolated browser
QA exercised move/resize/rotate for all six objects, text presets, offscreen
card adjustment through sliders, save/reload/cancel, denied storage and saved
layout application by the real PromoDisplayController. Controls were inspected
at 1450x833 and 390x844 with synthetic images and mocked camera/detector;
no real Attempt or physical camera was used for editor QA.

## Replay and display seconds

Operator addition, 2026-09-10: Advertising provides «Фотки вновь», a transparent
button fixed at the bottom right, available after a successful display.
It reloads the same four authorized
previews and QR, applies the current saved design and returns to advertising
after a full display interval. Replay does not create a new Attempt, repeat the
original display acknowledgement or restart capture cooldown. New sensor
triggers are ignored while replay is loading or visible. A failed media reload
returns to advertising with a message and leaves retry available.

Configuration exposes «Время показа фотографий, секунд». The positive whole
number is saved in this browser and applies to the next original or repeated
display. Without a valid local preference, the server's configured duration
is used. Server display-confirmation deadlines, success cooldown and QR
validity remain independent; replay does not renew the QR. An already expired
QR has an explicit notice on the replayed screen.

Only the latest successful result's references are retained in page memory;
they disappear on reload, and no photo or ticket is written to browser storage.
The duration preference survives reload. Ownership: `promo-display.js`
(replay/lifetime), `promo-display-preferences.js` (local seconds), `app.js`
(configuration and advertising controls).

Configuration keeps the central screen token and passage-sensor panels inside
the initially collapsed «доп настройки» disclosure. Routine camera, display
duration and layout controls remain directly accessible.

Validation: 57 client unit checks and all 19 browser tests passed. The new
`tests/client/test_promo_replay.spec.mjs` exercises the actual app's initial
disabled button, seconds save/reload, original render/ACK, repeated timed
returns to advertising, same four media references/QR/design, no new search
or duplicate ACK, expired-QR notice and failed-media retry. Camera/detector
and server responses were isolated fixtures; no real Attempt was created.

Operator follow-up: the requested manual testing scenarios were reported
working, with camera auto-disconnection recovery as the sole stated exception.
That defect is deferred by the operator; see the
[camera investigation](local-development.md#usb-recovery-and-reload-diagnostics--2026-09-10).
