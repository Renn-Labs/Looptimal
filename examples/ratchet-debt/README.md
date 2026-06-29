# Example: Ratchet — debt reduction loop

A worked LoopPrint blueprint for reducing a committed list of technical-debt findings using the
**ratchet** verifier shape. Each accepted iteration removes one finding; the committed `baseline`
integer tightens post-accept so the bar never slides back. Pattern: **performance**.

---

## The four atoms

| Atom | This loop |
|-|-|
| **Goal** | Reduce `findings.txt` to zero entries, proven by a monotonically decreasing count |
| **State** | `state.md` — append-only log of count, delta, and verifier result each iteration |
| **Verifier** | `verify.sh` — external, read-only gate: exits 0 iff `count <= baseline` |
| **Stop** | Budget: 30 min wall-clock; max iterations: 50; or touch `HALT` to abort early |

---

## Three-role separation

A ratchet loop has three structurally distinct roles — conflating any two breaks the integrity guarantee.

```
maker.sh           proposes a change (resolves one finding)
verify.sh          gates it:  READ-ONLY — never writes baseline
ratchet-advance.sh tightens:  the ONLY writer of baseline, called post-accept
```

The runner (`run-this-loop.sh`) enforces this as separate processes. No role may do another's job:

- `verify.sh` declares GREEN/RED but must not move the bar.
- `ratchet-advance.sh` moves the bar but only after the gate declares GREEN and the runner accepts.
- `maker.sh` proposes work but is never the checker.

---

## GREEN != done for a ratchet

A gate loop exits 0 when GREEN — goal met. A ratchet loop does **not**:

- GREEN means "count is no worse than baseline" — it proves regression-freedom, not completion.
- The loop stops on budget or max-iterations, whichever comes first.
- Progress is recorded in `baseline`, not in an exit code.

This is deliberate: a ratchet is a continuous-improvement discipline, not a one-shot fix.

---

## The committed baseline is the integrity record

`baseline` is a plain integer committed to the repo. After each accepted GREEN iteration
`ratchet-advance.sh` overwrites it with the new (lower) count. The **git diff of `baseline`**
is the durable, auditable progress record — no separate metrics database needed.

Safeguard: `verify.sh` is read-only. Even if the runner crashes mid-loop, the committed
`baseline` never regresses silently — only an explicit, accepted, passing iteration can tighten it.

---

## Standalone story

This example runs under **plain bash + coreutils** — no OMC, no plugins, no AI tools required:

```
bash examples/ratchet-debt/run_demo.sh
```

The demo copies committed fixtures into a tmpdir, runs the loop there, and prints the
before/after baseline. The committed `findings.txt` and `baseline` are never touched.
The same loop spec works identically under Claude Code, Codex, or any harness that can
invoke `bash run-this-loop.sh` — the runner is the only dependency.

---

## Files

- `loop-spec.yaml` — the four atoms, fully filled in.
- `findings.txt` — committed fixture: one debt item per line.
- `baseline` — committed integer: line count at seed (verify.sh is GREEN at rest).
- `verify.sh` — external, read-only gate.
- `ratchet-advance.sh` — sole writer of baseline; deterministic, no agent.
- `maker.sh` — deterministic demo maker (swap for any real dispatch).
- `run_demo.sh` — tmpdir-isolated demo runner.
- `state.md` — seed human-readable state.
