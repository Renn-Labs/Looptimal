# Decision Gate (Tier 0) — "Is this even a loop?"

The first and most valuable step. A loop is infrastructure; building one for the wrong task wastes more than it
saves. Run this before designing anything.

## The 4 conditions (ALL must hold)

A loop pays off only when every one of these is true:

1. **It recurs.** The task happens repeatedly, so the cost of building the loop amortizes across many runs.
   *One-off? → single high-quality pass, not a loop.*

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

Answer fast. Any "no" in 1–4 is a hard stop; the rest shape the design.

- [ ] **Recurs?** (cond. 1)
- [ ] **Objective gate exists / writable?** (cond. 2)
- [ ] **Retries affordable?** (cond. 3)
- [ ] **Agent can execute + observe results?** (cond. 4)
- [ ] **Failure is reversible** (or the irreversible steps can be gated behind a human)?
- [ ] **Clear "done"** — a machine or named reviewer can confirm success?
- [ ] **Safety limit** you're willing to set (max iters / budget / deadline)?

## Verdict

- **Pass (1–4 all yes):** you have a loop. Don't force it into the one-shot gate — **route** it (below) to the
  archetype whose *verifier* and *stop* shape actually fit. Note any unchecked safety items as required artifacts.
- **Fail (any of 1–4 no):** the gate **rejects** — recommend the honest alternative and stop. This is the most
  valuable thing Looptimal does; routing never overrides it.
  - Not recurring / retries costly → **one high-quality pass**.
  - No objective gate of *any* shape (not a test, not a ratchet baseline, not a rubric + independent critics, not
    even a human checkpoint) → **human-reviewed task**, not an autonomous loop.
  - Irreversible + judgment-heavy (prod deploy, auth, payments) → **human-gated process**.

## Route (only after a Pass) — pick the archetype, don't force one shape

Passing Tier-0 means a loop is justified; it does **not** mean "a one-time test gate." Classify by *what kind of
wrong you're correcting* and *how "done" is defined*, then route to the matching profile. The verifier and stop
shapes differ per archetype — that's the whole point.

| The request is… | Archetype | Verifier shape | Stop shape | loop-spec profile |
|-|-|-|-|-|
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
- **"Drive it down forever"** (no terminal done) used to fail cond. 2's "clear done" — now it's a **ratchet** with
  a **budget** stop. The gate is still external (count/metric ≤ baseline), just non-terminal.
- **"Is this any good?"** used to fail cond. 2 — but only when it's *unexaminable*. If you can write a **rubric**
  and point **independent critics** at it, that IS an objective gate → **critic-panel**. No rubric, no critics →
  still rejected.
- **"A human watches this"** used to fail cond. 4 — but cond. 4 only rejects *human-every-step*. A campaign the
  agent runs **between** human checkpoints passes → **autonomy: checkpoint**.

The bar is unchanged: there must still be an external, maker≠checker gate of *some* shape. Routing picks the right
shape **once the bar is met** — it never waves a task through that has no gate at all.

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
