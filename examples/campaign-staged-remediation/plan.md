# Campaign Plan — staged-remediation

## Objective

Bring a legacy module up to a machine-checkable spec in two supervised stages, with a human
checkpoint between them. Each stage is an independent Looptimal gate loop; the campaign
manifest (`campaign-spec.yaml`) records the composition — it is not a new loop type.

## Why two stages (not one)

A single spec-driven loop that derives the spec AND fixes violations in the same run has no
stable gate: the spec keeps changing as the agent writes it, so the verifier measures a moving
target. Splitting produces a fixed gate per stage:

| Stage | Makes | Gate |
|-|-|-|
| 1 — reverse-spec | `spec.md` (the derived spec) | `spec.md` exists |
| 2 — remediate | code changes that satisfy `spec.md` | `remediated.flag` exists |

The gate for stage 2 is only valid once stage 1 has committed its output — hence the inter-stage
human checkpoint.

## Scope boundary

- Stage 1 touches: analysis + documentation only (`spec.md`). No production code changes.
- Stage 2 touches: production code only. No spec changes. If the spec is wrong, stop and replan.
- Out of scope: dependency upgrades, test-infra changes, anything requiring a separate review.

## Inter-stage checkpoint (required)

Before running stage 2, a human must:
1. Review `spec.md` from stage 1 (is it accurate? complete?).
2. Approve the transition in writing (e.g., a `CHECKPOINT-OK` commit message or file).
3. Confirm the scope boundary is respected.

**If the spec is incomplete or wrong, stop the campaign and replan stage 1.** Do not advance
stage 2 against a bad spec.

## Exit-code semantics

| Exit | Meaning | stage_success |
|-|-|-|
| 0 | Gate GREEN — verifier passed | `gate` |
| 2 | Max-iters reached | `ratchet` |
| 3 | HALT file detected | campaign stops |
| 4 | Checkpoint declined | campaign stops |
| 5 | Preflight failed | campaign stops |
| 6 | Wall-clock budget exhausted | `ratchet` |

Both stages use `stage_success: gate` — success requires exit 0.

## Deferred: orchestrator script

`run-campaign.sh` (a general multi-stage orchestrator) is intentionally deferred. The manual
sequence in `README.md` is the runbook. Build the orchestrator when script-level maker≠checker
lint is GREEN AND a real supervised harness consumes campaign-spec.
