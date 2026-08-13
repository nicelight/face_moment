# Papercuts

- Container recovery inspection referenced the conventional `docker-compose.yml`, while this repository uses `compose.yaml`; the useful inspection completed before the final `sed` failure, but the filename mismatch made the command exit non-zero.
- Cleanup of the temporary overlay base tag was refused because an existing exited container still references that image; the tag was left intact to avoid forcing deletion of environment-owned state.
- The same retained-container behavior recurred for the Attempt 2 overlay base tag; cleanup again required a force operation, so the harmless tag was preserved.
- TASK-028 overlay base-tag cleanup was likewise blocked by an exited container retaining the prior image; the tag was preserved instead of forcing environment-owned cleanup.
- TASK-028 Attempt 2 base tag was retained for the same exited-container reference reason; no force cleanup was attempted.
