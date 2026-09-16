---
description: Compact current Memory Bank state; historical task evidence stays in task records.
status: active
---
# Changelog

## [2026-09-16] KISS-восстановление клиента после зависшего realtime-запроса

- [Realtime contract](contracts/realtime-attempt-api.md#bounded-client-waiting-and-realtime-io):
  watchdog клиента 20 секунд (увеличен с 10 по уточнению оператора) охватывает
  подготовку запроса, fetch и JSON body;
  abort возвращает рекламу и разрешает новый capture, поздний ответ игнорируется.
  Серверный default остаётся 7000 мс, без гарантии общего HTTP-дедлайна.
- Только realtime: DB connect/pool/lock wait 3 секунды, SQL/TCP timeout по
  realtime deadline; MinIO connect/read 2 секунды без SDK retries.
  Native hang по-прежнему требует ручного restart; новых процессов нет.
- Проверки: `npm run test:unit` — 80 passed; mypy — 106 source files без ошибок.
  На временном PostgreSQL прошли 41 профильная Python-проверка из
  `test_realtime_io_timeouts.py`, `test_realtime_orchestration.py`,
  `test_realtime_startup_recovery.py`, `test_realtime_attempt_integration.py`
  и `test_model_asset_admission.py` (40 в общем запуске, startup recovery после
  исправления устаревшего fixture — отдельным запуском). MinIO stalls проверены
  локальным HTTP fixture, без обращения к рабочим объектам.
- Для повторения Python-проверок: `uv run --locked --env-file .env.local python
  -m pytest` с указанными файлами; нужен доступный изолированный PostgreSQL.
  Рабочие сервисы в рамках этого исправления не перезапускались.

## [2026-09-16] Добавление экрана с выбором площадки

- По запросу оператора добавлена форма «Добавить экран» в «Экраны»: название,
  обязательный выбор активной площадки, создание и отмена. Каждый экран получает
  свой token через существующий owner; несколько экранов одной площадки разрешены.
- Карточка показывает название площадки; UUID остаётся в таблице. API защищён
  session/CSRF и operator/developer, отклоняет неизвестные/неактивные площадки.
- [Контракт и проверки](domains/display-client-access.md): реальная DB/API
  проверка scope, отдельных токенов и сохранности существующих экранов.
- 6 Python/API и 2 JS проверки прошли; mypy — 106 файлов без ошибок.
  Локальный backend перезапущен, Caddy validated/reloaded. HTTPS форма, JS asset
  и отказ POST с неверным UUID проверены; тестовые экраны в рабочей БД не создавались.
  Изолированный PostgreSQL с тестовыми данными удалён.

## [2026-09-16] Список часовых поясов при создании площадки

- По запросу оператора свободное поле заменено списком GMT+1…GMT+10,
  default GMT+7. Значения `Etc/GMT-N` дают соответствующие фиксированные
  положительные смещения; существующие площадки не менялись.
- Проверены все десять смещений через ZoneInfo, выбор default, mypy и JS
  формы. Изменение применено перезапуском локального backend.

## [2026-09-16] Создание площадки через админку

- По подтверждению оператора добавлены кнопка, форма названия/часового пояса и
  POST `/api/serving/spas`. Общая revision назначается сервером; свои настройки
  поиска создаются в той же транзакции. Права operator/developer и CSRF обязательны.
- [Контракт](contracts/boundary-map.md#staff-площадка-names): defaults и ошибки.
  Проверки: `tests/serving_control/test_spa_creation.py` (изолированный PostgreSQL)
  и `tests/client/test_spa_creation.mjs` (форма, CSRF, повторная отправка, ошибки).
- 3 PostgreSQL/API и 4 JS проверки прошли, mypy — 106 файлов без ошибок.
  Применено на локальном стенде: backend restart, Caddy reload. HTTPS форма и
  POST validation проверены; рабочие площадки/данные не создавались и не менялись.

## [2026-09-16] Functional multi-venue runtime

- Direct operator request, without a new DevRails queue: aligned product,
  architecture, boundary, processing and lifecycle docs with PRD Multi-venue
  operation, FR-SRCH-01, NFR-ARCH-01 and AC-27.
- Model consumers resolve one shared eligible revision across active venues.
  Empty/conflicting selection fails explicitly. Creation rejects another
  active revision; global switches serialize with creation/admission and guard
  every venue before atomically changing all pointers. No migration/data reset.
- Local preprocessing application supports multi-venue snapshots. Existing
  per-venue settings/search/worker paths, one realtime slot and sequential
  worker are retained. Historical data and inactive Calibration remain intact.
- 69 focused tests passed, including native two-venue PostgreSQL/MinIO/SFace
  search/Promo/QR, production lifecycles twice, conflict startup and cross-venue
  busy. Mypy passed for 106 source files. Updated the existing rename test to
  match the current Library venue links.
- [Verification scope](testing/index.md#functional-multi-venue-operation-ac-27)
  and [local operation](guides/local-development.md): commands and limits.
- Fresh dependency image build failed its downloaded-package SHA-256 check;
  the check was not bypassed. Packaged runtime verification uses current source
  layered on the previously working local image, with a recorded build limit.
- Two-venue packaged smoke passed, including actual container/dependency
  restarts and HTTPS. Existing local backend/realtime/worker were restarted and
  are healthy; existing display token/config and HTTPS probes passed. Before/after
  hashes preserve 42 Photos, settings, tokens, all 54 prior Attempts, 26 prior
  sessions and 270 prior objects. Two new sessions appeared through ongoing
  local activity; prior rows were independently compared unchanged. No test
  venues or revision changes were made in the working database.
- [Detailed evidence](../../.protocols/multi-venue-report.md): checks, local
  preservation and build limitation. All owned temporary test resources removed.

## [2026-09-16] Venue advertising playlists

- Added local screen configuration for an advertising caption and numeric text
  size (8–200 px), replacing three presets while preserving legacy values.
  Plain text overlays all advertising media at top left, hides outside
  advertising and persists in the kiosk's existing localStorage.

- Operator-approved Promo entrance: four staggered paper-card arrivals, then
  matching QR arrival, then text pressed into place one second after QR settles.
  Timing refined by operator: photo travel/stagger 50% longer (1350/270 ms),
  text duration subsequently increased to 6000 ms with linear easing so motion
  no longer settles early; full sequence approximately 10 seconds.
  Authored layout/reduced motion preserved; display ACK/timer follow actual
  QR entrance completion (~3.06 sec).

- Operator presentation update: finished Promo fades to black in 3 seconds,
  then advertising reveals in 1 second after its first material is ready.
  Existing server session/QR/ACK and advertising crossfade settings are preserved.

- Operator refinement: removed global advertising navigation/dashboard entry;
  each screen card now opens its venue playlist with «Реклама» below token copy.
  Playlist back navigation returns to «Экраны»; venue ownership is unchanged.

- Operator-approved direct KISS implementation: staff advertising for
  operator/developer, shared venue order/settings, existing private MinIO.
  Migration 0026 adds independent tables without changing Photo/Promo/history.
- Sequential display, first/random restart after unsuccessful recognition and
  personalized display, native crop/crossfade and audio stop. Cache Storage
  warms media; 30-second polling applies updates between materials.
- Codec validation and automatic tests waived by operator.
  [Contract and code](contracts/advertising-playlists.md): behavior and limitations.
- Applied locally: migration 0026, backend restart and Caddy reload succeeded;
  original data volumes retained. Functional checks remain operator-owned.

## [2026-09-15] Capture identity и ручной similarity threshold

- [Capture identity](domains/capture-identity.md): глобальные люди, связи с
  существующими photo faces, private crops и независимая диагностика. Crops
  хранятся обычные 90 суток; оценки верно/неверно и пропуски временные.
- Порог сходства перенесён в карточку площадки для текущей serving model,
  без второго хранилища. Calibration отключена от меню, HTTP и worker,
  включая startup interruption; прежние код и данные оставлены.
- Применено к локальным контейнерам по разрешению оператора: migration 0025,
  исходники, Caddy, существующий retention timer. Ручной cleanup не запускался.
  [Повторный запуск и проверки](guides/local-development.md#capture-identity-и-порог-сходства--локальное-применение).

## [2026-09-14] Per-площадка YuNet/BlazeFace controls

- Each площадка now exposes independent guarded edits for photographer-photo
  YuNet and browser BlazeFace confidence. Save locks the value; cancelling edits
  restores the last saved value. Today's-only mode saves automatically and
  hides the manual date range and its save button.
- Migration `0024_spa_detector_thresholds` adds venue values (`0.90` / `0.50`)
  and freezes the admission-time YuNet setting on new Photos. Existing Photos
  are not reprocessed. Native photo processing restores the detector threshold
  after each operation; reference matching and Calibration retain their paths.
- Authenticated display config carries the venue's BlazeFace threshold and is
  consumed before each browser detection, then reused for Promo. Caddy routes
  the two protected setting writes to backend. Existing three-field display
  responses remain readable during rollout.
- Verified mypy, 31 focused Python checks, 60 client checks, 25/26 initial
  PostgreSQL regressions, then five focused integration checks including the
  populated migration round-trip and worker snapshot. Two Chromium UI checks
  cover desktop/mobile. Caddy config validation passes. The single existing
  inventory-selector assertion failure is recorded in
  [session findings](../PAPERCUTS/gpt-6%20__%2009-14-2026%2008.56.md).
- The shared running database/application/edge were not migrated or restarted.
  Rollout requires migration to `0024`, updated backend/worker and Caddy config,
  then a browser refresh. No task statuses or planning revision were changed.
- [Settings contract](contracts/boundary-map.md#per-площадка-detector-thresholds),
  [browser config](contracts/promo-display-api.md),
  [processing ownership](domains/photo-processing.md).

## [2026-09-11] Per-площадка exit-camera search dates

- Operator requested direct KISS implementation: each «Площадки» card offers
  automatic today in its timezone or an inclusive manual «С»/«По» range.
  The separate settings menu is removed; its old page redirects to площадки.
- `serving_control` resolves each Attempt's range; exact search, result/session,
  diagnostics and phone continuation preserve both bounds. Additive fields
  retain historical one-day records without rewriting them.
- Migration `0023_search_date_ranges` enables automatic mode while preserving
  the old day as the saved manual range. No new task workflow was launched;
  Planning Revision 4, Foundation and existing task statuses remain unchanged.
- Verified scoped Python tests, migration round-trip, real Caddy save/reload,
  browser controls and phone tests; mypy passes. The shared running app was not
  restarted or migrated while the gallery agent works in parallel.
- [Search contract](domains/realtime-search.md),
  [staff API](contracts/boundary-map.md#active-search-date),
  [phone compatibility](contracts/qr-continuation-api.md#search-date-range-compatibility).

## [2026-09-11] Fix blank площадка page through HTTPS

- Added `/staff/spas` and `/api/serving/spas/*/name` to Caddy backend routing.
  Missing matchers had returned empty `200` responses before reaching FastAPI.
- Caddy validated and reloaded. Authenticated real HTTPS requests verified page
  content for operator/developer and mutation CSRF rejection. A real Chromium
  session rendered the page successfully; 3 routing/live-Caddy regression tests
  passed, including successful renaming in disposable state.
- [Routing explanation](guides/local-development.md#пустая-страница-площадок-https-routing),
  [live browser screenshot](../.tasks/spa-edge/spas-live.png).

## [2026-09-11] Compact single-field time controls

- Replaced three time dropdowns with one `HH:mm:ss` field and clock icon across
  all staff period forms. Supports `HH:mm` shorthand, keyboard segment adjustment
  and strict 24-hour validation, with no added dependency.
- Verified: 4 Python checks, 11 browser checks, mypy and visual inspection.
- [Time control behavior](guides/local-development.md#fixed-24-hour-time-selection).

## [2026-09-11] Separate площадка administration and administrator access

- `/staff/spas` lists active площадки with per-card rename forms for both
  operator and developer. Name editing moved out of search-date settings.
- Administrator (`developer`) can now use all operator sections, including
  `/staff/search-settings` and its date read/write API. Navigation and backend
  checks agree; photographer restrictions and CSRF remain enforced.
- Verified: 10 PostgreSQL-backed/route tests, 10 browser tests and mypy.
- [Access contract](domains/staff-access.md#administrator-access-to-operator-sections),
  [площадка names](contracts/boundary-map.md#staff-площадка-names).

## [2026-09-11] Readable staff timestamps

- Processing/statistics, event/Attempt, Calibration and retention displays use
  `dd.mm.yyyy HH:mm:ss` in UTC+7, without microseconds or `Z`. API and database
  timestamp precision remain unchanged. The shared footer identifies UTC+7.
- Verified: 4 Python checks, 8 browser checks and mypy; local backend restarted
  and current HTTPS page checked successfully.
- [Display and площадка administration](guides/local-development.md#displayed-timestamps).

## [2026-09-11] Locale-independent 24-hour time selectors

- All staff period forms now select hours 00–23, minutes and seconds explicitly;
  no locale-dependent AM/PM input remains. Saved intervals and UTC+7-to-UTC
  conversion are preserved.
- Verified: 3 Python checks, 7 browser tests and mypy for 97 source files.
- [Time selection](guides/local-development.md#fixed-24-hour-time-selection).

## [2026-09-11] Fixed dd.mm.yyyy date selectors

- All staff date fields now use locale-independent `dd.mm.yyyy` text with a
  native calendar trigger, including period filters, upload and search settings.
  Invalid dates are rejected; ISO API values and UTC+7 conversion are preserved.
- Verified: 10 Python checks, 6 browser checks (including calendar/text sync,
  leap date validation and mobile layout), mypy for 97 source files.
- [Usage and implementation](guides/local-development.md#fixed-date-display-format).

## [2026-09-11] UTC+7 and calendar/time filters

- Server application roles and PostgreSQL now default to `Asia/Novosibirsk`.
  Shared staff controls show calendar left/time right in UTC+7; event Severity
  and Component selects include `all` and explanations. Date-only upload and
  search-settings fields use calendars and a UTC+7 today default.
- [Behavior and runtime defaults](guides/local-development.md#server-timezone-and-staff-datetime-controls),
  [event form contract](contracts/server-event-api.md#staff-filter-controls-operator-update-2026-09-11).
- Verified: 41 Python checks passed, 5 browser tests passed, mypy passed for
  97 source files. One existing Attempt-role test fails because the common
  hidden navigation includes `/staff/calibrations`; reproduced with HEAD
  presentation/diagnostics code, independently of this change.
- Applied to the local source-overlay stack: all three roles healthy and
  reporting `+0700`; PostgreSQL `timezone` and `log_timezone` report
  `Asia/Novosibirsk`. HTTPS serves the new date/time asset. Disposable test
  PostgreSQL removed; existing application data volumes retained.

## [2026-09-11] Named площадка selectors and editing

- «Библиотека» and «Обработка» now use saved active площадка names, select the
  first available entry and preserve valid URL selection. The operator edits
  names in «Настройки поиска»; omitted configuration names become «Площадка N».
- [Name ownership and API](contracts/boundary-map.md#staff-площадка-names),
  [inventory UI](contracts/photo-inventory-api.md#staff-inventory-page-and-selection)
  and [processing UI](contracts/photo-processing-api.md#processing-health-and-slo).
- Verified: 13 PostgreSQL-backed API/owner tests, mypy over 96 source files,
  JavaScript syntax for populated/empty states of all three pages. No deployment
  or existing площадка rename was performed during implementation.
- Follow-up: restarted the local source-mounted backend at the operator’s
  request; live health returned 200 and OpenAPI includes the new rename route.

## [2026-09-10] Quiet kiosk menu and editable screen names

- Added hamburger navigation and editable screen names; Configuration shows
  the name and last five ID characters. [Usage](guides/promo-presentation.md#guest-screen-and-operator-menu).
- Verified: 15 backend tests, mypy, 57 client unit checks, 22 browser tests; local HTTPS identity,
  no-op rename and CSRF rejection passed.

## [2026-09-10] Advertising shortcut and simpler configuration

- Renamed replay to «Фотки вновь» and made the button transparent at the bottom
  right of the advertising screen.
- Central-token and passage-sensor controls now start collapsed under
  «доп настройки» in Configuration.
- Operator confirmed the manual no-face flow works; camera recovery remains
  deferred as previously agreed.

## [2026-09-10] Last-result replay and local display duration

- Advertising now replays the last successful four-photo result on demand;
  Configuration saves the visible duration in whole seconds for both original
  and repeated displays. Replay returns to advertising after a full interval.
- Replay re-fetches the same authorized previews and uses the saved design,
  without another search or display acknowledgement. It does not renew the QR;
  an expired QR has an explicit notice. Last-result references remain in page
  memory, while the seconds preference persists in this browser.
  See [presentation behavior](guides/promo-presentation.md#replay-and-display-seconds).
- Validation: 57 client unit checks and all 19 browser tests passed, including
  the actual-app replay/duration flow, failed-media retry and absence of a new
  search or duplicate display acknowledgement.

## [2026-09-10] Mouse-operated Promo composition editor

- Configuration now opens a full-screen editor for all four photo cards, QR
  and copy. Pointer gestures change position, size and rotation; text has three
  size presets. Toolbar sliders keep size/rotation accessible for cards that
  extend beyond the screen.
- Save persists local viewport-relative geometry and returns to Configuration;
  real Promo results reuse the same renderer and saved design. Cancel preserves
  the prior design, and storage failure keeps the unsaved draft visible.
  See the [editor guide](guides/promo-presentation.md#local-composition-editor).
- Validation: 55 client unit checks, the existing 17 browser tests and
  the new editor regression passed; mouse interactions and slider fallback
  were independently checked in isolated desktop/mobile browser viewports.

## [2026-09-10] USB reconnection and reload diagnostics

- Added the operator-requested 2-second settling delay before automatic USB
  camera recovery, with cancellation when selection or device state changes.
  All 54 client unit checks passed; physical color recovery remains to be
  checked after loading the updated client.
- Promo cards now overlap at 125% of grid-cell size and the stationary QR
  fills its allocated square. Wide-screen text clearance was corrected;
  six layout cases plus 1450x833 passed after the final CSS change. The local
  server serves the updated stylesheet. See the
  [presentation guide](guides/promo-presentation.md).
- Per operator request, the previously selected camera now reopens when the
  same deviceId returns. Other identities still require explicit selection.
- Bounded safe client diagnostics survive reload using sessionStorage, include
  camera transitions and preserve HTTP failure status. Denied storage is
  non-blocking. All 54 client unit tests and 17 browser tests passed; isolated
  Chromium also confirmed retained history rendering after reload.
- Browser evidence identified certificate distrust as the prior transport
  failure; the next actual Attempt reached the server with `no_proposals`.
  [Local diagnosis](guides/local-development.md#no-server-connection-notice--2026-09-10)
  distinguishes TLS, USB recovery and no-face outcomes.

## [2026-09-09] Native Promo fetch binding

- Bound `Window.fetch` in `PromoDisplayController`; native Chromium configuration
  and ACK calls now work. Added a receiver regression; 53 client tests passed.
- [Investigation](guides/local-development.md#native-browser-fetch-failure-after-preview-repair)
  records the prior wrapper-smoke limitation.

## [2026-09-09] Developer manual threshold control

- Added independent manual threshold input/save/current value to Calibration;
  stale forms are rejected and other settings/history are preserved. Nine
  disposable HTTP tests cover the route. See [details](guides/local-development.md#manual-threshold-in-calibration).

## [2026-09-09] Issued preview revision and display diagnostics

- Display and phone media now use the issuing Attempt's immutable revision;
  bounded browser diagnostics expose safe render-failure codes. Local SFace
  threshold was set to 0.4. [Investigation](guides/local-development.md#issued-preview-revision-repair-and-sface-threshold-04).

## [2026-09-09] Camera Attempt investigation presentation

- Added developer search summaries with pre-threshold best similarity and
  eligible-Photo count for fresh searches; historical missing values remain
  explicit. Twelve focused tests passed. [Diagnosis](guides/local-development.md#camera-search-diagnosis--2026-09-09).

## [2026-09-09] Wave 8 — Preserved local Photo reprocessing

- [TASK-118](tasks/TASK-118-T3-FT-002-W8.task.json): local `opencv-photo-640-v2`
  deployment, six ready Photos, preserved originals/admission/history and
  repeat-run proof. Fixed revision filtering; 34 focused tests, mypy, lint,
  build and semantic reviews passed. Camera identity still needs labelled attempts.

## [2026-09-09] Wave 7 — Measured SFace Photo preprocessing

- [TASK-117](tasks/TASK-117-T2-FT-002-W7.task.json): bounded original-pixel
  detection with shared EXIF decode. Six portraits recovered at 640; 1280 added
  no faces in supplied groups. 62 focused tests, mypy, lint and native measurements passed.

## [2026-09-07] Adaptive Promo photo cards

- Implemented the operator-approved paper-card presentation and exact download/domain copy in the existing Chromium client. Landscape, square and portrait layouts replace the fixed display assumption; QR remains stationary.
- [Presentation guide](guides/promo-presentation.md) records visual behavior and supersedes the earlier IDEA_APP six-cell/cursor animation. PRD, FT-005 and display-contract navigation are aligned. No task lifecycle or session/API behavior changed.
- Validation: 52 client unit tests and all 17 browser tests passed; browser layout coverage at six viewport sizes with synthetic landscape/portrait fixtures, reduced motion and stationary QR checks.

## [2026-09-07] Extended quality Calibration removed from pilot plans

- Operator explicitly deferred FR-DEV-08 / FT-011-AC-002, including extra measurement collection and shared redesign, outside the pilot. [PRD](prd.md) and [FT-011](features/FT-011.md#ft-011-ac-002--one-dimensional-quality-recommendations) retain the decision and historical criterion identity.
- Requirements, Calibration scope/testing and planning checkpoints now exclude that work from current obligations; the shared-measurement blocker is withdrawn. Existing search, threshold Calibration, comparison and manual apply remain in scope.
- No runtime, task lifecycle, historical verification or Global Backbone Planning Revision changed. Revised-scope semantic acceptance is not claimed.


## [2026-09-07] Operator defers measurements; remaining code confirmed

- Operator postponed FT-011 quality measurements/shared redesign and requested implementation-only continuation for TASK-115 → TASK-116. [Decision and code evidence](../.protocols/AUTONOMOUS-RUN/decision-log.md) supersede the earlier immediate design question for this scope.
- Both implementations already exist in the committed baseline: canonical Caddy forwarding and the working staff login form. Fresh Caddy validation, mypy (94 files), five routing/shell tests and six local login-script cases passed; no duplicate runtime edit was needed.
- Full acceptance remains deferred; task statuses and accepted criteria are unchanged. The [scheduler checkpoint](../.protocols/AUTONOMOUS-RUN/status.md) distinguishes this completed code handoff from full queue success.

## [2026-09-07] Wave 4 / Promoted Calibration case actions and design blocker

- Closed: [TASK-106](tasks/TASK-106-T3-FT-011-W4.task.json), AC-008, after independent functional PASS and task semantic-pass. Existing Calibration detail actions now promote only the selected curated case and delete its whole subset with separate confirmation; 11 tests, mypy and lint passed.
- Blocked: the [FT-011 feature review](../.tasks/FT-011/FT-011-S-RED-VERIFY-final-report-docs-01.md) proved missing production quality analyses for AC-002. Fresh local tasking traced this to absent shared per-occurrence measurements, not TASK-106 behavior; no follow-up task or implementation contract was invented.
- Next owner: operator decision and `/spec-redesign` for the bounded [shared measurement proposal](../.protocols/FT-011/clarification.md#shared-measurement-boundary--2026-09-07). Query-image retention and serving changes are not proposed. [Scheduler checkpoint](../.protocols/AUTONOMOUS-RUN/status.md) records `HALT_BLOCKING_QUESTIONS`; TASK-114/106 remain done and TASK-115/116 unselected.
- Cleanup: owned TASK-106 PostgreSQL and temporary connection file removed; default/operator data untouched. This records the completion/blocker handoff, not a completed wave sync or strict-readiness claim.

## [2026-09-07] Wave 6 / Buffalo native readiness closure

- Closed: [TASK-114](tasks/TASK-114-T3-FT-002-W6.task.json), AC-009, after fresh functional PASS and independent task/feature semantic-pass. Existing committed correction needed no further source change during resume.
- Verified: 26 tests, actual non-skipped native ONNX warmup, 16 serving/Calibration failure cases, mypy and lint. Dynamic detector preparation and both native inference calls precede readiness; failures remain closed.
- Reconciled: [FT-002](features/FT-002.md) maintenance completion and [testing evidence](testing/photo-processing.md). All 24 FT-002 tasks are closed; baseline ownership and current Planning Revision 4 approval are preserved. Cross-feature requirement/epic lifecycle is unchanged.
- Cleanup: task-owned tmpfs PostgreSQL removed after independent reviews; no deployment or default/operator data change. Scheduler owns post-sync lint and strict doctor before TASK-106.

## [2026-09-07] Multipilot prerequisite evidence reconciliation

- Normalized existing RED/GREEN field labels and full acceptance IDs in [TASK-110 progress](../.protocols/TASK-110-T3-FT-012-W3/progress.md), [TASK-110 verification](../.protocols/TASK-110-T3-FT-012-W3/verification.md) and [TASK-113 progress](../.protocols/TASK-113-T3-FT-003-W5/progress.md) so strict readiness can recognize retained closure evidence. Observations, attempts, verdicts, task lifecycle and runtime are unchanged.
- Explicit GENERAL owner requested this bounded early `/mb-sync` prerequisite for queue 114 → 106 → 115 → 116; scheduler owns subsequent lint and strict-doctor gates.

## [2026-09-07] ASTRA finding 10 — packaged runtime proof

- Updated smoke-runtime.sh and local-development guide for isolated project/network/volumes, migrated product schema, real SFace serving seed and current role readiness.
- Live packaged smoke passed HTTPS route/auth checks, dependency/application restart, storage persistence and owned cleanup; all 13 ASTRA findings are now accepted. No indexed lifecycle or deployment change.
- [Retained handoff and evidence](../.tasks/ASTRA-findings/10-packaged-smoke/implementation-report.md): logs, redacted topology and source links for the next deployment agent. User asked to retain useful artifacts and remove the obsolete test image after checks. The image was removed and its cleanup added to the script. The first preflight null-IPAM failure is also retained. Other project tasks remain untouched.

## [2026-09-07] ASTRA findings — operator pause

- Findings 3–9 and 11–13 are accepted; finding 9 source review and independent client gates confirm 52 unit and 11 browser passes, including 400/400 Blob URL cleanup.
- Finding 10 remains open: accepted plan and read-only preparation only; no script changes or packaged runtime run. Work stopped at operator request.
- The out-of-scope default-Compose pytest incident remains recorded; disposable-data clarification removes the preservation blocker without establishing retrospective isolation.
- [Session handoff](../.tasks/ASTRA-findings/session-handoff.md): accepted work, incident evidence and exact continuation boundary. [Consolidated review](../PAPERCUTS/TECHDEBTS/ASTRA-consolidated-review-2026-09-06.md): one remaining finding.

## [2026-09-06] Wave 5 / Responsive realtime admission

- Closed: [TASK-113-T3-FT-003-W5](tasks/TASK-113-T3-FT-003-W5.task.json), audit finding 2, after root functional PASS and independent semantic-pass.
- Fixed: blocking request work owns Sessions inside framework worker threads; only the unique insert winner starts processing. Concurrent health, same-key in_progress and distinct-key busy responses arrive before inference release.
- Evidence: 47 tests, real PostgreSQL insert/row-lock arbitration, Session cleanup, terminal replay and unchanged rate budgets; mypy/lint passed. JPEG hardening from TASK-112 is preserved. No deployment occurred.

## [2026-09-06] Wave 4 / Realtime JPEG admission hardening

- Closed: [TASK-112-T3-FT-003-W4](tasks/TASK-112-T3-FT-003-W4.task.json), audit finding 1, after root functional PASS and independent semantic-pass.
- Fixed: auth/rate checks precede multipart/crop work; JPEG header dimensions reject oversized crops before allocation. Existing full decode still validates bounded input before Attempt creation.
- Evidence: 15 current-source ASGI tests, independent 513x1/1x513/512x512 probes, mypy and lint. TASK-113 owns the remaining concurrent realtime fix; no runtime deployment occurred.

## [2026-09-06] TASK-104 KISS repair closed

- Repaired: production Calibration completion now composes one stored
  `Balance` threshold recommendation only from homogeneous selected Attempts
  for the exact current serving revision and their one common finite historical
  threshold; mixed or undefined input truthfully produces no recommendation.
- Preserved: the proposal changes only the threshold. Current server-owned
  query-quality and quality-gate settings remain unchanged; no grid search,
  weighting, inferred outcome, quality candidate or automatic apply was added.
- Repaired: the post-apply success notice now requires the current owner state
  to match both the returned settings revision and Calibration run ID, so a
  forged query value cannot report success.
- Hardened within the same KISS boundary: the stored recommendation now retains
  the exact calibrated `pipeline_revision_id`. A supported switch to another
  revision with the same pipeline code makes the old recommendation stale;
  owner apply and the success notice both reject that mismatch.
- Closed: `TASK-104-T3-FT-011-W3` is `done` after fresh focused and adjacent
  tests, mypy, Memory Bank lint, `git diff --check`, the required real-browser
  flow, independent functional `PASS` and task-scoped `semantic-pass`.
- Adversarial proof covers both switch-before-apply rejection and
  switch-after-apply stale-success suppression. No dependent was promoted and
  no unrelated workflow stage was run.

## [2026-09-05] Wave 2 / Calibration missing-original recovery

- Closed: `TASK-111-T3-FT-011-W2` is `done` after independent functional
  `PASS`, task-scoped `semantic-pass` and scheduler-owned closure.
- Reconciled: the supported S3 `NoSuchKey` path now terminalizes the claimed
  Calibration run as `failed/dataset_unavailable`, releases the singleton
  worker and permits queued Photo progress without replacement execution or a
  serving change; `REQ-CAL-003` is `verified` through `FT-011-AC-005`.
- Dependency state: TASK-104 is authoritatively `ready`; TASK-106 remains
  blocked on TASK-104. TASK-110 retains `blocked` status even though its former
  TASK-111 dependency condition is satisfied, pending the scheduler-owned
  post-sync gate and promotion pass. No task status was changed by this sync.
- Evidence: `.memory-bank/tasks/TASK-111-T3-FT-011-W2.task.json`,
  `.tasks/TASK-111-T3-FT-011-W2/TASK-111-T3-FT-011-W2-S-VERIFY-final-report-docs-01.md`
  and `.tasks/TASK-111-T3-FT-011-W2/TASK-111-T3-FT-011-W2-S-RED-VERIFY-final-report-docs-01.md`.

## [2026-09-05] Wave 2 / FT-012 role-scoped Photo visibility

- Closed: `TASK-107-T3-FT-012-W2` is `done` after independent functional
  `PASS`, task-scoped `semantic-pass` and scheduler-owned closure.
- Implemented: inventory-owned role-safe half-open Photo selection and
  idempotent `Photo.is_active` visibility change; inactive Photos leave new
  search and counters while issued media remains readable.
- Preserved: FT-012 and `REQ-INV-001..003` remain `planned`; TASK-110 remains
  blocked through failed TASK-101 and no blocked path was promoted.
- Evidence: `.memory-bank/tasks/TASK-107-T3-FT-012-W2.task.json` and
  `.tasks/TASK-107-T3-FT-012-W2/TASK-107-T3-FT-012-W2-S-RED-VERIFY-final-report-docs-01.md`.

## [2026-09-05] Wave 2 / FT-011 independent completed slices

- Closed: `TASK-102-T2-FT-011-W2`, `TASK-103-T2-FT-011-W2` and
  `TASK-105-T3-FT-011-W2` are `done` after their required task-scoped evidence;
  TASK-105 additionally has independent `semantic-pass` and scheduler closure.
- Implemented: threshold-profile locator validation, five independent quality
  recommendations including lower-is-better `blur_score <= cutoff`, and
  existing-owner expiry of old terminal ordinary Calibration runs under the
  shared strict 90-day cutoff.
- Preserved: FT-011 and its requirements remain `planned`; TASK-101 is failed,
  TASK-104 and TASK-106 remain blocked, and no dependent is promoted through
  that failed path.
- Evidence: task records `TASK-102`, `TASK-103`, `TASK-105`; TASK-105 reports
  `.tasks/TASK-105-T3-FT-011-W2/TASK-105-T3-FT-011-W2-S-VERIFY-final-report-docs-01.md`
  and `.tasks/TASK-105-T3-FT-011-W2/TASK-105-T3-FT-011-W2-S-RED-VERIFY-final-report-docs-01.md`.

## [2026-09-05] Wave 1 / FT-012 statistics and processing-cleanup providers

- Closed: `TASK-108-T3-FT-012-W1` and `TASK-109-T3-FT-012-W1` are `done`
  after their independent T3 functional `PASS`, task-scoped `semantic-pass`
  and scheduler-owned closure decisions.
- Implemented: the closed W1 providers cover exact direct recent per-СПА
  counters (`FT-012-AC-006`) and the processing-owned Photo derivative/row
  cleanup boundary needed by the later fixed-snapshot purge.
- Reconciled: `REQ-INV-004` is `verified` through the closed
  `FT-012-AC-006` slice. FT-012 and `REQ-INV-001..003` remain `planned`
  because TASK-107 and TASK-110 still own the remaining feature acceptance
  outcomes; no feature lifecycle transition or dependent promotion is made by
  this sync.
- Evidence: `.memory-bank/tasks/TASK-108-T3-FT-012-W1.task.json`,
  `.memory-bank/tasks/TASK-109-T3-FT-012-W1.task.json` and
  `.tasks/TASK-AUTONOMOUS/TASK-AUTONOMOUS-S-MB-SYNC-W1-final-report-docs-02.md`.

## [2026-09-04] FT-012 task decomposition closure

- Closed: fresh `/review-tasks-plan FT-012` approved the four-card task plan
  for Global Backbone Planning Revision `4`; no architecture review was
  required.
- Reconciled: `TASK-107..110` retain their reviewed scopes and statuses;
  `FT-012-AC-001..007` and `REQ-INV-001..004` keep complete, unambiguous
  task ownership and traceability.
- Evidence: `.tasks/TASK-MB-REVIEW-TASKS-PLAN/TASK-MB-REVIEW-TASKS-PLAN-S-TASKS-FT-012-final-report-docs-01.md`.
- Preserved: FT-012 and its requirements remain `planned` until implementation
  and verification; the applicable `/mb-doctor` gate precedes execution.

## [2026-09-04] Wave 2 / FT-010 feature closure

- Closed: `TASK-097-T3-FT-010-W2`, `TASK-098-T3-FT-010-W2` and
  `TASK-099-T3-FT-010-W2` are `done` after their required T3 functional
  `PASS`, task-scoped `semantic-pass` and scheduler-owned closure decisions.
- Verified: FT-010 is `verified` after all `FT-010-AC-001..005` outcomes and
  feature-level `semantic-pass`; `REQ-ANN-001` is reconciled to `verified`.
- Evidence: `.tasks/FT-010/FT-010-S-RED-VERIFY-final-report-docs-01.md` and the
  durable marker in `.memory-bank/features/FT-010.md#semantic-verification`.
- Preserved: EP-003 remains `planned` while FT-007 production acceptance and
  FT-011 are unfinished. Their tasks, all FT-012 work and all production-
  acceptance task statuses remain unchanged.

## [2026-09-04] Wave 1 / FT-010 normalized annotation provider closure

- Closed: `TASK-096-T3-FT-010-W1` is `done` after Attempt 2 functional `PASS`,
  required task-scoped `semantic-pass` and scheduler-owned closure.
- Implemented: the diagnostics-owned normalized provider persists valid
  detection `correct|false` and person-level `missed` semantics, exposes an
  immutable ordered calculation projection and rejects mutation after
  committed evidence expiry or removal.
- Evidence: `.tasks/TASK-096-T3-FT-010-W1/TASK-096-T3-FT-010-W1-S-VERIFY-final-report-docs-02.md`
  and `.tasks/TASK-096-T3-FT-010-W1/TASK-096-T3-FT-010-W1-S-RED-VERIFY-final-report-docs-02.md`.
- Preserved: `TASK-097..099`, FT-010 and `REQ-ANN-001` remain `planned` because
  the Wave 2 developer flow, promoted subset and ordinary-retention outcomes
  are unfinished. The current Planning Revision `4` task-plan `APPROVE` remains
  valid because this closure changes status and evidence only.

## [2026-09-04] FT-010 task decomposition closure

- Closed: fresh `/review-tasks-plan FT-010` approved the four-card task plan for
  Global Backbone Planning Revision `4`; no architecture review is required.
- Reconciled: `TASK-096..099` remain `planned`, every `FT-010-AC-001..005` has
  one owner, and the implementation-plan router now links IMPL-FT-010.
- Evidence: `.tasks/TASK-MB-REVIEW-TASKS-PLAN/TASK-MB-REVIEW-TASKS-PLAN-S-TASKS-FT-010-final-report-docs-01.md`.
- Preserved: FT-010 and `REQ-ANN-001` remain `planned` until implementation and
  verification; the applicable `/mb-doctor` gate precedes execution.

## [2026-09-04] Wave 3 / FT-009 feature closure

- Closed: FT-009 is `verified` after all `FT-009-AC-001..004` task outcomes,
  required T3 gates and feature-level `semantic-pass` completed.
- Reconciled: `REQ-LOG-001` is `verified`, and the feature router now reflects
  the closed persistence, developer-search and retention outcome.
- Evidence: `.tasks/FT-009/FT-009-S-RED-VERIFY-final-report-docs-01.md` and the
  durable marker in `.memory-bank/features/FT-009.md#semantic-verification`.
- Preserved: EP-003 remains `planned` while FT-010 and FT-011 are unfinished.

## [2026-09-03] Wave 3 / FT-009 server-event retention closure

- Closed: `TASK-093-T3-FT-009-W3` is `done` after functional PASS and required
  per-task `semantic-pass`.
- Implemented: the existing owner-ordered cleanup now expires diagnostics-owned
  structured server events strictly before the 30-day cutoff, reports the
  confirmed count and preserves truthful failure, overlap and rerun behavior.
- Verified: current and bookmarked search, FT-008 navigation and browser history
  cannot recover deleted event content; equal/newer events and 90-day
  Attempt/evidence state remain intact.
- Reconciled: all `FT-009-AC-001..004` implementation slices are closed, FT-009
  and `REQ-LOG-001` are `implemented`, and feature-level semantic verification
  remains the final gate before `verified`.

## [2026-09-03] Wave 2 / FT-009 server-event search closure

- Closed: `TASK-091-T3-FT-009-W2` is `done` after fresh Attempt 4 functional
  PASS and required per-task `semantic-pass`.
- Implemented: the effective release HTTPS route exposes the exact
  developer-only bounded server-event search with usable optional filters,
  fixed-field escaped HTML, paired FT-008 navigation and truthful uncorrelated
  rows; internal `event_id` values are not rendered.
- Preserved: FT-008 retains target authorization/projection ownership, denied
  and stale sessions disclose no rows, and diagnostics performs no Promo-table
  read for navigation.
- Reconciled: FT-009 now has closed producer/persistence and search/navigation
  slices. `TASK-093-T3-FT-009-W3` remains `planned` for retention expiry; its
  dependencies are satisfied, but this sync does not promote or select it.
- Lifecycle: FT-009 and `REQ-LOG-001` remain `planned` until the W3 retention
  outcome is implemented and receives its required verification.

## [2026-09-02] FT-008 closure and FT-009 producer slice

- Verified: FT-008 is complete. TASK-088 and TASK-089 are `done`, the
  feature-level adversarial review is `semantic-pass`, and `REQ-DIAG-003` is
  verified.
- Implemented: FT-009's isolated redacted persistence slice
  (`FT-009-AC-002`) is closed by TASK-094 with functional PASS and
  task-scoped semantic-pass.
- Reconciled: TASK-090 remains failed historical evidence and its resolved bug
  note is archived. TASK-091 and TASK-093 no longer carry the obsolete failed-
  dependency block; TASK-091 is `in_progress`, while TASK-093 remains `planned`.
- Clarified: one explicit bounded Promo-owned QR correlation query after commit
  is accepted ordinary owner access, not diagnostics writer latency. No global
  zero-SQL requirement was introduced.
- Local development now runs current editable Python source through locked
  `uv`; only PostgreSQL/pgvector and MinIO stay in the daily Compose overlay.
  The unchanged base Compose topology remains the packaged-runtime smoke.
- Backend HTTP adapters now reuse one composition-owned SQLAlchemy Engine and
  open a short Session per request. The Engine is disposed at backend shutdown;
  the diagnostics writer keeps its contract-required independent Session path.
  API, transaction ownership, schema and capability ownership are unchanged.
- Promo now derives effective `pending -> unconfirmed` display state through
  one pure `PromoAttempt` helper reused by display outcome and diagnostics
  timeline reads. The persisted state, expiry boundary and API remain unchanged.

## [2026-08-29] Development baseline after FT-001…FT-007

- All development work for `FT-001` through `FT-007` is terminal. Their
  completed task records are historical evidence, not active work or blockers.
- `TASK-075-T3-FT-004-W5` is `done_for_prod`. Its development evidence is
  accepted; `FT-004-AC-004` remains production-only and does not block
  development scheduling.
- `TASK-078-T3-FT-005-W2`, `TASK-081-T3-FT-006-W2` and
  `TASK-086-T3-FT-007-W3` are `done`. Their earlier failures, retry limits and
  halted-run records are superseded historical checkpoints.
- The remaining non-terminal `FT-001`…`FT-007` records are title-prefixed
  `Production acceptance:` tasks. They remain deferred until production and
  are excluded from development autopilot.
- No active bug or development blocker remains for `FT-001`…`FT-007`.

Current lifecycle authority is `.memory-bank/tasks/*.task.json`. Historical
verification entries inside terminal task records preserve provenance but do
not override the record's top-level status.

## 2026-09-08 — Local application deployment for operator testing

Rebuilt current source and started the persistent local Compose stack using
existing storage. Migrated to 0022, provisioned local SFace/SPA/display settings
and separate operator, photographer and developer accounts. Application roles
are healthy; HTTPS login and role-scoped page checks passed. Access paths,
restart command, test settings and verification limits are recorded in
[local-development.md](guides/local-development.md#persistent-local-testing-stand--2026-09-08).

## 2026-09-08 — Motion Atlas visual integration

Added distinct public and role-aware staff homepages, common staff styling,
selected motion effects and a phase-driven kiosk loading scene. Existing paper
Promo and QR continuation retain their behavior. Public camera capture UI is
presented explicitly as prelaunch: visitor search and payment are not connected;
gallery upload and Google OAuth remain deferred. See the
[presentation guide](guides/motion-presentation.md) for ownership, local review
routes and verification limits.

### Motion Atlas operator visual correction

Restored the original Fluid gradient tiling, color/background and rotation;
removed the added dark overlay. The operator confirmed that the reference's
visible rectangular boundaries are intentional. Earlier QA advice to smooth
those boundaries is superseded. The public portrait frame is now the
«Найти меня» link; the old hero CTA and registration tagline are removed.

### Fluid browser controls

Added the requested collapsible live-preview sliders on `/site`: spot size,
drift, speed (including pause), rotation and blur. Values apply immediately
to the public hero; reset restores the original preset. Settings are local to
the current page and do not change server configuration.

### Fluid hover zoom

The public «Найти меня» hit area now smoothly enlarges the existing Fluid layers
to an effective 100% spot size, returning to the slider-selected size on leave.
The effect uses CSS scale, with no gradient-size animation or JS frame loop.
Speed tuning now targets only drift animations so pause does not stop hover.

### Fluid hover timing refinement

Per operator feedback, increased the hover target from effective 100% to 200%
and changed scale easing to a slow 4-second ease-in-out transition. Pointer
leave reverses smoothly from the current scale; clicking never waits for zoom.

The operator subsequently adjusted the final Fluid hover target to 150%;
the 4-second transition and smooth return remain unchanged.


## 2026-09-11 — Staff venue media request

Recorded the operator's Library → venue Media table, date filters, thumbnail /
original viewing and per-row soft-delete request in PRD, FT-012 and the existing
inventory contract/boundary map. Existing processing creates 320px thumbnails
and 1024px previews by default. Bounded FT-012 planning delta; revision 4 and
historical task evidence unchanged. Implementation and checks remain pending.

## 2026-09-12 — Staff media implementation

TASK-119 adds Library links to venue media, upload-date filtering in UTC+7,
private thumbnails/native originals, persisted metadata and existing soft delete.
The operator clarified that no_faces Photos must be omitted. API tests (9),
real HTTPS/Playwright CLI journey (1), mypy and mb-lint pass; independent task
verification is next. See `.protocols/TASK-119-T3-FT-012-W3/handoff.md`.
Shared runtime was not restarted during concurrent FT-006 work.


## 2026-09-12 — Staff media independently verified

TASK-119 closed as done by GENERAL after independent functional PASS and
semantic-pass. Feature extension, task-plan handoff and task evidence are
synchronized; Planning Revision4 and historical requirement acceptance remain
unchanged. The operator also explicitly requested applying migration0023 and
updating shared services for both agents' changes after completion; rollout
preflight confirms live0022 and isolated search-settings tests23PASS.


## 2026-09-12 — Both changes deployed

On explicit operator request, applied migration0023_search_date_ranges to the
shared database and updated backend/realtime/background-worker to the newly
built image; validated/reloaded Caddy. All services healthy. Live HTTPS checks
as operator and developer passed Library, venue Media, actual thumbnail/original,
venue settings and search-dates API. Photo/Attempt/session counts preserved
(6/17/12). See guides/local-development.md and .tasks/staff-media-release/.
