---
description: Лог изменений Memory Bank.
status: active
---
# Changelog

## [2026-08-29] TASK-075 — explicit owner-accepted closure
- Accepted the existing independent AC-005/AC-006 evidence as sufficient for
  development closure and reconciled `TASK-075-T3-FT-004-W5` to
  `done_for_prod`.
- Superseded the historical AC-004 blocker by explicit owner decision;
  `FT-004-AC-004` remains a production-only residual risk under TASK-075. No
  production PASS was created and no verification was rerun.
- Preserved all historical verification and closure verdicts unchanged.
- Preserved FT-004, EP-002 and mapped RTM requirements as `planned`; feature
  completion and production acceptance remain open. Existing task index and
  canonical links remain unchanged.

## [2026-08-29] FT-007 feature boundary — semantic verification reconciled
- Reconciled the already-authoritative FT-007 feature-level
  `SEMANTIC_VERDICT: semantic-pass` with its final Red Verify report and
  protocol for the completed W3 non-production boundary TASK-083…086.
- Kept `REQ-DIAG-002` `verified` as already reconciled; the remaining affected
  RTM rows stay `planned` where other feature obligations remain open.
- Kept FT-007 and EP-003 at `lifecycle: planned`; TASK-087 and
  `FT-007-AC-006` remain planned and explicitly excluded as production
  acceptance. Existing feature, epic, root, task and implementation-plan
  routers and canonical links already agree, so no router repair was needed.
- Preserved TASK-086 `done`, TASK-075 `blocked`, FT-003 closed/ignored state,
  unrelated working-tree dirt and named data/volumes. No task, promotion,
  selection, production or scheduler decision was made by this sync.

## [2026-08-29] Wave W3 — TASK-086 ordinary retention closure reconciled
- Reconciled the scheduler-owned `done` closure for
  [TASK-086-T3-FT-007-W3](tasks/TASK-086-T3-FT-007-W3.task.json) with fresh
  functional Verify Attempt 3 `PASS`, required Red Verify Attempt 3
  `semantic-pass`, and the recorded T3 closure evidence; the earlier semantic
  failure remains historical.
- Advanced only `REQ-DIAG-002` to `verified`, because its complete
  `FT-007-AC-002..004` scope is now closed. Kept `REQ-DIAG-001`,
  `REQ-DIAG-003`, `REQ-DATA-001`, `REQ-PERF-001`, `REQ-SEC-001` and
  `REQ-ARCH-001` planned where other feature obligations remain open.
- Kept FT-007 and EP-003 `planned` because W4 `TASK-087` still owns
  `FT-007-AC-006`; no task status, promotion, dependent state or production
  acceptance decision was made by this sync.
- Restored the missing `IMPL-FT-007` entry in the implementation-plan router.

## [2026-08-29] Wave W3 — FT-007 realtime evidence integration reconciled
- Reconciled the scheduler-owned `done` closure for
  [TASK-085-T2-FT-007-W3](tasks/TASK-085-T2-FT-007-W3.task.json) with fresh
  independent Verify Attempt 1 `PASS` and the recorded T2 closure evidence.
- Reconciled the best-effort realtime diagnostics attachment for result,
  zero-proposal, busy, deadline and technical-failure outcomes, including
  explicit incomplete evidence gaps and unchanged participant truth.
- Confirmed the task remains indexed and kept FT-007, EP-003 and mapped RTM
  rows `planned`: TASK-086 and TASK-087 still own later FT-007 acceptance
  outcomes. No feature/epic closure or promotion decision was made by this
  sync.



- 2026-08-28: Documented the non-secret workstation SSH commands for the VPS
  and central server; local credentials remain outside version control.



- 2026-08-28: Deployed and verified a VPS-loopback-only FRP SSH proxy for
  central-server administration through OpenSSH `ProxyJump`; `ssh facecentral`
  reaches `face@face-pc`, while no central SSH port is exposed on the VPS
  public interface.

## [2026-08-28] Wave W1 — FT-006/FT-007 technical foundations reconciled
- Reconciled the scheduler-owned `done` closure for
  [TASK-080-T3-FT-006-W1](tasks/TASK-080-T3-FT-006-W1.task.json) with fresh
  functional Attempt 2 `PASS`, required T3 `semantic-pass` and durable
  isolated-PostgreSQL restart evidence for the one shared QR browser-access
  state.
- Reconciled the scheduler-owned `done` closure for
  [TASK-083-T3-FT-007-W1](tasks/TASK-083-T3-FT-007-W1.task.json) with final
  functional Attempt 3 `PASS` and T3 Red Verify Attempt 2 `semantic-pass` for
  authenticated best-effort client timing, effective display-expiry projection
  and unchanged persisted participant/session truth.
- Confirmed both records remain present in the authoritative task index and
  their final closure evidence links resolve. Kept FT-006, FT-007, EP-002,
  EP-003 and mapped RTM rows `planned` because later feature tasks and
  acceptance criteria remain open.


## [2026-08-28] Historical task lifecycle — done_for_prod reconciliation
- Reclassified `TASK-046`, `TASK-052`, `TASK-054` and `TASK-076` from `done`
  to `done_for_prod`: their development verification remains complete, while
  their own records retain deferred pilot or post-deployment acceptance.
- Preserved all pure `Production acceptance:` cards as `planned`; they remain
  excluded from development scheduling until the authorized deployed
  environment exists.
- Preserved `TASK-075` as `blocked`: its historical record has no final
  functional `PASS` or required T3 `semantic-pass`, so lifecycle migration
  cannot manufacture those missing development gates.

## [2026-08-28] VPS ingress — FRP WSS server foundation
- Зафиксирована замена заблокированного IKEv2/IPsec backhaul на исходящий FRP
  WSS/TLS transport через публичный Caddy/TCP 443.
- На VPS установлен и запущен `frps 0.70.1` только на loopback; разрешён один
  loopback application endpoint. Установлен `Caddy 2.11.4`, а его проверенная
  конфигурация ожидает выбранный публичный DNS hostname и выпуск сертификата.
- Подготовлены проверенные `frpc`/systemd-конфигурация и установочный пакет для
  центральной Kubuntu-машины; реальная WSS-связь и отключение legacy IPsec на
  центральной машине ещё не подтверждены.
- На VPS остановлены и отключены legacy strongSwan/XFRM units, удалён `ipsec0`
  и закрыты UDP 500/4500/55000 и ESP; конфиги и пакеты оставлены для обратимого
  восстановления.
- На центральной машине также остановлены и отключены strongSwan/XFRM units,
  удалён `ipsec0`, подтверждено отсутствие IPsec UDP-listeners. Legacy IPsec
  больше не участвует в runtime ни на одной стороне.
- Публичный DNS `face-time.moment-studio.ru` направлен на VPS, Caddy запущен и
  получил проверенный сертификат Let's Encrypt. Публичный application path
  пока отвечает `502` из-за отсутствующего loopback reverse endpoint.
- На центральной Kubuntu-машине установлен и запущен `frpc 0.70.1`; WSS login
  через публичный Caddy/TCP 443 успешен на фактическом мобильном канале. Остался
  application-layer blocker: локальный Caddy не слушает `127.0.0.1:8443`, из-за
  чего FRP health check не активирует reverse endpoint.

## [2026-08-25] FT-007 — approved task decomposition
- Reconciled the fresh task-plan `APPROVE` for FT-007 with Global Backbone
  Planning Revision `4`; schema validation covered all 86 indexed records, the
  DAG remained acyclic, Foundation closure remained intact and every
  `FT-007-AC-001..007` retained exactly one owner.
- Recorded `ARCHITECTURE_REVIEW: not_required` and the final five-card boundary:
  authenticated core timing, diagnostics evidence provider/privacy, realtime
  evidence integration, owner-ordered retention/latest result and production
  daily timer activation.
- Closed planning decomposition without promotion or lifecycle mutation:
  FT-007, EP-003, mapped requirements and `TASK-083..087` remain `planned`.
  Manual flow now routes to `/mb-doctor`; scheduler/autopilot flow routes to
  `/mb-doctor --strict`.

## [2026-08-22] Wave W4 — FT-004 result-session boundary reconciled
- Reconciled the scheduler-owned `done` closure for
  `TASK-072-T3-FT-004-W4` with fresh independent verification PASS and T3
  semantic-pass evidence.
- Reconciled the linear promo-session migration, atomic result publication,
  digest-only QR ticket storage, exact terminal idempotency and injected
  rollback proof; no search, assembly, singleton, startup or public-display
  ownership was added.
- Preserved FT-004, EP-002 and mapped requirements as `planned`: the final
  TASK-075 boundary and feature-level semantic gate remain open. No feature
  closure or terminal run decision was made by this sync.

## [2026-08-22] Wave W3 — FT-004 orchestration boundary reconciled
- Reconciled the scheduler-owned `done` closures for
  `TASK-071-T2-FT-004-W3` and `TASK-073-T3-FT-004-W3` with their indexed fresh
  verification evidence; TASK-073 retains the required T3 `semantic-pass`.
- Recorded the promo-owned deterministic result assembly correction for the
  exact-four selected-detection order and the singleton realtime
  admission/deadline boundary with busy, late-discard and cleanup evidence.
- Preserved FT-004, EP-002 and mapped requirements as `planned`: W4/W5 task
  cards and the feature-level semantic gate remain open. No promotion,
  dependent unblock, planning, spec or feature closure decision was made by
  this sync.

## [2026-08-22] Wave W2 — FT-004 exact search boundary reconciled
- Reconciled the scheduler-owned `done` closure for
  `TASK-070-T2-FT-004-W2` with its indexed independent T2 verification PASS.
- Reconciled the processing-owned exact compatible search, deterministic
  best-face grouping/order, query-quality threshold, independent occurrence
  searches and private-preview pHash evidence; no Promo/grouping/fallback
  boundary was added.
- Preserved FT-004, EP-002 and mapped requirements as `planned`: downstream
  FT-004 task cards and the feature-level semantic gate remain open. No
  promotion, dependency, planning, spec or contract decision was made by this
  sync.

## [2026-08-22] Wave W1 — FT-004 initial execution boundary reconciled
- Reconciled the scheduler-owned `done` closures for
  `TASK-068-T3-FT-004-W1`, `TASK-069-T2-FT-004-W1` and
  `TASK-074-T3-FT-004-W1` with their indexed independent verification
  evidence; TASK-068 and TASK-074 retain required T3 `semantic-pass` records.
- Reconciled the source-congruent execution evidence for the Staff active-date
  surface, native SFace/Buffalo reference-query preparation and deterministic
  startup interruption of stale realtime Attempts.
- Preserved FT-004, EP-002 and all mapped requirements as `planned`: later
  FT-004 tasks remain indexed and the feature-level acceptance gate is not
  complete. No promotion, dependent unblock, planning, spec or contract
  decision was made by this sync.
- Preserved the explicit TASK-049/TASK-051/TASK-056 blocked/deferred routes and
  TASK-065 planned/deferred route.

## [2026-08-22] FT-004 — approved task decomposition
- Reconciled the fresh task-plan `APPROVE` for FT-004 with Global Backbone
  Planning Revision `4`; all four coverage groups passed across the eight
  indexed schema-valid task cards, their dependencies and exact AC ownership.
- Recorded `ARCHITECTURE_REVIEW: not_required`. Both required Codex Luna
  co-review focus launches and retries were unavailable; no substitute model
  or co-review finding was used, and the main Reviewer retained the accepted
  verdict under the review contract.
- Closed planning decomposition without promotion or lifecycle mutation:
  FT-004, its mapped requirements and `TASK-068..075` remain `planned`.
  Manual flow now routes to `/mb-doctor`; scheduler/autopilot flow routes to
  `/mb-doctor --strict`.



## [2026-08-22] TASK-055 — safe degraded advertising integration
- Added the minimal client integration that completes the local attempt
  lifecycle after a BlazeFace load/detection failure, so the existing
  recoverable detector notice returns the loaded client to genuinely retryable
  advertising.
- Added the focused Playwright AC-008 matrix for missing camera, sensor/service
  unavailability, BlazeFace failure, central-service failure and absent
  optional assets. No offline metadata, fallback transport or new server path
  was introduced; T2 verification remains with `/verify`.


## [2026-08-18] Operator decision — OpenCV 5 migration strategy
- Added the operator-directed strategic plan for migrating the runtime from
  pinned OpenCV 4.10.0 to OpenCV 5, with SFace, InsightFace/Buffalo M,
  model-admission, runtime, rollback and acceptance gates.
- Kept implementation, dependency pins, database state, task statuses and
  TASK-045 evidence unchanged. The plan explicitly treats OpenCV as a runtime
  library rather than a model replacement and requires real model assets before
  runtime acceptance.

## [2026-08-18] OpenCV 5 dependency migration — source boundary
- Updated the sole runtime dependency pin to
  `opencv-python-headless==5.0.0.93`; Python, ONNX Runtime and InsightFace
  remain unchanged, while NumPy is pinned to `2.2.6` because the OpenCV 5
  wheel requires NumPy 2 on Python 3.11.
- Added focused OpenCV 5 regression/native smoke coverage for image
  decode/encode/resize and the existing YuNet/SFace APIs. Model loading is
  asset-mounted and does not create database revisions or SPA state.
- Container build and full runtime acceptance remain open because the current
  package-index/Docker environment could not complete dependency resolution;
  no product task status or TASK-045 evidence was changed.


## [2026-08-16] Wave W1 — closed TASK-063 managed kiosk policy boundary
- Reconciled TASK-063 as `done` after real host-managed Google Chrome policy
  evidence: `chrome://policy` reported the exact
  `https://localhost:8443` origin as Machine/Mandatory/OK and retained it
  after a browser restart.
- Added the bounded real-CDP listed/unlisted origin probe: the managed kiosk
  origin is `granted` for the Local Network Access permission names while an
  unlisted origin remains `prompt`; the kiosk page was restored afterward.


## [2026-08-16] Wave W1 — environment-bounded topology control
- Reconciled TASK-065 source outcomes and independent evidence for edge-only
  private-port bindings, with no credential, application, or internal-port
  mutation.
- Kept TASK-065 `blocked` because the bounded local scan observes a
  pre-existing native PostgreSQL listener on `127.0.0.1:5432` and no distinct
  outside observer is available; source-only Compose evidence is insufficient
  for the T3 topology claim. The record retains its exact pilot-host-capable
  resume route.

## [2026-08-14] Wave W7 — verified compatible processing and serving switch
- Reconciled the scheduler-owned `done` closures for
  `TASK-036-T3-FT-002-W7` and `TASK-040-T2-FT-002-W7` with their indexed
  functional evidence. TASK-036 retains its first semantic-fail and final
  retry `PASS` plus `semantic-pass`; TASK-040 has the scheduler-owned T2
  verification `PASS` for the guarded A-to-B switch and admission
  serialization.
- Reconciled `FT-002` as `verified` after all 23 indexed FT-002 task records
  reached `done` and the durable feature-level semantic gate is
  `semantic-pass`; the feature document is now `active` with its existing
  canonical SDD links unchanged.
- Advanced `REQ-ING-003`, `REQ-ING-004` and `REQ-REL-002` to `verified` in the
  RTM. Kept `REQ-SRCH-001`, `REQ-SEC-001` and `REQ-ARCH-001` `planned` because
  their other mapped product features remain unfinished.
- Kept `EP-001` `planned` because `FT-012` remains unfinished. Existing task,
  feature, epic and root routers already cover the reconciled documents; no
  task promotion/blocking, dependency, planning, spec, code or protocol-status
  decision was made by this sync.

## [2026-08-14] Wave W6 — reconciled processing observation closures
- Reconciled the already-recorded scheduler `done` states for
  `TASK-029-T2-FT-002-W6`, `TASK-031-T2-FT-002-W6`,
  `TASK-035-T3-FT-002-W6`, `TASK-038-T2-FT-002-W6`, and
  `TASK-039-T2-FT-002-W6` with their indexed independent evidence.
  `TASK-035` retains its Attempt 1 `semantic-fail` and final Attempt 2 `PASS`
  plus `semantic-pass`; the earlier successful functional verification remains
  part of that first unsuccessful T3 attempt.
- The closure evidence covers the bounded shared-worker Calibration hold and
  resume, immutable admission-lineage status selection, truthful independent
  uploader polling, the authenticated processing-health API, and the
  processing-owned exact-A read-only ordinary serving-revision guard. TASK-031's
  historical selector-gap stop report and its subsequent planning repair remain
  linked through TASK-038 rather than being replaced by the final PASS.
- Kept `FT-002`, its affected RTM rows, and `EP-001` `planned` because the W7
  processing-health UI/UAT and serving-control obligations remain indexed;
  `TASK-040-T2-FT-002-W7` remains `planned`. This sync made no promotion,
  dependent-state, task, evidence, product/design/spec, code, or Global
  Backbone Planning Revision `4` decision.

## [2026-08-14] FT-002 — admission-lineage status selector repair
- The existing immutable `Photo.admission_pipeline_revision_id` selects the
  one per-Photo status row as well as the SLO row: every state-bearing response
  field comes from the admission revision, while current-serving compatibility
  only derives `searchable` for that selected row.
- The Photo Processing API and verification matrix now cover the complete A+B
  compatibility matrix. An additional B state never replaces A or makes the
  read non-scalar; after serving switches to B the stable A response is
  `searchable=false`.
- Rebuilt only the affected plan surface: indexed planned
  `TASK-038-T2-FT-002-W6` owns the narrow selector repair, and blocked
  `TASK-031-T2-FT-002-W6` depends on it. `TASK-035` remains `ready`,
  `TASK-036` remains `blocked`, completed evidence remains intact, and Global
  Backbone Planning Revision stays `4`.

## [2026-08-14] Wave W5 — reconciled processing status, admission lineage and SLO closures
- Reconciled the already-recorded scheduler `done` states for
  `TASK-030-T3-FT-002-W5`, `TASK-037-T2-FT-002-W5`, and
  `TASK-028-T2-FT-002-W5` with their indexed independent `PASS` evidence;
  TASK-030 also retains its required `semantic-pass` evidence.
- The closure evidence covers authenticated per-Photo processing status,
  immutable Photo admission-revision lineage, and the full-population SLO
  projection that counts each accepted Photo exactly once through that
  lineage. TASK-028 retains its two historical verification failures and its
  final proof that later serving selection or state rows neither replace nor
  multiply the admitted Photo.
- Reconciled the bounded stale FT-002 edge-wording repair with the accepted
  lineage contracts. Fresh `/review-tasks-plan FT-002` returned `APPROVE` for
  Global Backbone Planning Revision `4`, with no blocker or queue/contract
  expansion.
- Kept `FT-002`, its affected RTM rows and `EP-001` `planned`: W6-W7
  obligations remain indexed. Existing downstream statuses remain unchanged,
  and this reconciliation made no task, dependency, evidence, lifecycle,
  product/design/spec, code, or Planning Revision change.

## [2026-08-13] Wave W4 — reconciled processing orchestration and projections
- Reconciled the already-recorded scheduler `done` states for
  `TASK-024-T2-FT-002-W4`, `TASK-027-T2-FT-002-W4`, and
  `TASK-032-T2-FT-002-W4` with their indexed independent `PASS` evidence.
  The closure evidence covers one-Photo owner-bound orchestration, compatible
  searchable-truth projection, and read-only queue/recovery health projection.
- `TASK-032` also records its bounded prerequisite removal of the W3 eager
  processing-package import cycle and independent packaged verification of the
  repaired cold-import path. The retained W3 HIGH observation is not resolved
  by this reconciliation; `/tech-debt wave W4` owns that advisory decision.
- Kept `FT-002`, the affected RTM rows, and `EP-001` `planned`: W5–W7
  obligations remain indexed. No promotion, dependency, product/design/spec,
  lifecycle, or task-plan-review decision was made by this reconciliation.

## [2026-08-13] Wave W3 — reconciled terminal publication and startup recovery closures
- Reconciled the already-recorded scheduler `done` state for
  `TASK-023-T3-FT-002-W3` and `TASK-025-T2-FT-002-W3` with their indexed
  independent `PASS` evidence; `TASK-023` also retains the required final
  `semantic-pass` evidence after its prior retained semantic-fail attempt.
- The closure evidence covers idempotent terminal face/derivative publication
  and atomic worker-startup recovery, while `FT-002`, its RTM rows and
  `EP-001` remain `planned` because W4–W7 obligations are still indexed.
- Preserved the TASK-023 Reviewer observation that a fresh import of
  `face_moment.serving_control.ingest_target` can reach the dependency-owned
  `processing.__init__` / `WorkerClaimRepository` export cycle as an advisory
  input for `/tech-debt wave W3`; this reconciliation makes no materiality,
  lifecycle, promotion, product, design or contract decision.

## [2026-08-12] Wave W2 — reconciled compatible-processing closures
- Reconciled the already-recorded scheduler `done` state for
  `TASK-019-T2-FT-002-W2`, `TASK-020-T2-FT-002-W2`,
  `TASK-021-T3-FT-002-W2`, `TASK-022-T2-FT-002-W2`, and
  `TASK-034-T3-FT-002-W2` with their indexed functional evidence; both T3
  tasks also retain required `semantic-pass` evidence.
- The closure evidence covers the native SFace and Buffalo M Photo paths,
  deterministic private derivatives, atomic bounded worker claim/failure, and
  independent private MinIO capacity observation.
- Kept `FT-002`, its RTM rows and `EP-001` `planned`: W3–W7 indexed obligations
  remain. No promotion, dependency, product/design/spec, or lifecycle decision
  was made by this reconciliation.

## [2026-08-12] Wave W1 — reconciled processing persistence and PostgreSQL capacity closures
- Reconciled the scheduler-owned `done` closure for
  `TASK-018-T2-FT-002-W1` with its fresh independent T2 `PASS` evidence for
  the compatible processing-persistence migration: unchanged refusal for a
  legacy revision and the empty direct linear persistence shape.
- Reconciled the scheduler-owned `done` closure for
  `TASK-033-T3-FT-002-W1` with its fresh functional `PASS` and required
  `semantic-pass` evidence for private read-only PostgreSQL capacity
  observation, bounded redaction and disposable-proof cleanup. The canonical
  Photo Processing specification records the accepted adapter and
  backend-only Compose view.
- Kept `FT-002`, its RTM rows and `EP-001` `planned`: indexed FT-002 W2–W7
  obligations remain. No promotion, dependency, product/design/spec, or
  lifecycle decision was made by this reconciliation.

## [2026-08-12] Wave W8 — verified independent photo admission
- Reconciled the scheduler-owned `done` closure for
  `TASK-017-T2-FT-001-W8` with its packaged/browser `PASS` evidence for the
  authenticated same-origin uploader, independent per-file outcomes and
  authoritative date projection.
- Preserved the complete `TASK-016-T3-FT-001-W7` history: the feature-level
  `semantic-fail`, Attempt 2 functional `FAIL`, and final Attempt 3
  `PASS` plus `semantic-pass` and scheduler re-closure. The feature retry
  records `SEMANTIC_VERDICT: semantic-pass` after the accepted early body-cap
  correction.
- Reconciled `FT-001` as `verified` after all its indexed tasks reached `done`
  and the required feature semantic gate passed. Advanced its exclusively
  owned `REQ-ING-001` and `REQ-ING-002` RTM rows to `verified`; kept
  `REQ-ING-003`, `REQ-SEC-001`, `REQ-ARCH-001` and `EP-001` planned because
  they retain separately indexed downstream feature obligations.
- No promotion, dependency, product/design/spec, or Epic lifecycle decision
  was made by this reconciliation.

## [2026-08-11] Wave W7 — reconciled secured upload-boundary closure
- Reconciled the scheduler-owned `done` closure for
  `TASK-016-T3-FT-001-W7` with its indexed execution evidence, fresh
  packaged-image functional `PASS`, and required independent T3
  `semantic-pass`. The closure proves the authenticated, rate-limited private
  upload boundary, exact standard failure mapping, accepted/duplicate response
  semantics, owner boundaries, redaction and disposable PostgreSQL/MinIO
  cleanup.
- Kept `EP-001`, `FT-001`, and the affected `REQ-ING-001`, `REQ-SEC-001` and
  `REQ-ARCH-001` RTM rows `planned`: the independent per-file photographer
  outcome remains owned by indexed W8 `TASK-017`, while the RTM rows also have
  later feature obligations.
- No task promotion, dependency change, feature/epic lifecycle transition, or
  product/design/spec decision was made by this reconciliation.

## [2026-08-11] Wave W6 — reconciled duplicate arbitration and crash-recovery closures
- Reconciled the scheduler-owned `done` closures for
  `TASK-013-T2-FT-001-W6` and `TASK-014-T2-FT-001-W6` with their indexed
  execution, fresh independent T2 verification and isolated PostgreSQL/MinIO
  evidence. The first proves one-winner duplicate arbitration and
  loser-only candidate cleanup; the second proves private pre-commit crash
  semantics and ordinary successful re-upload.
- Kept `EP-001`, `FT-001`, and the affected `REQ-ING-003` and
  `REQ-ARCH-001` RTM rows `planned`: secured upload and independent uploader
  outcomes remain owned by indexed W7/W8 work, while `REQ-ING-003` also has
  downstream FT-002 obligations.
- No task promotion, dependency change, feature/epic lifecycle transition,
  or product/design/spec decision was made by this reconciliation.

## [2026-08-11] Wave W5 — reconciled atomic Photo publication closure
- Reconciled the scheduler-owned `done` closure for
  `TASK-012-T2-FT-001-W5` with its indexed execution, fresh independent T2
  verification and isolated PostgreSQL evidence for atomic Photo plus initial
  serving `pending` publication and rollback.
- Kept `EP-001`, `FT-001`, and the affected `REQ-ING-003` RTM row `planned`:
  this closure verifies only `FT-001-AC-003`; duplicate exclusion, crash
  recovery, upload behavior and downstream FT-002 obligations remain indexed
  work.
- No task promotion, dependency change, feature/epic lifecycle transition,
  or product/design/spec decision was made by this reconciliation.

## [2026-08-11] Wave W4 — reconciled initial pending boundary closure
- Reconciled the scheduler-owned `done` closure for
  `TASK-009-T2-FT-001-W4` with its indexed execution and fresh independent
  functional-verification evidence for the processing-owned initial `pending`
  boundary, migration/transaction proof and cleanup.
- Kept `EP-001`, `FT-001`, and the affected `REQ-ING-003` RTM row `planned`:
  the atomic admission outcome remains owned by later `TASK-012`, and remaining
  FT-001 acceptance criteria and indexed tasks are not yet complete.
- No task promotion, dependency change, feature/epic lifecycle transition,
  or product/design/spec decision was made by this reconciliation.

## [2026-08-11] Wave W3 — reconciled credential, Photo identity and ingest-target closures
- Reconciled the scheduler-owned `done` closures for
  `TASK-005-T3-FT-001-W3`, `TASK-008-T2-FT-001-W3`, and
  `TASK-015-T3-FT-001-W3` with their indexed execution, functional-verification
  and closure evidence. Both T3 tasks end with fresh functional `PASS` and
  required `semantic-pass`; the T2 task ends with fresh functional `PASS`.
- Kept `EP-001`, `FT-001`, and the affected `REQ-ING-001`, `REQ-ING-002`,
  `REQ-ING-003`, `REQ-SEC-001`, and `REQ-ARCH-001` RTM rows `planned`:
  remaining FT-001 acceptance criteria and indexed feature tasks are not yet
  complete.
- No task promotion, dependency change, feature/epic lifecycle transition,
  or product/design/spec decision was made by this reconciliation.

## [2026-08-10] Wave W2 — reconciled staff-session and ingest-target closures
- Reconciled the scheduler-owned `done` closures for
  `TASK-004-T3-FT-001-W2` and `TASK-007-T2-FT-001-W2` with their indexed
  verification and closure evidence. TASK-004 ends with fresh functional
  `PASS` and required `semantic-pass`; TASK-007 ends with fresh functional
  `PASS` under its T2 obligations.
- Kept `EP-001`, `FT-001`, and the affected `REQ-ING-001`, `REQ-ING-003`,
  `REQ-SEC-001`, and `REQ-ARCH-001` RTM rows `planned`: remaining acceptance
  criteria and indexed feature tasks are not complete.
- No task promotion, dependency change, feature/epic lifecycle transition,
  or product/design/spec decision was made by this reconciliation.

## [2026-08-10] Wave W1 — completed FT-001 admission foundations
- Reconciled the already-recorded `done` closures for
  `TASK-003-T3-FT-001-W1`, `TASK-006-T2-FT-001-W1`,
  `TASK-010-T2-FT-001-W1`, and `TASK-011-T3-FT-001-W1` with their indexed
  functional verification, required T3 semantic verification, and durable
  task evidence.
- Kept `FT-001` and its `REQ-ING-*`, `REQ-SEC-001`, and `REQ-ARCH-001` RTM
  rows `planned`: their remaining acceptance criteria and linked product
  tasks are not yet complete.
- No task promotion, dependency change, spec/design change, or Planning
  Revision change was made by this reconciliation.

## [2026-08-06] Canonical boundary-map recovery
- Restored `.memory-bank/contracts/boundary-map.md` after framework sync had
  replaced it with an empty draft and preserved the accepted target without
  changing Global Planning Revision `4`.
- Retained the reconciled module inventory, explicit dependency graph, exact
  inline-contract headings and subject-spec routing required by the current
  DevRails boundary contract.
- Removed the duplicate `boundary-map-old.md`; the pre-overwrite and reconciled
  backup states remain recoverable from Git history.



## [2026-07-29] Client restart availability clarification
- Kept local advertising during transient server/network failure for an already
  loaded client.
- Removed the guarantee that tab reload or Chromium restart restores
  advertising while the central HTTPS origin is unavailable; normal automatic
  recovery resumes once that origin is reachable.

## [2026-07-28] Foundation current-state reconciliation
- Reconciled Product Brief, product, PRD, lifecycle and Architecture Spine
  wording with the verified Foundation: the executable server/storage substrate
  exists, while product behavior and the deployed pilot runtime remain target
  work.
- Preserved feature-level `not currently runnable` verification statements for
  product behavior that Foundation intentionally does not implement.

## [2026-07-24] Wave W0 — verified Foundation completion
- Reconciled scheduler-owned `done` closure for both indexed FT-000 tasks:
  TASK-001 has functional `PASS`, `semantic-pass` and
  `HUMAN_CHECKPOINT: done`; the TASK-002 final gate has independent
  `VERDICT: PASS`.
- Advanced only the already-decided `REQ-000` and FT-000 lifecycle surfaces
  from `planned` to `verified`; the global Planning Revision remains `2`.
- Linked the functional, semantic and final-gate verification reports plus the
  REQ-000/Foundation evidence map from the owning Foundation, feature and RTM
  surfaces. No findings, fixes, follow-ups or product tasks were created.

## [2026-07-24] Foundation executable-baseline queue
- Added `REQ-000` and the reserved `FT-000` pseudo-feature for the accepted
  greenfield executable baseline.
- Extended the existing testing spec with isolated build/typecheck/test,
  empty-database migration, private-storage, fake-engine, HTTPS and restart
  proof contracts without adding product behavior.
- Created the minimum two-task W0 queue: one T3 walking-skeleton
  implementation and one dependent T2 verification-only final gate.

## [2026-07-24] SDD verifier corrections
- Advanced Planning Revision once from `1` to `2` for three operator-approved
  corrections; the empty task queue made no plan stale.
- Fixed serving-revision recovery as an operator-owned manual action with no
  automatic rollback.
- Added the explicit Foundation `mypy` gate and an observable latest retention
  result.

## [2026-07-24] Global SDD backbone acceptance
- Completed the mandatory `/spec-design` gate with a
  `strict_architecture_scaffold`, `split-by-boundary-topic` strategy and
  Planning Revision `1`.
- Accepted the existing five-slice modular-monolith bundle without adding a
  new spec hub; fixed processing-projection reads, manual revision-switch
  orchestration and owner-ordered retention cleanup in the owning specs.
- Accepted `Foundation Required: true` because the greenfield repository has no
  executable release, entrypoints, migration/storage baseline or runnable
  build/start/test path.
- Kept product behavior outside Foundation and routed the next boundary to
  `/foundation-to-tasks`; the empty indexed task queue required no lifecycle
  invalidation.

## [2026-07-24] KISS session, offline-attempt and purge clarification
- Recorded explicit operator decisions as candidate `/spec-design` inputs; no
  successful global backbone run or positive Planning Revision was established.
- Clarified that soft delete blocks new search/result formation but does not
  invalidate an already issued Promo session.
- Simplified hard purge: it removes Photo-owned media/state while retaining
  existing Promo sessions, core Attempts and diagnostic evidence; UI/device
  loading skips unavailable media without rebuilding the session or `N`.
- Made client-only offline Attempt delivery best-effort and added the
  non-blocking 5–10-second server-communication failure notice.
- Fixed hard-purge concurrency by rejecting restore/restore-all for confirmed
  non-terminal snapshot members.
- Reconciled singleton realtime `busy` semantics, display acknowledgement,
  joint 19/20 acceptance, canonical feature links and supporting diagrams/docs.

## [2026-07-24] Photo Inventory Operations and SDD backbone
- Added role-scoped Photo soft delete/restore, project-wide restore-all and
  fixed-snapshot hard purge that retains core Attempts and diagnostic evidence.
- Added per-СПА 1/5/60-minute Photo processing counters with five-second Admin
  UI polling and traced the scope through `REQ-INV-*`, EP-001 and FT-012.
- Drafted the global SDD backbone and greenfield Foundation proposal; both
  remain candidate inputs until the first full `/spec-design` run.
- Drafted standard HTTP transport errors with typed capture/search outcomes and
  no custom error framework as candidate architecture input.
- Fixed one PostgreSQL application schema, shared SQLAlchemy `Base/MetaData`,
  one Alembic configuration/stream and ownership-safe foreign-key/cascade
  constraints across capability slices.
- Clarified that all application, backend, worker and deployment descriptions
  are target design; no working runtime or code exists yet.

## [2026-07-22] Pilot durability and QR-session simplification
- Removed backup as a pilot requirement and recorded accepted data loss after
  irreversible loss of the only primary disk/server.
- Corrected the greenfield boundary: the backend/admin application is delivered
  by this project; no existing backend or external IdP is assumed.
- Simplified QR continuation to one session-wide browser access state with no
  per-device grant records while retaining the 30-minute first-open and
  60-minute shared idle limits.
- Clarified that browser JPEG upload crosses the HTTPS backend boundary and
  private MinIO is never a browser endpoint.

## [2026-07-20] СПА terminology synchronization
- Updated the human-readable venue term from Latin spelling to Cyrillic `СПА`
  across current project Markdown documents.
- Preserved ASCII machine identifiers such as `spa_id`, `spa_client_token` and
  `SpaPromoClient`; changed the illustrative folder placeholder to `spa_code`.
- Reconciled PRD, Product Brief, requirements, epics, features, supporting
  discovery records and Memory Bank routers without changing product meaning.

## [2026-07-18] One-СПА pilot PRD clarification
- Completed the one-СПА pilot PRD clarification against the ratified
  Constitution and current Product Brief.
- Recorded the final Promo/QR, ingest-deduplication, diagnostics, retention,
  access and acceptance decisions directly in the normative PRD sections.
- Updated `mb-lint` so a complete PRD is validated by the absence of unresolved
  markers/blockers rather than by requiring a historical Clarifications section.

## [2026-07-17] Project Constitution ratification
- Ratified project governance as `medium` with KISS and an explicit
  `DO NOT Overengineering` principle.
- Set performance and stable Promo/QR as the current leading product priority.
- Simplified current product risks, gates, and open questions to the concerns
  that matter for the pilot.
- Aligned Product Brief, discovery inputs, invariants, testing guidance, and
  spec routing with the ratified priorities.

## [2026-07-11] Discovery input refinement
- Linked `IDEA_APP.md` and `IDEA_OS.md` as non-normative pre-PRD inputs.
- Preserved blocked SDD readiness until the formal brief/PRD/spec workflow runs.
- Split the central host into administrative `facemoment` and unprivileged
  autologin `display` users; required the standard Chromium sandbox.

## [2026-07-09] Initial setup
- Created Memory Bank skeleton
- Seeded core docs (product, requirements, testing, task registry)
