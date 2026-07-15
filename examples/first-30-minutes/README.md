# First 30 minutes — controlled RED, durable state, honest terminal

A loop is not proven because its first output looks plausible. It is proven when
a **separate check can reject it**, the rejection survives in **durable state**,
and the next attempt responds to that evidence without inventing authority.

**First 30 minutes** is an **instructional operator budget**, not a measured
wall-clock guarantee. This example is a **controlled maker/verifier
demonstration** on the product path. It is **not** external customer proof,
demand evidence, corpus certification, commercial listing status, a managed
offering, or a ship-to-production seal.

## Governance (read this first)

| Layer | What it is | What it is not |
|-|-|-|
| This demo | A self-contained offline demo of the four loop atoms (goal, state, verifier, stop) with a deliberate RED→GREEN lineage | An independent product approval authority |
| Embedded subprocess check | Maker and checker run as distinct processes inside `run_demo.sh` so the teaching contract is executable offline | A substitute for independent review |
| Independent review | External maker ≠ checker governance (separate engines/agents) **outside** this demo | Anything claimed by the demo scripts alone |

Attempt 1’s RED is **deliberately induced** by a concrete candidate defect
(missing prior-rejection lineage) that the demo verifier is written to detect.
It is a scripted teaching failure, not a finding from independent review.
Attempt 2 repairs that defect by binding the sealed attempt-1 evidence once.

`ACCEPTED` is committed only after `scripts/verify-outcome.py` has produced and
validated a complete outcome receipt. A receipt failure leaves a recoverable
non-accepted state and a nonzero exit.

## What you will see

| Step | What happens | Artifact |
|-|-|-|
| Source pin | Full local git **commit + tree object ids** (not a tag label); missing/unresolved pin → `BLOCKED` (never silent `main`) | `source-pin.json` in the run root |
| Attempt 1 | Controlled `RED` on a concrete defect (prior-rejection lineage absent) | `attempt-evidence/attempt-001.json` |
| Persist | Durable state written before any resume | `state/loop.json` + `state.md` |
| Attempt 2 / resume | Reads attempt-1 state; lineage increments once | `attempt-evidence/attempt-002.json` |
| Receipt then terminal | Build/validate outcome receipt **first**, then atomic `ACCEPTED` | `outcome/looptimal-receipt.json` + `terminal.json` |
| Terminal | One of `ACCEPTED`, `EXHAUSTED`, `BLOCKED` | `terminal.json` |

## Four terms that must not be collapsed

| Term | Meaning |
|-|-|
| **Install / doctor verdict** | Tooling health (`looptimal-doctor`, structural `verify.sh` without a run root). Proves the package is present, not that an outcome passed. |
| **Attempt evidence** | Per-attempt JSON with `"kind": "attempt-evidence"`. Inspectable rejection or pass for **one** attempt. **Not** an accepted outcome receipt. |
| **Verifier verdict** | `GREEN` / `RED` / `BLOCKED` for a single attempt's external check (demo subprocess — not independent approval). |
| **Accepted outcome receipt** | `looptimal-receipt.json` emitted **only** by `scripts/verify-outcome.py` after a GREEN live re-run, **before** `ACCEPTED` is committed. Never written for RED, EXHAUSTED, or BLOCKED. |

If a file is named like a receipt but carries `"kind": "attempt-evidence"`, it is
**attempt evidence**. Only `"kind": "looptimal-receipt"` from the product
outcome verifier is an accepted outcome receipt.

## Run the demo

From the repository root (stdlib + bash only; offline; no network):

```bash
bash examples/first-30-minutes/run_demo.sh
```

Default mode is the correctable path: attempt 1 controlled `RED` → durable
state → attempt 2 `GREEN` → validated product outcome receipt → terminal
`ACCEPTED`.

Other honest terminals:

```bash
bash examples/first-30-minutes/run_demo.sh --mode exhaust   # RED, RED → EXHAUSTED (no outcome receipt)
bash examples/first-30-minutes/run_demo.sh --mode block     # missing source pin → BLOCKED (no outcome receipt)
```

Resume / terminal idempotency (full fail-closed re-verify; no new attempt
evidence; hashes preserved on success):

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
lineage, terminal idempotency, transactional acceptance (receipt before
`ACCEPTED`), and the product receipt path on ACCEPTED only.

Forbidden: fixed-duration success stories, external customer proof, demand or
fit claims, corpus certification, category leadership, commercial listing
status, managed offerings, external authority movement, treating attempt
evidence as acceptance, or presenting this demo’s embedded check as independent
product approval.
