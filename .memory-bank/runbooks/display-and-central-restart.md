---
description: Operator recovery procedure for Chromium/display failure and ordinary central-runtime restart with intact primary volumes.
status: active
last_updated: 2026-08-15
source_of_truth:
  - .memory-bank/runbooks/display-and-central-restart.md
---
# Display And Central Restart Recovery

## Scope And Limits

This procedure covers two recoverable pilot failures:

1. Chromium or `SpaPromoClient` failure while the central HTTPS origin is
   reachable;
2. an ordinary backend/server-role restart while the configured PostgreSQL and
   MinIO primary volumes remain intact.

It does not claim offline client startup while the central origin is
unreachable, restore after irreversible loss of the sole primary disk/server,
or backup/replication recovery. Never use `docker compose down -v`, delete a
volume, reset a display token or change a serving revision as part of this
procedure.

## Serving-Revision Boundary

An ordinary serving-revision change is a separate authenticated maintenance
action, not a recovery step. Before any A-to-B asset/settings update or
model-consuming-process restart, the operator uses the `serving_control`
command. Its processing-owned pre-commit guard rejects B while an A-admitted
Photo has A state `pending` or `processing`; rejection keeps A and the current
deployment untouched. `ready`, `no_faces` and `failed` A states permit the
command to commit B, after which the AD-012 maintenance/restart path applies.
Calibration/model comparison is test-only and cannot bypass this command.
Direct database edits, restart or this recovery procedure are not alternative
revision-switch paths.

Source: [Architecture Spine AD-012](../architecture/system-architecture.md#architecture-spine)
and the [manual serving-revision contract](../contracts/boundary-map.md#manual-serving-revision-switch).

## Preconditions

- The operator has administrative SSH access as the `facemoment` OS user. The
  autologin `display` user has no `sudo`, Docker group or deployment-secret
  access.
- The checked-out deployment configuration and environment identify the
  intended one-server pilot, public HTTPS origin and intact named PostgreSQL/
  MinIO volumes.
- `deploy/systemd/user/spa-promo-client.service` is the source-managed user
  service installed for the `display` user. It starts sandboxed Chromium
  without `--no-sandbox` and uses `Restart=always`.
- `scripts/check-ft003-recovery.sh` is the non-destructive check command
  supplied with the deployed release. It records central role readiness,
  authenticated backend/realtime probes, intact-volume durable-state checks
  and display advertising state without printing credentials or protected
  payloads.
- The intended kiosk already holds the manually copied current central
  display-client token in its managed browser profile. The authoritative token
  remains visible to an authenticated Admin in server settings; this recovery
  procedure does not copy, reset or reveal it.

If any precondition cannot be established, stop. Do not improvise a volume,
credential, migration, browser flag or serving-setting repair.

## Browser Failure

1. Confirm the central HTTPS origin is reachable from the display host.
2. Observe the `display` user's `spa-promo-client.service` state and the current
   Chromium process identity without exposing its profile contents or tokens.
3. Terminate only the managed Chromium process for the recovery exercise, or
   restart only `spa-promo-client.service` when recovering an actual browser
   failure.
4. Confirm automatic process replacement by the user service and successful
   reload from the central HTTPS origin.
5. Confirm the page reaches usable local advertising and that no prior
   personalized result, reference frame, QR/session token or active Attempt
   state is restored. Confirm the existing central display-client credential
   remains configured without printing or rendering its value.
6. Run the browser portion of `scripts/check-ft003-recovery.sh` and retain its
   redacted result.

Success requires automatic replacement/reload, usable advertising and absence
of prior personalized client state. If the origin is unreachable, record that
condition and restore the central runtime first; no offline-start guarantee
applies.

## Ordinary Central-Runtime Restart

1. Record `docker compose ps` and confirm the configured PostgreSQL and MinIO
   volumes are present. Do not recreate, rename or delete them.
2. Record one non-sensitive durable-state locator through the supplied recovery
   check. It must include an existing authenticated application read and one
   queued Photo-processing locator without exposing commercial
   media, secrets or raw storage paths.
3. Restart only the application roles and HTTPS edge through the source-managed
   Compose project. Leave PostgreSQL and MinIO volumes intact. If the database
   or object-store process itself must restart, use the same configured service
   and volumes; do not initialize replacement storage.
4. Wait for migrate/init, backend, `BackgroundPhotoWorker`,
   `RealtimeFaceService` and HTTPS readiness. A migration or readiness failure
   is a stop condition, not permission to edit schema or serving state.
5. Run `scripts/check-ft003-recovery.sh` and confirm:
   - every central role is ready without a KDE/Chromium/display session;
   - an authenticated backend request succeeds;
   - intact-volume durable state from step 2 is preserved and queued Photo work
     can make its expected owner transition;
   - one fresh realtime request reaches admission;
   - Chromium reloads automatically after HTTPS returns and reaches usable
     local advertising without restoring prior personalized client state.
6. Retain the redacted check report and current Compose/service status as the
   recovery artifact.

## Failure And Escalation

Stop and hand off when a primary volume is missing, migration ancestry is
invalid, a role cannot become ready, authentication cannot be restored with
the existing credential, the display service needs privileged/sandbox-disabled
execution, or the check would require protected payload disclosure or a
destructive action. This runbook authorizes restart and observation only; it
does not authorize source repair, credential rotation, serving-setting changes
or data recovery after primary loss.

## Verification Targets

- The browser procedure is followed from advertising and active/result state;
  both runs prove automatic replacement, reload, advertising, retention of the
  configured central credential and discard of personalized state.
- The central procedure is followed from an ordinary role/server restart with
  intact volumes and proves role independence, durable-state preservation,
  queued Photo progress and fresh realtime admission.
- A review confirms the procedure states the no-offline-start and irreversible-
  primary-loss limits and contains no destructive or permission-expanding step.
