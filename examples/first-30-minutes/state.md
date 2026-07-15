# Loop state — first-30-minutes

> Durable record for the first-30-minutes teaching example. **Append, never
> reset** until the loop reaches an honest terminal. Machine-readable state
> for a live run lives under the run root as `state/loop.json`; this file is
> the committed human-readable seed and the template `run_demo.sh` rewrites
> inside a temp run root.

- **Goal:** controlled RED → durable state → resume → honest terminal
  (`ACCEPTED` | `EXHAUSTED` | `BLOCKED`)
- **Pattern:** morty (reproduce rejection, fix lineage, verify, stop)
- **Verifier:** `bash examples/first-30-minutes/verify.sh` — GREEN means the
  package is complete and any supplied run root has consistent attempt lineage
  (demo gate; independent product approval is outside this example)
- **Stop:** ACCEPTED only after a validated outcome receipt · or EXHAUSTED at
  max_iters 2 · or BLOCKED on missing/unresolved source pin · instructional
  budget 30 minutes (not measured wall time)
- **Status:** OPEN
- **Started:** (set when a run root is created)

## Claim boundary

This example is a **controlled maker/verifier demonstration**. It does **not**
prove external customer proof, demand, market fit, ship-to-production readiness,
corpus certification, commercial listing status, or a managed offering. Its
embedded subprocess is not the independent approval authority.

## Vocabulary (do not collapse these)

| Term | What it is | What it is not |
|-|-|-|
| **Install / doctor verdict** | `looptimal-doctor` / tooling selftest health | An accepted outcome |
| **Attempt evidence** | Per-attempt JSON under `attempt-evidence/` (`kind: attempt-evidence`) | A `looptimal-receipt` |
| **Verifier verdict** | `GREEN` / `RED` / `BLOCKED` for one attempt | A terminal outcome receipt |
| **Accepted outcome receipt** | `looptimal-receipt.json` from `scripts/verify-outcome.py` before ACCEPTED commit | Attempt evidence or a self-grade |

## Iteration log

| # | timestamp | change made | verifier | result / next |
|-|-|-|-|-|
| 0 | (seed) | baseline — no attempts yet; source pin required before attempt 1 | — | hypothesis: attempt 1 omits lineage (induced defect) → controlled RED |

## Open hypotheses
- Attempt 1 fails closed when prior-rejection lineage is absent (controlled/induced RED).
- Resume reads attempt-1 state and increments lineage exactly once.
- Receipt is fully validated before ACCEPTED is committed; receipt failure leaves non-accepted state.
- Only ACCEPTED may retain `looptimal-receipt.json` from the product outcome verifier.

## Decisions & dead ends
- Silent fallback to `main` when a source pin is missing is forbidden → BLOCKED.
- Source pins bind full local git commit/tree object ids and blob digests from those objects.
- RED / EXHAUSTED / BLOCKED never emit `looptimal-receipt.json`.
- Forged or incomplete ACCEPTED state fails fail-closed re-verify on rerun.

## Hand-off / escalation
- If BLOCKED: restore an explicit immutable source pin (full commit object id); do not invent one.
- If EXHAUSTED: inspect attempt evidence and the durable RED reasons; widen
  the budget only with a human decision, never by forging a GREEN.
- Independent maker/checker approval for real product claims happens outside this demo.
