# Advisory technical debt — Wave 6 / TASK-114

## Проверенная область

Только TASK-114 из текущей очереди 114 → 106 → 115 → 116: исходная adapter delta `ff08b8d^..ff08b8d`, актуальный Buffalo adapter, тесты и task/feature evidence. Исторические чужие задачи Wave 6 не включены.

## Наблюдения

- `src/face_moment/processing/buffalo_adapter.py:129`: configured native preparation остаётся внутри существующего адаптера.
- `src/face_moment/processing/buffalo_adapter.py:173`: readiness открывается после detector/recognizer warmup; существующий helper проверки embedding используется повторно.
- `.protocols/TASK-114-T3-FT-002-W6/verification.md`: актуальные native и consumer probes подтверждают accepted AC-009.
- `.tasks/FT-002/FT-002-S-RED-VERIFY-final-report-docs-01.md`: feature integration и прежние owner boundaries сохранены.

Существенный technical debt в проверенной области не подтверждён. Этот вывод ограничен текущей maintenance delta и не является аудитом всего репозитория.

## Подтверждённые замечания

Нет.
