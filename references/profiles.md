# Harness profiles — conforming to a specific system without coupling to it

Looptimal's core is generic: it works on plain Claude Code (or anything) with zero configuration, defaulting to
a `loops/<slug>/` directory, a `verify.sh` gate, and a shell runner. But on a real harness (oh-my-claudecode,
oh-my-codex/OMX, or your own), you usually want the generated blueprint to use *that* system's conventions —
its state directory, its reviewer agent, its dispatch mechanism.

The design rule that makes this safe:

> **Looptimal does not know about harnesses. A harness (or you) declares a *binding* that Looptimal consumes.**

Looptimal depends only on the abstract **binding contract** below — never on a hardcoded "harness X uses Y"
matrix. That matrix is exactly what would rot every time OMC/OMX/SuperPowers cut a release, so it lives nowhere
in this repo. The *values* are owned by whoever owns the volatile thing (the harness, or your `~/.loopprint`).

## Resolution order (first found wins)
1. `./.loopprint/profile.yaml` — repo-local binding (checked into the project being worked on).
2. `~/.loopprint/profile.yaml` — your personal binding for this machine's harness.
3. **Runtime detection** — `scripts/loopprint-detect.py` probes for ecosystem *markers* (`.omc/`, `.omx/`,
   `omc` on `PATH`, …) and *names* what it sees, then suggests the matching example profile. It maps
   marker→ecosystem-name (stable) — it never embeds ecosystem→binding-values (volatile).
4. **Generic defaults** — no profile, nothing detected: pure portable behavior (`loops/<slug>/`, `verify.sh`).

## The binding contract (`profile.yaml`)
```yaml
harness: <name>              # informational, e.g. "oh-my-claudecode"
state_dir: loops/<slug>      # where the loop's state + artifacts live (generic default: loops/<slug>)
marker_path: ""              # optional: where to record the verifier verdict, if the harness enforces one
verifier:
  default: ""                # default EXTERNAL gate (command or named reviewer) for generated specs
dispatch:
  maker: ""                  # how this harness runs the maker step
  checker: ""                # how it runs an INDEPENDENT checker (must differ from maker)
runner: run-this-loop.sh     # the runner to emit/use
banner: ""                   # optional status-line convention
```

Only `state_dir` and `verifier.default` meaningfully change behavior; the rest are hints the wizard weaves into
the generated package and instructions.

## Shipped examples
[`profiles/`](../profiles/) contains **illustrative** example profiles (e.g. `oh-my-claudecode.example.yaml`).
They are **not maintained against harness releases** — copy one to `~/.loopprint/profile.yaml` and adjust it to
*your* installed version. Treat them as documentation of the contract, not a dependency. If your harness changes
its conventions, update *your* profile; Looptimal needs no release.

## Why this survives harness churn
The entity that changes owns its own binding. When oh-my-claudecode bumps a convention, whoever maintains that
harness (or you, in `~/.loopprint/profile.yaml`) updates the binding there — the same way a propagator keeps a
project's instructions current. Looptimal, depending only on the contract, is untouched.
