# Loop state — first-30-minutes

> Durable record for the first-30-minutes teaching example. **Append, never
> reset** until the loop reaches an honest terminal. Machine-readable state
> for a live run lives under the run root as `state/loop.json`; this file is
> the committed human-readable seed and the template `run_demo.sh` rewrites
> inside a temp run root.

- **Goal:** deliberate RED → durable state → resume → honest terminal
  (`ACCEPTED` | `EXHAUSTED` | `BLOCKED`)
- **Pattern:** morty (reproduce rejection, fix lineage, verify, stop)
- **Verifier:** `bash examples/first-30-minutes/verify.sh` — GREEN means the
  package is complete and any supplied run root has consistent attempt lineage
- **Stop:** ACCEPTED after RED+resume · or EXHAUSTED at max_iters 2 · or
  BLOCKED on missing/unresolved source pin · instructional budget 30 minutes
  (not measured wall time)
- **Status:** OPEN
- **Started:** (set when a run root is created)

## Claim boundary

This example is an **instructional mechanism demo**. It does **not** prove
external customer proof, demand, market fit, ship-to-production readiness,
corpus certification, commercial listing status, or a managed offering.

## Vocabulary (do not collapse these)

| Term | What it is | What it is not |
|-|-|-|
| **Install / doctor verdict** | `looptimal-doctor` / tooling selftest health | An accepted outcome |
| **Attempt evidence** | Per-attempt JSON under `attempt-evidence/` (`kind: attempt-evidence`) | A `looptimal-receipt` |
| **Verifier verdict** | `GREEN` / `RED` / `BLOCKED` for one attempt | A terminal outcome receipt |
| **Accepted outcome receipt** | `looptimal-receipt.json` from `scripts/verify-outcome.py` on GREEN only | Attempt evidence or a self-grade |

## Iteration log

| # | timestamp | change made | verifier | result / next |
|-|-|-|-|-|
| 0 | (seed) | baseline — no attempts yet; source pin required before attempt 1 | — | hypothesis: attempt 1 will omit lineage and earn a controlled RED |

## Open hypotheses
- Attempt 1 fails closed when prior-rejection lineage is absent (authentic RED).
- Resume reads attempt-1 state and increments lineage exactly once.
- Only ACCEPTED may invoke the product outcome verifier and emit a receipt.

## Decisions & dead ends
- Silent fallback to `main` when a source pin is missing is forbidden → BLOCKED.
- RED / EXHAUSTED / BLOCKED never emit `looptimal-receipt.json`.

## Hand-off / escalation
- If BLOCKED: restore an explicit immutable source pin; do not invent one.
- If EXHAUSTED: inspect attempt evidence and the durable RED reasons; widen
  the budget only with a human decision, never by forging a GREEN.
