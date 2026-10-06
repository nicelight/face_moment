# Tech debt advisory — resumed Wave 12 / TASK-137

## Checked scope

Only the resumed TASK-137-T3-FT-016-W12 implementation delta for FT-016-AC-002:
`src/face_moment/promo/photo_payment.py`, `photo_payment_http.py`,
`src/face_moment/infrastructure/yookassa_payments.py`, their wiring in
`src/face_moment/entrypoints/backend.py` and `infrastructure/settings.py`,
the related `.env.example`/`compose.yaml` inputs, focused
`tests/promo/test_photo_payment_initiation.py`, and the adjusted order HTTP
assertion. Earlier Wave 12 delivery work and later confirmation/browser tasks
are outside this review. This is advisory; no new execution or external probe
was run.

## Evidence inspected

- `src/face_moment/promo/photo_payment.py:112-174`: owner/ready checks,
  durable attempt marker, frozen receipt, provider correlation and replay limit.
- `src/face_moment/promo/photo_payment_http.py:19-58` and
  `src/face_moment/infrastructure/yookassa_payments.py:14-54`: public admission,
  threadpool call, authenticated provider transport and response checks.
- `src/face_moment/entrypoints/backend.py:89-139`,
  `src/face_moment/infrastructure/settings.py:76-84,198-205`, `.env.example`,
  `compose.yaml`: runtime binding and configuration surface.
- `tests/promo/test_photo_payment_initiation.py:117-388`,
  `.tasks/TASK-137-T3-FT-016-W12/claim-evidence.md`,
  `.protocols/TASK-137-T3-FT-016-W12/verification.md`, and
  `.tasks/TASK-137-T3-FT-016-W12/TASK-137-T3-FT-016-W12-S-RED-VERIFY-final-report-docs-01.md`:
  focused local, external TEST and independent review evidence.

## Confirmed findings

None. The inspected evidence did not establish a material maintenance,
coupling, regression or reliability debt attributable to this delta.

## Uncertainty and limits

`photo_payment.py:160-174` holds the order row lock while the provider call
runs; `yookassa_payments.py:16,35` bounds that call with a ten-second timeout.
This is an observable same-order serialization mechanism, but the available
tests and evidence show no harmful contention or repeated change cost. It is
not admitted as debt without such evidence. Merchant fiscal issuance and a
real-shop SBP redirect remain separate proof limits in the task evidence, not
technical-debt findings for this implementation delta.
