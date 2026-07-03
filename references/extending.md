# Extending Looptimal — the platform contract and where you plug in

Looptimal turns an objective into a **verified outcome**: a sealed acceptance suite, an independent verifier that
re-runs it against live state, and maker ≠ checker throughout. The platform is the **standard** — two composable
surfaces you can build on without coupling to Looptimal's internals.

The design rule that keeps this safe:

> **Looptimal does not ingest third-party extensions. It publishes a contract; you implement it in your own repo.**

The first-party verified loop library (`library/`) ships loops that conform to the same standard any adopter can
meet. Competitors like [loops.show](https://loops.show) and Forward Future are prose or editorial-score
directories — useful inspiration, but no machine enforcement at the door. Our edge is **runs in your env** plus
**live re-run** plus **receipts**, not a stored trust field.

## The two composable surfaces

| Surface | What it is | When it applies |
|-|-|-|
| **LOOPS** | Installable `loop-spec.yaml` bundles with a real external `verify.sh` | Recurring or standalone work you want gated by a portable four-atom contract |
| **COMPONENTS** | Definition-time modules the pipeline folds into a stage per challenge | Analyze (and adjacent definition work) when a mission needs deeper domain tooling |

Both surfaces are **dependency-light** and **generic** — plain YAML + POSIX shell for loops; plain artifacts and
delegation hooks for components. Neither requires a specific harness, cloud service, or proprietary runtime.

---

## 1. LOOPS — the four-atom portable contract

A loop is a `loop-spec.yaml` plus sibling scripts (`verify.sh`, runner, state path). The stable core is the four
atoms:

| Atom | Field(s) | Contract |
|-|-|-|
| **Goal** | `goal` | One testable sentence; "done" must be machine- or reviewer-checkable. |
| **State** | `state.path` | Durable record; never reset until the goal is met. |
| **Verifier** | `verifier.*` | An **external** gate — `verifier.command` or `verifier.reviewer` — run as a separate process. |
| **Stop** | `stop.*` | A safety limit (`max_iterations` and/or `budget`) that ends the loop even if the goal is never met. |

Canonical schema: [`schema.md`](schema.md). Canonical template: [`templates/loop-spec.yaml`](../templates/loop-spec.yaml).

### The linter bar

The **executable** schema is [`scripts/loopprint-lint.py`](../scripts/loopprint-lint.py). It is what makes
"verified" mean something at publish time — not prose in this page.

`lint_spec` **hard-rejects**:

- **Empty gates** — no `verifier.command` and no `verifier.reviewer`.
- **No-op gates** — trivial always-pass commands (`true`, `exit 0`, …).
- **Self-grading gates** — verifier strings that read like the maker judging its own work.

A blueprint that fails lint is not a loop; it is a wish. The linter exists so LoopPrint cannot ship the defect
Looptimal was built to prevent.

### `verifier.kind` — documented, not lint-enforced

[`schema.md`](schema.md) lists `verifier.kind` as a required enum (`test`, `build`, `lint`, `repro`, `benchmark`,
`rubric`, `reviewer`, `critic-panel`). That prose is the readable index.

**Honest caveat:** `lint_spec` does **not** validate `verifier.kind` against that enum. The linter checks that a
real external gate exists and is not trivial or self-grading; it only special-cases `kind: critic-panel` for panel
quorum fields. Any other `kind` value — or a missing `kind` — passes lint if the command/reviewer bar is met. This
is **open by omission**, not by design: tightening it is a future schema bump, not a hidden guarantee today.

### Extending loops in your repo

To add a loop outside the first-party library:

1. Copy a conforming bundle shape from [`templates/`](../templates/) or [`examples/`](../examples/).
2. Write `verify.sh` as an external gate (exit 0 = GREEN); paste recipes from
   [`templates/verifier-library.yaml`](../templates/verifier-library.yaml) — never `eval` a command string from
   the spec.
3. Gate with `python3 scripts/loopprint-lint.py loops/<slug>/loop-spec.yaml`.
4. Run the loop via your harness binding ([`profiles.md`](profiles.md)) or the generic `run-this-loop.sh` runner.

The library CLI ([`library.md`](library.md)) is optional — it is how *this* repo distributes first-party loops to
consumer repos. Your extension does not need to land in `library/` to be valid.

---

## 2. COMPONENTS — definition-time modules per challenge

**Components** are pluggable definition-time modules — not universal pipeline gates. Analyze (Stage 1) produces a
**Capability Manifest** ([`pipeline.md`](pipeline.md)); when a challenge warrants deeper tooling, the pipeline
**folds a component into that stage** for that mission. A component does not run on every objective; it runs when
the manifest says the work needs it.

| Component | Status | Role |
|-|-|-|
| **esat** | Shipped precedent | Tri-model stress-test of definition, scope, and oracle adequacy during Analyze; feeds the Capability Manifest — does not replace Frame or Verify-outcome. |
| **pmf-simulation** | Next | Demand / market-fit simulation folded into Frame/Analyze when the challenge is demand-uncertain: synthetic user personas score candidate loops/features against a fixed rubric (Pain, Recurrence, VerifiabilityFit, EaseOfAdoption, Portability, Stickiness) to surface PMF gaps. Cross-provider judge quorum verifier; hypothesis generator routing to real user validation — never a truth oracle. |

Components honor the same invariants as loops at the altitude they operate: sealed inputs before execution,
external checks where claims are made, maker ≠ checker for anything that grades an outcome. They are **not** a
substitute for Stage 6 (`verify-outcome.py`) or a loop's `verify.sh`.

### How to extend with a component

1. Declare the capability in the Capability Manifest (domain, risks, integration edges).
2. Emit artifacts to a predictable path under the mission `state_dir` so downstream stages can consume them.
3. Keep the module **invokable, not embedded** — a script, skill, or harness dispatch the binding profile can call;
   Looptimal's generic files must not hardcode harness or agent names ([`agent-foundry.md`](agent-foundry.md)).
4. Do not weaken the global rule: acceptance is proven by hashes, re-execution, and external receipts — never by
   a component's self-report alone.

---

## Other extension points (already in the standard)

### Oracle patterns — project-local extensions

[`oracle-library.md`](oracle-library.md) seals domain outcome-oracle patterns. Every acceptance criterion must bind
to one. Projects may add **project-local** oracle patterns when the extension is:

- reviewed before execution
- assigned a stable id
- sealed with fixed inputs
- lint-visible
- referenced from the accepted plan
- externally checkable by Stage-6

Project-local extensions must not weaken the global rule: raw booleans and unsealed loop-authored checks are still
rejected.

### Persona extension

Domain experts and pipeline roles resolve through the two-tier foundry ([`agent-foundry.md`](agent-foundry.md)):

- **Tier A** — curated `personas/<capability>.md` files in-repo or under `~/.looptimal/personas/`.
- **Tier B** — synthesized from [`templates/agent-persona.md`](../templates/agent-persona.md) when no curated
  persona exists; promotable to Tier A after a checker-GREEN mission
  ([`scripts/looptimal-persona-promote.py`](../scripts/looptimal-persona-promote.py)).

Adding a persona is an extension of the **capability surface**, not a change to Looptimal core.

### Pattern extension

The four shipped work patterns (`morty`, `spec-driven`, `performance`, `hybrid`) are enumerated in
[`patterns.md`](patterns.md) and enforced by `lint_spec` today. **Hybrid** is the composition escape hatch: nest or
sequence sub-loops, each keeping its own verifier, with a composite outer gate. New *work shapes* beyond the enum
require a schema bump and linter update — they are not silent extensions.

Verifier **shape** (`gate`, `ratchet`, `critic-panel`) is orthogonal to pattern; route it from the
[Decision Gate](decision-gate.md), not from the work pattern alone.

### Harness bindings

[`profiles.md`](profiles.md) covers repo-local and user-level `profile.yaml` bindings — how a generated blueprint
maps to *your* harness without Looptimal hardcoding volatile ecosystem details.

---

## What the library does not do

- **No third-party ingestion.** The first-party `library/` catalog is maintained in this repo under the same lint
  and smoke gates as any adopter's loops. There is no submission form, editorial score, or imported directory.
- **No trust-by-metadata.** Verified means `verify.sh` executes to a real verdict in the consumer repo
  ([`library.md`](library.md)) — not a badge field you can write by hand.
- **No coupling.** Extensions live in your repo, your `~/.loopprint/`, or your `~/.looptimal/personas/` — not as
  forks of Looptimal internals.

Build on the standard; keep the gates external; let the verifier re-run live state. That is the whole platform
contract.