# TASK-123 execution papercuts

- Corrected during this task: using the lock-taking serving snapshot provider inside the native/profile transaction blocked same-venue Promo before its nonblocking slot check. The unchanged competing route test observed result after native watchdog release instead of immediate busy. Public orchestration now commits its immutable read snapshot before native work; fresh test observes busy in <1 s while inference remains held, then successful Promo QR. Provider semantics unchanged; see `.tasks/TASK-123-T3-FT-013-W6/competing-promo-failure.md`.
- Existing native test run warnings: Alembic config lacks path_separator and the repository's legacy multipart imports emit deprecation warnings. They do not affect the task gates; no unrelated cleanup performed.
