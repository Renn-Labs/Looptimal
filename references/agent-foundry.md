# Agent Foundry — dynamic domain experts

Looptimal never ships a fixed expert roster. The **Capability Manifest** (Stages 1–2) names the domains a mission needs; Stage 3 maps every task node to a **capability**; Execute spins up one domain expert per capability. The foundry is the resolver that turns `(capability, role, lane)` into a concrete agent invocation on *this* harness — without hardcoding harness or agent names in generic files.

Binding source (first found wins): `./.looptimal/profile.yaml` → `~/.looptimal/profile.yaml` → `scripts/looptimal-detect.py` → generic defaults. Contract: [`roles.md`](roles.md).

---

## 1. Capability Manifest drives who spins up

| Stage | Manifest work | Foundry effect |
|:-----:|---------------|----------------|
| 1 **Analyze** | Enumerate material domains, integration edges, risks, outcome-oracle families | Seed `capabilities[]` — each entry is a named skill surface the mission will need (e.g. `payments-reconciliation`, `terraform-iac`, `compliance-review`) |
| 2 **Design-loop** | Confirm archetype; prune domains that belong outside the loop; add archetype-specific capabilities (e.g. ratchet metric steward, orchestration coordinator) | Finalize `capabilities[]` and tag each with `lane_hint` + `oracle_family` |
| 3 **Plan** | Every task-graph node carries `capability: <id>` (required) | Execute queue = distinct capabilities referenced by ready nodes |
| 5 **Execute** | One domain-expert invocation per capability (shared across nodes) | Foundry resolves each capability twice per iteration gate: **executor** and **checker** |

The manifest is the single source of truth for *which* experts exist this run. Adding a new domain never requires a code change — only manifest + persona synthesis.

Artifact: `capability-manifest.yaml` under the resolved `state_dir`.

```yaml
capabilities:
  - id: api-hardening
    domain: "HTTP API security and authZ"
    lane_hint: task
    oracle_family: integration-test
    tasks: [T-014, T-021]          # Stage 3 back-links
  - id: docs-accuracy
    domain: "Public API reference truth"
    lane_hint: recurring
    oracle_family: published-hash
    tasks: [T-030]
```

---

## 2. Two-tier resolver

Every role binding (including `domain-expert`) resolves through the **same** two-tier path. Tier A is leveraged when the harness advertises a native match; Tier B is the portable floor that works with zero native agents.

### Resolution algorithm

```
resolve(capability, role, lane, side) → ResolvedAgent
  side ∈ {executor, checker}   # maker ≠ checker enforced here

  1. lane_cfg  ← profile.lanes[lane.archetype]
  2. role_id   ← side == executor ? lane_cfg.executor_role : lane_cfg.checker_role
                 (domain-expert tasks override role_id → domain-expert for executor side only)
  3. tier      ← coalesce(capability.model_tier, lane_cfg.model_tier, role.model_tier, "standard")

  4. TIER A — registry native specialist
     if profile.registry[capability.id].agent is non-empty:
       return { agent: registry[capability.id].agent,
                model_tier: registry[capability.id].model_tier ?? tier,
                tier: "A", persona: null }

  5. TIER B — synthesized domain expert (self-contained floor)
     persona ← load_persona(capability)
     base    ← profile.roles[role_id].agent ?? profile.dispatch.maker (executor)
               ?? profile.dispatch.checker (checker) ?? generic sub-agent slot
     return { agent: base, model_tier: tier, tier: "B", persona: persona }

  6. POST-CHECK (lint + runtime)
     assert executor.agent ≠ checker.agent
     assert checker.agent ≠ profile.verifier.default   # outer outcome verifier is third party
```

### Tier A — native specialist (leveraged, not required)

When `profile.registry[<capability>]` advertises a harness-native agent, bind directly. This is faster and richer when the harness ships curated specialists — but **never mandatory**. Empty or missing registry entries fall through to Tier B automatically.

```yaml
registry:
  terraform-iac:
    agent: "harness:terraform-specialist"   # YOUR binding — illustrative only
    model_tier: strong
  python-refactor:
    agent: ""
    model_tier: standard                    # empty agent → Tier B
```

Tier A still receives mission context (task node, acceptance hooks, sealed suite hash) as injected preamble. The native agent definition is not edited per run.

### Tier B — synthesized domain expert (portable floor)

Tier B = **generic agent slot** + **persona prompt**. Works on a bare agent runtime, shell dispatch, or any harness with a sub-agent primitive and no native library.

Persona load order:

1. `personas/<capability-id>.md` — curated, versioned, ships in-repo (**consistency**)
2. `personas/<domain-slug>.md` — fallback slug from manifest `domain` field
3. `templates/agent-persona.md` — meta-template fill (**dynamism**)

Meta-template variables (all required at synthesis time):

| Variable | Source |
|----------|--------|
| `{domain}` | manifest entry `domain` |
| `{mission-context}` | objective summary + task node scope + sealed suite criterion IDs |
| `{success-criteria}` | per-node acceptance hooks + oracle family |
| `{anti-patterns}` | archetype failure modes from Simulate + domain risks from Analyze |
| `{checklist}` | idempotent steps, blast-radius tags, rollback notes from Plan |

Synthesized personas are written to `state_dir/spinups/<capability-id>/persona.md` for audit and resume. They are ephemeral per run but reproducible from manifest + template.

---

## 3. Consistency vs dynamism

| | Consistency | Dynamism |
|---|-------------|----------|
| **What** | `personas/` library checked into the skill/repo | Capability Manifest + `agent-persona.md` meta-template |
| **When** | Known domains you run repeatedly | Novel cross-domain missions, one-off integrations |
| **Stability** | Reviewed prompts, stable tone and guardrails | Generated per run from mission facts |
| **Harness** | Tier A or B | Tier B only (Tier A optional accelerator) |
| **Change surface** | Edit persona file; registry points at it implicitly | Edit manifest/domain text; no code change |

Both tiers honor the same acceptance hooks and maker ≠ checker rules. Consistency does not mean a fixed roster — the manifest still decides *which* personas load. Dynamism does not mean chaos — synthesized personas use the same meta-template sections and lint the same way.

---

## 4. Maker ≠ checker (both tiers, three altitudes)

Looptimal enforces separation at three altitudes. `looptimal-lint.py` RED-fails on collapse.

| Altitude | Executor | Checker | Rule |
|----------|----------|---------|------|
| **Iteration gate** (per capability / per loop pass) | `resolve(..., side=executor)` | `resolve(..., side=checker)` | `executor.agent ≠ checker.agent`; distinct model context strongly recommended |
| **Task node** (Plan hook) | domain-expert executor | critic or domain-expert checker per lane | checker must not share session memory with executor |
| **Outcome** (Stage 6) | Stage 5 makers collectively | `profile.verifier.default` via `dispatch.checker` | checker ≠ any executor agent used in the run; re-runs **SEALED** suite vs live state |

Tier A does not exempt the run: a native specialist as executor still requires a different agent (native or synthesized) as checker. Tier B default: executor uses `roles.domain-expert` binding; checker uses `roles.critic` or lane `checker_role`.

```
looptimal-lint.py checks:
  - dispatch.maker ≠ dispatch.checker
  - lanes[*].executor_role ≠ lanes[*].checker_role (role IDs)
  - resolved executor agent ≠ resolved checker agent (when spinup artifacts exist)
  - verifier.default not equal to any registry.agent slated for execution
```

---

## 5. Tiered model routing

`model_tier` routes cost and capability. Resolution precedence:

```
capability.registry.model_tier → lane.model_tier → role.model → default "standard"
```

| Tier | Typical use | Examples |
|------|-------------|----------|
| **strong** | Multi-step reasoning, security, architecture, ambiguous integration | orchestration coordinator, authZ redesign, simulate red-team |
| **standard** | Default delivery work | feature implementation, test authoring |
| **cheap** | Bounded transforms, deterministic edits, formatting | changelog sync, badge update, structured JSON emit |

Hard lanes (orchestration, persistent-ratchet, security capabilities) should bias **strong** on executor; checkers can be **standard** if the oracle is predominantly external. Bounded recurring freshness tasks bias **cheap** on executor with **standard** checker.

Profile binds tiers to harness-specific model IDs in `roles` or a separate `models:` map (harness-owned; not hardcoded here).

---

## 6. Spin-up contract (Execute)

For each capability entering execution:

1. Read manifest entry + ready task nodes.
2. `executor ← resolve(capability, domain-expert, lane, executor)`
3. `checker   ← resolve(capability, lane.checker_role, lane, checker)`
4. Write `state_dir/spinups/<id>/binding.yaml` recording tier, agent IDs, model_tier, persona path.
5. Dispatch executor with: persona (if Tier B), task slice, non-writable suite hash, safety limits.
6. On executor completion, dispatch checker with: executor artifact hashes only — not executor chain-of-thought session.
7. Checker verdict is informational until Stage 6 outcome verifier rules.

Resume: if `binding.yaml` exists and capability id unchanged, reuse tier/persona; if manifest domain text changed materially, re-synthesize persona and bump `persona_rev`.

---

## 7. Generic defaults (no profile)

| Field | Default |
|-------|---------|
| Executor | `dispatch.maker` → shell / generic sub-agent |
| Checker | `dispatch.checker` → separate generic sub-agent |
| Tier | B for all capabilities |
| Persona | always synthesize from `templates/agent-persona.md` |
| Registry | empty — no Tier A |

The foundry is fully functional with zero native agents. Registry entries are accelerators, not dependencies.

---

## 8. Anti-patterns (REJECT or lint RED)

- Fixed roster in skill text ("always spin up python-pro and sql-pro") — use manifest + registry instead.
- Same native agent as executor and checker because "it's the best expert".
- Tier B persona that omits `{success-criteria}` or acceptance hook IDs — untestable spin-up.
- Hardcoded harness agent names in `references/` or `templates/` — belong only in user profile YAML.
- Executor grading its own output before checker dispatch — checker must run in a separate context/process.

---

## Related

- Process roles and lane routing: [`roles.md`](roles.md)
- Profile contract: [`roles.md`](roles.md)
- Stage 1 manifest: [`pipeline.md`](pipeline.md)
- Stage 3 task graph: [`pipeline.md`](pipeline.md)
- Stage 5 execute: [`pipeline.md`](pipeline.md)
- Persona meta-template: [`../templates/agent-persona.md`](../templates/agent-persona.md)
