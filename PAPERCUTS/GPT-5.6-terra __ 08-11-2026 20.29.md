# Papercuts

- `collaboration.wait_agent` rejects a sub-10-second wait even when only a brief mailbox poll is intended; use its documented minimum of 10 seconds.
