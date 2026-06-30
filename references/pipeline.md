# Looptimal Pipeline Protocol (Stages 0–7)

Harness-decoupled meta-orchestrator protocol. Each stage produces durable artifacts under the resolved binding `state_dir` (generic default: `loops/<slug>/`). Advance only when the stage GATE is satisfied. Maker ≠ checker at every altitude.

## Conventions

| Symbol | Meaning |
|--------|---------|
| `contract_hash` | SHA-256 of `acceptance-suite.yaml` at seal time; must match at Verify-outcome |
| `objective_hash` | SHA-256 of normalized objective text; resume requires match |
| `sealed/` | Non-writable path subtree; maker has no write access after Frame |
| `oracle` | External, machine- or system-checkable outcome probe (not agent prose) |
| `symptom` | Maker-controlled or proxy metric (CI green once, coverage %, lint score alone) |
| `blast-radius` | Irreversible or hard-to-rollback action class (deploy, send, delete, revoke, cutover) |

Lint entrypoints (resolve from binding or skill `scripts/`):
- `contract-lint` — Stage 0 gate; validates acceptance suite shape and oracle bindings
- `loopprint-lint` — Stage 2 gate; validates each `loop-spec.yaml`
- `looptimal-lint` — Stage 3+ gate; validates full run package

---

## Stage 0 — Frame

**Job:** Turn the objective into a hash-pinned, SEALED acceptance suite. Every criterion asserts an **outcome** (not a symptom) and binds to a domain **outcome-oracle**. Inputs are non-writable by the maker after seal.

### Inputs
- User objective (natural language) or resumed `objective.md` with matching `objective_hash`
- Resolved binding profile (`state_dir`, oracle defaults, dispatch hints)
- Optional constraints: scope registry, budget, deadline, forbidden actions, environment class (dev/staging/prod-adjacent)
- Optional prior runs (for diff only; do not reuse an unsealed suite)

### Work performed
1. **Normalize objective** — one sentence: what must be **true in the world** when done (not what tasks were performed).
2. **Scope registry** — enumerate closed sets the outcome quantifies over: repos, services, tenants, tables, endpoints, files, experiment IDs. Use `∀` quantification; no open-ended "all relevant X."
3. **Decompose acceptance criteria** — each criterion must:
   - Assert a **behavioral outcome** observable outside the maker's workspace
   - Bind to exactly one **sealed outcome-oracle** (command, probe, read-only API pull, published-content hash, compliance receipt)
   - Include pass threshold, time window, and scope slice from the registry
   - Reject symptom-only phrasing; reframe or split until outcome-anchored
4. **Oracle catalog** — document per criterion: oracle id, invocation, credentials class (read-only / holdout-sealed), expected artifact shape, flake policy (single-run vs quorum).
5. **Anti-gaming clauses** — embed in suite metadata:
   - No narrowing scope mid-execute without re-Frame
   - No maker write access to suite, oracle configs, holdout labels, or verifier credentials
   - Partial completion (`N-1 of N`) is FAIL unless criterion explicitly scoped
   - Registry completeness is part of the contract (not discovered during Execute)
6. **Seal suite** — write `acceptance-suite.yaml` under `sealed/`; compute `acceptance-suite.sha256`; record `contract_hash` in `frame-manifest.json`.
7. **Contract-lint** — run `contract-lint` (or `scripts/looptimal-lint.py --stage frame`):
   - Every criterion has an external check (exit code, probe response, hash match, metric threshold)
   - Every criterion asserts outcome, not maker-controlled symptom
   - Every criterion binds an oracle with sealed credentials/config path
   - Suite and oracle configs live under `sealed/` (non-writable by maker role)
   - No unfilled placeholders; no self-referential meta-loop acceptance ("Looptimal says GREEN")
   - Evidence-bundle schema stub present for Stage 6

### Outputs / artifacts
| Artifact | Purpose |
|----------|---------|
| `objective.md` | Normalized outcome statement + `objective_hash` |
| `scope-registry.yaml` | Closed enumerations (∀ targets) |
| `sealed/acceptance-suite.yaml` | Hash-pinned acceptance contract |
| `sealed/acceptance-suite.sha256` | Integrity pin |
| `sealed/oracle-catalog.yaml` | Oracle definitions, cred classes, quorum rules |
| `frame-manifest.json` | `contract_hash`, seal timestamp, lint transcript, forbidden-action list |
| `contract-lint.txt` | GREEN/RED transcript |

### GATE → Stage 1
**contract-lint GREEN** AND:
- [ ] `contract_hash` recorded
- [ ] Every criterion: external check + outcome assertion + oracle binding
- [ ] Suite path is sealed / non-writable by maker
- [ ] Scope registry is closed (no "etc." / "relevant")
- [ ] No meta-loop or symptom-only criteria remain
- [ ] User acknowledged the sealed acceptance contract (brief confirmation in state)

**On RED:** fix criteria, re-seal (new hash), re-lint. Do not proceed.

---

## Stage 1 — Analyze

**Job:** Produce a Capability Manifest — domains, integration map, risks, dependencies, verifier surfaces. Delegate deep definition to **esat** when stakes warrant tri-model stress-test.

### Inputs
- Sealed `acceptance-suite.yaml` + `scope-registry.yaml` (read-only)
- `objective.md`
- Repository / system context (tree, docs, tickets, incident history)
- Binding profile

### Work performed
1. **Domain identification** — list material domains touched (backend, frontend, data, infra, security, ML, QA, docs, compliance, release, etc.).
2. **Capability Manifest** — for each domain:
   - Required expertise and tools
   - Integration edges (upstream/downstream, blocking externals)
   - Known risks and failure history
   - Oracle surfaces available vs gaps (missing probes → Frame gap or Stage 2 REJECT)
3. **Integration map** — directed graph of systems, teams, deploy order, data flows, shared credentials.
4. **Risk register** — classify: env drift, partial completion, silent failure, flaky verifier, blast-radius, goal drift, context rot, external blockers.
5. **Dependency ledger** — human merges, third-party SLAs, credentials provisioning, ephemeral env needs.
6. **Optional esat delegation** — for high-stakes objectives: tri-model stress-test of definition, scope, and oracle adequacy; merge findings into manifest (esat does not replace Frame or Verify-outcome).
7. **Manifest completeness check** — every sealed criterion has a domain owner and at least one integration edge documented.

### Outputs / artifacts
| Artifact | Purpose |
|----------|---------|
| `capability-manifest.yaml` | Domains, experts, tools, gaps |
| `integration-map.mmd` or `.yaml` | System/team/data-flow graph |
| `risk-register.yaml` | Classified risks with severity |
| `dependency-ledger.yaml` | External blockers and lead times |
| `analyze-summary.md` | Human-readable synopsis |
| `esat/` (optional) | Tri-model artifacts if delegated |

### GATE → Stage 2
- [ ] Capability Manifest covers **all material domains** referenced by sealed criteria
- [ ] Every integration edge crossing team/repo/env boundary is documented
- [ ] Every sealed criterion maps to ≥1 domain with resolvable oracle surface (or logged Frame gap with user ack)
- [ ] Risk register includes blast-radius and silent-failure classes
- [ ] No unresolved P0 definition ambiguity (if any → re-Frame or stop)

---

## Stage 2 — Design-loop

**Job:** Select loop archetype or **REJECT**. Produce or delegate runnable loop blueprint when appropriate.

### Archetypes
| Archetype | When | Stop condition |
|-----------|------|----------------|
| **Task** | Bounded delivery, terminal outcome | Outcome verifier GREEN once |
| **Recurring** | Scheduled freshness / hygiene | Per-run outcome + schedule in spec |
| **Supervised** | Autonomous within guardrails | Human gates on irreversibles; outcome per episode |
| **Persistent-ratchet** | Each pass strictly improves outcome metric | Ratchet monotonicity + re-Frame cadence |
| **Orchestration** | Multi-actor / multi-repo coordination | ∀ registry members at outcome |
| **REJECT** | Not-a-loop, meta-loop, judgment-only, symptom-only | Honest alternative issued; pipeline stops |

### Inputs
- `capability-manifest.yaml`, `integration-map`, sealed suite (read-only)
- `objective.md`, `risk-register.yaml`
- LoopPrint templates (if blueprint needed)

### Work performed
1. **Not-a-loop test** — one-shot Q&A, single edit, explain-error, meta-loop ("verify Looptimal with Looptimal"), judgment-only goals → **REJECT** with honest alternative.
2. **Archetype selection** — pick one archetype; document why others were ruled out.
3. **Symptom guard** — if success metric is proxy-only (coverage %, complexity score, CI green once) → REJECT or require re-Frame with behavioral anchor.
4. **Loop blueprint** — when runnable iteration is needed, delegate to **LoopPrint** (or hand-author) producing under `loops/<slug>/`:
   - `loop-spec.yaml`, `verify.sh`, `maker.sh`, `run-this-loop.sh`, `state.md`, `safety-checklist.md`
   - Loop verifier hooks **iteration gates**; sealed suite hooks **outcome gate** (Stage 6). Do not collapse.
5. **Meta-loop rejection** — no criterion where the loop grades its own orchestration; no auto-merge on self-reported GREEN.
6. **Re-Frame cadence** — for Persistent-ratchet / long-horizon: specify periodic `contract_hash` re-seal schedule in `loop-design.md`.
7. **loopprint-lint** — run on every `loop-spec.yaml`:
   - External verifier (maker ≠ checker)
   - Safety limit present
   - No self-grading verifier
   - No unfilled placeholders

### Outputs / artifacts
| Artifact | Purpose |
|----------|---------|
| `loop-design.md` | Archetype choice, rationale, re-Frame cadence |
| `loop-spec.yaml` (+ LoopPrint package) | Runnable loop blueprint when applicable |
| `reject.md` (if REJECT) | Reason + honest alternative (one-shot, human-gated, LoopPrint-only) |
| `loopprint-lint.txt` | Per-spec lint transcript |

### GATE → Stage 3 (or STOP on REJECT)
- [ ] Archetype chosen and documented **OR** REJECT issued with alternative
- [ ] On REJECT: user acknowledged; pipeline stops unless user reframes objective
- [ ] Every `loop-spec.yaml` passes **loopprint-lint GREEN**
- [ ] Iteration verifier ≠ outcome verifier (separate hooks documented)
- [ ] No meta-loop shape; safety limits set

---

## Stage 3 — Plan

**Job:** Build consensus task graph with per-task acceptance hooks, blast-radius tags, rollback notes, budgets.

### Inputs
- Sealed suite + `loop-design.md` + Capability Manifest
- `integration-map`, `dependency-ledger`, `risk-register`
- Loop blueprint (if any)

### Work performed
1. **Task decomposition** — nodes with: id, description, domain, estimated effort, idempotency class, rollback notes.
2. **DAG construction** — acyclic graph; explicit dependencies including external human merges.
3. **Acceptance hooks** — every node maps to ≥1 sealed criterion id (traceability matrix).
4. **Blast-radius tagging** — tag nodes: `reversible`, `soft-irreversible`, `hard-irreversible`; attach pre-action checkpoint requirements.
5. **Expert resolution** — each node lists required capability; must resolve to agent/persona + tool set via binding profile (no orphan tasks).
6. **Budget & stop** — token/time/iteration limits, scope fence tied to `contract_hash`.
7. **Resumability** — checkpoint fields per node: `pending|in_progress|blocked|done|failed` + resume command.
8. **looptimal-lint** — run on full `loops/<slug>/` package:
   - Writable verifier inputs → RED
   - Symptom-only criteria → RED
   - Missing oracle binding → RED
   - Maker=checker collapse → RED
   - Missing safety limit → RED
   - Meta-loop shape → RED
   - No-op or missing external check → RED

### Outputs / artifacts
| Artifact | Purpose |
|----------|---------|
| `task-graph.yaml` | Nodes, edges, tags, hooks |
| `traceability-matrix.yaml` | criterion_id ↔ task_id mapping |
| `blast-radius-checkpoints.yaml` | Pre-action gates for irreversibles |
| `plan-consensus.md` | Brief rationale; dissent notes if any |
| `looptimal-lint.txt` | GREEN/RED transcript |

### GATE → Stage 4
**looptimal-lint GREEN** AND:
- [ ] Task graph is acyclic
- [ ] Every node hooks to ≥1 sealed criterion
- [ ] Every hard-irreversible node has pre-action checkpoint + rollback note
- [ ] Every node capability resolves to agent + tools (no TBD)
- [ ] Safety limits and scope fence recorded
- [ ] `execute-scope.yaml` pins files/repos/actions allowed under this `contract_hash`

---

## Stage 4 — Simulate

**Job:** War-game the plan before any autonomous Execute. Roll forward, pre-mortem, harden. See `references/simulate.md` for full protocol.

### Inputs
- `task-graph.yaml`, sealed suite, `loop-design.md`
- `risk-register.yaml`, `blast-radius-checkpoints.yaml`
- `capability-manifest.yaml`, `integration-map`
- Loop blueprint (if any)

### Work performed
Execute the four-phase Simulate protocol (path generation → rollout → pre-mortem → plan-hardening). Produce `simulation.md` and `plan-hardening.md`. Apply hardening deltas to plan and suite; if suite changes, re-seal → new `contract_hash` → user ack.

### Outputs / artifacts
| Artifact | Purpose |
|----------|---------|
| `simulation.md` | Paths, rollouts, failure forecasts |
| `plan-hardening.md` | Mitigations, residual risks, plan deltas |
| `simulation-paths.yaml` | Machine-readable path catalog |
| `task-graph.yaml` (updated) | Hardened plan |
| `sealed/acceptance-suite.yaml` (optional update) | If hardening strengthened criteria |
| `frame-manifest.json` (updated) | If `contract_hash` changed |
| `looptimal-lint.txt` (re-run) | Post-hardening GREEN required |

### GATE → Human GO
- [ ] Top-K paths simulated (happy + likely divergences)
- [ ] Every **high-severity** simulated failure has **mitigation** in plan **OR** **acknowledged residual risk** logged in `plan-hardening.md`
- [ ] Post-hardening **looptimal-lint GREEN**
- [ ] If `contract_hash` changed: user acknowledged new seal
- [ ] Irreversibles, open dependencies, top residual risks summarized for GO decision
- [ ] **Human GO gate** — explicit approval recorded in `go-decision.json` (see GO section below)

**Degrade:** User may say `skip simulate` only after Design + Plan complete; require written risk callout and explicit confirmation. Simulate gate waived; all other gates remain.

---

## Human GO Gate

**Job:** Explicit human approval before Execute. Not procedural — substantive.

### Inputs
- `simulation.md`, `plan-hardening.md` (or degrade callout)
- `task-graph.yaml`, `blast-radius-checkpoints.yaml`
- `contract_hash`, `go-brief.md` (auto-summarized top risks)

### Work performed
Present: objective, `contract_hash`, archetype, irreversibles list, open external dependencies, top residual risks, budget/stop limits. Record decision.

### Outputs / artifacts
| Artifact | Purpose |
|----------|---------|
| `go-brief.md` | One-screen decision summary |
| `go-decision.json` | `{ "approved": true|false, "by": "...", "timestamp": "...", "degrade": "skip_simulate|null", "notes": "..." }` |

### GATE → Stage 5
- [ ] `go-decision.json` has `approved: true`
- [ ] Approver is human (not maker/checker agent)
- [ ] Degrade path documented if Simulate was skipped

**No GO → no Execute.** Offer: refine plan, re-simulate, re-Frame, or stop.

---

## Stage 5 — Execute

**Job:** Run the task graph with dynamic domain-expert sub-agents. Maker ≠ checker at iteration gates. Honor pre-action blast-radius checkpoints. Durable, resumable, idempotent steps.

### Inputs
- Approved `go-decision.json`
- `task-graph.yaml`, `execute-scope.yaml`, sealed suite (read-only)
- Binding `dispatch.maker`, `dispatch.checker` profiles
- Loop runner (`run-this-loop.sh`) when archetype includes iteration

### Work performed
1. **Preflight** — confirm `contract_hash` matches sealed suite; scope fence active; no Execute if GO missing.
2. **Dispatch** — for each ready node: resolve capability → agent + tools; log assignment in `execute-log.jsonl`.
3. **Pre-action gates** — before any `hard-irreversible` or `soft-irreversible` step: run checkpoint from `blast-radius-checkpoints.yaml`; require human approval where specified; log receipt.
4. **Maker work** — agent performs node work within `execute-scope.yaml`; writes artifacts; updates node state.
5. **Iteration checker** (per loop iteration, if applicable) — **separate** checker runs `verify.sh` / iteration oracle; maker self-report is informational only.
6. **Checkpointing** — after every meaningful step: update `task-graph.yaml` node status, append `execute-log.jsonl`, sync `state.md`.
7. **Blocked handling** — external dependency blocked → `blocked` status + reason; do not forge ahead on partial registry.
8. **Failure handling** — rollback per node notes; resume from last checkpoint; never silently drop failed nodes.
9. **Budget guard** — stop at safety limit; mark `halted_budget`.

### Outputs / artifacts
| Artifact | Purpose |
|----------|---------|
| `execute-log.jsonl` | Per-step audit trail |
| `task-graph.yaml` (live) | Node statuses |
| `state.md` | Human-readable execution state |
| `checkpoint-receipts/` | Pre-action approvals |
| `iteration-results/` | Per-iteration verifier transcripts (informational) |
| `maker-complete.json` | Maker declaration (informational only; not truth) |

### GATE → Stage 6
- [ ] All in-scope nodes `done` OR explicit scoped-down re-Frame occurred (new `contract_hash`)
- [ ] Every task capability resolved to agent at dispatch time
- [ ] Every pre-action blast-radius checkpoint honored (receipts on file)
- [ ] No `hard-irreversible` action without checkpoint pass
- [ ] `maker-complete.json` present (informational)

**Maker declares complete → informational only.** Checker owns truth in Stage 6.

---

## Stage 6 — Verify-outcome

**Job:** A **separate** checker re-runs the **SEALED** acceptance suite against **live state**. Ignore loop self-reported GREEN. Gate on evidence bundle.

### Inputs
- `sealed/acceptance-suite.yaml`, `contract_hash`
- `sealed/oracle-catalog.yaml`
- `scope-registry.yaml`
- Maker artifacts (untrusted until verified)
- Binding `dispatch.checker` (must differ from maker)

### Work performed
1. **Contract integrity** — verify `contract_hash` matches `sealed/acceptance-suite.sha256`; FAIL on mismatch.
2. **Clean artifact build** — rebuild from clean checkout at pinned SHAs (not maker dirty tree).
3. **Oracle execution** — for each criterion: run sealed oracle with read-only / holdout credentials; apply quorum if flake policy requires (e.g., 5× on fresh runners).
4. **Write-back receipts** — redeployed config, published URL, secret fingerprint, warehouse `max(event_time)` — **re-pulled from external system** by checker, not trusted from maker logs.
5. **Final-state assertions** — live probes maker cannot mutate; ∀ quantification over `scope-registry.yaml`.
6. **Evidence bundle** — assemble:
   - Artifacts + hashes (clean build)
   - Tool receipts with write-back
   - Final-state assertion transcripts
   - Unresolved risks list (any P0/P1 unresolved → FAIL even if narrow criteria pass)
7. **Repeat/quorum** — for non-deterministic oracles: run quorum; never accept single lucky pass.
8. **Verdict** — GREEN only if all sealed criteria pass under quorum rules and `contract_hash` matches.

### Outputs / artifacts
| Artifact | Purpose |
|----------|---------|
| `outcome-verdict.json` | `{ "result": "GREEN|RED", "contract_hash": "...", "criteria": [...], "findings": [...] }` (written via `--out`, never into the bundle dir) |
| `evidence-bundle/` | Artifacts, receipts, assertion logs |
| `checker-transcript.txt` | Full oracle run log |
| `unresolved-risks.md` | P0/P1 items |

### GATE → Stage 7
- [ ] Sealed suite re-run passes **externally** (checker role, not maker)
- [ ] Quorum satisfied for flaky oracles
- [ ] `contract_hash` matches `frame-manifest.json`
- [ ] Evidence bundle complete
- [ ] No unresolved P0 risks
- [ ] `verify-outcome.json` verdict == **GREEN**

**On FAIL:** record remediation class (`fix-and-resume`, `re-Frame`, `re-Plan`, `abort`); do not mark done.

---

## Stage 7 — Persist

**Job:** Write durable state for resume, audit, and organizational learning.

### Inputs
- All stage artifacts
- `verify-outcome.json` (GREEN or FAIL)
- `execute-log.jsonl`, `simulation.md`, `plan-hardening.md`

### Work performed
1. **Outcome record** — objective, `objective_hash`, `contract_hash`, archetype, verdict, timestamps.
2. **Remediation class** — durable fix | temporary-backfill | partial-blocked | aborted | success.
3. **What worked / failed** — honest postmortem; include silent-failure near-misses.
4. **Oracle results summary** — per-criterion final values.
5. **Resume pointers** — if FAIL: exact stage/node to resume; if GREEN: none.
6. **Lessons** — feed LoopPrint skillify only after **checker GREEN** (never on maker report).
7. **Re-Frame schedule** — for Recurring / Persistent-ratchet: next seal date.

### Outputs / artifacts
| Artifact | Purpose |
|----------|---------|
| `persist-summary.md` | Human-readable closeout |
| `run-manifest.json` | Machine-readable full provenance |
| `lessons.yaml` | Patterns for future runs |
| `resume.json` | Resume pointer or null |

### GATE → Done
- [ ] `run-manifest.json` written
- [ ] Remediation class recorded (not just GREEN/FAIL)
- [ ] Resume pointer valid if FAIL
- [ ] For Recurring: next run schedule + re-Frame cadence persisted

---

## Resume rules

| Condition | Action |
|-----------|--------|
| `objective_hash` matches + prior incomplete | Resume last incomplete stage |
| `objective_hash` changed materially | Re-Frame (new `contract_hash`) |
| `contract_hash` changed mid-run | Re-Plan minimum; re-Simulate if plan structure changed |
| Prior REJECT | Fresh Design-loop after re-Frame |
| FAIL at Stage 6 with `fix-and-resume` | Resume Execute at failed node; Stage 6 re-run |

---

## Stage transition diagram

```
0 Frame ──contract-lint GREEN──► 1 Analyze ──manifest complete──► 2 Design-loop
                                                                    │
                                    REJECT ──► STOP (honest alt)    │
                                    loopprint-lint GREEN            ▼
                                                              3 Plan ──looptimal-lint GREEN──► 4 Simulate
                                                                                                      │
                                                                                    hard-sev mitigated/residual acked
                                                                                                      ▼
                                                                                              Human GO
                                                                                                      │
                                                                                              approved:true
                                                                                                      ▼
                                                                                              5 Execute
                                                                                                      │
                                                                                              maker-complete (info)
                                                                                                      ▼
                                                                                              6 Verify-outcome
                                                                                                      │
                                                                                              checker GREEN + contract_hash match
                                                                                                      ▼
                                                                                              7 Persist ──► Done
```

Author: Renn Labs. MIT.
