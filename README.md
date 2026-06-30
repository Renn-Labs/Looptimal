<p align="center">
  <img src="assets/logo.svg" width="760" alt="Looptimal">
</p>

<p align="center"><em>from objective to verified outcome</em></p>

---

# Looptimal

Most "autonomous agent" failures aren't prompt problems. They're **missing-loop-component** problems: no durable state, no objective gate, no stop condition, the maker grading its own work. Looptimal fixes that at two levels.

At the **loop level**, it refuses to blueprint a loop until all four atoms are real:

| Atom | What it is | The failure it prevents |
|-|-|-|
| **Goal** | One objective, stated once | Scope drift, moving goalposts |
| **State** | A durable record of tried / failed / context | Re-doing work, amnesia across iterations |
| **Verifier** | A hard, **external** gate — test / build / lint / repro / rubric, or a separate reviewer | "Looks good to me" — the maker grading itself |
| **Stop** | Success criteria **and** a safety limit (max iters / budget / halt) | Runaway loops, burning budget on a stuck task |

Plus one rule that ties them together: **maker ≠ checker** — nothing is "done" until something *other than the thing that produced it* says so.

At the **outcome level**, Looptimal goes further: it frames a sealed acceptance suite, picks or rejects the right loop archetype, war-games the plan before you commit, dispatches maker and checker agents, and re-runs the sealed suite against live state before anything is called done. "Done" means the outcome is proved against live state by a separate verifier — not asserted by the agent that did the work.

The loop-design wizard (formerly the standalone LoopPrint) is embedded as **Stage 2: Design-loop**. It also runs as a direct fast-path when you only want a loop blueprint. One product, one `/looptimal` skill.

## Before the loop: the decision gate

The most valuable thing Looptimal does is sometimes tell you **not** to build a loop. A loop only pays off when:

1. **It recurs** — the setup cost amortizes over many runs.
2. **An objective gate can reject bad output** — you can write the verifier.
3. **The budget absorbs retries** — iterating is cheaper than getting it right once by hand.
4. **The agent can run what it writes** — there's a real feedback signal, not a human in every cycle.

If any fail, the honest answer is a single high-quality pass, not a loop. The metric that matters is **cost-per-accepted-change**, not tokens spent.

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

## Verify it yourself

```bash
python3 scripts/looptimal-lint.py --selftest        # plan-time gate self-test
python3 scripts/verify-outcome.py --selftest        # Stage-6 outer verifier self-test (tamper → RED)
python3 scripts/loopprint-lint.py examples/ci-triage/loop-spec.yaml   # loop-design wizard gate (GREEN)
python3 scripts/looptimal-doctor.py                 # install health check

# Worked example round-trip against live state:
python3 scripts/looptimal-lint.py examples/issue-to-pr-bugfix/mission.yaml
python3 scripts/verify-outcome.py --bundle examples/issue-to-pr-bugfix/evidence-bundle.json \
  --workdir examples/issue-to-pr-bugfix --repeat 3
```

## Security model (and its honest limit)

The outer verifier (`verify-outcome.py`) is deliberately hostile to the maker: it loads the **sealed** contract the bundle points at (never a maker-supplied one), refuses non-sealed paths, canonicalizes and matches the contract hash, re-runs every criterion authoritatively (the bundle's self-reported results can only *lose*), requires each check to invoke a sealed, workdir-contained oracle script, and re-hashes artifacts.

**Disclosed limit:** sealing rests on the *checker* controlling `--workdir` and the *framer* owning the `sealed/` directory via OS permissions. If the framer does not own `sealed/` and the checker does not control `--workdir`, the sealing guarantee does not hold at the deployment level. A cryptographic framer hash-pin (v1.1) removes even that deployment-level trust. Do not over-claim tamper-proofness.

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

Tooling: `loopprint-lint.py` gates the loop spec; `loopprint-ls.py` reports health of every loop in the repo (rot radar); `loopprint-report.py` computes cost-per-accepted-change from `metrics.jsonl`; `loopprint-skillify.py` promotes a GREEN loop to a reusable skill. Verifier recipes: [`templates/verifier-library.yaml`](templates/verifier-library.yaml). Schema contract: [`references/schema.md`](references/schema.md).

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
