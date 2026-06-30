# Schema reference — the portable Looptimal contract

Looptimal's artifacts are plain YAML + POSIX shell. This page is the **canonical, versioned schema** for them, so
any runtime can *emit* a conforming loop and any validator can *consume* one without coupling to Looptimal's
internals.

> **The executable schema is [`scripts/loopprint-lint.py`](../scripts/loopprint-lint.py).** This page is the
> prose contract; the linter is the *enforced* one (portable — `python3` + PyYAML, runs anywhere). The two cannot
> drift: [`tests/test_schema_doc.py`](../tests/test_schema_doc.py) fails the build if this page stops listing any
> value the linter accepts. We deliberately ship **no JSON Schema** — a second machine-readable copy would rot
> against the linter, the same anti-rot rule [`profiles.md`](profiles.md) applies to harness bindings. The linter
> *is* the schema; this page is its readable index.

## Schema version

`schema_version: 1` — the current version, understood by `loopprint-lint`. See [Versioning policy](#versioning-policy).

## `loop-spec.yaml` — one loop

The four atoms (Goal / State / Verifier / Stop) plus the work pattern and guardrails. Canonical template:
[`templates/loop-spec.yaml`](../templates/loop-spec.yaml).

| Field | Type | Required | Notes |
|-|-|-|-|
| `schema_version` | int | yes | Must be ≤ the linter's `SCHEMA_VERSION`. |
| `slug` | string | yes | kebab-case; also the `loops/<slug>/` dir name. No unfilled `<placeholders>`. |
| `created` | date | no | `YYYY-MM-DD`. |
| `pattern` | enum | yes | One of: `morty`, `spec-driven`, `performance`, `hybrid`. The *work*, not the verifier. |
| `goal` | string | yes | One testable sentence; "done" must be machine- or reviewer-checkable. |
| `state.path` | path | yes | Durable record; never reset until the goal is met. |
| `verifier.kind` | enum | yes | One of: `test`, `build`, `lint`, `repro`, `benchmark`, `rubric`, `reviewer`, `critic-panel`. |
| `verifier.shape` | enum | no (default `gate`) | `gate` = one-shot pass/fail. `ratchet` = "no worse than a committed baseline"; requires `stop.budget` + a sibling `baseline` + `ratchet-advance.sh`. |
| `verifier.command` | string | one of command/reviewer | Exact shell command; exit 0 = GREEN. Run as a SEPARATE process — never the maker. |
| `verifier.reviewer` | string | one of command/reviewer | A named reviewer/agent that MUST differ from the maker (maker ≠ checker). |
| `verifier.panel` | map | only for `critic-panel` | `n` (int > 0), `quorum_k` (int, 0 < k ≤ n), `threshold` (int 0–100). |
| `stop.max_iterations` | int | yes (or a budget) | Hard safety cap. |
| `stop.budget.tokens` / `.wall_clock_minutes` | int \| null | yes (or max_iterations) | Wall-clock is the hard cap for ratchet/persistent loops; tokens are adapter-dependent. |
| `autonomy` | enum | yes | One of: `full`, `checkpoint`, `dry-run`. |
| `checkpoint_mode` | enum | no | One of: `before`, `after`. `before` = authorize each iteration; `after` = review each GREEN. |
| `human_checkpoints` | list | yes (may be `[]`) | Irreversible/high-stakes steps that require a human (a STOP shape, not a verifier — see [verifiers.md](verifiers.md#human-in-the-loop-two-distinct-roles-not-a-verifier-shape)). |
| `metrics.path` / `.state_jsonl` | path | no | Append-only observability the runner emits. |

The runner [`run-this-loop.sh`](../templates/run-this-loop.sh) is **YAML-blind**: it reads bash vars the wizard
fills, never parses this file, and execs sibling scripts only (never `eval`s a command string from the spec).

## `campaign-spec.yaml` — an ordered, supervised campaign of loops

A campaign is a **composition**: each stage is a normal `loop-spec` loop. Canonical template:
[`templates/campaign-spec.yaml`](../templates/campaign-spec.yaml); full contract in [`campaign.md`](campaign.md).

| Field | Type | Required | Notes |
|-|-|-|-|
| `kind` | const | yes | Must be `campaign`. |
| `goal` | string | yes | The campaign objective. |
| `plan` | path | yes | A human plan artifact (`plan.md`) — without it a campaign is a shell `for`-loop. |
| `autonomy` | const | yes | Must be `checkpoint` — campaigns are supervised between stages. |
| `stages[].slug` | string | yes | Distinct per campaign. |
| `stages[].goal` | string | yes | The stage subgoal. |
| `stages[].loop_dir` | path | yes | A real leaf loop dir (has `loop-spec.yaml` + `verify.sh`). |
| `stages[].stage_success` | enum | yes | One of: `gate`, `ratchet`. `gate` ⇒ stage OK on runner exit `0`; `ratchet` ⇒ OK on exit `2` or `6` (a ratchet never exits 0). |

## `verifier-library.yaml` — copy-paste recipes

A library of `verify.sh` recipes (test, lint, build, repro, benchmark, llm-rubric-judge, human-vote,
critic-panel). Each is an EXTERNAL gate (exit 0 = GREEN). Recipes are **pasted into `verify.sh`** — never `eval`d
from the spec. `human-vote` is the verifier-of-last-resort (distinct from a human *checkpoint* stop-shape).

## The portable emit / consume contract

The format is pinned so it can cross runtime boundaries:

- **Emit** — any runtime or harness can generate a `loop-spec.yaml` / `campaign-spec.yaml` that conforms to this page.
- **Validate** — `python3 scripts/loopprint-lint.py <spec> …` is the executable schema (exit 0 = conforms, non-zero
  = RED with findings). It is the single source of truth; this page indexes it.
- **Consume** — `run-this-loop.sh` consumes a loop via bash vars (YAML-blind); the wizard bridges spec → vars.

**Honest scope:** there is **no external consumer path today**. This contract is a **defensive hedge** — it exists
so that *if* another runtime (Ralph, OMX, your own harness) later wants to emit or consume Looptimal loops, the
format is already versioned and pinned. It is a published contract, not a near-term integration. All three review
models rated this Low for exactly that reason; it ships as a forward-compatibility note.

### `/ralph` emits a spec (worked reference)

A persistence harness like **Ralph** can emit a `loop-spec.yaml` instead of running an ad-hoc loop — pinning its
goal, its external verifier, and its stop budget into a portable artifact that `loopprint-lint` then gates:

```bash
# A harness emits a conforming spec (illustrative — no runtime consumes it yet):
cat > loops/ralph-debt/loop-spec.yaml <<'YAML'
schema_version: 1
slug: ralph-debt
pattern: performance
goal: "Drive lint-debt to zero without regressing the test suite."
verifier: { kind: lint, shape: ratchet, command: "bash verify.sh" }
stop: { max_iterations: 200, budget: { tokens: null, wall_clock_minutes: 120 } }
autonomy: full
human_checkpoints: []
YAML
python3 scripts/loopprint-lint.py loops/ralph-debt/loop-spec.yaml   # the executable schema gates it
```

This is the **emit** half of the contract. Looptimal validates and (via the wizard + runner) can consume it; no
*third-party* runtime consumes it yet — that's the deferred half.

## Versioning policy

- `schema_version` is an integer. The linter understands specs up to its `SCHEMA_VERSION` and flags any spec that
  declares a higher version (forward-compat warning).
- **Additive** fields (a new optional key, a new profile) do **not** bump the version — older linters ignore them.
- A **breaking** change (renamed/removed field, changed semantics of an existing field) bumps `schema_version`.
- The **four atoms** (goal / state / verifier / stop) are the stable core. Everything else — `pattern`,
  `verifier.shape`, `panel`, `campaign`, dispatch/provider profile metadata — is additive on top of them.
