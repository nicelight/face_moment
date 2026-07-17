---
description: Глобальные инварианты и запреты проекта (MUST/NEVER).
status: active
last_updated: 2026-07-17
source_of_truth:
  - .memory-bank/invariants.md
---
# Invariants

## MUST

- Для текущего закрытого pilot и следующих нескольких версий приоритизировать
  измеримые latency и стабильность контура Promo/QR.
- Подтверждать новые acceptance gates текущим Product Brief или явным решением
  владельца продукта.

## NEVER

- Не добавлять speculative product gates для будущих версий в текущий pilot.

## Notes

- Эти правила основаны на ratified
  [.memory-bank/constitution.md](constitution.md) и должны быть пересмотрены
  вместе с ней при изменении product priorities.
- Ссылайся на этот файл из архитектурных, контрактных и execution docs, если
  правило является cross-cutting.
