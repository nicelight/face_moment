# TASK-121 papercuts

- Карточка TASK-121 указывает advisory migration path `src/face_moment/infrastructure/migrations/versions/`, которого нет. Фактический общий Alembic stream находится в `migrations/versions/`; реализация использует существующий stream.
- Alembic выдаёт DeprecationWarning: в `alembic.ini` отсутствует `path_separator`; текущие миграции работают. Конфигурация не изменена вне задачи.
