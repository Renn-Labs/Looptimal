# Verifier cookbook

Looptimal ships reusable verifier recipes in [`templates/verifier-library.yaml`](../templates/verifier-library.yaml). Each recipe is a bash snippet to paste into `loops/<slug>/verify.sh`. The contract is binary: **exit 0 = GREEN**, **non-zero = RED**.

## How the wizard picks a recipe

| Pattern | Default recipe | Why |
|-|-|-|
| **morty** | `repro-test` | Done = the bug no longer reproduces AND the full suite shows no regression. |
| **spec-driven** | `test-suite` | Done = the derived spec encoded as tests all pass. |
| **performance** | `benchmark-threshold` | Done = metric ≤ target AND the correctness suite still passes (two gates, every iteration). |
| **hybrid** | composite of sub-gates | Done = every sub-pattern's gate passes — paste each sub-recipe into `verify.sh` and require all to succeed before exit 0. |

For hybrid loops, wire sub-gates in sequence (or as functions) so a single weak gate cannot masquerade as the whole. Example composite shape:

```bash
set -euo pipefail
bash ./verify-repro.sh      # MORTY sub-gate: the bug stays fixed
bash ./verify-spec.sh       # Spec sub-gate: derived tests pass
bash ./verify-bench.sh      # Performance sub-gate: metric <= target
echo "verify: hybrid composite GREEN (all sub-gates passed)"
```

Each sub-gate is its own script; the composite exits 0 only when every one does. No sub-gate may source or exec the maker.

## Human in the loop: two distinct roles (not a verifier shape)

"Human approval" is the most-confused part of the taxonomy. It is **never a third verifier shape** next to `gate`
and `ratchet` — it appears in one of two orthogonal places, and conflating them is the original category error:

| Role | Axis | What it is | How to express it |
|-|-|-|-|
| **Human checkpoint** | **Stop / autonomy** | The runner **pauses** before/after an irreversible or high-stakes step so a person can accept or abort. It gates *when the loop proceeds*, not pass/fail. | `autonomy: checkpoint` + the `human_checkpoints:` list (shipped — the runner pauses at `checkpoint_mode: before\|after`). |
| **`human-vote`** | **Verifier (of last resort)** | The `verify.sh` gate **is** a recorded human `APPROVED` — used only when *no machine gate exists* for a judgment-heavy or irreversible goal. The human is the external checker, so maker != checker still holds. | The [`human-vote`](../templates/verifier-library.yaml) recipe (async file approval). |

The distinction that keeps both honest:

- A **checkpoint** is about **autonomy** — the loop already has a real verifier (gate / ratchet / critic-panel) and
  merely stops for a human at dangerous boundaries. Reach for it whenever an action can't be undone. Most loops want this.
- **`human-vote`** is about **verification** — the escape hatch for when you genuinely *cannot* encode the done-state
  as a machine check. It turns the loop into a checkpointed workflow whose throughput depends on a human, so use it
  sparingly: if any slice of the goal *can* be a machine gate, gate that slice and put the human on a checkpoint instead.

So the verifier *shape* axis stays exactly two — `gate` and `ratchet` (see
[patterns.md](patterns.md#verifier-shape-is-a-separate-axis)), with `critic-panel` a composition over the gate. Human
judgment is a **stop** or a **last-resort verifier**, never a shape.
