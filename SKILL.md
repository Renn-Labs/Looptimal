---
name: looptimal
description: "Looptimal — turns an objective into a delivered, VERIFIED OUTCOME by designing, war-gaming, and running the right loop. Use on 'looptimal', '/looptimal', 'run an outcome loop', 'orchestrate this objective to done', 'plan and ship this goal', or any non-trivial objective that needs a sealed acceptance suite, the right loop archetype, and independent verification before you call it done. ALSO handles loop-design wizard requests ('design a loop', 'build a loop', 'new loop', 'loop wizard', or a vague recurring task to automate) via the 'design' fast-path (Stage 2 only, no outcome orchestration). Runs an 8-stage pipeline: 0 Frame (hash-pinned SEALED acceptance suite) → 1 Analyze (Capability Manifest) → 2 Design-loop (wizard: Task / Recurring / Supervised / Persistent-ratchet / Orchestration, or REJECT) → 3 Plan → 4 Simulate (roll forward N steps, pre-mortem, harden) → [human GO] → 5 Execute (domain-expert sub-agents, maker ≠ checker) → 6 Verify-outcome (separate checker re-runs the SEALED suite vs live state) → 7 Persist. Fast-path hints: say 'design' or 'loop wizard' for Stage 2 blueprint only; 'skip wizard' to bypass the interview in Stage 2; 'skip simulate' to jump to Plan after Design-loop with explicit risk callout; 'fast path' for Frame + Design-loop + Plan then stop. If install looks broken — skill won't trigger, a script errors, profile won't resolve — run 'looptimal doctor' via scripts/looptimal-doctor.py."
license: MIT
---

# Looptimal — outcome orchestrator

Turn an objective into a delivered, **verified outcome**: seal the acceptance criteria, pick or reject the right loop, war-game the plan, execute with domain experts, and gate completion on a separate verifier re-running the sealed suite against live state — never on self-reported GREEN.

The loop-design wizard (formerly the standalone LoopPrint) is embedded as Stage 2: Design-loop. It also runs as a `design` fast-path when you only want a loop blueprint without outcome orchestration.

## When to use
- "looptimal", "/looptimal", "run an outcome loop", "orchestrate this objective to done", "plan and ship this goal".
- A non-trivial objective where "done" must be proved against live state, not asserted by the agent that did the work.
- Multi-domain work needing a Capability Manifest, consensus plan, and maker ≠ checker at the outcome altitude.
- Recurring, supervised, ratchet, or orchestration patterns — after Design-loop confirms this is actually a loop.
- You want Simulate to war-game the plan before any autonomous execution.

## When to use the design fast-path
- "design a loop", "build a loop", "new loop", "loop wizard", or a vague recurring task to automate.
- You only want a loop blueprint (spec + artifacts) — no outcome orchestration.
- Jumps directly to Stage 2 (Decision Gate → wizard → artifact generation) and stops.

## When NOT to use
- A one-shot answer, quick edit, or conversational question → just do it well once.
- Analysis with no delivery obligation → answer directly or use esat.
- Irreversible, judgment-heavy actions with no human willing to hold the GO gate → recommend a human-gated process.
- Meta-loops ("run Looptimal to verify Looptimal", "auto-merge when Looptimal says GREEN") → Design-loop must REJECT.
- Symptom-only success metrics with no behavioral outcome oracle → re-Frame or REJECT.

## Operating rules (read first)
- This is a **skill**, not a persona or mode. Open with **one** activation line, then do the work.
- **Checkpoint-gated**: Frame → Analyze → Design-loop → Plan → Simulate each stop for brief status. Execute never starts without explicit human GO after Simulate.
- **Never auto-run irreversibles**: prod deploys, sends, payments, credential rotation, data deletion — pre-action human gates only.
- **Harness-decoupled**: resolve bindings from `./.looptimal/profile.yaml` → `~/.looptimal/profile.yaml` → `scripts/looptimal-detect.py` → generic defaults. Contract: [`references/agent-foundry.md`](references/agent-foundry.md).

**Activation line examples:**
- Full pipeline: *"Looptimal — framing this objective into a sealed outcome loop."*
- Design fast-path: *"Looptimal — blueprinting this loop."*
- **Invoked bare** (no objective): ask exactly one question — *"What outcome should be true when we're done?"* — then Stage 0. For design-only bare invocation: *"What's the recurring task you want to blueprint?"* — then Stage 2.
- **Objective already given**: acknowledge in one line and enter Stage 0 (full) or Stage 2 (design).

### Resolve the binding (Stage 0 preamble)
```bash
python3 scripts/looptimal-detect.py          # probe markers; suggest profile
# or read ./.looptimal/profile.yaml → ~/.looptimal/profile.yaml
```
Supplies `state_dir`, `dispatch.maker`, `dispatch.checker`, `verifier.default`, optional `banner`. Generic defaults: `loops/<slug>/`, shell verifier.

---

## The 8-stage pipeline

| Stage | Name | Job | Reference |
|:-----:|------|-----|-----------|
| 0 | **Frame** | Turn the objective into a hash-pinned, **SEALED** acceptance suite. Every criterion asserts an outcome (not a symptom) and binds a domain outcome-oracle. Inputs are non-writable by the maker. Emit `acceptance-suite.yaml` + `acceptance-suite.sha256`. | [`references/pipeline.md`](references/pipeline.md) |
| 1 | **Analyze** | Produce a Capability Manifest: domains, integration map, risks, dependencies. Delegate deep definition work to **esat** when stakes warrant tri-model stress-test. | [`references/pipeline.md`](references/pipeline.md) |
| 2 | **Design-loop** | Run the loop-design wizard (see below). Pick archetype — **Task** (bounded delivery), **Recurring** (scheduled freshness), **Supervised** (autonomous within guardrails), **Persistent-ratchet** (each pass strictly improves an outcome metric), **Orchestration** (multi-actor / multi-repo) — or **REJECT** if not-a-loop / meta-loop. | [`references/pipeline.md`](references/pipeline.md) |
| 3 | **Plan** | Build a consensus task graph: nodes, dependencies, per-task acceptance hooks tied to the sealed suite, blast-radius tags, rollback notes. | [`references/pipeline.md`](references/pipeline.md) |
| 4 | **Simulate** | Roll the loop forward N steps; pre-mortem failure modes (reward-hacking, silent failure, partial completion, env drift); harden the plan. Present findings and any deltas to the sealed suite (re-hash + user ack). | [`references/pipeline.md`](references/pipeline.md) |
| — | **Human GO** | Explicit approval to execute. Surface top risks, irreversibles, open dependencies. No GO → no Execute. | [`references/pipeline.md`](references/pipeline.md) |
| 5 | **Execute** | Spin up dynamic domain-expert sub-agents per the binding profile. Maker ≠ checker at iteration gates. Resumable, idempotent steps; rollback paths for partial failure. Pre-action gates on irreversibles. | [`references/pipeline.md`](references/pipeline.md) |
| 6 | **Verify-outcome** | A **separate** checker re-runs the SEALED suite against **live state**. Ignore loop self-reported GREEN. Gate on an evidence bundle. | [`references/pipeline.md`](references/pipeline.md) |
| 7 | **Persist** | Write durable state: objective hash, suite hash, what worked/failed, oracle results, remediation class, resume pointers, lessons for next run. | [`references/pipeline.md`](references/pipeline.md) |

### Stage transitions (default)
- 0 → 1: sealed suite exists, every criterion has an oracle, hash recorded.
- 1 → 2: Capability Manifest covers all material domains and integration edges.
- 2 → 3: archetype chosen (or REJECT issued with honest alternative).
- 3 → 4: task graph is acyclic, every node hooks to a suite criterion, safety limits set.
- 4 → GO: simulation report delivered; plan hardened; irreversibles tagged.
- GO → 5: explicit human approval captured in state.
- 5 → 6: maker declares iteration complete — informational only; checker owns truth.
- 6 → 7: evidence bundle GREEN; else FAIL with remediation class and resume pointer.

### Resume
If a prior run exists under `state_dir` and the objective hash matches, resume from the last incomplete stage. If the objective changed materially, re-Frame (new suite hash). Never resume across a REJECT without a fresh Design-loop.

---

## Stage 2 — Design-loop wizard

The wizard enforces the four atoms, runs an archetype decision gate, and generates the full artifact package. It lives in Stage 2 of the full pipeline and also runs standalone as the `design` fast-path.

### Wizard entry
- **Full pipeline** (called from Stage 2): goal is the outcome from Stage 0. Skip to Step 0.5.
- **Design fast-path** (direct invocation): open with one activation line; if no goal given, ask one question first.

### Step 0.5 — Resolve the binding
Run `scripts/loopprint-detect.py` (or read `./.loopprint/profile.yaml` → `~/.loopprint/profile.yaml`) to get `state_dir`, `verifier.default`, `dispatch`, `marker_path`, `runner`, `banner`. Generic defaults: `loops/<slug>/`, `verify.sh`. Contract: [`references/profiles.md`](references/profiles.md). Never hardcode harness conventions.

### Step 1 — Decision Gate (+ route)
Run the Tier-0 test in [`references/decision-gate.md`](references/decision-gate.md): 4 conditions + 30-second checklist. Report **Pass** or **Fail** with one line of reasoning per condition. On Fail, recommend the honest alternative and **stop unless the user overrides**. On Pass, route by archetype. Routing never overrides a Fail.

### Step 2 — Goal Refinement
Ask **3–5 targeted questions** (not more):
1. Sharpened goal — one sentence, testable.
2. Recurrence / frequency — confirms the loop amortizes.
3. Verification method — what *external* signal says an iteration succeeded?
4. Irreversible risks — what can't be undone? (→ human checkpoint)
5. Autonomy level — fully autonomous, checkpoint-gated, or dry-run?

### Step 3 — Primitive Enforcement
Force a concrete value for each atom. Do not proceed with any left vague:
- **Goal** — the one-sentence objective from Step 2.
- **State** — durable artifact path from the binding's `state_dir`; what it records: attempt log, what failed, current hypothesis, context.
- **Verifier** — the exact external command or named reviewer. If the only proposed check is the same agent self-assessing, **reject it** and find a real gate. Maker ≠ checker.
- **Stop** — success criteria **and** a safety limit (max iterations, token/time budget, explicit halt). No loop ships without a safety limit.

### Step 4 — Profile Selection
Pin the archetype's full profile — work pattern (from [`references/patterns.md`](references/patterns.md)) and verifier/stop shape:
- **MORTY** — specific bug; verifier = reproduction test; finish-gate.
- **Spec-Driven** — conform to a spec; derived tests pass.
- **Performance** — metric target (gate), or open-ended ratchet: `verifier.shape: ratchet` + `stop.budget`.
- **Hybrid** — composite gate.
- **Critic-panel** — `verifier.kind: critic-panel`; `panel: {n, quorum_k, threshold}`; judge ≠ maker; cross-provider strongest.
- **Supervised** — human checkpoints between autonomous runs; `autonomy: checkpoint`.

Pattern = the *work*; verifier shape/kind + stop + autonomy = *how it's gated and when it stops* — orthogonal axes.

### Step 5 — Artifact Generation
Create `loops/<slug>/` and write the package from [`templates/`](templates/):

| File | Purpose |
|-|-|
| `loop-spec.yaml` | Four atoms + pattern + budget, machine-readable |
| `state.md` | Durable State artifact, seeded at iteration 0 |
| `maker.sh` | Maker step — SEPARATE process from verify.sh (maker ≠ checker) |
| `verify.sh` | External verifier as an exit-code gate |
| `run-this-loop.sh` | Engine-agnostic runner; emits `metrics.jsonl` + `state.jsonl` each iteration |
| `safety-checklist.md` | Human checkpoints + budget guardrails + maker≠checker checker identity |
| `flow.mmd` | Mermaid diagram of this loop |

Record `profile.dispatch.checker` in `safety-checklist.md`; note cross-provider option when 2+ CLIs available from `loopprint-detect.py`.

After generation: preflight with `bash run-this-loop.sh --check`. Use `loopprint-report.py loops/<slug>/metrics.jsonl` for cost-per-accepted-change; `loopprint-skillify.py loops/<slug>` to promote a GREEN loop to a reusable skill (only after sealed checker passes). `loopprint-ls.py` for rot radar.

**Self-check (required):** run `scripts/loopprint-lint.py loops/<slug>/loop-spec.yaml`. Do **not** present the blueprint as ready until it prints GREEN. RED = empty or self-grading verifier, missing safety limit, unfilled placeholder.

### Step 6 — Final Review
Show the generated file tree and a 3-line summary (Goal / Verifier / Stop). Offer and wait:
- **Run now** — execute `run-this-loop.sh` (respecting autonomy level from Step 2).
- **Refine** — adjust any atom/artifact and regenerate.
- **Export** — adapt for another orchestrator.
- **Save as skill** — promote this loop into a reusable skill.

Never auto-run. Step 6 is a stop-and-confirm.

### Skip-wizard / direct-run mode
Say **"skip wizard"** or **"direct run"** to bypass Steps 1–4's interview: read or accept an existing `loop-spec.yaml` (or a one-paragraph goal), backfill missing atoms with sensible defaults, **call out anything defaulted**, generate the package (Step 5), stop at Step 6. Never silently invent a verifier — if there's no external gate, say so and ask.

---

## Core invariants
- **Outcome ≠ symptom** — "CI green", "coverage up", "complexity down" are symptoms unless tied to a behavioral outcome oracle. Symptom-only → REJECT or re-Frame.
- **Sealed verifier inputs** — the maker cannot edit the acceptance suite, oracle configs, or holdout credentials after Frame.
- **Maker ≠ checker** — at every altitude: iteration gates *and* the final outcome verifier. No self-grading.
- **Every criterion binds a sealed domain outcome-oracle** — tests, live API probes, read-only metric pulls, published-content hashes, compliance receipts — not agent prose.
- **War-game before GO** — Simulate is mandatory on the default path.
- **Resumable / idempotent execution** — durable state after every meaningful step; safe retry and rollback.
- **External write-back receipts** — claims of "deployed", "published", "rotated" must be re-pulled from the external system by the checker.
- **Partial completion is failure** — outcome criteria quantify over the full scope unless the sealed suite explicitly scopes down.

### Evidence bundle (Stage 6 minimum)
1. Artifacts + hashes — built from clean checkout at pinned SHAs, not the maker's dirty tree.
2. Tool receipts with write-back — redeployed config, published URL, rotated secret fingerprint — re-read by the checker.
3. Final-state assertions — live probes the maker cannot mutate (read-only creds, holdout split the maker never saw).
4. Unresolved risks — any P0/P1 unresolved → FAIL even if narrow criteria pass.

---

## Degrade / fast-path rules
- **"design"** / loop wizard fast-path — enter Stage 2 wizard; stop after artifact generation. No outcome orchestration.
- **"skip simulate"** — allowed after Design-loop + Plan; print a one-paragraph risk callout (top failure modes Simulate would have caught); require explicit user confirmation before GO.
- **"fast path"** — Frame + Design-loop + Plan, then stop with a ready-to-run package. No autonomous Execute.
- **"analysis-only"** — stop after Stage 1 with Capability Manifest + esat output.
- Degrade never bypasses: sealed suite, maker ≠ checker, irreversible human gates, or Stage 6 live-state verifier.

---

## Self-verifier gate (required before autonomous run)
```
python3 scripts/looptimal-lint.py loops/<slug>/mission.yaml
```
Do **not** proceed until it prints **GREEN**. RED = writable verifier inputs, symptom-only criteria, missing oracle binding, maker=checker collapse, missing safety limit, meta-loop shape — fix and re-lint.

Loop-design output is gated separately:
```
python3 scripts/loopprint-lint.py loops/<slug>/loop-spec.yaml
```

---

## Doctor / repair
```
python3 scripts/looptimal-doctor.py          # bottom-up health check; copy-pasteable fix per problem
python3 scripts/looptimal-doctor.py --fix    # apply SAFE repairs (chmod +x, relink dangling symlink)
python3 scripts/looptimal-doctor.py --json   # machine-readable findings

python3 scripts/loopprint-doctor.py          # diagnose the loop-design wizard install
python3 scripts/loopprint-doctor.py --fix    # safe repairs for wizard scripts
```
Apply safe `fix:` lines yourself; for anything that re-clones, edits user config, or deletes, confirm with the user first. One-shot heal — re-run once to confirm no FAIL, then stop. Full map: [`references/troubleshooting.md`](references/troubleshooting.md).

---

## Hard guards (always)
- No criterion the maker can satisfy by self-assessment. Bind to an external oracle or stop.
- No Execute without human GO after Simulate (or documented degrade acceptance).
- No irreversible action without a pre-action human gate and blast-radius disclosure.
- No meta-loop: the orchestrator must not grade its own orchestration as the outcome.
- No "done" without Stage 6 Verify-outcome GREEN on live state — loop self-reported GREEN is informational only.
- No promotion of a failing loop into a reusable skill — `loopprint-skillify` applies only after the sealed checker passes.
- Log state + verifier result every iteration; only the sealed checker permits outcome completion.
- No loop without a safety limit. No autonomous run without Step 6 / human GO approval.
- Irreversible actions become human checkpoints, never autonomous steps.

## REJECT patterns (Design-loop must stop)
- One-shot Q&A, single-file edit, "explain this error" — not a loop.
- Meta-loop: automating approval of Looptimal's own output, or any self-referential verifier.
- Judgment-only goals with no machine- or oracle-checkable outcome ("make it feel premium").
- Symptom ratchet with no behavioral anchor (coverage %, lint score, complexity metric alone).
- When honest alternative is better: direct execution, human-gated checklist, or design fast-path without outcome orchestration.

## Common failure modes (stay honest)
- **Reward-hacking** — suite passes by narrowing scope, quarantining tests, stubbing externals. Simulate + outcome oracles are the fix; if they are weak, say FAIL early.
- **Silent failure** — temporary backfill masks a broken upstream. Persist remediation class; require receipt + invariant cross-check.
- **Goal drift** — long-horizon loops redefine the metric. Re-Frame checkpoints or downgrade to Supervised.
- **Stale environment** — checker hits a snapshot the maker seeded. Final-state probes must be freshly provisioned or read live production-adjacent state per the sealed suite.
- **Partial orchestration** — 9/10 repos merged, 9/10 tenants migrated. Quantify ∀ scope in Frame or accept FAIL.

## Related skills
- **esat** — tri-model analysis for high-stakes definition during Analyze. Feeds the Capability Manifest; does not replace Frame or Verify-outcome.

Author: Renn Labs. MIT.
