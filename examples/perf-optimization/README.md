# Example: Performance optimization loop

A worked LoopPrint blueprint for **cutting endpoint p95 below a target** without trading away correctness. It recurs (perf budgets slip as features land), has a dual external gate (benchmark + integration suite), and each iteration is a measurable experiment. Pattern: **performance** — profile, change one thing, re-benchmark, stop at target or the iteration cap.

Files:
- `loop-spec.yaml` — the four atoms, filled in.
- `verify.sh` — two gates: p95 <= 200 ms AND `pytest tests/integration -q` passes.
- `state.md` — the durable log, seeded with the baseline p95 measurement.

Adapt the benchmark script, target, and test paths to your stack before running.
