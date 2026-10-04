---
description: Accepted global SDD backbone, coverage matrix and Foundation routing for the Face Moment pilot.
status: active
last_updated: 2026-10-03
---
# SDD Spec Backbone

## Pre-PRD Spec Status

- Status: ready_for_prd
- Last updated: 2026-10-03
- Notes: Расширение публичного поиска и покупки принято в
  [PAYMENS_TS.md](../PAYMENS_TS.md); [PRD](prd.md) имеет complete clarification,
  vocabulary и accepted сценарий достаточны для `/prd-to-features`.
  Прежняя декомпозиция и accepted backbone Revision 4 сохраняются.

## Decomposition Inputs

Ниже сохранены inputs принятого Promo/QR baseline. Новый сценарий из
[PAYMENS_TS.md](../PAYMENS_TS.md) включает камеру сайта, локальную историю селфи,
скрытый browser profile с А/Б и единственным сбросом, выбор 1–3 площадок,
поиск по всем доступным датам внутри выбора, галерею, ЮKassa и архив.
Настройки дат Promo-поиска его не ограничивают. Общие `no_faces` доступны
только за даты личных совпадений данной площадки и бесплатны везде.
Retention shielding исходников/архивов и гарантии ссылки вопреки удалению
не приняты. Ownership принят в [Public Search API](contracts/public-photo-search-api.md)
и [Purchase API](contracts/photo-purchase-api.md).
Актуальные принятые правила единого marginal тарифа, заказа по нескольким
площадкам, бесплатного выбора, email, ручного возврата, frozen quote и
сохранения профиля/last visit находятся в [PRD](prd.md); они не открытые вопросы.
Локальное хранение — IndexedDB JPEG Blob, начальный resize до 960 px long edge
и quality 0.85 с проверкой качества; quota вызывает предупреждение и продолжение
без сохранения нового снимка, старые не удаляются. Личные preview имеют
снимаемый frontend watermark и фактическую ширину не менее 320 px. Originals
private; платёжная форма открывается после готовности ZIP, платная выдача —
только после server-confirmed payment. Promo/QR preview contract не меняется.

- User scenarios: PRD `Users / Actors`, `UX / Interaction Flow`, `Edge Cases /
  Failure Handling` and `Acceptance Criteria`; no separate scenario artifact is
  needed.
- Domain model: PRD `Data / Domain Model`, with terms disambiguated by
  [.memory-bank/glossary.md](glossary.md).
- Constraints: PRD `FR-CAP-01..17`, `NFR-PERF-01`,
  `NFR-SEC-02`, `NFR-SEC-07` and `NFR-ARCH-06`.
- Non-goals: PRD `Non-goals` and `Downstream SDD Inputs`.
- Risks: PRD `Risks` and `Edge Cases / Failure Handling`, including the
  accepted first-20 traversal trade-off and site-dependent camera geometry.
- Boundary hints: PRD source precedence, `FR-CAP-03`, `FR-CAP-09..17` and
  `NFR-SEC-02/07`; the accepted client boundaries do not redefine
  server-internal ranking, selection, embeddings or search.
  Галерея использует on-demand reduced JPEG из original, включая historical
  no_faces, по [Public Search API](contracts/public-photo-search-api.md);
  terminal states/derivatives/backfill не меняются.
- Lifecycle hints: PRD `Participant Promo and continuation flow`,
  `FR-CAP-01..03`, `FR-CAP-10..17` and `FR-DIAG-01..02`.

## Open Design Questions

- Продуктовых вопросов, блокирующих decomposition, не осталось; принятые
  решения и acceptance находятся в [PRD](prd.md) `FR-PUB` / `AC-PUB`.
- Public API/data/state/ownership приняты в четырёх subject specs ниже;
  configuration и compression fixtures проверяются owning tasks, без нового
  продуктового вопроса. Baseline FT-003 не переоткрывается.

## Handoff To /prd-to-features

- Ready: yes
- Required reads: [.memory-bank/constitution.md](constitution.md), the current
  [.memory-bank/prd.md](prd.md), [.memory-bank/glossary.md](glossary.md), this
  decomposition framing and the pure
  [.memory-bank/spec-index.md](spec-index.md).
- Stop conditions: decomposition не должна выдумывать scope или менять
  принятый baseline. Следующий шаг `/prd-to-features`, затем применимый
  decomposition review и `/spec-redesign` принятого backbone.
  Существующие task statuses, approvals и completed evidence сохраняются.

## New Scope Design Routing

- `/spec-redesign` завершён: `bounded`, Planning Revision `4` → `4`.
- Изменённая planning semantics: новый public auth/search/quote/order/ZIP/payment
  flow и их verification принадлежат FT-013..016. Exact specs:
  [profile](domains/browser-search-profile.md),
  [search](contracts/public-photo-search-api.md),
  [orders](domains/photo-orders.md), [purchase](contracts/photo-purchase-api.md).
- Существующие FT-001..012 сохраняют acceptance, APIs, slicing/dependencies и
  verification: новые public calls добавлены к прежним owners; Promo search/date/
  QR/evidence и Photo worker/purge не меняются. Gallery renderer не меняет
  no_faces/derivatives и не требует backfill. ZIP executor не занимает shared
  worker. Поэтому product-wide impact отсутствует.
- FT-013..016 task-linked: [планы](tasks/plans/index.md) содержат 20 indexed
  задач TASK-120–139 (7/6/4/3); все четыре независимых task-plan review —
  APPROVE при Planning Revision 4, см. [planning evidence](../.protocols/public-photo-task-planning/plan.md).
  Bounded repair markers для старых features не нужны; их statuses,
  completed evidence и unaffected approvals сохранены.
- Foundation decision/executable baseline не изменены. Выполнение идёт через
  последовательную reviewed queue и применимые tier gates; task-plan approval
  не означает завершения или verification features.

## Global Backbone Status
- Status: complete
- Planning Revision: 4
- Mode: strict_architecture_scaffold
- Architecture artifact strategy: split-by-boundary-topic
- Not applicable areas:
  - agent_io_contracts: not_applicable - the product has no agent/tool/model-I/O boundary.
- Notes: The full source, coverage and consequence review is complete. Public
  HTTPS/security boundaries, retention, one migration stream and irreversible
  hard purge justify strict mode; the implementation remains a KISS modular
  monolith. The registered system, boundary and lifecycle subjects are the
  smallest useful split. The selected client transport/proposal contract
  changed the durable global boundary from Planning Revision `3` to `4`;
  Foundation remains accepted, verified and complete.

## Source Roles

Target authority was applied in this order:

1. [.memory-bank/constitution.md](constitution.md) and explicit accepted
   operator decisions, including the selected FT-003 directions recorded in
   [.memory-bank/analysis/brainstorming/BR-004.md](analysis/brainstorming/BR-004.md)
   and the compatible client/media decisions in
   [IDEA_CLIENT.md](../IDEA_CLIENT.md);
2. the registered [system architecture](architecture/system-architecture.md),
   [boundary map](contracts/boundary-map.md),
   [lifecycle map](states/lifecycle-map.md) and
   [Foundation decision](foundation.md) for the accepted technical target;
3. [.memory-bank/prd.md](prd.md), [.memory-bank/requirements.md](requirements.md)
   and feature/epic composition for product behavior and acceptance;
4. Remaining `IDEA_*` files as overview/discovery evidence under the precedence
   declared in the PRD.

The verified Foundation is as-is evidence for substrate only. It does not
define product behavior or override the Planning Revision `4` target.

## Backbone Area Matrix

Матрица описывает принятый Revision 4 backbone; public extension покрыт
subject specs, consumer trace и маршрутом выше.

| Area | Status | Authoritative source | Notes |
|---|---|---|---|
| architecture_style | authoritative | [system architecture](architecture/system-architecture.md) | One greenfield Python/FastAPI modular monolith, one release and three server process entrypoints. |
| source_of_truth | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | PostgreSQL owns durable state in one application schema/migration stream; private MinIO owns stored binary bytes regardless of media classification; one capability owns every mutable invariant. |
| module_boundaries | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Five capability packages сохраняются; public profile/order ownership и additive boundaries приняты в Public Search / Purchase specs. |
| user_scenarios | authoritative | [.memory-bank/prd.md](prd.md) | Actors and scenario-sensitive flows are reviewed through clarified PRD behavior; no separate scenario document is required. |
| constraints | authoritative | [.memory-bank/constitution.md](constitution.md), [.memory-bank/prd.md](prd.md), [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | KISS, one shared server/model across venues, client/sensor and proposal boundaries, one-clock performance, security and no-backup limits are explicit. |
| non_goals | authoritative | [.memory-bank/prd.md](prd.md), [system architecture](architecture/system-architecture.md) | Baseline исключал paid delivery и standalone selfie; они приняты и спроектированы как отдельное public расширение. Local-detector miss proof/frame upload, speculative scale и extra lifecycle machinery остаются вне baseline. |
| domain_model | authoritative | [.memory-bank/prd.md](prd.md), [lifecycle map](states/lifecycle-map.md), [.memory-bank/glossary.md](glossary.md) | Product entities, face proposal occurrences, Photo visibility, purge, Attempt and session semantics are explicit. |
| data_flow | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Client proposals, existing server-owned search, Promo, diagnostics, inventory, revision recovery and retention have named owners and failure paths. |
| storage | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md), [lifecycle map](states/lifecycle-map.md), [Photo Processing](domains/photo-processing.md) | Private PostgreSQL/MinIO authority, ownership-safe persistence, optional capture media, retention and restart semantics are explicit; operator-managed model assets remain read-only deployment inputs outside the image and database. |
| api_contracts | authoritative | [boundary map](contracts/boundary-map.md), [sensor passage API](contracts/sensor-passage-api.md), [realtime attempt API](contracts/realtime-attempt-api.md) | Existing transport/FT-003 boundaries сохранены; public search/purchase endpoints, authorization, failures и provider integration заданы отдельными canonical contracts. |
| event_message_contracts | authoritative | [Purchase API](contracts/photo-purchase-api.md) | HTTPS YooKassa notification, server verification и idempotent transition; broker/event bus не добавлены. |
| agent_io_contracts | not_applicable | [.memory-bank/prd.md](prd.md) | No agent/tool I/O is a product or runtime boundary. |
| security_safety | authoritative | [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md), [.memory-bank/prd.md](prd.md) | Capture-derived media is not protected solely as media; credentials, infrastructure, commercial/personalized data, names/annotations and admin actions retain protection. |
| deployment | authoritative | [system architecture](architecture/system-architecture.md), [Photo Processing](domains/photo-processing.md), [.memory-bank/foundation.md](foundation.md) | The verified Compose walking skeleton provides the substrate; model-consuming roles bind only the committed validated revision from operator-managed read-only assets and fail closed before work on mismatch. Production deployment remains outside Foundation. |
| risks | authoritative | [.memory-bank/prd.md](prd.md), [system architecture](architecture/system-architecture.md), [boundary map](contracts/boundary-map.md) | Client proposal-order and site-camera trade-offs plus accepted pilot/deferred-complexity risks are explicit; missing or mismatched model assets keep the affected role unavailable instead of falling back. |
| open_questions | authoritative | [system architecture](architecture/system-architecture.md), [.memory-bank/prd.md](prd.md) | Baseline/public design принят; продуктовых blockers нет, owning tasking route указан выше. Feature-level completion остаётся у owning feature. |

## Foundation Decision

Canonical decision, gate anchors and evidence:
[.memory-bank/foundation.md](foundation.md).
