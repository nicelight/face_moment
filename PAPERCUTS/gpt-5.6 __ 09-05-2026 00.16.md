# Papercuts

- `uv run --locked --env-file .env.local python -m pytest tests/inventory/test_recent_statistics.py tests/inventory/test_photo_inventory_ui.py` passes but emits Alembic's deprecation warning that `alembic.ini` has no `path_separator`. The warning is pre-existing configuration drift and outside TASK-108 scope.
