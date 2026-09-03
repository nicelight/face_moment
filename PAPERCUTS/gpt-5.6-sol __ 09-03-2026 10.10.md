# Papercuts

- `tests/staff_access/test_sessions.py::test_staff_session_root_paths_preserve_https_edge_routing`
  compares an exact one-tab Caddy snippet, while the committed
  `deploy/Caddyfile` nests the same handlers inside `route` and therefore uses
  two tabs. The test fails against unchanged HEAD topology before TASK-091's
  added matcher, despite the effective Caddy configuration being valid. The
  assertion should test routing semantics or tolerate structural indentation.
