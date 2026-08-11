---
description: Minor workflow friction observed by the TASK-017 verification session.
---

- `playwright cli run-code` executes without Node's global `Buffer`, and its
  `setInputFiles` rejects a `Uint8Array` replacement. An attempted in-memory
  oversized-file probe failed before any request; use a pre-created file source
  when a large payload is mandatory.
