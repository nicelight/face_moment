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
visible card/text/QR bounds, stationary QR and reduced motion. Synthetic
fixtures establish layout only; physical scan distance needs on-site checking.

Sources: [PRD](../prd.md), [FT-005](../features/FT-005.md),
[display contract](../contracts/promo-display-api.md).
