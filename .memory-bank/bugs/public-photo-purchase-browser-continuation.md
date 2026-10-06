---
description: Exhausted-retry browser purchase failure and bounded successor repair route.
status: active
last_updated: 2026-10-06
---
# Public photo purchase browser continuation

## Failure

[TASK139](../tasks/TASK-139-T3-FT-016-W14.task.json) exhausted initial attempt plus two retries and remains immutable failed evidence. Final independent served verification proves two implementation-only breaks of accepted FT-016-AC-001/005:

- Free-to-paid venue change after quote and before order POST sends no receipt email/method, gets422 and never opens payment form.
- Pending provider return followed by new public search leaves retry visible but sends no status GET for the retained order because the handler starts with an empty selection.

Native unit108, paidbrowser6 and freebrowser1 pass but do not cover these transitions. Earlier paid-unavailable guidance, server-order amount/paid-to-free mode and ordinary return retry corrections remain preserved; no claim of complete browser purchase or deployment readiness.

## Evidence

- [Independent final functional FAIL](../../.protocols/TASK-139-T3-FT-016-W14/verification.md)
- [Independent Reviewer report](../../.tasks/TASK-139-T3-FT-016-W14/cli-attempt3-verification.txt)
- [Historical semantic-fail](../../.protocols/TASK-139-T3-FT-016-W14/red-verification.md)

## Follow-up route

Normal `/feature-to-tasks FT-016` successor task planning and separate `/review-tasks-plan FT-016`, then readiness gates and bounded execution; TASK139 is not reopened for a fourth retry. Existing server-authoritative amount/email/payment and retained owner-order refresh semantics are fixed; no new schema, supplier, refund, retention or product behavior is required. Independently verifiable repair outcomes remain explicit, with served regressions for both supported paths and fresh functional/semantic gates. FT016/EP004 and remaining public REQs stay planned.

## Deployment boundary

Public site and both SSH hops accessible; current running release remains unchanged. Final runtime snapshot packaged smoke PASS and source/migration preparation review APPROVE do not replace failed browser acceptance. No Git release commit, remote source/env write, migration or restart was performed. Public TEST keys must not grant real originals; real-shop activation and SMTP setup remain separate missing operational inputs. Timer stop/start additionally requires interactive sudo on central host.
