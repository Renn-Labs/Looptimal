# Example: Spec-driven remediation loop

A worked LoopPrint blueprint for bringing an undertested module up to a **derived spec** — the spec is written first, then implementation is driven until every case passes. It recurs (legacy modules lack coverage), has an objective gate (the spec suite), and retries are cheap. Pattern: **spec-driven** — write or extend spec cases, implement to green, stop when the spec suite passes or the iteration cap is hit.

Files:
- `loop-spec.yaml` — the four atoms, filled in.
- `verify.sh` — the external gate: `pytest tests/spec -q` must pass.
- `state.md` — the durable log, seeded with the baseline spec failures.

Adapt the module path and spec location to your codebase before running.
