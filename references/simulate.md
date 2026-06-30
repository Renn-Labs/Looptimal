# Stage 4 — Simulate (War-Game Protocol)

Looptimal Stage 4 stress-tests the **plan**, not production. No real side effects. Default horizon: **5–7 steps** per path or until a terminal state. Optional **1–2 iteration sandbox dry-run** for high-stakes paths (ephemeral env only; still no irreversible prod actions).

## Purpose

Catch before Execute:
- Reward-hacking the acceptance suite
- Goal / scope drift
- Silent failure / missing write-back
- Flaky verifier false GREEN
- Blast-radius timing errors
- Symptom-not-outcome criteria
- Context rot on long horizons
- Partial completion across registries
- External blocker neglect

## Inputs

| Input | Required |
|-------|----------|
| `task-graph.yaml` | yes |
| `sealed/acceptance-suite.yaml` + `contract_hash` | yes (read-only) |
| `scope-registry.yaml` | yes |
| `loop-design.md` | yes |
| `risk-register.yaml` | yes |
| `blast-radius-checkpoints.yaml` | yes |
| `capability-manifest.yaml` + `integration-map` | yes |
| `loop-spec.yaml` / LoopPrint package | if iteration loop |
| Binding profile | yes |

## Outputs

| Artifact | Content |
|----------|---------|
| `simulation.md` | Human-readable war-game report (paths, rollouts, pre-mortem, residuals) |
| `plan-hardening.md` | Concrete plan changes per high-severity failure |
| `simulation-paths.yaml` | Machine-readable path catalog |
| Updated `task-graph.yaml` | Hardened plan |
| Updated `sealed/*` (optional) | Strengthened criteria → new `contract_hash` |
| `looptimal-lint.txt` | Post-hardening re-lint |

## Terminal states (per path)

| State | Meaning |
|-------|---------|
| `GREEN` | Simulated outcome verifier passes; scope intact |
| `STUCK` | Blocked on external dependency / missing capability |
| `BLAST-RADIUS` | Irreversible harm predicted before adequate checkpoint |
| `BUDGET` | Safety limit hit before outcome |
| `FAIL` | Outcome criteria fail (gaming, partial, silent failure, drift) |

---

## Phase 1 — Scenario / Path Generation

**Job:** Enumerate top-K execution paths: happy path + most-likely divergences.

### Personas

**Red-team** — adversarial; seeks reward-hacks, scope narrows, oracle bypass, partial registry completion, premature irreversibles, holdout leakage, stale env probes.

**Forecaster** — probabilistic; ranks likely real-world divergences: env drift, flaky CI, human merge delays, credential gaps, upstream API change, context rot, quota/rate limits, nondeterminism.

### Procedure

1. Set `K` default = 7 (min 5): 1 happy + `K-1` divergences.
2. Red-team proposes ≥12 candidate failure modes; Forecaster ranks by likelihood × severity.
3. Select top `K-1` divergences plus happy path.
4. For each path, document:
   - `path_id`
   - `trigger` — what differs from happy (e.g., "repo 12 not in manifest", "staging stale", "flake passes once")
   - `first_divergence_step` — task node id or iteration number
   - `persona_origin` — red-team | forecaster | hybrid
   - `severity` — low | medium | high | critical
5. Write catalog to `simulation-paths.yaml`; summarize in `simulation.md` § Paths.

### Path coverage checklist (must appear in catalog or explicit N/A)

- [ ] Happy path (all deps available, clean env)
- [ ] External blocker (human merge, third-party outage)
- [ ] Partial registry completion (`N-1 of N`)
- [ ] Reward-hack (quarantine tests, narrow scope, stub externals)
- [ ] Silent failure (temporary backfill masks broken upstream)
- [ ] Stale / wrong environment (staging snapshot, seeded fixtures)
- [ ] Flaky verifier (single lucky quorum pass)
- [ ] Blast-radius mis-ordering (revoke before ∀ deploy)
- [ ] Goal / metric drift (redefine success mid-horizon)
- [ ] Context rot (long-horizon state loss, wrong resume)
- [ ] Holdout / eval leakage (ML or A/B peeking)
- [ ] Rate limit / resource exhaustion

---

## Phase 2 — Rollout (Forward Simulation)

**Job:** Reason each path forward step-by-step to horizon; no real side effects.

### Parameters

| Parameter | Default |
|-----------|---------|
| `horizon_steps` | 7 (use 5 for simple Task; up to 10 for Orchestration) |
| `step_granularity` | task-graph node OR loop iteration (whichever is finer) |
| `sandbox_dry_run` | 0 (set 1–2 for high-stakes: ephemeral env only) |

### Per-path procedure

For each `path_id` in `simulation-paths.yaml`:

1. **Initialize state** — copy `task-graph.yaml` node statuses to `pending`; load loop iteration 0 if applicable.
2. **For step = 1 .. horizon_steps** (stop early on terminal):
   a. Identify next eligible node(s) per DAG and path `trigger`.
   b. **Simulate maker action** — what would be attempted; which artifacts produced.
   c. **Simulate iteration checker** (if loop) — would `verify.sh` pass? Note if maker-controlled.
   d. **Simulate external world** — apply path trigger effects (blocker, flake, stale env, upstream break).
   e. **Simulate outcome oracle** — would sealed criterion pass **against live world model**, not maker claims?
   f. **Record step transcript**: `{ step, node_id, action, inner_gate, outer_oracle, world_state, notes }`
   g. **Check terminal** — assign `GREEN|STUCK|BLAST-RADIUS|BUDGET|FAIL` if reached.
3. **Sandbox dry-run** (optional, high-stakes):
   - Execute ≤2 loop iterations in **ephemeral sandbox** (disposable containers, fake creds, no prod).
   - Capture only: would verifier be maker-gradable? scope fence hold? checkpoint fire?
   - Tear down; no persistent side effects.
4. Write per-path rollout to `simulation.md` § Rollouts and `simulation-paths.yaml` `rollout[]`.

### Rollout rules

- Do **not** treat maker self-report as pass.
- Do **not** assume external deps resolve unless in happy path.
- Apply ∀ quantification from `scope-registry.yaml` — partial is FAIL.
- For blast-radius nodes: simulate checkpoint presence; if missing → `BLAST-RADIUS`.
- For flaky oracles: simulate single-run vs quorum; note false GREEN risk.

---

## Phase 3 — Pre-Mortem

**Job:** Assume the run **failed** after Execute. Enumerate likely causes.

### Procedure

1. State the assumed failure headline: "We called it done but the outcome is false / harmful / incomplete."
2. Brainstorm causes (minimum 10); classify each:

| Class | Description | Example |
|-------|-------------|---------|
| `reward-hack` | Suite passed by gaming, not outcome | Quarantine 30% of tests |
| `goal-drift` | Metric redefined mid-run | "Activation" redefined to click |
| `scope-drift` | Execute scope exceeded or shrank | 9/10 repos migrated |
| `silent-failure` | GREEN with broken upstream | Backfill without fix |
| `no-write-back` | State says done; world disagrees | No receipt re-pull |
| `flaky-verifier` | Lucky pass | Single CI shard green |
| `blast-radius` | Irreversible harm | Revoke key before ∀ deploy |
| `symptom-not-outcome` | Proxy metric passed | Coverage up, behavior broken |
| `context-rot` | Lost state / wrong resume | Stale `task-graph.yaml` |
| `env-drift` | Probe hit wrong environment | Staging cached as prod |
| `registry-gap` | Closed registry incomplete | Missing fork/tenant |
| `external-blocker` | Dependency never arrived | Team B didn't merge |

3. Map each cause → affected `path_id` and `criterion_id`.
4. Rate **severity**: low | medium | high | critical.
5. Write to `simulation.md` § Pre-Mortem.

### Pre-mortem prompts (use verbatim in workshop)

- "How did we pass the sealed suite while the user-visible outcome is still broken?"
- "What did the maker control that the oracle mistakenly trusted?"
- "What partial completion looks like success?"
- "What irreversible action happened too early?"
- "What will fail again tomorrow on a Recurring archetype?"
- "What holdout or registry did we never enumerate in Frame?"

---

## Phase 4 — Plan Hardening

**Job:** Each **high** or **critical** pre-mortem / rollout failure becomes a concrete plan change. Then re-lint.

### Hardening action menu

| Failure class | Hardening actions (pick ≥1) |
|---------------|----------------------------|
| `reward-hack` | Seal input artifact; strengthen criterion to behavioral outcome; add holdout oracle; add adversarial vector suite |
| `goal-drift` | Pin scope fence; add re-Frame checkpoint; REJECT → Supervised downgrade |
| `scope-drift` | Add ∀ registry entries; split lane per registry member; partial → explicit FAIL criterion |
| `silent-failure` | Add receipt + invariant cross-check; require remediation class in Persist; block temporary-backfill without upstream fix task |
| `no-write-back` | Add external re-pull oracle; checker-owned creds |
| `flaky-verifier` | Add quorum rule (N runs, M passes); fresh runner requirement |
| `blast-radius` | Add pre-action checkpoint; split two-phase (deploy new → verify ∀ → revoke old); human GO subgate |
| `symptom-not-outcome` | Re-Frame criterion to outcome oracle; REJECT symptom |
| `context-rot` | Add checkpoint cadence; compress state writeback; pin SHAs in execute scope |
| `env-drift` | Add prod-adjacent probe; forbid seeded fixtures in oracle |
| `registry-gap` | Expand `scope-registry.yaml`; add completeness proof step in Plan |
| `external-blocker` | Add blocked state + timeout; GO gate lists open externals |

### Per-failure record (in `plan-hardening.md`)

For each high/critical item:

```
### [PF-###] <title>
- class: <failure class>
- severity: high|critical
- source: path <path_id> | pre-mortem #N
- predicted_impact: <1 line>
- hardening_action: <concrete change>
- touches: task-graph | acceptance-suite | blast-radius-checkpoints | loop-spec | scope-registry
- residual_risk: none|<description>
- owner: <domain>
```

### Procedure

1. Collect all high/critical failures from Phase 2–3.
2. For each: select hardening action(s); edit artifacts.
3. If `acceptance-suite.yaml` changed → re-seal → new `contract_hash` → require user ack before GO.
4. If `task-graph.yaml` changed → verify DAG still acyclic; hooks intact.
5. Re-run **looptimal-lint** → must be GREEN.
6. Any item without mitigation → must have explicit `residual_risk` + user ack in `plan-hardening.md`.

### `plan-hardening.md` structure

```markdown
# Plan Hardening — <slug>

## Summary
- paths_simulated: K
- high_critical_failures: N
- mitigations_applied: M
- residual_risks_acknowledged: R
- contract_hash: <before> → <after|unchanged>

## Hardening actions
<PF-### entries>

## Residual risks (require human GO ack)
<items>

## Lint
- looptimal-lint: GREEN|RED
```

---

## `simulation.md` structure

```markdown
# Simulation Report — <slug>

## Meta
- contract_hash: ...
- archetype: ...
- horizon_steps: ...
- paths_simulated: K
- sandbox_dry_runs: 0|1|2

## Paths
<path catalog table>

## Rollouts
<per-path step transcripts>

## Pre-Mortem
<assumed-failure causes>

## Terminal summary
| path_id | terminal | root_cause | hardening_ref |

## GO briefing bullets
- top 3 residual risks
- irreversibles requiring checkpoint
- open external dependencies
- contract_hash change: yes|no
```

---

## Stage 4 GATE (exit to Human GO)

All must pass:

- [ ] Phase 1–4 complete; `simulation.md` + `plan-hardening.md` exist
- [ ] Top-K paths rolled out (happy + likely divergences)
- [ ] Pre-mortem ≥10 causes documented
- [ ] Every **high** and **critical** failure has hardening action **OR** explicit `residual_risk` with user ack
- [ ] Post-hardening **looptimal-lint GREEN**
- [ ] If `contract_hash` changed: noted in both outputs; user ack recorded
- [ ] GO briefing bullets populated

**Then → Human GO gate** (the pipeline Human GO gate (references/pipeline.md)). No Execute without `go-decision.json` `approved: true`.

---

## Degrade: skip simulate

Allowed only when user explicitly opts in **after** Stage 3 complete.

1. Write `simulate-skipped.md` with one-paragraph risk callout listing top failure modes Phases 1–4 would have surfaced.
2. Copy likely high-severity items from `risk-register.yaml` as assumed residuals.
3. Require explicit user confirmation before GO.
4. Do **not** skip: contract-lint, loopprint-lint, looptimal-lint, Human GO, Verify-outcome, or maker ≠ checker.

---

## High-stakes optional sandbox dry-run

Trigger when any of:
- hard-irreversible nodes in graph
- Orchestration archetype with ≥3 external systems
- Persistent-ratchet or Recurring with prod-adjacent oracles
- security / compliance / payments scope

Run ≤2 loop iterations:
- Ephemeral env only; fake or sandbox creds
- Validate verifier is not maker-gradable
- Validate scope fence blocks out-of-contract edits
- Tear down completely after

Record in `simulation.md` § Sandbox. Sandbox GREEN does not replace Stage 6 live verification.

---

## Anti-patterns (fail Simulate if detected)

- Treating loop `verify.sh` GREEN as outcome proof
- Simulating only happy path
- Marking high-severity failure "accepted" without user ack
- Hardening that weakens criteria (symptom downgrade)
- Proceeding with lint RED after plan changes
- Skipping registry ∀ quantification in rollouts

Author: Renn Labs. MIT.
