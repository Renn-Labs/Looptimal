# Decision Gate (Tier 0) — "What route should this objective take?"

The first and most valuable step. A loop is infrastructure; building one for the wrong task wastes more than it
saves. But "not a reusable loop" is not the same as "not worth orchestrating." Run this before designing anything
so Looptimal can route the objective to a reusable loop, a one-time mission, a single verified pass, a
human-gated workflow, or a hard reject.

## The 4 conditions

A reusable loop blueprint pays off only when every one of these is true. A one-time objective can still be a
**Mission / Goal Run** when it has a real verifier and benefits from bounded iteration to reach a terminal outcome.

1. **It recurs, or it is a bounded mission that benefits from iteration.** Recurrence amortizes reusable loop
   scaffolding across many runs. A one-time build/debug/launch can still justify an execution loop when repeated
   attempts against a verifier are cheaper and safer than one blind pass.
   *One-off with no useful retry loop? → single verified pass. One-off with iterative work? → Mission / Goal Run,
   not a reusable loop blueprint.*

2. **An objective gate can reject bad output.** You can name a test / build / lint / reproduction / rubric / or a
   distinct reviewer that says yes-or-no without the maker's opinion.
   *Can't write the gate? → you can't close the loop; don't open it.*

3. **The budget absorbs retries.** Iterating to a good answer is cheaper (time/tokens/money) than producing it
   right the first time by hand.
   *Each retry is expensive or risky? → do it carefully once.*

4. **The agent can run what it writes.** There's a real execution feedback signal each cycle — not a human in the
   middle of every iteration.
   *Needs a human judgment every step? → that's a workflow, not an autonomous loop.*

## 30-second checklist

Answer fast. The answers route the work; only missing verification/safety is a hard stop.

- [ ] **Recurs or needs bounded iteration?** (cond. 1)
- [ ] **Objective gate exists / writable?** (cond. 2)
- [ ] **Retries affordable?** (cond. 3)
- [ ] **Agent can execute + observe results?** (cond. 4)
- [ ] **Failure is reversible** (or the irreversible steps can be gated behind a human)?
- [ ] **Clear "done"** — a machine or named reviewer can confirm success?
- [ ] **Safety limit** you're willing to set (max iters / budget / deadline)?

## Verdict

- **Reusable-loop pass (recurs + 2–4 yes):** you have a reusable loop candidate. **Route** it (below) to the
  archetype whose *verifier* and *stop* shape actually fit. Note any unchecked safety items as required artifacts.
- **Mission / Goal Run route (not recurring, but bounded iteration + 2–4 yes):** not a reusable loop blueprint,
  but still loop-executable. Use a goal driver such as Ultragoal/Autopilot, Team when parallel lanes help, or an
  explicit Ralph fallback when that persistence loop is intentionally selected. Persist state, run the verifier,
  and stop on accepted outcome or budget.
- **Single verified pass (not recurring, no useful retry loop, but a verifier exists):** one high-quality pass with
  Looptimal's `single-pass` mode — see `SKILL.md`'s Degrade rules. It still carries the sealed suite +
  independent Stage-6 verify through without loop scaffolding.
- **Human-gated workflow:** if the agent cannot safely run/observe every step, but human checkpoints can serve as
  the external gate, route to supervised/human-gated execution instead of pretending it is autonomous.
- **Hard REJECT:** reserve this for objectives with no external gate of any shape, self-referential/meta-loop
  objectives, symptom-only success metrics with no behavioral anchor, or irreversible judgment-heavy work with no
  human willing to hold the gate.
  - No objective gate of *any* shape (not a test, not a ratchet baseline, not a rubric + independent critics, not
    even a human checkpoint) → **human-reviewed task**, not an autonomous loop.
  - Irreversible + judgment-heavy (prod deploy, auth, payments) → **human-gated process**.

## Route — pick the execution shape, don't force one model

Passing Tier-0 means a loop or mission route is justified; it does **not** mean "a recurring automation." Classify
by *what kind of wrong you're correcting* and *how "done" is defined*, then route to the matching profile. The
verifier and stop shapes differ per archetype — that's the whole point.

| The request is… | Archetype | Verifier shape | Stop shape | loop-spec profile |
|-|-|-|-|-|
| A one-time objective that needs iteration until accepted (feature slice, launch task, migration prep) | **Mission / Goal Run** | sealed outcome verifier + task/checker gates | finish-gate or budget | route artifact chooses Ultragoal/Autopilot, Team, or explicit Ralph fallback |
| A recurring regression to keep fixed (CI triage, dep bumps, lint/format) | **Recurring** | one-time **gate** (test/build/lint) | finish-gate | `pattern` by work · gate verifier · `max_iterations` |
| A specific, reproducible bug | **MORTY / debug** | reproduction test (gate) | finish-gate | `pattern: morty` |
| Conform to a (maybe reverse-engineered) spec | **Spec-Driven** | derived test suite (gate) | finish-gate | `pattern: spec-driven` |
| Drive a metric with **no terminal "done"** (perf, debt, coverage, dep-freshness) | **Persistent / Ralph** | **ratchet** — "no worse than a committed baseline" | **budget** (wall-clock / max-iters) | `pattern: performance` · `verifier.shape: ratchet` · `stop.budget` |
| Judge subjective quality you **can express as a rubric** (docs, answers, design) | **Critic-panel (Eval)** | **k-of-N independent critics** vs a rubric (judge ≠ maker) | finish-gate (quorum met) | `verifier.kind: critic-panel` · `panel: {n, quorum_k, threshold}` |
| Coordinate multi-agent output, judged by critics | **Orchestration** | critic-panel over the coordinated result | finish-gate | `verifier.kind: critic-panel` |
| A multi-stage campaign a human **supervises at checkpoints** (agent runs between them) | **Supervised / Autopilot** | per-stage gate **+ human checkpoint** | finish-gate / budget | `autonomy: checkpoint` · see [`references/campaign.md`](campaign.md) for the multi-stage composition schema |

*(`verifier.shape: ratchet` ships with the ratchet/persistent vertical; `verifier.kind: critic-panel` with the
critic-panel vertical. Route to the archetype; its profile fields come with it.)*

### Routing expands the Pass set — without lowering the bar
The archetypes are exactly what let the gate **route instead of reject** for cases the one-shape gate used to turn
away:
- **"Do this once to completion"** used to fail cond. 1's recurrence/amortization test — now it routes to
  **Mission / Goal Run** when bounded iteration and an external verifier exist, or **single verified pass** when
  iteration is not useful. It is still not a reusable loop blueprint unless it recurs or becomes a starter pattern.
- **"Drive it down forever"** (no terminal done) used to fail cond. 2's "clear done" — now it's a **ratchet** with
  a **budget** stop. The gate is still external (count/metric ≤ baseline), just non-terminal.
- **"Is this any good?"** used to fail cond. 2 — but only when it's *unexaminable*. If you can write a **rubric**
  and point **independent critics** at it, that IS an objective gate → **critic-panel**. No rubric, no critics →
  still rejected.
- **"A human watches this"** used to fail cond. 4 — but cond. 4 only rejects *human-every-step*. A campaign the
  agent runs **between** human checkpoints passes → **autonomy: checkpoint**.

The bar is unchanged: there must still be an external, maker≠checker gate of *some* shape. Routing picks the right
shape **once the bar is met** — it never waves a task through that has no gate at all. Recurrence is the reusable
loop amortization test; it is not the whole outcome-orchestration test.

## The metric

Optimize **cost-per-accepted-change**, not tokens spent or iterations run. A loop that burns 10× the tokens but
lands accepted changes hands-off can still win; one that loops cheaply forever without passing the gate loses.

## Good vs bad loops (quick reference)

| Good (build the loop) | Bad (don't) |
|-|-|
| CI failure triage | Architecture rewrites |
| Dependency bumps | Auth / payments changes |
| Lint / format auto-fix | Production deploys |
| Flaky-test reproduction | Judgment-call "is this good?" *with no rubric you can write* |
| Issue → PR on well-tested code | Anything irreversible without a human gate |
| Drive coverage/debt to a floor (ratchet) | Drive a metric you can't measure |
| Quality you can rubric + have critics judge (critic-panel) | Quality only the maker can "feel" |
