# Papercuts

- Existing alembic.ini lacks path_separator; all TASK127 disposable migration runs emit Alembic DeprecationWarning about legacy prepend_sys_path splitting. Tests pass; config left unchanged because outside task.
