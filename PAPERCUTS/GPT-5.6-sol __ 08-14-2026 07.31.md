# Papercuts

- The current backend image does not include `httpx`; an initial task probe collected only an import-time setup failure. Reused the repository's dependency-free ASGI request helper pattern before rerunning the claim probe.
- A malformed empty `apply_patch` hunk for a protocol path was rejected before changing files; retried with the complete intended evidence patch.
- An evidence patch containing a multi-line command block missed one leading `+` and was rejected before changing files; retried with a complete added block.
- The retry of that evidence patch repeated the same missing-prefix mistake on `git diff --check`; no files changed before the corrected retry.
- An executor attempt to patch the verifier-owned `verification.md` no longer matched after independent verification updated it; no file changed, and the executor left verifier evidence untouched.
