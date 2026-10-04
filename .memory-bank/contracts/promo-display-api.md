---
description: Exact authenticated Promo display configuration, teaser-media and post-render acknowledgement API contract.
status: active
last_updated: 2026-09-16
source_of_truth:
  - .memory-bank/contracts/promo-display-api.md
---
# Promo Display API

## Scope And Ownership

This contract specializes the central-origin `SpaPromoClient -> backend`
display boundary after a successful
[Realtime Attempt API](realtime-attempt-api.md) result. `promo` owns display
configuration projection, authorized teaser delivery, acknowledgement
orchestration and core Attempt display state. `inventory` and `processing`
supply only their accepted Photo/preview projections. HTTP handlers,
infrastructure, generic helpers and the composition root MUST NOT own this
flow or write capability state directly.

Every endpoint below reuses the active central display-client Bearer principal
from [Display Client Access](../domains/display-client-access.md). The server
derives authoritative `spa_id` from the stored token hash; a session or media
reference from another СПА is not disclosed.

## Display Configuration

- Identity headers: `X-Face-Moment-Display-Client-Id` (authenticated caller's
  UUID), `X-Face-Moment-Display-Name` (UTF-8 percent-encoded owner-stored name).
  Configuration displays the name and last five ID characters.
- Method and path: `GET /api/promo/display/config`.
- Authentication: `Authorization: Bearer <spa-client-token>`.
- Success: `200 application/json` with exactly:

  ```json
  {
    "schema_version": 1,
    "result_display_ms": 15000,
    "success_cooldown_ms": 30000,
    "capture_detector_threshold": 0.5
  }
  ```

Both durations MUST be positive integers and come from two independent
deployment settings. The values above are examples, not product defaults. A
missing or invalid value returns `503`; it MUST NOT silently reuse the other
duration or create a settings framework. The same `result_display_ms` value is
used when `promo` fixes
`display_expires_at = qr_issued_at + result_display_ms` for a newly issued
result.

Operator addition, 2026-09-14: `capture_detector_threshold` comes from the
authenticated display token's площадка and is a finite number in `(0, 1]`.
It controls browser BlazeFace only. The browser obtains this configuration
before series detection and updates its already loaded detector; the same
configuration is reused for Promo rendering. The existing five-second config
deadline remains in force. A client accepts the old three-field response with
the historical `0.5` capture default during a rollout; new responses always
include the venue value. Refresh already loaded kiosk pages after deploying
the client change.

Operator addition, 2026-09-10: the kiosk may override its **local visible
duration** with a positive whole-second preference from Configuration. The
response above remains the fallback and the server-owned initial display
acknowledgement window; its schema and persisted deadline are unchanged.
Explicit replay reloads the latest successful result's authorized previews
without sending another display acknowledgement or extending the QR lifetime.
See [kiosk operation](../runbooks/app_guide_ru.md#киоск-promo-и-qr).

## Teaser Media

Each `media_url` in Realtime Attempt API Response Version 1 resolves through:

- method and path:
  `GET /api/promo/sessions/{session_id}/media/{photo_id}`;
- authentication: the same display-client Bearer principal;
- success: `200 image/jpeg` containing the low-quality no-watermark preview
  for exactly one of that session's four teaser Photos;
- response headers: `Cache-Control: no-store`.

Both path values are UUIDs already present in the authenticated realtime
result. The server MUST load the session by primary key, require its `spa_id`
to equal the display principal's СПА, and require `photo_id` among that
session's four teaser IDs. It MUST NOT scan historical sessions, sign the IDs,
expose a raw MinIO key or produce a participant-facing presigned URL. Unknown,
unavailable, hard-purged, non-teaser or foreign-СПА combinations return `404`
without replacement selection or session/`N` mutation. The display treats any
missing or undecodable teaser as render failure and never presents a partial
Promo.

The preview revision is the immutable `pipeline_revision_id` of the issuing
Promo Attempt, reached through the session's `attempt_id`. It is not the
Photo's admission revision or today's serving revision. This preserves the
issued result after Photo reprocessing or a later serving switch. Missing
issuing Attempt/revision content remains unavailable without fallback.

## Display Acknowledgement

- Method and path:
  `PUT /api/promo/sessions/{session_id}/display`.
- Authentication: the same display-client Bearer principal.
- Content type: `application/json`.
- A confirmed request contains exactly:

  ```json
  {
    "schema_version": 1,
    "status": "confirmed",
    "qr_fully_visible_elapsed_ms": 8421
  }
  ```

- A render-failure request contains exactly:

  ```json
  {
    "schema_version": 1,
    "status": "failed"
  }
  ```

`schema_version` MUST be integer `1`. `status` MUST be `confirmed` or
`failed`. `qr_fully_visible_elapsed_ms` is required only for `confirmed`, MUST
be a non-negative integer monotonic offset from that Attempt's
`reference_series_ready` zero and MUST be absent for `failed`. Unknown fields
or invalid relationships return `422`.

The client sends `confirmed` only after all four teaser JPEGs have decoded and
the locally generated QR is fully visible. The first accepted report before
`display_expires_at` atomically records the terminal stored display status,
server receipt time and, for `confirmed`, the client monotonic elapsed value.
Repeating the same terminal status is idempotent and returns the originally
stored result without changing its elapsed value or timestamps. A conflicting
terminal status or any first report after the pending window has derived
terminal `unconfirmed` returns `409` and changes nothing. A late report never
reopens `unconfirmed`.

A successful response is `200 application/json` with exactly
`schema_version`, `session_id`, `status`, `display_expires_at` and, only for
`confirmed`, the persisted `qr_fully_visible_elapsed_ms`. The acknowledgement
does not change the Promo session, QR ticket, `qr_issued_at`, first-open expiry,
teaser IDs, union or `N`.

## Optional Second Slide

Решение оператора, 2026-10-04: локальная «Конфигурация» сохраняет toggle второго
слайда и его положительную длительность в целых секундах. Без включения показ
прежний. Первый слайд сохраняет четыре teaser, текст, QR, timing и ACK.
Включённый второй слайд — полноэкранная сетка без QR и текста, 4 колонки × 3 строки: те же четыре Photos плюс до
восьми дополнительных уникальных Photos; FIRST → SECOND использует только
opacity crossfade 2 секунды. Handoff в рекламу остаётся прежним. Click/replay
из рекламы при включении открывает второй слайд последнего успешного результата;
иначе действует прежний replay. Нового поиска/session/ACK и продления QR нет.

`promo` сразу при исходной сборке выбирает все до 12 Photos: неизменные первые
четыре teaser, затем до восьми разнообразных union members без повторов.
Существующий pHash farthest-first продолжает выбор относительно первых четырёх,
с исходными similarity/`photo_id` tie-breaks. Нехватку дополняют доступные общие
`no_faces` той же площадки за любые даты, затем пустые ячейки. Commons не входят
в union/`N` и не помогают достичь обязательных четырёх личных teaser.
В исходный realtime result добавляется `gallery_photos`: упорядоченный массив
до 12 `{photo_id, kind, media_url}`, `kind` = `matched|common`; первые четыре
совпадают с `teasers`. Список фиксируется с session для exact terminal repeat
и replay; union остаётся существующей полной `session_result_photo_ids`.
Нового поиска, manifest endpoint, job или polling нет. Клиент загружает
дополнительные изображения после полного первого render; они не задерживают
первый QR/ACK. Старый клиент игнорирует additive field, новый допускает его
отсутствие у старого backend и использует прежний четырёхфотографический показ.

Новый media path: `GET /api/promo/sessions/{session_id}/gallery/media/{photo_id}`
→ `200 image/jpeg`, `Cache-Control: no-store`. Display Bearer, primary-key
session lookup, равенство СПА и membership фиксированного gallery списка
обязательны; чужое/неизвестное/недоступное → `404`. Исходный `/media/{photo_id}`
остаётся строго four-teaser-only. `inventory` через public read-only provider
подтверждает площадку/active visibility commons при выборе, `processing`
подтверждает `no_faces` и предоставляет уменьшенный no-watermark JPEG через
существующий on-demand gallery renderer. Matched preview использует issuing
revision. Originals, raw keys и presigned URLs не выдаются; media read не
меняет union, `N`, QR, ACK, browser access или pipeline state. Потеря дополнения
не отменяет подтверждённый первый показ; missing ячейка остаётся пустой.

Уточнение оператора, 2026-10-04: второй слайд содержит только фотографии на весь
экран; общие фотографии берутся за любые даты этой площадки. Переход происходит
по таймеру первого слайда без ожидания дополнительных изображений: готовые
показываются сразу, остальные ячейки заполняются по мере загрузки; ошибка
оставляет ячейку пустой. Длительность второго слайда отсчитывается после
двухсекундного перехода; при replay — с появления сетки. При reduced-motion
переход мгновенный. Локальная длительность обязательна для включения второго
слайда. Общие Photos выбираются в стабильном порядке `photo_id`, не более
оставшихся мест; ограничения дат публичной телефонной галереи не меняются.

## Client Outcome Rules

- A compact realtime `result` is eligible for rendering only when its exact
  four-teaser/result shape validates. The client fetches and decodes all four
  authorized media responses and generates the QR locally from `qr_url`.
- Final Promo, optional Chime and success cooldown begin only after the four
  teasers and fully visible QR have formed one complete display result.
- Operator-approved paper entrance (2026-09-16) keeps QR offscreen until four
  photo arrivals finish, then brings it into its saved position. Fully-visible
  timing, display ACK and the result-display timer follow QR settlement
  (~3.06 seconds after insertion). The text entrance follows one second later
  and does not delay ACK. Reduced-motion skips this cosmetic sequence.
- Any non-result outcome, invalid/partial result, media/decode/QR/render error,
  stale response, camera/sensor/network/processing failure or missing display
  configuration leaves or returns the client to usable local advertising and
  starts no success cooldown. A best-effort `failed` report is allowed only
  for a server-issued result.
- First-slide expiry follows [Optional Second Slide](#optional-second-slide) when enabled. Final result-display expiry changes only local presentation. It returns to
  advertising and MUST NOT call a session-expiry/invalidation path. Result
  display and success cooldown use their independent configured durations.
- Missing optional audio/animation is silent and non-blocking. A server-
  communication failure keeps the accepted replaceable 5–10-second
  timestamped notice.

## Failures And Security

- Missing, invalid, reset or inactive display authentication returns `401`.
- A valid principal requesting a foreign or unknown session/media reference
  receives `404` without resource disclosure.
- Invalid JSON/fields return `422`; applicable rate limiting returns `429`;
  unavailable configuration/readiness returns `503`; technical failure returns
  `5xx`.
- Authorization headers, token plaintext/digests, personalized result payloads
  and raw storage identities MUST NOT enter URLs or logs. Media and JSON
  responses are `no-store`; PostgreSQL, MinIO and internal ports remain private.
- No custom error envelope, acknowledgement outbox, scheduler, reliable retry
  queue, media cache, replacement of issued teasers or parallel session owner is added.

## Verification Targets

- Contract tests cover the original three paths and the gallery media path, strict JSON shapes, authenticated
  principal scope, standard statuses, `no-store` delivery and absence of raw
  storage/credential material.
- Media fixtures prove primary-key session lookup without historical scans,
  four authorized low-quality no-watermark previews,
  foreign/non-teaser/missing/hard-purged `404` and zero partial/replacement result.
- State tests prove pending `-> confirmed|failed`, duplicate idempotency,
  conflicting/late rejection, derived terminal `unconfirmed` and unchanged
  session/ticket/expiry/teaser/union/`N` values.
- Client fixtures prove acknowledgement only after four decodes plus full QR
  visibility, independent display/cooldown timers, advertising fallback,
  optional-asset silence and no success cooldown on every named failure.
- The controlled 20-attempt artifact joins stable `attempt_id` values to the
  FT-004 server-correctness rows and records one-clock fully-visible elapsed,
  target-display rendering and representative-phone scan results without
  excluding timeout or no-match.

## Presentation

[Kiosk operation](../runbooks/app_guide_ru.md#киоск-promo-и-qr) describes
the existing adaptive card layout and replay controls. Optional second-slide additions follow [Optional Second Slide](#optional-second-slide).
