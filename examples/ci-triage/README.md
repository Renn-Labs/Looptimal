# Example: CI-triage loop

A worked Looptimal blueprint for a classic good loop — **automatically triaging a failing CI run** on a
well-tested codebase. It recurs (CI fails often), has an objective gate (the test suite), retries are cheap, and
the agent can run the tests. Pattern: **MORTY** — reproduce the failure locally, fix the cause, verify against
the reproduction, stop at green or a 6-iteration cap.

Files:
- `loop-spec.yaml` — the four atoms, filled in.
- `verify.sh` — the external gate: the test suite must pass.
- `state.md` — the durable log, seeded with the baseline failure.

This is illustrative — adapt the commands to your stack before running.
