---
name: looptimal
description: "Looptimal — turns an objective into a delivered, VERIFIED OUTCOME by designing, war-gaming, and running the right loop or mission route. Use on 'looptimal', '/looptimal', 'run an outcome loop', 'orchestrate this objective to done', 'plan and ship this goal', or any non-trivial objective that needs a sealed acceptance suite, the right execution driver, and independent verification before you call it done. ALSO handles loop-design wizard requests ('design a loop', 'build a loop', 'new loop', 'loop wizard', or a vague recurring task to automate) via the 'design' fast-path (Stage 2 only, no outcome orchestration). For a single, non-recurring deliverable you still want proven — not trivial, just not a reusable loop — it routes to mission / goal-run when bounded iteration is useful, or degrades to 'single-pass' mode when one pass is enough: Frame → (Analyze if multi-domain) → light pre-mortem → Execute → Verify-outcome → Persist, skipping reusable-loop scaffolding. When the objective's shape is ambiguous, asks one upfront mode-fork question (single-pass / bounded mission or recurring system / just a blueprint) before any Frame work starts. Runs an 8-stage pipeline: 0 Frame (hash-pinned SEALED acceptance suite) → 1 Analyze (Capability Manifest + local capability readiness) → 2 Design-loop / Route (wizard: Task / Recurring / Supervised / Persistent-ratchet / Orchestration, mission / goal-run, single-pass, or REJECT) → 3 Plan → 4 Simulate (roll forward N steps, pre-mortem, harden) → [human GO] → 5 Execute (domain-expert sub-agents, maker ≠ checker) → 6 Verify-outcome (separate checker re-runs the SEALED suite vs live state) → 7 Persist. Fast-path hints: say 'design' or 'loop wizard' for Stage 2 blueprint only; 'single-pass' for one verified pass with no loop; 'skip wizard' to bypass the interview in Stage 2; 'skip simulate' to jump to Plan after Design-loop with explicit risk callout; 'fast path' for Frame + Design-loop + Plan then stop. If install looks broken — skill won't trigger, a script errors, profile won't resolve — run 'looptimal doctor' via scripts/looptimal-doctor.py."
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
- A single, non-trivial objective you want delivered once and proven against live state. If it needs bounded iteration, route it as a mission / goal-run; if one careful pass is enough, use single-pass mode (see the mode fork below).

## When to use the design fast-path
- "design a loop", "build a loop", "new loop", "loop wizard", or a vague recurring task to automate.
- You only want a loop blueprint (spec + artifacts) — no outcome orchestration.
- Jumps directly to Stage 2 (Decision Gate → wizard → artifact generation) and stops.

## When NOT to use
- A **trivial** one-shot answer, quick edit, or conversational question → just do it well once, no tool needed. (A *substantive* one-shot objective you still want proven — not trivial, just not recurring — routes to mission / goal-run or single-pass below, not a reason to skip Looptimal entirely.)
- Analysis with no delivery obligation → answer directly or use esat.
- Irreversible, judgment-heavy actions with no human willing to hold the GO gate → recommend a human-gated process.
- Meta-loops ("run Looptimal to verify Looptimal", "auto-merge when Looptimal says GREEN") → Design-loop must REJECT.
- Symptom-only success metrics with no behavioral outcome oracle → re-Frame or REJECT.

## Operating rules (read first)
- This is a **skill**, not a persona or mode. Open with **one** activation line, then do the work.
- **Checkpoint-gated**: Frame → Analyze → Design-loop / Route → Plan → Simulate each stop for brief status. Execute never starts without explicit human GO after Simulate — or, in single-pass mode, after the light pre-mortem that substitutes for the Analyze/Design-loop/Plan/Simulate checkpoints (see the mode fork below).
- **Never auto-run irreversibles**: prod deploys, sends, payments, credential rotation, data deletion — pre-action human gates only.
- **Harness-decoupled**: resolve bindings from `./.looptimal/profile.yaml` → `~/.looptimal/profile.yaml` → `scripts/looptimal-detect.py` → generic defaults. Contract: [`references/agent-foundry.md`](references/agent-foundry.md).

**Activation line examples:**
- Full pipeline: *"Looptimal — framing this objective into a sealed outcome loop."*
- Design fast-path: *"Looptimal — blueprinting this loop."*
- Single-pass: *"Looptimal — one verified pass on this, no loop."*
- **Invoked bare** (no objective): ask exactly one question — *"What outcome should be true when we're done?"* — then the mode fork below.
- **Objective already given**: acknowledge in one line, then the mode fork below.

### The mode fork (before Frame — ask once, cheaply)
Looptimal's loop-worthiness judgment is the Decision Gate (Step 1 of the wizard, below) — but today that only fires deep in Stage 2, after Frame and Analyze have already run. Decide the shape **before** any of that work starts instead:

- **Phrasing already unambiguous — skip the question:**
  - Design-fast-path trigger words ("design a loop", "build a loop", "blueprint", "loop wizard") → Stage 2 directly.
  - Explicit one-shot language that also rules out useful retries ("single pass", "one careful pass", "no retry loop needed") → single-pass directly.
  - Explicit one-time delivery language with possible verifier/retry work ("one-shot", "just do X once", "build/fix/ship this once") → full pipeline so the Decision Gate can choose mission / goal-run vs single-pass.
  - Explicit recurrence/cadence language ("nightly", "every PR", "keep this fresh", "ongoing") → full pipeline directly.
- **Otherwise — ask one structured, three-option question before touching Stage 0:**
  1. *Get it done once, proven* — a single verified outcome with no useful retry loop → **single-pass**.
  2. *Run a mission or build a loop* — either **bounded** (a mission / goal-run that iterates until a gate, then stops — bug fixes, spec conformance, one-time builds) or **recurring** (runs on a schedule/trigger indefinitely) → full pipeline (Stage 0 → 1 → 2; the Decision Gate picks the route/archetype — Task / Recurring / Supervised / Persistent-ratchet / Orchestration, mission / goal-run, or hard reject).
  3. *Just generate a loop blueprint* → design fast-path (Stage 2 only).

This surfaces the same loop-worthiness call the Decision Gate already makes as the user's own judgment, upfront and cheap, instead of only reachable after Analyze, Design-loop, and Plan have already been spent on the wrong shape (Frame runs regardless of the chosen mode, so it's never wasted). If Stage 0/1 evidence later contradicts the chosen mode — a "single-pass" objective turns out to clearly recur or need iteration until a gate, or a "recurring system" doesn't survive the Decision Gate — say so plainly and let the user redirect. Never silently override their choice; never silently comply with a mode the evidence doesn't support.

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
| 1 | **Analyze** | Produce a Capability Manifest and local capability readiness inventory: domains, integration map, risks, dependencies, available skills/plugins/connectors/MCPs/agents/data. Delegate deep definition work to **esat** when stakes warrant tri-model stress-test. | [`references/pipeline.md`](references/pipeline.md) |
| 2 | **Design-loop / Route** | Run the loop-design wizard or route the objective. Pick archetype — **Task** (bounded delivery), **Recurring** (scheduled freshness), **Supervised** (autonomous within guardrails), **Persistent-ratchet** (each pass strictly improves an outcome metric), **Orchestration** (multi-actor / multi-repo), mission / goal-run, single-pass — or **REJECT** only for hard no-verifier/meta-loop/symptom-only cases. | [`references/pipeline.md`](references/pipeline.md) |
| 3 | **Plan** | Build a consensus task graph: nodes, dependencies, per-task acceptance hooks tied to the sealed suite, blast-radius tags, rollback notes. | [`references/pipeline.md`](references/pipeline.md) |
| 4 | **Simulate** | Roll the loop forward N steps; pre-mortem failure modes (reward-hacking, silent failure, partial completion, env drift); harden the plan. Present findings and any deltas to the sealed suite (re-hash + user ack). | [`references/pipeline.md`](references/pipeline.md) |
| — | **Human GO** | Explicit approval to execute. Surface top risks, irreversibles, open dependencies. No GO → no Execute. | [`references/pipeline.md`](references/pipeline.md) |
| 5 | **Execute** | Spin up dynamic domain-expert sub-agents per the binding profile. Maker ≠ checker at iteration gates. Resumable, idempotent steps; rollback paths for partial failure. Pre-action gates on irreversibles. | [`references/pipeline.md`](references/pipeline.md) |
| 6 | **Verify-outcome** | A **separate** checker re-runs the SEALED suite against **live state**. Ignore loop self-reported GREEN. Gate on an evidence bundle. | [`references/pipeline.md`](references/pipeline.md) |
| 7 | **Persist** | Write durable state: objective hash, suite hash, what worked/failed, oracle results, remediation class, resume pointers, lessons for next run. | [`references/pipeline.md`](references/pipeline.md) |

### Stage transitions (default)
- 0 → 1: sealed suite exists, every criterion has an oracle, hash recorded.
- 1 → 2: Capability Manifest covers all material domains, integration edges, and local capability readiness.
- 2 → 3: archetype or mission route chosen (or hard REJECT issued with honest alternative).
- 3 → 4: task graph is acyclic, every node hooks to a suite criterion, safety limits set.
- 4 → GO: simulation report delivered; plan hardened; irreversibles tagged.
- GO → 5: explicit human approval captured in state.
- 5 → 6: maker declares iteration complete — informational only; checker owns truth.
- 6 → 7: evidence bundle GREEN; else FAIL with remediation class and resume pointer.

### Resume
If a prior run exists under `state_dir` and the objective hash matches, resume from the last incomplete stage. If the objective changed materially, re-Frame (new suite hash). Never resume across a hard REJECT without a fresh Design-loop / Route.

---

## Stage 2 — Design-loop / Route wizard

The wizard enforces the four atoms, runs the route decision gate, and then branches. Reusable-loop routes generate the full LoopPrint artifact package. Mission / goal-run routes emit `route.md` + a mission package (`mission.yaml` after Stage 3) and continue to Stage 3 Plan without reusable-loop scaffolding. Single-pass routes emit `route.md` plus the light pre-mortem and follow the single-pass Degrade path. It lives in Stage 2 of the full pipeline and also runs standalone as the `design` fast-path.

### Wizard entry
- **Full pipeline** (called from Stage 2): goal is the outcome from Stage 0. Skip to Step 0.5.
- **Design fast-path** (direct invocation): open with one activation line; if no goal given, ask one question first.

### Step 0.5 — Resolve the binding
Run `scripts/loopprint-detect.py` (or read `./.loopprint/profile.yaml` → `~/.loopprint/profile.yaml`) to get `state_dir`, `verifier.default`, `dispatch`, `marker_path`, `runner`, `banner`. Generic defaults: `loops/<slug>/`, `verify.sh`. Contract: [`references/profiles.md`](references/profiles.md). Never hardcode harness conventions.

### Step 1 — Decision Gate (+ route)
Run the Tier-0 test in [`references/decision-gate.md`](references/decision-gate.md): 4 conditions + 30-second checklist. Report the route with one line of reasoning per condition. Recurrence remains the reusable-loop amortization test, not the whole orchestration gate: non-recurring but verifier-backed work can route to mission / goal-run or single-pass. Hard **REJECT** remains mandatory when there is no external verifier/human checkpoint, when the objective is self-referential/meta-loop, or when success is symptom-only with no behavioral anchor.

Immediately branch on the selected route:
- **Reusable loop route:** continue through Steps 2-6, pin the loop archetype/profile, generate `loops/<slug>/`, and run `loopprint-lint`.
- **Mission / Goal Run route:** do **not** continue to loop profile or artifact generation. Emit `route.md` with driver, state artifact, verifier, stop/budget, autonomy level, readiness gaps, and why no reusable loop blueprint is being produced; then continue to Stage 3 Plan, which emits `mission.yaml`, `task-graph.yaml`, `execute-scope.yaml`, and `looptimal-lint.txt`.
- **Single Verified Pass route:** do **not** continue to loop profile or artifact generation. Emit `route.md` with verifier, state artifact, stop, readiness gaps, and a 3-scenario light pre-mortem; then follow the `single-pass` Degrade path instead of Stage 3/4.
- **Human-gated workflow route:** emit `route.md` with the human checkpoints and external checker, then continue only through the supervised path that matches those gates.
- **Hard REJECT:** emit `reject.md` with the unverifiable/unsafe reason and honest alternative; stop unless the user reframes the objective.

### Step 2 — Reusable-loop Goal Refinement
Ask **3–5 targeted questions** (not more):
1. Sharpened goal — one sentence, testable.
2. Recurrence / frequency — confirms the reusable loop amortizes.
3. Verification method — what *external* signal says an iteration succeeded?
4. Irreversible risks — what can't be undone? (→ human checkpoint)
5. Autonomy level — fully autonomous, checkpoint-gated, or dry-run?

### Step 3 — Reusable-loop Primitive Enforcement
Force a concrete value for each atom. Do not proceed with any left vague:
- **Goal** — the one-sentence objective from Step 2.
- **State** — durable artifact path from the binding's `state_dir`; what it records: attempt log, what failed, current hypothesis, context.
- **Verifier** — the exact external command or named reviewer. If the only proposed check is the same agent self-assessing, **reject it** and find a real gate. Maker ≠ checker.
- **Stop** — success criteria **and** a safety limit (max iterations, token/time budget, explicit halt). No loop ships without a safety limit.

### Step 4 — Reusable-loop Profile Selection
Pin the archetype's full profile — work pattern (from [`references/patterns.md`](references/patterns.md)) and verifier/stop shape:
- **MORTY** — specific bug; verifier = reproduction test; finish-gate.
- **Spec-Driven** — conform to a spec; derived tests pass.
- **Performance** — metric target (gate), or open-ended ratchet: `verifier.shape: ratchet` + `stop.budget`.
- **Hybrid** — composite gate.
- **Critic-panel** — `verifier.kind: critic-panel`; `panel: {n, quorum_k, threshold}`; judge ≠ maker; cross-provider strongest.
- **Supervised** — human checkpoints between autonomous runs; `autonomy: checkpoint`.

Pattern = the *work*; verifier shape/kind + stop + autonomy = *how it's gated and when it stops* — orthogonal axes.

### Step 5 — Reusable-loop Artifact Generation
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

### Step 6 — Reusable-loop Blueprint Final Review
Show the generated file tree and a 3-line summary (Goal / Verifier / Stop). Offer and wait:
- **Run now** — execute `run-this-loop.sh` (respecting autonomy level from Step 2).
- **Refine** — adjust any atom/artifact and regenerate.
- **Export** — adapt for another orchestrator.
- **Save as skill** — promote this loop into a reusable skill.

Never auto-run. Step 6 is a stop-and-confirm.

### Skip-wizard / direct-run mode
Say **"skip wizard"** or **"direct run"** to bypass Steps 1–4's interview for a reusable-loop route: read or accept an existing `loop-spec.yaml` (or a one-paragraph goal), backfill missing atoms with sensible defaults, **call out anything defaulted**, generate the package (Step 5), stop at Step 6. If the Decision Gate routes the objective to mission / goal-run or single-pass, skip LoopPrint artifact generation and emit the corresponding `route.md` branch instead. Never silently invent a verifier — if there's no external gate, say so and ask.

---

## Core invariants
- **Outcome ≠ symptom** — "CI green", "coverage up", "complexity down" are symptoms unless tied to a behavioral outcome oracle. Symptom-only → REJECT or re-Frame.
- **Sealed verifier inputs** — the maker cannot edit the acceptance suite, oracle configs, or holdout credentials after Frame.
- **Maker ≠ checker** — at every altitude: iteration gates *and* the final outcome verifier. No self-grading.
- **Every criterion binds a sealed domain outcome-oracle** — tests, live API probes, read-only metric pulls, published-content hashes, compliance receipts — not agent prose.
- **War-game before GO** — Simulate is mandatory on the default path (single-pass substitutes a light pre-mortem; see Degrade rules).
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
- **"mission / goal-run"** — a non-recurring objective that still benefits from bounded iteration until an external gate accepts it. Use the full Frame → Analyze → Route → Plan → Simulate → GO → Execute → Verify-outcome → Persist discipline, with the route artifact selecting the best available local driver (Ultragoal/Autopilot, Team when useful, or explicit Ralph fallback).
- **"single-pass"** (or chosen via the mode fork above) — the Decision Gate's own honest alternative ("one high-quality pass") made directly selectable, not just the fallback when Stage 2 fails: Frame (sealed suite — the maker ≠ checker guarantee matters just as much for one outcome) → Analyze only if the objective is genuinely multi-domain, else skip → a **light pre-mortem** (the 3-scenario "this will fail because…" check, one line of prevention each — not full N-step Simulate, since there's no loop to roll forward) → human GO → Execute (one pass; no archetype, no iteration loop) → Verify-outcome (Stage 6, unchanged — still a separate checker, still live state) → Persist. Skips reusable-loop archetype selection and Plan's consensus task graph entirely.
- **"design"** / loop wizard fast-path — enter Stage 2 wizard; stop after artifact generation. No outcome orchestration.
- **"skip simulate"** — allowed after Design-loop + Plan; print a one-paragraph risk callout (top failure modes Simulate would have caught); require explicit user confirmation before GO.
- **"fast path"** — Frame + Design-loop + Plan, then stop with a ready-to-run package. No autonomous Execute.
- **"analysis-only"** — stop after Stage 1 with Capability Manifest + esat output.
- Degrade never bypasses: sealed suite, maker ≠ checker, irreversible human gates, or Stage 6 live-state verifier (single-pass's light pre-mortem is a legitimate substitute for full Simulate — it is not a bypass of the GO gate itself).

---

## Self-verifier gate (required before autonomous run)
```
python3 scripts/looptimal-lint.py <state_dir>/mission.yaml
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
- No Execute without human GO after Simulate, or the light pre-mortem in single-pass mode (or other documented degrade acceptance).
- No irreversible action without a pre-action human gate and blast-radius disclosure.
- No meta-loop: the orchestrator must not grade its own orchestration as the outcome.
- No "done" without Stage 6 Verify-outcome GREEN on live state — loop self-reported GREEN is informational only.
- No promotion of a failing loop into a reusable skill — `loopprint-skillify` applies only after the sealed checker passes.
- No promotion of a synthesized persona into the curated library from an unverified or maker-only-reported mission — `looptimal-persona-promote` applies only after Stage 6 is checker GREEN.
- Log state + verifier result every iteration; only the sealed checker permits outcome completion.
- No loop without a safety limit. No autonomous run without Step 6 / human GO approval.
- Irreversible actions become human checkpoints, never autonomous steps.

## REJECT patterns (Design-loop must stop)
- Trivial one-shot Q&A, tiny single-file edit, "explain this error" — not a reusable loop; answer directly or use single-pass only if an explicit verifier is needed.
- Meta-loop: automating approval of Looptimal's own output, or any self-referential verifier.
- Judgment-only goals with no machine- or oracle-checkable outcome ("make it feel premium").
- Symptom ratchet with no behavioral anchor (coverage %, lint score, complexity metric alone).
- When honest alternative is better: direct execution, **single-pass** (Frame + Verify-outcome without loop scaffolding — see Degrade rules), human-gated checklist, or design fast-path without outcome orchestration.

## Common failure modes (stay honest)
- **Reward-hacking** — suite passes by narrowing scope, quarantining tests, stubbing externals. Simulate + outcome oracles are the fix; if they are weak, say FAIL early.
- **Silent failure** — temporary backfill masks a broken upstream. Persist remediation class; require receipt + invariant cross-check.
- **Goal drift** — long-horizon loops redefine the metric. Re-Frame checkpoints or downgrade to Supervised.
- **Stale environment** — checker hits a snapshot the maker seeded. Final-state probes must be freshly provisioned or read live production-adjacent state per the sealed suite.
- **Partial orchestration** — 9/10 repos merged, 9/10 tenants migrated. Quantify ∀ scope in Frame or accept FAIL.

## Related skills
- **esat** — tri-model analysis for high-stakes definition during Analyze. Feeds the Capability Manifest; does not replace Frame or Verify-outcome.

Author: Renn Labs. MIT.
