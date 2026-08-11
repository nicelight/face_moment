# Papercuts

- A source-mounted `docker compose run` still imported the installed package
  rather than `/app/src`; set `PYTHONPATH=/app/src` for current-worktree
  pytest probes without rebuilding the image.
- The exact packaged-image pytest gate passes but emits a non-failing cache
  permission warning because the container user cannot create `/app/.pytest_cache`.
- `apply_patch` rejects a patch without its required `*** Begin Patch` header.
