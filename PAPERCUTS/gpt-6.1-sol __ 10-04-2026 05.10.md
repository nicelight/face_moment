# Evidence-backed papercuts

- Disposable PostgreSQL fixture runs Alembic logging fileConfig, which disables already imported application loggers. Mail-failure caplog tests initially missed actual logger.error calls; scoped test restores executor logger.disabled=False after migration. Production logging configuration was not changed.
