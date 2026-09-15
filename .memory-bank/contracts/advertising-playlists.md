---
description: Operator-approved KISS venue advertising administration, browser cache and display cycle.
status: active
last_updated: 2026-09-16
---
# Advertising playlists

## Scope and ownership

Operator requested direct implementation without full DevRails, extra agents,
codec validation or automatic tests. `promo` owns independent advertising
tables and `advertising/<spa-id>/<media-id>` objects in existing private MinIO.
No Photo, annotation, search or historical-data contract is changed.
Migration `0026_advertising_playlists` adds tables only.

## Administration

The staff entry is the «Реклама» button below «Скопировать токен» in every
«Экраны» card. It links to `/staff/advertising?spa_id=<screen's-spa-id>`;
the playlist remains shared by that venue's screens. No global advertising
navigation/dashboard entry is shown. The playlist back link returns to «Экраны».
`GET /staff/advertising` still supports venue selection for direct links.
Staff reads/writes require operator/developer; mutations also require existing
session-backed CSRF authentication.

- `GET/PUT /api/advertising/{spa_id}/playlist`: ordered IDs, common duration
  per image (default 5 seconds), crossfade (default 1; zero disables) and
  random-start flag. PUT saves order/settings together with the read revision;
  stale revision or changed membership returns 409. Image duration is positive,
  crossfade nonnegative; finite values at most one day.
- `POST /api/advertising/{spa_id}/media`: one multipart file and optional
  browser-reported video duration. JPEG/PNG/WebP/WebM selected by extension,
  no codec inspection/transcoding. Nonempty file up to 2 GiB minus one byte.
  Upload/delivery stream bytes; new assets append immediately.
- `DELETE /api/advertising/{spa_id}/media/{media_id}`: removes only that venue's
  advertising item and binary object immediately. Staff unsaved order/settings
  remain a local draft. Video preview is black/orange Play.
- `GET /api/advertising/media/{media_id}`: staff media including byte ranges
  for native video playback; standard 401/403/404/416 failures.

## Display cycle

`GET /api/promo/advertising/playlist` and `/api/promo/advertising/media/{media_id}`
use existing display Bearer authentication. Venue derives from the principal,
never display input; foreign-venue assets return 404.

Start from first/random index on first opening, after unsuccessful recognition
and after client-photo display (including replay); then play sequentially,
never shuffle. Images use common duration, videos run to `ended`.
Native `object-fit: cover` preserves ratio and crops. Crossfade animates incoming
opacity; outgoing video audio pauses before incoming playback. Advertising
stops at capture/search, personalized result or configuration navigation.
If Chrome blocks sound autoplay, retry muted; kiosk policy is a separate action.
Empty/all-failed playlists use existing background. Failed assets skip;
wholly failed lists retry after 30 seconds.

Operator update: after the configured client-photo display interval, the whole
Promo screen fades to black over 3 seconds. It remains display-visible during
this fade so sensor triggers cannot interrupt it. Once the first advertising
asset is ready, black fades away over 1 second. Empty/all-failed playlists reveal
the existing background instead. Replay uses the same transition; errors do not.
The extra presentation time does not alter server QR/session lifetimes or ACK.
New capture/result loading cancels the cosmetic handoff overlay.

## Cache and updates

Per-screen browser configuration also includes «Текст поверх рекламы» and
numeric caption size from 8 to 200 CSS pixels (default 32). Legacy
small/medium/large values map to their previous computed size on this viewport;
the next save persists pixels. `advertising-caption.js` stores this small
setting in localStorage; it does not change the venue playlist. A plain-text,
multiline white caption with a dark shadow appears at top left above images and
videos, stays still across advertising crossfades and hides whenever advertising
stops. Empty text hides it. Changes apply on returning from configuration.
The existing black Promo handoff covers both media and caption.

Poll every 30 seconds, compare venue/revision, apply latest list between assets.
Deleted current item finishes first; if its ID is absent, start the new list's
first item at that boundary. No sync service or cold-start offline guarantee.

Explicit Cache Storage stores media, not the roughly 5 MiB localStorage area.
Cache names use a SHA-256 credential fingerprint, never a raw token.
Warm sequentially; retry unavailable assets on later polls and prune obsolete
URLs in the current namespace. Temporary disconnect keeps in-memory playlist
and cached assets. Quota/permission failures warn and allow online playback;
uncached assets have no offline guarantee. Browser can evict ordinary cache.
Old credential namespaces are isolated and can be cleared through site storage.

## Code and verification

- [advertising.py](../../src/face_moment/promo/advertising.py): storage and projection.
- [advertising_http.py](../../src/face_moment/promo/advertising_http.py): access and delivery.
- [advertising-admin.js](../../client/advertising-admin.js): staff drafts/mutations.
- [advertising-player.js](../../client/advertising-player.js): cache, polling, playback.
- [app.js](../../client/app.js): existing display-cycle integration.

Automatic tests and codec validation were explicitly waived. Real media, access
boundaries, offline playback, sound and kiosk smoothness remain operator checks.

## Local application — 2026-09-16

Applied to the existing `.env.testing` stack with original volumes intact:
copied migration 0026 and current `migrations/env.py` into the source-mounted
backend, ran `face-moment-migrate`, restarted backend and reloaded Caddy.
Migration completed and backend reported application startup complete.
This is startup evidence only, not functional verification.

Open `https://localhost:8443/staff/advertising` and refresh existing display tabs.
Python/client source uses the existing read-only source mounts. Migration copies
inside this container are ephemeral; rebuilding the normal image includes the
committed-tree migration files. No remote deployment or commit was performed.
