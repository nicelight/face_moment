# Papercuts

- An ad-hoc SQLAlchemy crash-recovery probe accessed `Photo.id` after its session closed and hit `DetachedInstanceError`; retain primitive IDs inside the session before asserting later projections.
- `docker compose port minio 9000` reported `invalid IP:0` instead of a clear no-published-port result; use Compose service inspection as the topology observation.
