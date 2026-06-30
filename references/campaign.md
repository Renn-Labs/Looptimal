# Campaign — supervised multi-stage composition

A **campaign** is an ordered set of independent Looptimal leaf loops composed by a
`campaign-spec.yaml` manifest. It is a **composition**, not a new loop type: each stage is a
normal loop with its own `loop-spec.yaml`, `verify.sh`, `maker.sh`, and `run-this-loop.sh`.
The manifest records the order, success criteria, and human checkpoint requirement. The runner
stays YAML-blind — it reads env vars and emits exit codes; the campaign layer reads those codes.

See `examples/campaign-staged-remediation/` for a worked two-stage example.

---

## When to use a campaign

A campaign is justified when:
- The work naturally decomposes into stages with **different verifiers** (e.g. derive-spec then
  remediate — one gate cannot serve both).
- A **fixed gate per stage** is only valid after the previous stage commits its output.
- A human needs to **inspect and approve** between stages before the next can start.

If a single verifier covers the whole work, use one loop. A campaign for one stage is overhead.

---

## Schema (`campaign-spec.yaml`)

```yaml
schema_version: 1
kind: campaign          # REQUIRED — distinguishes from loop-spec.yaml
goal: "<one-sentence campaign objective>"
plan: plan.md           # REQUIRED — human plan artifact; must exist on disk
autonomy: checkpoint    # REQUIRED — campaigns are supervised; inter-stage checkpoint is mandatory
stages:
  - slug: stage-1-<name>          # unique within the campaign
    goal: "<stage subgoal>"
    loop_dir: stage-1             # must resolve to a dir with loop-spec.yaml + verify.sh
    stage_success: gate           # gate or ratchet (see exit-code semantics below)
  - slug: stage-2-<name>
    goal: "<stage subgoal>"
    loop_dir: stage-2
    stage_success: gate
stop:
  on_stage_failure: halt-and-flag # NEVER auto-advance past a failed stage
  resume: "--from-stage N"        # documented resume (orchestrator, when built)
```

### Lint rules (enforced by `loopprint-lint.py`)

**Blocking (RED):**
- `kind` must be `"campaign"`.
- `goal` must be non-empty.
- `autonomy` must be `"checkpoint"` — a campaign without inter-stage checkpoints is a shell
  for-loop, not Autopilot.
- `plan` must name a file that exists on disk.
- `stages` must be a non-empty list.
- Each stage must have `slug`, `goal`, `loop_dir`, and `stage_success`.
- Stage slugs must be unique within the campaign.
- `stage_success` must be `gate` or `ratchet`.
- Each `loop_dir` must resolve to a directory containing **both** `loop-spec.yaml` and `verify.sh`.

**Advisory (non-failing, `~` prefix):**
- If a stage's leaf `loop-spec.yaml` has `verifier.shape: ratchet` but `stage_success` is
  `gate` (or vice versa) — consistency hint.
- If `schema_version` exceeds the linter's known version — forward-compat note.

---

## Exit-code semantics and `stage_success`

The runner emits a process exit code after each stage. The campaign layer interprets it:

| Exit | Meaning | `stage_success: gate` | `stage_success: ratchet` |
|-|-|-|-|
| `0` | Gate GREEN — verifier passed | OK, advance | STOP (gate loops don't exit 0 at budget) |
| `2` | Max-iters reached | STOP | OK, advance |
| `3` | HALT file detected | STOP | STOP |
| `4` | Checkpoint declined | STOP | STOP |
| `5` | Preflight failed | STOP | STOP |
| `6` | Wall-clock budget exhausted | STOP | OK, advance |

"STOP" means the campaign halts, records the failure, and exits non-zero. **No stage is ever
auto-advanced past a failure.** A human reviews the state and replans.

**The orchestrator only reads exit codes and state files — it never redefines GREEN/RED.**
GREEN is owned by the leaf loop's `verify.sh`, not by any campaign layer.

---

## The `plan.md` requirement

Every campaign must include a `plan.md` (or any named file set in `plan:`). The plan must record:
- Why the work decomposes into these stages (not one loop, not three).
- The explicit scope boundary per stage — what the maker is allowed to touch.
- Why a human checkpoint sits between stages.

The lint checks that the plan file exists. Its content is for humans, not the linter.

---

## Inter-stage human checkpoint (`autonomy: checkpoint`)

`autonomy: checkpoint` is mandatory for campaigns. A human checkpoint between every pair of
stages is not optional — it is the definition of the Supervised/Autopilot archetype:

> "A human watches this" used to fail decision-gate cond. 4 — but cond. 4 only rejects
> *human-every-step*. A campaign the agent runs **between** human checkpoints passes.
> — `references/decision-gate.md`

The checkpoint is where the human:
1. Reviews the previous stage's output.
2. Approves (or stops and replans) the transition.
3. Confirms the scope boundary is respected.

A demo script may skip the checkpoint with `AUTONOMY=full` to prove the mechanical composition
works — but production use requires the human pause.

---

## The `stages` artifact (YAML-blind runbook input)

Alongside `campaign-spec.yaml`, a plain-text `stages` file lists one `loop_dir` per line
(comments with `#` allowed). This is what the future orchestrator reads — not the YAML manifest.
The orchestrator never parses YAML; it reads `stages`, runs each directory's `run-this-loop.sh`,
and interprets the exit code.

```
# stages — one loop_dir per line
stage-1
stage-2
```

---

## Deferred: `run-campaign.sh` orchestrator

A general orchestrator that reads `stages`, drives each loop, enforces checkpoints, and
halts-and-flags on failure is **intentionally not shipped**. The manual runbook in each
example's `README.md` is the specification. Build the orchestrator when:

1. Script-level maker≠checker lint is GREEN (a prerequisite for trusting the dispatch layer), AND
2. A real supervised harness asks for it (a consumer path exists to justify the complexity).

The example README and `stages` file fully specify the orchestrator — building it later is
mechanical, not a redesign.

---

## Replan = STOP + flag (no auto-magic)

When a stage fails (any non-success exit), the campaign **stops immediately** and records the
failure. There is no auto-retry at the campaign level, no auto-replan, no fallback loop.
A human reviews the failure, edits the stage's loop-spec or verifier as needed, and restarts
from the failed stage with `--from-stage N` (when the orchestrator is built) or manually.

This is the only correct behaviour: auto-advancing past a failure hides the failure and
corrupts the state that subsequent stages depend on.
