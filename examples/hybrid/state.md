# Loop state — hybrid

> Durable record. Append, never reset until GREEN.

- **Goal:** Fix the perf-related bug where `/api/export` times out on large datasets while still meeting the export spec in `tests/spec/test_export_spec.py` — repro green, spec green, and p95 within budget.
- **Pattern:** hybrid
- **Verifier:** `bash examples/hybrid/verify.sh` — GREEN means repro test passes, export spec passes, and export p95 <= 5000 ms
- **Stop:** verifier GREEN · max_iters 7 · budget 40min · halt: touch `HALT`
- **Status:** OPEN
- **Started:** 2026-06-26T00:00Z

## Iteration log

| # | timestamp | change made | verifier | result / next |
|-|-|-|-|-|
| 0 | 2026-06-26T00:00Z | baseline: repro RED (`TimeoutError` at 30s on 10k-row fixture); spec 2/6 RED (`test_column_order`, `test_null_handling`); p95 unmeasured (times out) | RED | hypothesis: streaming writer buffers entire CSV in memory — switch to chunked `yield_per` and fix column ordering in the same pass |

## Open hypotheses
- The timeout and the `test_column_order` failure share a root cause: rows are accumulated then sorted in-memory instead of emitted in spec order during the DB cursor walk.

## Decisions & dead ends
- (none yet)

## Hand-off / escalation
- If still RED at iter 7: attach repro log, spec diff, and last p95 — hand to a human; may need a schema or infra change beyond a code fix.
