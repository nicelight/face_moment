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

Работающего приложения/backend/runtime пока нет: диаграммы показывают target
design. При расхождении product behavior определяет PRD, а architecture
mechanics — `arch_vision.md`:

1. [`.memory-bank/constitution.md`](../.memory-bank/constitution.md)
2. [`.memory-bank/prd.md`](../.memory-bank/prd.md)
3. [`arch_vision.md`](../arch_vision.md)
4. [`.memory-bank/glossary.md`](../.memory-bank/glossary.md) и
   [`.memory-bank/invariants.md`](../.memory-bank/invariants.md)
5. [`IDEA_APP.md`](../IDEA_APP.md), [`IDEA_INGEST.md`](../IDEA_INGEST.md),
   [`IDEA_OS.md`](../IDEA_OS.md), [`IDEA_DEBUG.md`](../IDEA_DEBUG.md)

Термины на диаграммах следуют
[`.memory-bank/glossary.md`](../.memory-bank/glossary.md): `Photo`, `reference
series`, core `Attempt`, Promo/search session и session-wide browser access —
разные сущности.
