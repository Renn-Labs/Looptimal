# Verifier cookbook

LoopPrint ships reusable verifier recipes in [`templates/verifier-library.yaml`](../templates/verifier-library.yaml). Each recipe is a bash snippet to paste into `loops/<slug>/verify.sh`. The contract is binary: **exit 0 = GREEN**, **non-zero = RED**.

## How the wizard picks a recipe

| Pattern | Default recipe | Why |
|-|-|-|
| **morty** | `repro-test` | Done = the bug no longer reproduces AND the full suite shows no regression. |
| **spec-driven** | `test-suite` | Done = the derived spec encoded as tests all pass. |
| **performance** | `benchmark-threshold` | Done = metric ≤ target AND the correctness suite still passes (two gates, every iteration). |
| **hybrid** | composite of sub-gates | Done = every sub-pattern's gate passes — paste each sub-recipe into `verify.sh` and require all to succeed before exit 0. |

For hybrid loops, wire sub-gates in sequence (or as functions) so a single weak gate cannot masquerade as the whole. Example composite shape:
