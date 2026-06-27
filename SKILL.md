---
name: loopprint
description: "LoopPrint — an interactive wizard that turns a vague goal into a complete, runnable loop blueprint (spec + state + external verifier + run script + safety checklist). Use when the user says 'design a loop', 'build a loop', 'new loop', 'loopprint', 'loop wizard', or hands over a vague recurring task they want to automate. Runs a Tier-0 decision gate (is this even a loop?), sharpens the goal with 3-5 questions, enforces the four atoms (Goal/State/Verifier/Stop), recommends a pattern (debug / spec-driven / performance / hybrid), and generates the full artifact package into loops/<slug>/. Say 'skip wizard' or 'direct run' to bypass the interview. If the user says 'loopprint doctor', 'is the install broken', or LoopPrint seems mis-installed (wizard won't trigger, a script errors, a clone looks partial), run scripts/loopprint-doctor.py to self-diagnose and repair."
license: MIT
---

# LoopPrint — loop-design wizard

Turn a vague goal into a runnable loop **blueprint**: the four atoms made concrete, plus the artifacts to
execute and audit the loop. The job is to **design the system**, not to perform a persona.

## When to use
- "Design / build a loop for X", "new loop", "loopprint", "loop wizard".
- The user hands over a recurring, automatable task and wants it set up properly.
- Any time someone is about to point an autonomous agent at a task with no state, no gate, or no stop.

## When NOT to use
- A one-shot task with no recurrence → just do it well once (the Decision Gate will say so).
- A purely conversational question → answer it.
- Irreversible, judgment-heavy work (prod deploys, auth/payments, "is this good enough" calls) → these need a
  human, not a loop. LoopPrint will flag them and recommend a human gate instead of autonomy.

## Operating rules (read first)
- This is a **skill**, not a mode. It does not require a banner on every reply, a confirmation phrase, or
  language that it "governs all activity." Open with **one** activation line, then do the work.
- The wizard is **conversational and honest**. If the goal fails the gate, say so plainly and stop.
- Keep the user in control: never start an autonomous run without explicit approval at Step 6.

---

## The wizard (six steps)

**Step 0 — entry.** Open with a single activation line, e.g. *"🖨️ LoopPrint — let's blueprint this loop."*
- **Invoked bare** (`/loopprint` with no goal, or just "design a loop" / "loop wizard"): don't guess and don't
  run the gate against nothing. Ask exactly one question first — *"What's the recurring task you want to turn
  into a loop?"* — then proceed to Step 1 with the answer.
- **Goal already given** (in this message or recent context): acknowledge it in one line and go straight to Step 1.

### Step 0.5 — Resolve the binding (conform to this system)
Figure out how *this* environment wants loops wired, so the package fits the user's harness rather than generic
defaults. Run `scripts/loopprint-detect.py` (or read `./.loopprint/profile.yaml` → `~/.loopprint/profile.yaml`).
It yields a binding — `state_dir`, `verifier.default`, `dispatch`, `marker_path`, `runner`, `banner` — to use in
Steps 3 & 5. If nothing resolves, use generic defaults (`loops/<slug>/`, `verify.sh`) and say so; the core works
with no harness. Contract: [`references/profiles.md`](references/profiles.md). Never hardcode a harness's
conventions here — always read them from the binding.

### Step 1 — Decision Gate
Run the Tier-0 test in [`references/decision-gate.md`](references/decision-gate.md): the 4 conditions + the
30-second checklist. Report **Pass** or **Fail** with one line of reasoning per condition. On Fail, recommend the
honest alternative (single high-quality pass, or a human-gated process) and **stop unless the user overrides**.

### Step 2 — Goal Refinement
Ask **3–5 targeted questions** (not more). Cover:
1. **Sharpened goal** — one sentence, testable. ("Done" must be checkable by a machine or a named reviewer.)
2. **Recurrence / frequency** — how often does this run? (Confirms the loop amortizes.)
3. **Verification method** — what *external* signal says an iteration succeeded? (test/build/lint/repro/rubric/reviewer)
4. **Irreversible risks** — what could this loop do that can't be undone? (→ becomes a human checkpoint)
5. **Autonomy level** — fully autonomous, checkpoint-gated, or dry-run only?

### Step 3 — Primitive Enforcement
Force a concrete value for each atom. Do not proceed with any left vague:
- **Goal** — the one-sentence objective from Step 2.
- **State** — the durable artifact path from the resolved binding's `state_dir` (Step 0.5; generic default
  `loops/<slug>/state.md`) and what it records: attempt log, what failed, current hypothesis, context.
- **Verifier** — the exact external command or named reviewer. If the only proposed check is the same agent
  self-assessing, **reject it** and find a real gate (this is the most common defect). Maker ≠ checker.
- **Stop** — success criteria **and** a safety limit (max iterations, token/time budget, explicit halt). First to
  hit wins. No loop ships without a safety limit.

### Step 4 — Pattern Selection
Recommend one pattern from [`references/patterns.md`](references/patterns.md) and explain the choice in 1–2 lines:
- **MORTY** — a specific bug to fix. Verifier = a reproduction test.
- **Spec-Driven Remediation** — bring a system up to a (possibly reverse-engineered) spec. Verifier = derived tests.
- **Performance Optimization** — make something faster/cheaper. Verifier = benchmark target + no regressions.
- **Hybrid** — real work mixing the above. Verifier = composite gate.

### Step 5 — Artifact Generation
Create `loops/<slug>/` (slug = kebab-case of the goal) and write the package, filling the
[`templates/`](templates/) with the Step 2–4 answers:

| File | From template | Purpose |
|-|-|-|
| `loop-spec.yaml` | `templates/loop-spec.yaml` | The four atoms + pattern + budget, machine-readable |
| `state.md` | `templates/state-template.md` | The durable State artifact, human view (seed it with iteration 0) |
| `maker.sh` | `templates/maker.sh` | The maker step — a SEPARATE process from verify.sh (maker ≠ checker) |
| `verify.sh` | `templates/verification-hook.sh` | The external verifier as an exit-code gate |
| `run-this-loop.sh` | `templates/run-this-loop.sh` | Engine-agnostic runner; emits `metrics.jsonl` + `state.jsonl` each iteration |
| `safety-checklist.md` | `templates/safety-checklist.md` | Human checkpoints + budget guardrails |
| `flow.mmd` | `templates/flow.mmd` | Mermaid diagram of this loop |

After generation: preflight with `bash run-this-loop.sh --check`; once the loop has run, `loopprint-report.py
loops/<slug>/metrics.jsonl` reports **cost-per-accepted-change**; `loopprint-skillify.py loops/<slug>` (Step 6
"Save as skill") promotes a GREEN loop into a reusable skill. Pick a verifier from `templates/verifier-library.yaml`.

If a heavy orchestrator (e.g. glueRun-go) is in play, also emit `templates/gluerun-snippet.yaml` adapted.

**Self-check (required):** run `scripts/loopprint-lint.py loops/<slug>/loop-spec.yaml`. Do **not** present the
blueprint as ready until it prints GREEN. A RED means an empty or self-grading verifier, a missing safety limit,
or an unfilled placeholder — fix it and re-lint. Maker ≠ checker applies to LoopPrint's own output too.

### Step 6 — Final Review
Show the tree of generated files and a 3-line summary (Goal / Verifier / Stop). Then offer, and wait:
- **Run now** — execute `run-this-loop.sh` (respecting the autonomy level from Step 2).
- **Refine** — adjust any atom/artifact and regenerate.
- **Export** — adapt for glueRun-go / another orchestrator.
- **Save as skill** — promote this loop into its own reusable skill.

Never auto-run; Step 6 is a stop-and-confirm.

---

## Direct-run mode
If the user says **"skip wizard"** / **"direct run"**, skip Steps 1–4's interview: read or accept an existing
`loop-spec.yaml` (or a one-paragraph goal), backfill any missing atom with a sensible default, **call out
anything you defaulted**, generate the package (Step 5), and stop at Step 6. Never silently invent a verifier —
if there's no external gate, say so and ask for one.

## Repair / doctor
If LoopPrint itself seems broken or mis-installed — the wizard won't trigger, a script errors, a clone
looks partial, a symlink dangles after the repo moved — diagnose before anything else:

```
python3 scripts/loopprint-doctor.py          # bottom-up health check; a copy-pasteable fix per problem
python3 scripts/loopprint-doctor.py --fix    # also apply SAFE repairs (chmod +x, relink a dangling symlink)
python3 scripts/loopprint-doctor.py --json   # machine-readable findings
```

Apply the safe `fix:` lines yourself; for anything that re-clones, edits user config, or deletes, confirm
with the user first (maker ≠ checker). It's a **one-shot heal** — re-run once to confirm no FAIL, then stop;
it is *not* a loop verifier, so don't iterate on it. Full symptom→cause→fix map (by install type):
[`references/troubleshooting.md`](references/troubleshooting.md).

## Hard guards (always)
- No verifier that the maker can satisfy by self-assessment. Find an external one or stop.
- No loop without a safety limit. No autonomous run without Step 6 approval.
- Irreversible actions become human checkpoints, never autonomous steps.
- Log a state change + a verifier result every iteration; only a GREEN verifier permits "done".
