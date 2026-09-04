---
description: Evidence-backed papercuts recorded during the autopilot scheduler session.
status: active
---
# Papercuts

- The first fresh `/verify TASK-100-T2-FT-011-W1` reported a functional failure
  to the scheduler but left no final verifier report and no task `verify` entry.
  The scheduler must replay the safe read-only verification to restore durable
  evidence before authorizing any correction attempt.
