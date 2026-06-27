# Loop state — spec-driven-remediation

> Durable record. Append, never reset until GREEN.

- **Goal:** Bring the undertested `billing/invoice.py` module up to the derived spec in `tests/spec/test_invoice_spec.py` — every spec case passes with no regressions elsewhere in the suite.
- **Pattern:** spec-driven
- **Verifier:** `pytest tests/spec -q` — GREEN means all derived spec cases pass — the module behavior matches the written spec
- **Stop:** verifier GREEN · max_iters 8 · budget 45min · halt: touch `HALT`
- **Status:** OPEN
- **Started:** 2026-06-26T00:00Z

## Iteration log

| # | timestamp | change made | verifier | result / next |
|-|-|-|-|-|
| 0 | 2026-06-26T00:00Z | baseline: 4/12 spec cases RED — `test_proration_partial_month`, `test_tax_jurisdiction`, `test_credit_note`, `test_rounding_half_up` | RED | hypothesis: proration and rounding share a missing `Decimal` quantize helper; fix that first |

## Open hypotheses
- Invoice math uses raw floats; spec expects `Decimal` with `ROUND_HALF_UP` — a shared `quantize_money()` helper may green three cases at once.

## Decisions & dead ends
- (none yet)

## Hand-off / escalation
- If still RED at iter 8: list remaining spec gaps and hand to a human — likely a product rule the spec author must clarify.
