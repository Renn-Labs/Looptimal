# Throwaway prototypes for the agent-friendly plan

These scripts settle three design questions. They are not production code.
Do not import them from `scripts/` or `looptimal_cli/`.

Run from the repo root.

```bash
python3 prototypes/agent-friendly/wrong_lint.py
python3 prototypes/agent-friendly/docs_untracked_path.py
python3 prototypes/agent-friendly/dispatch.py
```

Each script prints a decision and exits 0 when the observation matches the
comment in `docs/agent-friendly-plan.md`.
