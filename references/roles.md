# Process roles — abstract bindings through profile.yaml

Looptimal separates **process roles** (what function someone performs in the pipeline) from **harness agents** (how this machine dispatches work). Generic files name only process roles. Concrete agent strings live in `profile.yaml` — never hardcoded in references, templates, or scripts.

Every role resolves through the **same two-tier mechanism** as domain experts (see [`agent-foundry.md`](agent-foundry.md)): Tier A when `roles.<role>.agent` or `registry` advertises a native match; Tier B as generic slot + persona when not.

---

## 1. Process role catalog

| Role | Pipeline function | Typical stages | Default side |
|------|-------------------|:--------------:|:------------:|
| **framer** | Turn objective into hash-pinned SEALED acceptance suite; bind criteria to outcome-oracles | 0 | executor |
| **analyst** | Produce Capability Manifest — domains, integrations, risks | 1 | executor |
| **planner** | Build consensus task graph; attach acceptance hooks and safety limits | 3 | executor |
| **architect** | Structural decisions — boundaries, interfaces, rollback topology | 2–4 | executor |
| **critic** | Independent review of artifacts; challenge assumptions; no direct edits | 1–6 | checker |
| **verifier** | Outcome altitude — re-run SEALED suite vs live state; assemble evidence bundle | 6 | checker |
| **executor** | General bounded work units not requiring a domain persona | 5 | executor |
| **domain-expert** | Capability-scoped delivery per manifest + foundry spin-up | 5 | executor |
| **promoter** | Persist durable state; promote lessons; optional skillify handoff | 7 | executor |
| **red-team** | Adversarial pre-mortem — reward-hacking, silent failure, scope shrink | 4 | checker |
| **forecaster** | Simulate roll-forward; predict failure modes; harden plan | 4 | executor |

Roles are not agents. They are stable IDs used in `profile.yaml` → `roles:` and `lanes:`.

---

## 2. profile.yaml binding (LoopPrint + Looptimal)

Looptimal **extends** LoopPrint's binding contract. Inherited keys behave identically; new keys drive role and capability resolution.

```yaml
# --- LoopPrint base (unchanged semantics) ---
harness: <informational>
state_dir: loops/<slug>
marker_path: ""
verifier:
  default: ""                # Stage 6 outer outcome gate — MUST differ from all executors
dispatch:
  maker: ""                  # default executor dispatch
  checker: ""                # default checker dispatch (≠ maker)
runner: run-this-loop.sh
banner: ""

# --- Looptimal extensions ---
registry:
  <capability-id>:
    agent: ""                # optional native specialist; empty → Tier B foundry
    model_tier: strong | standard | cheap

roles:
  <role-id>:                 # framer | analyst | planner | architect | critic | verifier |
                             # executor | domain-expert | promoter | red-team | forecaster
    agent: ""                # harness-specific agent/command; empty → dispatch fallback
    model: ""                # or model_tier alias

lanes:
  <archetype>:               # task | recurring | supervised | persistent-ratchet | orchestration
    executor_role: <role-id>
    checker_role: <role-id>  # MUST ≠ executor_role
    model_tier: strong | standard | cheap
```

Resolution order for profile: `./.looptimal/profile.yaml` → `~/.looptimal/profile.yaml` → `scripts/looptimal-detect.py` → generic defaults.

### Fallback chain (per role)

```
roles.<role>.agent
  → (if domain-expert) registry.<capability>.agent via foundry
  → dispatch.maker  (executor-side roles)
  → dispatch.checker (checker-side roles)
  → generic sub-agent slot
```

`verifier` role maps to `verifier.default` for Stage 6 — not `dispatch.checker` unless profile explicitly aliases them (lint warns on collapse).

---

## 3. Two-tier resolution (roles)

Identical to foundry; repeated here because every stage uses it.

**Tier A** — `roles.<role>.agent` or `registry.<capability>.agent` is non-empty and harness recognizes it → bind native specialist.

**Tier B** — empty agent → generic slot (`dispatch.maker` / `dispatch.checker` / sub-agent primitive) + persona:

| Role | Persona source |
|------|----------------|
| domain-expert | `personas/<capability>.md` or [`agent-persona.md`](../templates/agent-persona.md) |
| framer, analyst, planner, architect, promoter, forecaster | `personas/<role>.md` or `templates/agent-persona.md` |
| critic, verifier, red-team | `personas/<role>.md` — checker personas emphasize independence |

All roles: lint enforces `executor.agent ≠ checker.agent ≠ verifier.default` at the resolved binding layer.

---

## 4. Lane → role routing (archetypes)

`lanes.<archetype>` sets the **default executor and checker roles** for iteration gates in that loop shape. Stage 5 domain work still uses `domain-expert` for capability-scoped nodes; lane roles govern orchestration altitude and cross-capability gates.

| Archetype | executor_role | checker_role | model_tier | Routing notes |
|-----------|---------------|--------------|:----------:|---------------|
| **task** | executor | critic | standard | Bounded delivery; checker reviews diffs + hooks before merge to Stage 6 |
| **recurring** | promoter | critic | cheap | Freshness passes; executor often rotates cheap tier; oracle is
