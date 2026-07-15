# First 30 minutes — deliberate RED, durable state, honest terminal

A loop is not proven because its first output looks plausible. It is proven when
a **separate check can reject it**, the rejection survives in **durable state**,
and the next attempt responds to that evidence without inventing authority.

**First 30 minutes** is an **instructional operator budget**, not a measured
wall-clock guarantee. This example is a mechanism demo on the product path. It
is **not** external customer proof, demand evidence, corpus certification,
commercial listing status, a managed offering, or a ship-to-production seal.

## What you will see

| Step | What happens | Artifact |
|-|-|-|
| Source pin | Explicit immutable pin; missing/unresolved pin → `BLOCKED` (never silent `main`) | `source-pin.json` in the run root |
| Attempt 1 | Deterministic authentic `RED` (prior-rejection lineage absent) | `attempt-evidence/attempt-001.json` |
| Persist | Durable state written before any resume | `state/loop.json` + `state.md` |
| Attempt 2 / resume | Reads attempt-1 state; lineage increments once | `attempt-evidence/attempt-002.json` |
| Terminal | One of `ACCEPTED`, `EXHAUSTED`, `BLOCKED` | `terminal.json` |
| Outcome receipt | **Only** on `ACCEPTED`, via `scripts/verify-outcome.py` | `looptimal-receipt.json` |

## Four terms that must not be collapsed

| Term | Meaning |
|-|-|
| **Install / doctor verdict** | Tooling health (`looptimal-doctor`, structural `verify.sh` without a run root). Proves the package is present, not that an outcome passed. |
| **Attempt evidence** | Per-attempt JSON with `"kind": "attempt-evidence"`. Inspectable rejection or pass for **one** attempt. **Not** an accepted outcome receipt. |
| **Verifier verdict** | `GREEN` / `RED` / `BLOCKED` for a single attempt's external check. |
| **Accepted outcome receipt** | `looptimal-receipt.json` emitted **only** by `scripts/verify-outcome.py` after a GREEN live re-run. Never written for RED, EXHAUSTED, or BLOCKED. |

If a file is named like a receipt but carries `"kind": "attempt-evidence"`, it is
**attempt evidence**. Only `"kind": "looptimal-receipt"` from the product
outcome verifier is an accepted outcome receipt.

## Run the demo

From the repository root (stdlib + bash only; offline; no network):

```bash
bash examples/first-30-minutes/run_demo.sh
```

Default mode is the correctable path: attempt 1 `RED` → durable state →
attempt 2 `GREEN` → terminal `ACCEPTED` → product outcome receipt.

Other honest terminals:

```bash
bash examples/first-30-minutes/run_demo.sh --mode exhaust   # RED, RED → EXHAUSTED (no outcome receipt)
bash examples/first-30-minutes/run_demo.sh --mode block     # missing source pin → BLOCKED (no outcome receipt)
```

Resume / terminal idempotency (no new attempt evidence; hashes preserved):

```bash
ROOT=$(mktemp -d)
bash examples/first-30-minutes/run_demo.sh --root "$ROOT"
bash examples/first-30-minutes/run_demo.sh --root "$ROOT"   # rerun: same terminal, same hashes
```

Structural gate only (install-level; not an outcome receipt):

```bash
bash examples/first-30-minutes/verify.sh
```

## Files

| File | Role |
|-|-|
| `loop-spec.yaml` | Four atoms + stop budget (instructional 30 minutes) |
| `state.md` | Human-readable durable-state seed / vocabulary |
| `verify.sh` | External structural + optional run-root lineage gate |
| `run_demo.sh` | Deterministic offline demo engine (all modes) |
| `README.md` | This teaching contract |

## Claim ceiling

`INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF`

Allowed: mechanism claims about controlled rejection, durable state, attempt
lineage, terminal idempotency, and the product receipt path on ACCEPTED only.

Forbidden: fixed-duration success stories, external customer proof, demand or
fit claims, corpus certification, category leadership, commercial listing
status, managed offerings, external authority movement, or treating attempt
evidence as acceptance.
