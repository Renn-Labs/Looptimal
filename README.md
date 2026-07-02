<p align="center">
  <img src="assets/logo.svg" width="760" alt="Looptimal">
</p>

<p align="center"><em>from objective to verified outcome</em></p>

<p align="center">
  <a href="https://github.com/Renn-Labs/Looptimal/actions/workflows/ci.yml"><img src="https://github.com/Renn-Labs/Looptimal/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/Renn-Labs/Looptimal/stargazers"><img src="https://img.shields.io/github/stars/Renn-Labs/Looptimal" alt="GitHub stars"></a>
</p>

---

# Looptimal

Most "autonomous agent" failures aren't prompt problems. They're **missing-loop-component** problems: no durable state, no objective gate, no stop condition, the maker grading its own work. Looptimal fixes that at two levels.

## Prove it in under a minute

No clone required — this runs the real Stage-6 outer verifier against a fixture, tampers with the
fixture, and confirms the tamper is caught:

```bash
uvx --from git+https://github.com/Renn-Labs/Looptimal@v2.1.0 verify-outcome --selftest
```

```text
SELFTEST GREEN
```

That single line is the whole pitch: an honest bundle round-trips GREEN, then the same fixture is
tampered (the artifact the loop claims to have fixed is reverted) with `contract_hash` left
untouched — and the outer verifier catches it. A maker's self-reported GREEN can't buy a pass here;
only a live re-check can. This is why maker ≠ checker isn't a slogan in Looptimal — it's the
literal thing `verify-outcome.py` does on every run, including this one.

At the **loop level**, it refuses to blueprint a loop until all four atoms are real:

| Atom | What it is | The failure it prevents |
|-|-|-|
| **Goal** | One objective, stated once | Scope drift, moving goalposts |
| **State** | A durable record of tried / failed / context | Re-doing work, amnesia across iterations |
| **Verifier** | A hard, **external** gate — test / build / lint / repro / rubric, or a separate reviewer | "Looks good to me" — the maker grading itself |
| **Stop** | Success criteria **and** a safety limit (max iters / budget / halt) | Runaway loops, burning budget on a stuck task |

Plus one rule that ties them together: **maker ≠ checker** — nothing is "done" until something *other than the thing that produced it* says so.

This isn't a hunch. [SpecBench](https://arxiv.org/abs/2605.21384) measures reward hacking as the
pass-rate gap between a coding agent's visible validation tests and a held-out set covering the
same requirements, and finds that gap widens ~28 percentage points for every 10× increase in code
size — even as agents saturate the visible suite. [ImpossibleBench](https://arxiv.org/abs/2510.20270)
found cheating rates as high as 76% when test files are visible (even mutated), dropping to near
zero once they're simply hidden from the model. And Cursor's own [SWE-bench Pro
study](https://cursor.com/blog/reward-hacking-coding-benchmarks) found 63% of Opus 4.8 Max's
"successful" resolutions had been retrieved from git history or the public web rather than derived.
A maker that can see or grade its own gate will, on average, find the gate — not the fix.

At the **outcome level**, Looptimal goes further: it frames a sealed acceptance suite, picks or rejects the right loop archetype, war-games the plan before you commit, dispatches maker and checker agents, and re-runs the sealed suite against live state before anything is called done. "Done" means the outcome is proved against live state by a separate verifier — not asserted by the agent that did the work.

The loop-design wizard (formerly the standalone LoopPrint) is embedded as **Stage 2: Design-loop**. It also runs as a direct fast-path when you only want a loop blueprint. One product, one `/looptimal` skill.

## Demo

<p align="center">
  <img src="assets/demo.gif" alt="Looptimal: an honest verify-outcome selftest passes GREEN, then a worked critic-panel example runs a quorum PASS followed by a deliberate fail-flip that correctly gates RED" width="720">
</p>

Every line of output above is real — recorded by actually running `scripts/verify-outcome.py
--selftest` and `examples/critic-panel/run_demo.sh` (see `scripts/record-demo.py`, and
[`assets/demo.cast`](assets/demo.cast) for the raw asciinema recording). Nothing is scripted
sales copy; it's the outer verifier and the critic-panel quorum doing exactly what `SECURITY.md`
and the pitch above claim, on this exact codebase.

## Before the loop: the decision gate

The most valuable thing Looptimal does is sometimes tell you **not** to build a loop. A loop only pays off when:

1. **It recurs** — the setup cost amortizes over many runs.
2. **An objective gate can reject bad output** — you can write the verifier.
3. **The budget absorbs retries** — iterating is cheaper than getting it right once by hand.
4. **The agent can run what it writes** — there's a real feedback signal, not a human in every cycle.

If any fail, the honest answer is a single high-quality pass, not a loop. The metric that matters is **cost-per-accepted-change**, not tokens spent.

## Where this fits

Ralph loops, Claude Code's native loop support, and similar patterns **run** a loop — they're the
execution engine. Looptimal is the layer around whichever one you're already using: the Tier-0
decision gate that says whether a loop is even worth building before you build it, the sealed
definition of "done" frozen before the loop starts, and the independent verifier that re-proves the
outcome once it's finished. Maker ≠ checker applied to whatever loop you're already running — not a
replacement for it.

Spec-driven tools like GitHub spec-kit and AWS Kiro **write** a spec, which is a real and different
problem. Neither verifies the built thing against a live outcome once the spec is implemented —
that's exactly what Stage 6 (Verify-outcome) exists to close.

If you just want a loop that runs, those tools are great at that. Looptimal is for when you need to
prove what it claims when it's done — CI for agent done-claims, not another way to write or run one.

## The 8-stage pipeline

| # | Stage | What it does |
|-|-|-|
| 0 | **Frame** | Turn the objective into a hash-pinned, **sealed** acceptance suite; every criterion asserts an outcome (not a symptom) and binds a domain oracle. |
| 1 | **Analyze** | Produce a Capability Manifest — the domains, risks, and dependencies the work touches. |
| 2 | **Design-loop** | Run the loop-design wizard: pick the archetype (Task / Recurring / Supervised / Persistent-ratchet / Orchestration), or **REJECT** if it isn't a loop. |
| 3 | **Plan** | Build a consensus task graph with per-task acceptance tied to the sealed suite. |
| 4 | **Simulate** | War-game the loop forward N steps, pre-mortem the failure modes, harden the plan. |
| — | **Human GO** | Explicit approval to execute. No GO, no Execute. |
| 5 | **Execute** | Dispatch dynamic domain-expert sub-agents; maker ≠ checker; pre-action gates on irreversibles. |
| 6 | **Verify-outcome** | A **separate** checker re-runs the sealed suite against live state, ignoring self-reported GREEN. |
| 7 | **Persist** | Record evidence, decisions, rejected paths, and the next continuation state. |

The **Design-loop wizard** also runs as a direct fast-path when you only want a loop blueprint — say "design a loop" or "loop wizard" and Looptimal jumps to Stage 2 without outcome orchestration.

## Install

```text
/plugin marketplace add Renn-Labs/Looptimal
/plugin install looptimal@renn-labs
```

Invoke as `/looptimal` (v2.0.0). Say "design a loop for …" for the wizard fast-path.

**Other harnesses.** Looptimal is a self-contained folder skill (`SKILL.md` + `templates/` + `references/` loaded on demand). Clone once and symlink where your harness discovers skills:

| Harness | Install |
|-|-|
| **Claude Code (folder skill)** | `ln -s ~/looptimal ~/.claude/skills/looptimal` |
| **OpenCode** | `ln -s ~/looptimal ~/.config/opencode/skills/looptimal` |
| **OpenClaw / EClaw** | `ln -s ~/looptimal ~/.openclaw/skills/looptimal` |
| **Hermes** | `ln -s ~/looptimal ~/.hermes/skills/looptimal` |
| **Codex / OMX** | `cp -r ~/looptimal ~/.codex/skills/looptimal` (re-copy after updates) |
| **grok build** | add `~/looptimal/SKILL.md` entry to your `AGENTS.md` catalog |

**Just the tooling, no clone.** The doctor/lint/verify scripts are also installable as ordinary
console commands via [`uv`](https://docs.astral.sh/uv/)/`pipx` — useful if you only want to run
`looptimal-lint`/`verify-outcome` against your own mission files, not install the skill itself:

```bash
uvx --from git+https://github.com/Renn-Labs/Looptimal@v2.1.0 verify-outcome --bundle path/to/evidence-bundle.json
```

This is a convenience layer over the same `scripts/*.py`, not a separate implementation — pin to a
tagged ref (`@v2.1.0`, not `@main`) so the command doesn't silently move under you. Not yet on
PyPI; the `uvx --from git+...` form works today without one.

## Verify it yourself

```bash
python3 scripts/looptimal-lint.py --selftest        # plan-time gate self-test
python3 scripts/verify-outcome.py --selftest        # Stage-6 outer verifier self-test (tamper → RED)
python3 scripts/loopprint-lint.py examples/ci-triage/loop-spec.yaml   # loop-design wizard gate (GREEN)
python3 scripts/looptimal-doctor.py                 # install health check

# Worked example round-trip against live state — sealed with a demo HMAC key (see
# examples/issue-to-pr-bugfix/DEMO-KEY-NOT-SECRET.hex; loudly non-secret, never reuse it):
K=examples/issue-to-pr-bugfix/DEMO-KEY-NOT-SECRET.hex
python3 scripts/looptimal-lint.py examples/issue-to-pr-bugfix/mission.yaml --key-file "$K"
python3 scripts/verify-outcome.py --bundle examples/issue-to-pr-bugfix/evidence-bundle.json \
  --workdir examples/issue-to-pr-bugfix --repeat 3 --key-file "$K"
```

## Security model (and its honest limit)

The outer verifier (`verify-outcome.py`) is deliberately hostile to the maker: it loads the **sealed** contract the bundle points at (never a maker-supplied one), refuses non-sealed paths, canonicalizes and matches the contract hash, re-runs every criterion authoritatively (the bundle's self-reported results can only *lose*), requires each check to invoke a sealed, workdir-contained oracle script, and re-hashes artifacts.

**Disclosed limit:** by default, with no framer key configured, `canonical_contract_hash()` is an unkeyed sha256 self-digest over the contract mapping, and sealing rests on OS permissions — the *framer* owning `sealed/`, the *checker* controlling `--workdir`; the residual is that anyone who can write `sealed/` can also recompute a matching hash after tampering. Passing a framer key (`--key-file` or the `LOOPTIMAL_FRAMER_KEY` env var) switches to a keyed HMAC-SHA256 digest folded over every file under `sealed/` — the in-toto "materials" pattern — binding the oracle scripts a criterion actually invokes, not just the contract text naming them, so tamper-then-recompute no longer produces a matching hash. The residual that remains even when keyed is key custody: the key must live outside every maker-writable root, which is the checker's responsibility exactly like `--workdir` control already is. Do not over-claim tamper-proofness.

Loop blueprints generated by the Design-loop wizard (`run-this-loop.sh`, `verify.sh`) are executable code parameterized by `loop-spec.yaml` — treat them as code, not data. See [SECURITY.md](SECURITY.md).

## What Looptimal generates

From the **Design-loop wizard** (Stage 2 / design fast-path), a self-contained runnable package per loop:

- `loop-spec.yaml` — four atoms + pattern + budget, machine-readable
- `maker.sh` — the maker step, run as a **separate process** from the verifier (maker ≠ checker)
- `verify.sh` — the external verifier (exit-code gate)
- `state.md` — the durable State artifact, updated every iteration
- `run-this-loop.sh` — engine-agnostic runner; emits `metrics.jsonl` + `state.jsonl` each iteration
- `safety-checklist.md` — human checkpoints + budget limits + checker identity
- `flow.mmd` — Mermaid diagram of the loop

From the **full pipeline**, additionally: `acceptance-suite.yaml` + `acceptance-suite.sha256`, Capability Manifest, consensus task graph, Simulate report, and evidence bundle.

Tooling: `loopprint-lint.py` gates the loop spec; `loopprint-ls.py` reports health of every loop in the repo (rot radar) — `--update-index` opts a repo's loops into an append-only, local-only `~/.loopprint/index.jsonl`, and `loopprint-ls.py --global` reads it back ranked by cost-per-accepted-change across every repo that's opted in, flagging ROTTEN loops; deleting the index loses nothing, it's a rebuildable pointer cache; `loopprint-report.py` computes cost-per-accepted-change from `metrics.jsonl`; `loopprint-skillify.py` promotes a GREEN loop to a reusable skill. Verifier recipes: [`templates/verifier-library.yaml`](templates/verifier-library.yaml). Schema contract: [`references/schema.md`](references/schema.md).

## Updating

```bash
python3 scripts/loopprint-update.py            # dry-run: shows what would change, does nothing
python3 scripts/loopprint-update.py --apply    # performs it
```

Symlinked installs (Claude Code folder skill, OpenCode, OpenClaw/EClaw, Hermes) update for free
the moment you `git pull` the clone they point at. Copy-based installs (Codex/OMX:
`cp -r ~/looptimal ~/.codex/skills/looptimal`) don't — `loopprint-update.py` `git pull`s the clone
and re-syncs any copy-based install it finds at a known path, reporting exactly what changed
(never anything untracked — `.omc/`/`.buildlog/`-style local state is never synced). Dry-run by
default; nothing is touched without `--apply`.

## Troubleshooting

```bash
python3 scripts/looptimal-doctor.py        # diagnose, copy-pasteable fix per problem
python3 scripts/looptimal-doctor.py --fix  # apply safe repairs (chmod +x, relink dangling symlink)
python3 scripts/loopprint-doctor.py        # diagnose the loop-design wizard install
python3 scripts/loopprint-doctor.py --fix
```

Full symptom→cause→fix map per install type: [`references/troubleshooting.md`](references/troubleshooting.md).

## Design principles

- **The skill is the system.** Looptimal encodes *components and gates*, not a personality. It does not demand a banner on every reply or a confirmation incantation. A loop works because its parts are real, not because the model recites a mantra.
- **Stack-agnostic core.** The methodology and artifacts stand alone. Heavier orchestration (isolated sub-agent dispatch, a separate plan/judge reviewer, cross-repo leasing) is described generically — wire in whatever you use.
- **Honest gates.** A verifier the maker can satisfy by self-assessment is not a verifier. Looptimal always points the gate at something external.
- **Outcome, not completion.** "Tests pass" is not the bar; live-state re-verification against a sealed acceptance suite is.

## About

Built by **Erik Ford** at **[Renn Labs](https://github.com/Renn-Labs)** — an AI research & advisory firm. Looptimal distills one lesson from building autonomous agents: reliability comes from *loop components and verified outcomes* — durable state, external verification, stop conditions, maker ≠ checker — not from clever prompts.

## License

MIT © Renn Labs LLC
