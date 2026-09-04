# Papercuts

- The focused disposable PostgreSQL tests emit Alembic's `path_separator` deprecation warning from `alembic.ini`; tests still pass. The configuration should declare `path_separator=os` when a maintenance task owns the warning cleanup.
