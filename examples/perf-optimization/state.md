# Loop state — perf-optimization

> Durable record. Append, never reset until GREEN.

- **Goal:** Cut the `/api/search` endpoint p95 latency below 200 ms under the standard load profile, with no correctness regression in the integration suite.
- **Pattern:** performance
- **Verifier:** `bash examples/perf-optimization/verify.sh` — GREEN means p95 <= 200 ms on the standard profile AND the integration suite passes
- **Stop:** verifier GREEN · max_iters 5 · budget 30min · halt: touch `HALT`
- **Status:** OPEN
- **Started:** 2026-06-26T00:00Z

## Iteration log

| # | timestamp | change made | verifier | result / next |
|-|-|-|-|-|
| 0 | 2026-06-26T00:00Z | baseline: p95 412 ms on standard profile; integration suite GREEN | RED | hypothesis: N+1 query in `SearchService.rank_results` — add eager load on `document.tags` |

## Open hypotheses
- Profiler shows 68% of request time in repeated `SELECT` for tags; a single joined load should cut p95 roughly in half without touching ranking logic.

## Decisions & dead ends
- (none yet)

## Hand-off / escalation
- If still RED at iter 5: capture flamegraph and p95 trend — hand to a human for infra or index changes beyond code tweaks.
