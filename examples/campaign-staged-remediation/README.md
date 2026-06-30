# campaign-staged-remediation

A worked example of a **Looptimal campaign**: two independent gate loops composed by a
`campaign-spec.yaml` manifest, with a mandatory human checkpoint between stages.

This example is a **composition**, not a new loop type. Each stage (`stage-1/`, `stage-2/`)
is a normal Looptimal loop with its own `loop-spec.yaml`, `verify.sh`, `maker.sh`, and
`run-this-loop.sh`. The campaign manifest records the order and success criteria; it does not
replace or extend the runner.

See [`references/campaign.md`](../../references/campaign.md) for the full schema and design rationale.

---

## Runbook (manual — the orchestrator is deferred, see below)

Run each stage by hand. The runner is YAML-blind; it only reads env vars and exit codes.

### Step 1 — run stage 1

```bash
cd examples/campaign-staged-remediation/stage-1
cp ../../templates/run-this-loop.sh .
AUTONOMY=full bash run-this-loop.sh
```

**Stage success (`stage_success: gate`):** runner exits `0`. Any other exit = campaign STOP.

### Step 2 — human checkpoint (REQUIRED before stage 2)

1. Review `stage-1/spec.md` — is it accurate and complete?
2. Confirm the scope boundary: stage 1 touches docs only; stage 2 touches code only.
3. Record approval (e.g. a `CHECKPOINT-OK` commit or note in `stage-1/state.md`).
4. If the spec is wrong or incomplete: **stop the campaign, replan stage 1**. Do not advance.

### Step 3 — run stage 2

```bash
cd examples/campaign-staged-remediation/stage-2
cp ../../templates/run-this-loop.sh .
AUTONOMY=full bash run-this-loop.sh
```

**Stage success (`stage_success: gate`):** runner exits `0`. Any other exit = campaign STOP.

### Step 4 — campaign complete

Commit the remediated code. Archive state files. Campaign done.

---

## Exit-code semantics

| Exit | Meaning | Campaign action |
|-|-|-|
| `0` | Gate GREEN | Advance (after checkpoint) |
| `2` | Max-iters reached | STOP — human replans |
| `3` | HALT file detected | STOP — human replans |
| `4` | Checkpoint declined | STOP — human replans |
| `5` | Preflight failed | STOP — fix infra |
| `6` | Wall-clock budget exhausted | STOP — human replans |

`stage_success: gate` accepts exit `0` only. `stage_success: ratchet` accepts exit `2` or `6`.
Anything else stops the campaign immediately; record the failure and replan.

---

## Deferred: `run-campaign.sh` orchestrator

A general `run-campaign.sh` script that reads `stages`, drives each stage, and enforces the
checkpoint is **intentionally not shipped**. Reasons (unanimous trio verdict in the plan):

- The composition works today via the manual runbook above.
- An orchestrator before a real consumer path adds subprocess/TTY/ratchet-edge-case complexity
  with no caller to justify it.
- The `stages` file and this README fully specify the orchestrator — building it later is mechanical.

**Named trigger:** build `run-campaign.sh` when *script-level maker≠checker lint is GREEN AND
a real supervised harness asks for it*.

---

## Demo (tmpdir only)

```bash
bash examples/campaign-staged-remediation/run_demo.sh
```

Runs both stages in a tmpdir with `AUTONOMY=full` (skips the human checkpoint). Prints `PASS`.
`git status` is clean after — no tracked files are mutated.
