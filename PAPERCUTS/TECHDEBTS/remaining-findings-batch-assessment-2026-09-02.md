---
description: Evidence-backed repair batching assessment for the remaining repository findings under a 200k-token fresh-agent context.
status: active
---
# Оценка пакетов для оставшихся findings

## Проверенный scope

Проверены оставшиеся findings из
`PAPERCUTS/TECHDEBTS/tech-debt-2026-09-02.md`, названные code/test locations,
актуальные FastAPI/Caddy/browser/SQLAlchemy paths, связанные task cards,
feature `spec_design_links` и размеры обязательного fresh-agent prime и
канонических specs. Реализация не менялась.

Оценка рассчитана для полного цикла в одном fresh context: compliant priming,
чтение task-linked specs, discovery, изменение, focused verification,
разбор failures и handoff. Это не оценка только размера diff.

## Контекстный бюджет

- Обязательные `AGENTS.md`, Constitution, Memory Bank rules, backbone/index и
  GENERAL role занимают около `44 KB`, то есть примерно `11–15k` tokens.
- Общие system architecture, boundary map и lifecycle map добавляют около
  `69 KB`, или `17–23k` tokens.
- Один task card/plan и его feature/subject specs обычно добавляют ещё
  `15–45k` tokens; cross-feature repair может потребовать `50–70k`.
- Для code/tests, tool output, tracebacks, повторных прогонов и финального
  handoff нужно оставлять минимум `50–70k` tokens.

Поэтому безопасная цель — закончить repair примерно к `130–160k`, а не
планировать расход всех `200k`. Три findings в одном окне допустимы только на
бумаге: реальный красный test output способен один занять десятки тысяч tokens.

## Findings

### 2. Realtime paths продублированы в FastAPI и Caddy

Finding подтверждён. `deploy/Caddyfile:16` вручную перечисляет два paths, а
реальные handlers находятся в `entrypoints/realtime.py:146,307`. Сейчас список
синхронизирован, но ранее child route уже выпадал из edge surface.

Минимальный repair: один namespace matcher для принятого realtime API с тем же
body cap и proxy headers; неизвестные paths по-прежнему отвергает FastAPI.
Отдельный строгий Caddy allow-list нужен только при явном контракте, которого в
проверенных specs не найдено.

- Отдельный budget: `65–95k` tokens.
- Лучший пакет: вместе с finding 3, потому что они разделяют FT-003, Caddy,
  client-realtime verification и browser-runtime proof.

### 3. Browser recovery test ненадёжен

Finding подтверждён и немного шире исходной формулировки. В repository нет
`package.json`/lockfile, `playwright` CLI установлен, но Node не разрешает
`playwright/test`. От этого зависит также
`test_degraded_advertising.spec.mjs`. Recovery fixture сохраняет `sensor_id`,
тогда как production config ожидает `sensorId`, и после restart проверяется
raw localStorage, а не успешное чтение production-кодом.

Минимальный repair: один воспроизводимый project-managed browser-test runner и
проверка восстановленной конфигурации через production read/behavior boundary,
с очисткой persistent profile.

- Отдельный budget: `80–115k` tokens.
- В пакете с finding 2: `125–165k` суммарно благодаря общим specs и probes.

### 4. Effective display state вычисляется дважды

Finding подтверждён. `display_outcome.py:213-221` и
`client_timing.py:146-153` независимо реализуют один переход
`pending -> unconfirmed` на границе expiry.

Минимальный repair: одна Promo-owned pure projection function, используемая
обоими reads, плюс before/equal/after tests без изменения stored state или DB
schema.

- Fresh-agent budget: `70–100k` tokens.
- Делать отдельно: да; diff мал, но нужно прочитать Promo/display/diagnostics
  contracts FT-005/FT-007/FT-008 и доказать отсутствие semantic drift.

### 5. Engine создаётся на каждый HTTP request

Finding подтверждён в пяти adapters:
`platform/auth/http.py:131`, `inventory/http.py:214`,
`serving_control/http.py:160`, `diagnostics/http.py:259` и
`promo/http.py:470`. Каждый helper создаёт и уничтожает свой Engine, поэтому
pool не переживает один request. Realtime/model consumers уже показывают
рабочий process-lifecycle precedent.

Минимальный repair: один backend-lifecycle Engine/session factory, создаваемый
composition root и закрываемый при shutdown; HTTP adapters получают короткую
Session из этой factory. Не вводить DI framework, global hidden cache или
несколько pools.

- Fresh-agent budget: `145–185k` tokens при focused `--tb=short` verification.
- Делать строго отдельно. Это widest change surface: пять adapters, backend
  lifecycle, auth/inventory/promo/diagnostics specs и многочисленные test seams.
- Если discovery выявит нерешённый lifecycle/transaction contract, design и
  implementation должны разойтись по двум fresh contexts, а не переполнить
  один.

### 6. Revision switch требует чистую Session

Finding подтверждён: `ingest_target.py:131` вызывает `Session.begin()`, который
конфликтует с SQLAlchemy autobegin после обычного pre-read. Все текущие callers
в tests создают свежую Session, а пользовательского route нет, поэтому impact
пока латентный.

Минимальный repair при появлении caller: явно назначить transaction owner и
проверить pre-read + switch + rollback/commit semantics. Не использовать
savepoint как способ скрыть неясное владение outer transaction.

- Fresh-agent budget: `65–95k` tokens.
- Сейчас разумно отложить. Если делать — в новом context после finding 5,
  потому что общий DB lifecycle может изменить естественный caller boundary.

## Рекомендуемые пакеты

| Пакет | Findings | Оценка | Решение |
|---|---:|---:|---|
| A | 2 + 3 | 125–165k | Единственная выгодная пара: общий FT-003 edge/browser context. |
| B | 4 | 70–100k | Малый semantic refactor с отдельным proof. |
| C | 5 | 145–185k | Только один finding; высокий риск переполнения. |
| D | 6 | 65–95k | Отложить; при необходимости делать после 5 в fresh context. |

Практический предел для этого списка — **два findings за раз**, обычный размер
— **один**. Не рекомендуется объединять оставшиеся несвязанные items: они
почти не делят specs/proof и нарушают независимые task outcomes.

## Неопределённость

Оценки не являются tokenizer-exact: фактический расход зависит от формы task
card, количества полностью task-linked specs и объёма failure output. Для
finding 5 нет production load measurement. Эта неопределённость уже учтена
верхней границей и резервом, а не основанием объединять больше работы.
