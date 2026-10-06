# Tech debt advisory — Wave 13 / TASK-138

## Checked scope

Only the TASK-138-T3-FT-016-W13 implementation delta for FT-016-AC-003/004:
server-confirmed payment transition, YooKassa notification route, authenticated
provider GET, owner status refresh and the existing bearer delivery join. Actual
production files inspected were `src/face_moment/promo/photo_payment.py`,
`promo/photo_payment_http.py`, `promo/photo_order_http.py`,
`infrastructure/yookassa_payments.py` and `entrypoints/backend.py`; focused
coverage was `tests/promo/test_photo_payment_confirmation.py`. TASK-137
initiation and TASK-139 browser work were not reviewed as separate outcomes.
This is advisory; no new tests or external calls were run.

## Evidence inspected

- `src/face_moment/promo/photo_payment.py:185-233`: provider-truth comparison,
  locked payment transition and owner refresh.
- `src/face_moment/promo/photo_payment_http.py:23-47`: notification parsing uses
  only `object.id` as the pointer for server verification.
- `src/face_moment/infrastructure/yookassa_payments.py:25-42` and
  `src/face_moment/entrypoints/backend.py:89-123`: authenticated provider GET
  transport and runtime binding.
- `src/face_moment/promo/photo_order_http.py:107-142` and
  `tests/promo/test_photo_payment_confirmation.py:120-244`: owner status and
  focused confirmation/bearer probes.
- `.tasks/TASK-138-T3-FT-016-W13/claim-evidence.md`,
  `.protocols/TASK-138-T3-FT-016-W13/verification.md`, and
  `.protocols/TASK-138-T3-FT-016-W13/red-verification.md`: attempt 1 defect,
  attempt 2 correction, fresh functional PASS and independent semantic-pass.

## Confirmed findings

None. The inspected evidence establishes no material recurring change cost,
coupling, regression risk, reliability loss or maintenance burden attributable
to this delta. The full-object webhook rejection was corrected in attempt 2
and is retained only as historical evidence.

## Uncertainty and limits

Pending-order status refresh can call the provider (`photo_order_http.py:110-113`,
`photo_payment.py:225-233`). A provider outage therefore can make that refresh
return a technical error, but the available evidence shows no repeated outage
or material user impact; this is not admitted as debt. Browser continuation,
production receipt issuance and external real-shop SBP proof are outside this
TASK-138 change surface.
