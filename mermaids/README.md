# Face Moment diagrams

Эта папка содержит шесть обзорных Mermaid-диаграмм для быстрого понимания
текущего one-СПА pilot.

> Статус: диаграммы визуализируют принятые product и architecture contracts.
> Они не утверждают, что показанные компоненты уже реализованы в коде.

## Граница текущего pilot

Текущий pilot заканчивается проверенной phone continuation page после сканирования QR. Payment, выдача originals и standalone selfie-search относятся к post-pilot продукту или отдельной зависимости.

## Диаграммы

| № | Файл | На какой вопрос отвечает |
|---:|---|---|
| 1 | [01-product-context.md](01-product-context.md) | Кто пользуется системой и где проходит граница pilot? |
| 2 | [02-end-to-end-pilot-flow.md](02-end-to-end-pilot-flow.md) | Как выглядит полный путь от upload до phone continuation? |
| 3 | [03-runtime-architecture.md](03-runtime-architecture.md) | Какие процессы и хранилища работают под капотом? |
| 4 | [04-ingest-processing-lifecycle.md](04-ingest-processing-lifecycle.md) | Как JPEG становится searchable, soft-deleted/restored и hard-purged? |
| 5 | [05-realtime-promo-sequence.md](05-realtime-promo-sequence.md) | Что происходит после sensor trigger и как формируется Promo? |
| 6 | [06-diagnostics-and-calibration.md](06-diagnostics-and-calibration.md) | Как расследовать попытки и безопасно подбирать параметры? |

## Канонические источники

Verified Foundation предоставляет только executable substrate; product
behavior на диаграммах остаётся target design. Authority order совпадает с
`.memory-bank/spec-backbone.md`:

1. [`.memory-bank/constitution.md`](../.memory-bank/constitution.md) и явные
   operator decisions, включая [`IDEA_CLIENT.md`](../IDEA_CLIENT.md)
2. [System architecture](../.memory-bank/architecture/system-architecture.md),
   [boundary map](../.memory-bank/contracts/boundary-map.md) и
   [lifecycle map](../.memory-bank/states/lifecycle-map.md)
3. [`.memory-bank/prd.md`](../.memory-bank/prd.md), requirements и features
4. [`.memory-bank/spec-backbone.md`](../.memory-bank/spec-backbone.md) как
   readiness/coverage registry
5. [`.memory-bank/glossary.md`](../.memory-bank/glossary.md) и
   [`.memory-bank/invariants.md`](../.memory-bank/invariants.md)
6. [`IDEA_APP.md`](../IDEA_APP.md), [`IDEA_INGEST.md`](../IDEA_INGEST.md),
   [`IDEA_OS.md`](../IDEA_OS.md), [`IDEA_DEBUG.md`](../IDEA_DEBUG.md)
   только как subordinate overview/discovery evidence

Термины на диаграммах следуют
[`.memory-bank/glossary.md`](../.memory-bank/glossary.md): `Photo`, `reference
series`, core `Attempt`, Promo/search session и session-wide browser access —
разные сущности.
