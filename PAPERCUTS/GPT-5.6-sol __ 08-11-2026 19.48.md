- `docker compose run backend python .tasks/...` does not see task evidence because
  the backend image neither copies nor mounts `.tasks/`; mount the task artifact
  read-only explicitly when rerunning a verifier-owned probe from that directory.
