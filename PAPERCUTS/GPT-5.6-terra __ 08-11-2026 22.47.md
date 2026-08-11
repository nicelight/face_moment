# Papercuts

- A combined inspection command used an outdated feature filename and an unbalanced `jq` predicate, so the durable-state reads had to be rerun with the canonical paths and balanced checks.
