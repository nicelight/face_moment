---
description: Minor workflow friction observed in this agent session.
status: active
---
# Papercuts

- `docker compose build backend` invalidates and rebuilds the complete pinned dependency wheel layer after any `src/` change because the Dockerfile copies application source before `pip wheel`; two small source rebuilds each redownloaded and rebuilt the full ML dependency set.
