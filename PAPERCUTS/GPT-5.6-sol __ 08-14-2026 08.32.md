# Papercuts

- `docker compose run` does not forward a shell-only disposable fixture variable unless the command also supplies `-e NAME`; the first TASK-036 UAT seed stopped before any database write with `KeyError`.
- `compose.yaml` hard-codes both capacity view paths, so setting a shell variable cannot create an unavailable-store UAT case. Task-owned disposable Compose overlays are required; the failed direct restart observed the unchanged normal path and did not alter data or source behavior.
- Host environment exposes `python3` but no `python` alias; the first local redaction invocation did not run and left trace files unchanged.
