# Papercuts

- Packaged `docker compose run` pytest gates emit `PytestCacheWarning` because
  the image user cannot create `.pytest_cache` under `/app`. The tests still
  pass, but `-p no:cacheprovider` or a writable cache location would keep gate
  evidence clean.
