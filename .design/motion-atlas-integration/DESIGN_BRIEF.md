# Face Moment — Motion Atlas integration

Status: visual implementation authorized by the operator on 2026-09-08
(«вопросы остались? Если нет, приступай к реализации»). The following draft
preserves design discussion provenance; the implementation decisions below
supersede its pending-placement and first-slice wording.

## Implemented scope — 2026-09-08

- Public `/site` and staff `/staff` homepages have Fluid heroes below the menu.
  `/` remains the existing Chromium entry; `/display` is its alias.
- Shared staff presentation, role-filtered menu, Aurora login, upload perspective,
  rolling counts, display-card tilt and touch rings are implemented. Existing
  server authorization and form/API contracts retain ownership.
- Global ambient motion follows 0.4× and the chosen local speeds. Upload
  perspective uses an actual 700 ms transition, 20 px corners and stays changed
  until all concurrent file requests settle. This is the implementation choice
  under the general go-ahead, not a separately confirmed timing exception.
- The kiosk signal uses seven smooth routes and two synchronized outer progress
  strokes at real local phase boundaries (0/25/45/80/100). No numeric percent,
  backend progress polling or cosmetic request/acknowledgement delay is added.
- Paper Promo cards and the stationary QR remain; only a 450 ms background
  handoff is added. Phone continuation receives the common palette and count.
- Public camera preview, capture and retake UI are implemented without login.
  The public search/payment backend does not exist in the accepted current
  runtime. `/site` therefore clearly states prelaunch status and makes no upload
  request; it is not a completed visitor search/payment feature. Gallery upload
  and Google OAuth remain deferred as explicitly requested.
- Browser QA confirms role login, responsive pages and mobile navigation.
  Camera success is unverified in the automated environment. Evidence and
  remaining verification limits live in `.protocols/motion-atlas-qa/REVIEW.md`.

See [implementation guide](../../.memory-bank/guides/motion-presentation.md)
for code ownership and local review access.

## Problem

Staff pages are separate, mostly unstyled server-rendered forms and tables.
The display shell and phone page share a blue dark theme; the accepted Promo
presentation uses cream photo cards on warm graphite. A coherent visual language
should make daily work readable while giving the visitor-facing experience a
recognizable atmosphere.

## Authoritative operator preferences

Reference: `/home/serg/Projects/space-drift-duel/motion-atlas/`.

| Setting / effect | Requested values |
| --- | --- |
| Global | speed 0.4×; hue 170°; ambient 37%; cursor light 2% |
| Holographic card (`tilt`) | tilt 18°; shine 14% |
| Touch rings (`ripple`) | radius 80 px; lifetime 0.7 s; speed 1.15× |
| Different perspective (`transition`) | duration 700 ms; radius 20 px |
| Mechanical counter (`odometer`) | selected; no custom parameters supplied |
| Fluid (`mesh`) | spots 65%; drift 70 px; speed 1.4× |
| Aurora (`aurora`) | amplitude 56 px; light 63%; speed 2× |
| Signal flow (`circuit`) | packet 14%; channels 7; speed 1×; smoothly rounded routes |

Reference mechanics checked in `assets/effects.js`, `assets/app.js`, and
`assets/style.css`. Global speed multiplies local speed. Literal transfer gives
0.46× rings (~1.52 s per ring before stagger), 0.56× Fluid, 0.8× Aurora,
0.4× signal flow, and a 1.75 s state transition at the default local 1×.
Fluid's 65% parameter controls background sizing, not opacity. Hue controls the
accent and related colors; several reference gradients contain fixed colors.

## Proposed experience principles

1. One prominent ambient effect per view; controls and dense text stay legible.
2. Counters and activity illustrations reflect actual available data.
3. Photos retain their natural colors; QR remains stationary with a white quiet zone.

## Proposed placement

| Surface | Composition and selected effects |
| --- | --- |
| `/staff/login` | Focused, stable login form; Aurora in a separate background/side panel; rings on the submit action. |
| `/staff/photo-upload` | Clear SPA/date/file controls; Different perspective switches once at batch upload start, holds the changed composition during upload, and returns once every file upload has settled. Processing after admission is separate. Real accepted/failed counters. |
| `/staff/processing-health` | Prominent real queue counters and explicit states; the primary signal-flow placement is now the Chromium client processing screen. |
| `/staff/photo-inventory` | Existing recent statistics become readable counter cards; stable operational controls; no animated destructive-action treatment. No new gallery assumed. |
| `/staff/display-clients` | Compact kiosk identity cards may use holographic tilt; token/copy controls remain outside the moving surface. Current active flag must not be presented as live connectivity. |
| `/staff/search-settings` and `/#configuration` | Stable form panels, rings on primary actions, explicit save feedback. Different perspective is reserved for exceptional sustained states. |
| `/staff/attempts`, details, events, calibration, annotations | Shared typography, navigation and panels. Dense evidence and forms remain stable; no routine Different perspective transitions. |
| Public website homepage (route pending) | Operator requests Fluid hero immediately below the menu. This is distinct from the Chromium client: visitors take and submit a selfie without registration/login to find relevant photographs and obtain the matching set after payment. Gallery upload requires Google OAuth first; both gallery upload and Google OAuth are explicitly deferred. |
| Admin homepage (route pending) | Operator also requests Fluid hero immediately below the menu. Proposed content: concise role-appropriate summary and quick actions into existing staff pages; show only metrics available from existing authorized APIs. |
| Chromium client, after capture until Promo ready | Operator requests full-screen signal flow with seven smooth channels, two outer progress strokes and subtle bottom-aligned phase text. Flow fades out while photo cards fade in. |
| Promo result | Proposal: retain accepted cream paper cards, natural photos and stationary QR; consider Aurora only at the background edges. Needs explicit scope decision. |
| `/phone` | Proposal: quiet shared palette, real found-photo counter, rings on the primary action; preserve the current single teaser/continuation behavior. |

## Existing patterns and implementation fit

- Client/phone: native HTML, CSS, ES modules; system sans-serif.
- Staff: HTML produced by Python route handlers; no shared stylesheet currently
  linked by the inspected staff templates.
- Reference: dependency-free CSS/SVG/JavaScript. Reuse selected mechanics and a
  shared local stylesheet/module; no framework migration is required by this design.
- Preserve existing form IDs, field names, routes, role checks and data contracts.
- Introduce a common staff layout and role-appropriate navigation as the base;
  on narrow screens navigation wraps or collapses and tables scroll locally.

## Interaction and accessibility

### Operator refinement: upload perspective

Different perspective is a held composition change, not a repeating animation
or routine page transition. Enter at photo batch upload start; return when all
upload requests settle, including individual failures. Preserve failed rows and
retry affordances. Do not wait for background face processing. Existing
`Promise.all` over `uploadFile` supplies the batch boundary; implementation must
avoid restoring idle while any concurrently accepted batch remains in flight.

### Operator refinement: full-screen signal progress

Start when the captured reference series is available, before local face
detection. Keep the selected packet/channel/speed values and use smooth curves
for both the muted guides and their moving packets. The topmost and bottommost
channels additionally fill together from 0 to 100%; they are two views of the
same approximate progress, not separate measurements.

Proposed KISS phase targets (not measured workload percentages):

| Real client boundary | Exact operator copy | Target |
| --- | --- | --- |
| Reference series ready, local detection begins | определение области лиц | 0% |
| Detection complete, crop/encoding begins | обрезка лиц для поиска фоток | 25% |
| Multipart ready, request dispatched | поиск ваших фотографий | 45% |
| Result accepted, teaser download/decode begins | получение ваших фотографий | 80% |
| All teaser images decoded and result ready for insertion | Same final label until exit | 100% |

Use CSS interpolation of the two stroke fills, approximately 400 ms, with no
fake backend stages, polling, elapsed-time estimator, or displayed percentage.
The actual server search progress is unavailable; hold the current target
while waiting. Fast stages may be skipped visually; do not delay the operation
to display each label. The four labels are small, low-emphasis text near the
bottom with a safe inset, never over photos.

Proposed reveal: one signal scene and the existing result component, with a
short opacity handoff (~450 ms) once previews have decoded. Reuse the existing
photo-card appearance animation. Do not gate acknowledgement on a cosmetic
timer or confirm a QR while an opaque loading layer obscures it. Avoid whole-page
View Transitions and any extra media fetch to implement this handoff.

No match, network failure, timeout, cancellation and stale attempts must follow
the existing outcome flow and clear the loading presentation. Do not show 100%
or the final receiving-photos label on an unsuccessful outcome.

Proposal: retain 0.4× for ambient motion but make the state transition actually
700 ms and keep immediate button feedback. This would differ from literal Atlas
speed multiplication and requires operator confirmation. Visual animation must
not delay request dispatch, save confirmation or control availability.

On touch screens omit cursor glow and hover tilt; use touch rings. Preserve
keyboard focus and feedback without pointer input. Respect reduced motion,
pause offscreen/background effects, and avoid competing ambient animations
during camera capture/inference. Actual performance must be measured during
implementation; the reference's cost labels are not a Face Moment benchmark.

## Decisions pending

1. Scope: staff + waiting screen with paper Promo retained; full Atlas including
   Promo/phone; or staff only.
2. Literal global timing multiplication versus the proposed faster UI feedback.
3. Public self-photo search and post-payment delivery are operator product
   intent; this design draft does not establish that those capabilities already
   exist or silently change the accepted backend contracts. The entry choice is
   settled: camera selfie without account/login now; gallery upload only after
   Google OAuth later. This access condition is specific to public visitor
   self-photo upload, not the existing staff photographer upload flow.
4. Routes for the distinct public homepage, admin homepage and Chromium client;
   preserve the currently working client entry until routing is explicitly designed.

Confirmed homepage scope: Fluid hero below the menu belongs on both the public
website homepage and the admin homepage. The public homepage is not the current
Chromium kiosk shell. Public hero invites the visitor into photo discovery;
admin hero provides a concise work entry. Keep dense administrative content
below the hero on stable surfaces. Do not expose developer-only actions to other
staff roles through the new homepage.

Confirmed public entry: prioritize a single “Сделать селфи” action in the Fluid
hero, followed by browser camera permission, capture and submission. Do not
insert a registration or sign-in screen into this path. Proposed UI keeps the
deferred gallery and Google sign-in controls absent until their implementation;
do not substitute gallery upload when camera access fails. The exact capture/
retake/send interaction is still a design detail, not an approved automatic
submission requirement.

## Proposed first reviewable slice

Login and photo upload: one atmospheric entry view and one practical work page.
After these establish the visual direction, extend the shared layout to the
remaining pages. This is a proposal, not implementation authorization beyond
the current design discussion.

## Out of scope for this draft

New backend metrics, measured server-progress claims, implicit backend contract
changes, a new photo gallery, modified roles, QR behavior changes, and production
deployment. Public visitor gallery upload and Google OAuth are explicitly
deferred by the operator.
