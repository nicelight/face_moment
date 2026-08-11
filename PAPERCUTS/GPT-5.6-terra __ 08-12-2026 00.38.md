## Task-record verification array is heterogeneous

`TASK-013-T2-FT-001-W6.task.json` retains a legacy string alongside structured
verification entries, so a generic jq query that assumes every item has a
`stage` field aborts. Filter by `type == "object"` when inspecting mixed
historical evidence.
