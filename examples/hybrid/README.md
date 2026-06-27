# Example: Hybrid loop

A worked LoopPrint blueprint for a **perf-related bug that must also meet a spec** — reproduce the failure, fix root cause, and prove both correctness and speed. It recurs (timeouts surface after data growth), has a composite external gate (repro + spec + benchmark), and each iteration must satisfy all three. Pattern: **hybrid** — debug the repro, implement to spec, benchmark, stop when all gates pass or the iteration cap is hit.

Files:
- `loop-spec.yaml` — the four atoms, filled in.
- `verify.sh` — three gates: repro test, spec suite, and p95 benchmark.
- `state.md` — the durable log, seeded with the baseline timeout and spec failures.

Adapt the repro fixture, spec path, and benchmark script to your codebase before running.
