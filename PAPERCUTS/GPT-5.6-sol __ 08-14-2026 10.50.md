- The application image does not contain `/app/compose.yaml`; a combined
  host/image checksum probe therefore exited after confirming the four actual
  packaged TASK-036 files matched. Compare Compose through repository scope
  evidence instead of assuming deployment orchestration is copied into the
  runtime image.
- A browser-residue audit matched its own diagnostic shell because the command
  text contained both the task path and `playwright`. Exclude the probe's
  process ancestry when scanning `/proc` for task-owned browser processes.
