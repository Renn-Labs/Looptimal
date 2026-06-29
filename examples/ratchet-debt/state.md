# Loop state — ratchet-debt

> Durable record. Append each iteration; never reset until budget exhausted or baseline reaches zero.

- **Goal:** Reduce committed technical-debt findings in `findings.txt` to zero, verified by a monotonically decreasing count against a committed baseline.
- **Pattern:** performance (ratchet)
- **Verifier:** `bash verify.sh` — GREEN means count <= baseline (no regression); advance tightens baseline post-accept
- **Stop:** budget 30 min · max_iters 50 · halt: touch `HALT`
- **Status:** OPEN
- **Started:** 2026-06-28T00:00Z

## Iteration log

| # | timestamp | finding resolved | count before | count after | verifier | baseline |
|-|-|-|-|-|-|-|
| 0 | 2026-06-28T00:00Z | seed — 8 items committed | — | 8 | GREEN (8 <= 8) | 8 |

## Open findings (seed)

1. `billing/invoice.py` — magic numbers
2. `auth/session.py` — dead branch
3. `data/loader.py` — bare except
4. `utils/pagination.py` — missing docstring
5. `config/settings.py` — mutable default argument
6. `db/migrations/0014_legacy.sql` — stale commented migration
7. `reports/aggregate.py` — divide-by-zero guard missing
8. `api/handlers.py` — missing type annotations

## Decisions & dead ends

- (none yet)

## Hand-off / escalation

- If still open at iter 50 or 30 min: commit baseline progress, open an issue with remaining findings, hand to team.
