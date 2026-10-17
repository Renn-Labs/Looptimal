# Make Looptimal safe for agents to change

Erik Ford reviews most of this tree himself. He wants an agent pull request to be
trustworthy without him rereading architecture, naming, and honesty by hand.
This plan is a how-to for that. It does not rewrite the product in this change.

A top expert would not start with a longer `AGENTS.md`. They would count the
mistakes that already happened, change the code so the cheap path is the right
path, then add a check that fails on a real past commit, and only then write a
short rule table. That is the inverse pyramid. Codebase first, then static
analysis, then prose, human review last.

## Restate the goal

Erik's problem is not "agents need more instructions." His problem is that the
same classes of mistake keep reaching him.

An agent opens one file, copies the nearest example, and takes the shortest
path that runs. In this repo that path is often the wrong altitude
(`loopprint-*` versus `looptimal-*`), a GREEN that was not earned, or a doc
claim the tree does not support. Erik then spends review time on those, instead
of on judgment calls that still need a person.

Done means a later agent can change a loop spec, a mission, or a script, and
the cheap commands fail with the file and the tool to use, before Erik opens
the diff. Human review remains for irreversible work, new CLI flags, and
`SKILL.md` routing.

## How to read this

One box is one unit of work. Check a box only when its evidence exists. A
command, a SHA, a screenshot, or a test name counts. A self-report does not.

This document is a how-to. The appendices record evidence and rejected shapes.

Tests alone are not sufficient verification. A later PR is verified only when
its unit, live CLI, and timing boxes are all checked.

## Evidence this plan used

Measured on `origin/main` at `e16259d` (88 commits, 14 pull requests, 6 issues).

- Erik (`Rennlabs`) wrote 13 of 14 pull requests and left the only detailed
  human review, on [PR #12](https://github.com/Renn-Labs/Looptimal/pull/12).
- [PR #11](https://github.com/Renn-Labs/Looptimal/pull/11) is a 12-finding
  self-review of rot-radar, generated with Claude Code, then landed by Erik.
- [PR #20](https://github.com/Renn-Labs/Looptimal/pull/20) is the only open
  agent PR. It repairs library pins after `e16259d` left
  `library/product-slice-ship/loop-spec.yaml` unparseable.
- Issue threads are thin. The richest corrections are follow-up commits and
  commit bodies, not GitHub review comments.
- There is no `AGENTS.md`. `CLAUDE.md` is 40 lines and only steers the build
  journal. `SKILL.md` is the product skill (263 lines), not a contributor map.
- `scripts/` has 8 `loopprint-*.py` files and 7 `looptimal-*.py` files. Both
  `lint` and `doctor` exist at each altitude.

## Pitfall classes

A class counts once it has happened twice. Counts below are distinct
corrections or live failures, not file hits.

### 1. Wrong altitude, 5 plus one live prototype

An agent treats `lint` as one tool. It is two.

| Evidence | What happened |
| --- | --- |
| `fb49eaf` | `loopprint-doctor` still expected the old skill name after the rebrand. |
| `eec12e6` | Plugin plus folder-skill dual registration passed each check in isolation. |
| `CONTRIBUTING.md` | A whole section exists so people do not rename prefixes ad hoc. |
| Issue #9 | Still titled as a `loopprint` CLI after the product is Looptimal. |
| Prototype `wrong_lint.py` | Wrong lint never names the other lint. |

Live observation, run from this branch.

```text
looptimal-lint examples/ci-triage/loop-spec.yaml
RED: cannot parse mission: unexpected indentation near 'The failing test(s)...'
```

```text
loopprint-lint examples/issue-to-pr-bugfix/mission.yaml
goal: missing or empty.
pattern: 'None' not one of ['hybrid', 'morty', 'performance', 'spec-driven'].
```

Both look like a broken file of the lint's own kind. Neither says "this is a
loop-spec, run `loopprint-lint`" or "this is a mission, run `looptimal-lint`."

`looptimal_cli/__init__.py` already groups commands, then still maps
`looptimal lint` to `looptimal-lint` and `loopprint lint` to `loopprint-lint`
with no artifact check.

### 2. Unearned GREEN or a masked RED, 6

Erik's reviews keep returning to honesty of status.

| Evidence | What happened |
| --- | --- |
| PR #11 finding 1 | `RUNNING` masked a terminal RED inside `--running-grace`, so CI rot exit missed a finished failure. |
| PR #12 polish 2 | `-WhatIf` printed "install complete" without creating the junction. |
| `affbdae` | README still called the keyed HMAC seal future `(v1.1)` after it shipped. |
| Docs-check header | The v2.0.0 quickstart pinned a tag that could not run the code it advertised. |
| `fa77d37` | First-30-minutes RED was bound to attempt number, not a frozen source-manifest mismatch. |
| `649e01e` | The same demo needed a second harden pass. |

The product already encodes this for loop-specs. `tests/golden/red/` has
`selfgrade`, `trivial-gate`, `empty-verifier`, `placeholder-goal`, and
`no-stop`. `scripts/_common.py` `NOOP_COMMANDS` and `loopprint-lint.py`
`TRIVIAL_GATE` reject `true` and `exit 0`. The repo's own status paths still
learn this the hard way.

### 3. Docs that point at a tree the reader does not have, 4

| Evidence | What happened |
| --- | --- |
| `b9a1754` | `CONTRIBUTING.md` and `hooks/pre-push` pointed at a gitignored `.claude/skills/...` path. |
| `affbdae` | Shipped feature described as future work. |
| `#18` / `ef329d9` | v2.0.0 release-surface reconcile. Stale-doc hygiene. |
| `beed6f6` | `looptimal-docs-check.py` added for the two classes above. |

The catalog in `scripts/looptimal-docs-check.py` has one forward-reference
entry plus README `@vX.Y.Z` pin matching. Prototype `docs_untracked_path.py`
rebuilds the `b9a1754` sentence. Today's check stays GREEN. A missing-path
check goes RED.

### 4. Host-dependent tests and leaked process env, 5

| Evidence | What happened |
| --- | --- |
| `2061e89` | `test_looptimal_lint.py` passed locally because `~/.looptimal/profile.yaml` existed, then failed on clean CI. |
| `709712f` | Pre-push inherited `GIT_DIR` / `GIT_WORK_TREE`. Pytest temp repos wrote into the real worktree. |
| `07ec28e` | Windows encoding in `persona-promote`. |
| `46bd4ec` | `USERPROFILE` and native path separators. |
| `7cd2dc5` | `sed -i` and bash-only tests on Windows CI. |

### 5. Shell-out at a boundary, 2

| Evidence | What happened |
| --- | --- |
| PR #12 requested change | `cmd.exe /c mklink` re-parsed `-SkillName`. A quote plus `&` ran another command on PowerShell 7. |
| `709712f` | Git hook env leaked into nested git. |

Erik's review said the fix was `New-Item -ItemType Junction` so paths stay
arguments, not a string a shell re-parses.

### 6. Skillspector baseline churn after a nearby edit, 2

`c627dd8` and `d3fd6af` are the same class. A later commit moved lines in
already-reviewed code and CI failed on the baseline. The second commit body
calls this "the same churn class."

### 7. Status inferred from loose signals, 8 findings in one review

PR #11 also fixed substring glob markers, scanning `LOOPPRINT_ROOT` as a loops
root, corrupt `metrics.jsonl` aborting the ladder, unparseable timestamps
becoming false ROTTEN or HEALTHY, unused `green_ever`, SKIP-only labeled
`never_run`, and future timestamps treated as RUNNING without a lock. That is
one shape. Health is inferred from time windows and path strings instead of a
closed set of states.

### 8. Library YAML that agents cannot quote, 1 live plus PR #20

`library/product-slice-ship/loop-spec.yaml` line 22 is

```yaml
command: "git status --porcelain | test -z "$(cat)""
```

`loopprint-lint.py library/*/loop-spec.yaml` is RED on `main` today. The file
does not parse. PR #20 rewrites it to `bash verify.sh`. The deeper mistake is
that `verifier.command` is a free string, so nested quotes are legal to type
and illegal to parse.

## Map each class to the highest pyramid tier that kills it

| Class | Highest tier that works | Why not higher | Why not lower |
| --- | --- | --- | --- |
| Wrong altitude | Architecture. Parse the file at the CLI boundary and route, or name the other lint. | A mass rename still leaves two `lint` commands. Prototype `dispatch.py` shows keys already separate the shapes. | `CONTRIBUTING.md` already explains the prefixes. The prototype still fails. |
| Unearned GREEN | Architecture plus types. One status owner. Illegal combinations cannot be printed. | Already partly done for loop-specs via golden red fixtures. Repo status paths are the remainder. | Another paragraph in `SECURITY.md` will not stop `-WhatIf` or a grace window. |
| Docs that lie | Static analysis. Grow the docs-check catalog with a check that fails on `b9a1754` text. | The path is prose. There is no type to brand. | Writing "do not point at `.claude/`" is the instruction they already had. |
| Host-dependent tests | Tests plus a small CI lint. Fail if a test uses `Path.home()` or implicit profile resolution without an isolated `HOME`. | Not a domain type. | Docs in `CONTRIBUTING.md` did not stop `2061e89`. |
| Shell-out | Boundary discipline. No `cmd.exe` / `shell=True` / interpolated command strings. | PR #12 already picked this tier. | A comment above `mklink` would not have closed the quote. |
| Baseline churn | Architecture of the check. Key findings on symbols, not line numbers, or refresh the baseline in the same commit that moves the lines. | Line-number baselines cannot survive edits. | Telling agents to "update the baseline" is a repeat of `d3fd6af`. |
| Loose health signals | Types. A closed health enum. `RUNNING` only with a live lock. | PR #11 fixed cases, not the shape. | More rot-radar prose will grow another boolean. |
| Unquotable command strings | Architecture. `verifier.command` as a list or a path to `verify.sh`, not a double-quoted shell line. | YAML scalars are the wrong structure for a pipeline. | A quoting note in `references/schema.md` is the current state, and `main` is still RED. |

## Ranked changes

Do these in order. Each item is one later PR. This PR only lands the plan and
the prototypes.

### PR-1. Typed artifact dispatcher (do this first)

**Depends on.** None.

**Why this is first.** It is the daily agent mistake. The cheap command is
`looptimal lint <file>` or `loopprint lint <file>`. Today that command lies
about what is wrong.

**Shape, recommended.** Keep both prefixes. `CONTRIBUTING.md` forbids an ad hoc
rename, and prototype `dispatch.py` classified four real files from keys
alone.

At the CLI boundary in `looptimal_cli` and at the top of
`scripts/looptimal-lint.py` / `scripts/loopprint-lint.py`:

1. Load the YAML mapping.
2. Classify it.
   - `contract_ref` and `lanes` mean a mission. Owner is `looptimal-lint`.
   - `kind: campaign` or `stages` means a campaign. Owner is `loopprint-lint`.
   - `goal` plus `verifier` or `stop` means a loop-spec. Owner is `loopprint-lint`.
3. If the invoked lint does not own the file, exit 2 and print the exact
   command to run, including the path.
4. If classification is unknown, print both owners and the keys that decide.

**Files.**

- Edit `looptimal_cli/__init__.py`.
- Edit `scripts/looptimal-lint.py`.
- Edit `scripts/loopprint-lint.py`.
- Create `scripts/_artifact.py` for the classifier. One owner. Both lints
  import it.
- Test `tests/test_artifact_dispatch.py`.

**You see.**

```text
looptimal-lint: examples/ci-triage/loop-spec.yaml is a loop-spec.
Run: python3 scripts/loopprint-lint.py examples/ci-triage/loop-spec.yaml
```

**Verify, unit.** Replay `prototypes/agent-friendly/wrong_lint.py` against the
new lint. Both cases must name the other tool. Replay
`prototypes/agent-friendly/dispatch.py` on the same four files.

**Verify, live.** Run the grouped CLIs.

```bash
python3 -c "from looptimal_cli import looptimal; import sys; sys.argv=['looptimal','lint','examples/ci-triage/loop-spec.yaml']; looptimal()"
python3 scripts/loopprint-lint.py examples/ci-triage/loop-spec.yaml
python3 scripts/looptimal-lint.py examples/issue-to-pr-bugfix/mission.yaml
```

**Review gate.** None. This PR does not change a user interaction.

### PR-2. Grow docs-check on the classes it still misses

**Depends on.** None. Can land beside PR-1.

**Why this is second.** `looptimal-docs-check.py` already has the right shape.
A catalog of `{phrase, code-evidence}` pairs. It only covers two historical
bugs. The next agent will repeat `b9a1754` because nothing fails.

Add two checks, each proven on a reconstructed past file.

1. Tracked Markdown or hook text that names a repo-relative path which is
   gitignored or absent. Fixture is the `b9a1754` sentence. Today's check is
   GREEN. The new check is RED. See `prototypes/agent-friendly/docs_untracked_path.py`.
2. User-facing install docs that still tell a current user to link
   `~/.claude/skills/loopprint` as the current name. That string is valid in
   `CHANGELOG.md` history. It is stale in `references/troubleshooting.md`
   rows that describe a live install.

Do not turn docs-check into a prose linter. Add catalog entries. The file
header already says to do that.

**Files.**

- Edit `scripts/looptimal-docs-check.py`.
- Edit `tests/test_docs_check.py`.
- Edit `references/troubleshooting.md` only if the new check fails on `main`.

**You see.** A fixture tree with the `b9a1754` sentence exits 1. Current
`CONTRIBUTING.md` stays GREEN.

**Review gate.** None.

### PR-3. Make `verifier.command` a list or a script path

**Depends on.** PR-1 so the lint that owns loop-specs is the one that fails.

**Why this is third.** `main` is RED on `library-lint` today because a
double-quoted pipeline does not parse. PR #20 patches one file. The next
starter will ship the same quotes.

Change the schema so a command is either

- a YAML list of argv tokens, or
- a path that exists and is executable, usually `verify.sh`.

Reject a scalar that contains both `"` and `$`. Point the author at
`library/secret-scan` as the copy source.

Leave graph v1 plan-only. Do not invent missing library bundles.

**Files.**

- Edit `scripts/loopprint-lint.py` and `references/schema.md`.
- Edit `library/product-slice-ship/loop-spec.yaml` (or land after PR #20).
- Test `tests/test_lint.py` with the current nested-quote file as a red fixture.

**You see.** `python3 scripts/loopprint-lint.py library/*/loop-spec.yaml`
exits 0. The old nested-quote body is a golden red.

**Review gate.** None.

### PR-4. Closed loop-health states

**Depends on.** None.

**Why this is fourth.** PR #11 fixed eight symptoms of one missing type.

Replace the boolean and grace-window ladder in `scripts/loopprint-ls.py` with
one function that returns a closed variant.

```text
HEALTHY | PENDING | STALE | ROTTEN | RUNNING | UNKNOWN(reason)
```

`RUNNING` requires a `.running` lock that the runner still holds. A terminal
RED cannot occupy `RUNNING`. Tests that used to lock in the grace-window bug
stay, and they must fail if the lock rule is removed.

**Files.**

- Edit `scripts/loopprint-ls.py`.
- Edit `tests/test_ls.py`.
- Edit `references/rot-radar.md` only to name the variants.

**Review gate.** None.

### PR-5. Hermetic-test lint

**Depends on.** None.

**Why this is fifth.** Five fix commits were "it passed on my machine."

Add `scripts/check-hermetic-tests.py` (stdlib) that fails a test module which
calls `Path.home()`, `os.environ["HOME"]`, or `resolve_profile` without
patching `HOME` to a temp dir. Prove it on the pre-`2061e89` pattern.

Scrub `GIT_*` stays in `hooks/pre-push`. Do not re-teach it.

**Review gate.** None.

### PR-6. Skillspector findings keyed by symbol

**Depends on.** None.

**Why this is sixth.** Two CI fires were line shifts, not new bugs.

If SkillSpector cannot key on symbols, refresh `.skillspector-baseline.yaml`
in the same commit that moves the lines, and add a CI step that fails when
`scripts/_common.py` or `scripts/verify-outcome.py` change without a baseline
touch. That is a repo rule, not a SkillSpector fork.

**Review gate.** None. Anything that touches `_common.py` crypto or
`safe_env` still needs a second reviewer, as `CONTRIBUTING.md` already says.

### PR-7. Minimal `AGENTS.md` last

**Depends on.** PR-1 through PR-5, so every line in the table has an enforcer.

**Why this is last.** Nothing fails when an agent skips a markdown file.

Write one page. A table that pairs each rule with the command that enforces
it. No second copy of `SKILL.md`. No essay.

```text
| Rule | What fails |
| maker is not the checker | loopprint-lint / looptimal-lint / verify-outcome --selftest |
| Use the lint that owns the file | dispatcher exit 2 names the command |
| Do not point docs at a missing path | looptimal-docs-check.py |
| Tests do not read ~/.looptimal | check-hermetic-tests.py |
| No network in scripts/ | check-no-network-imports.py |
```

Point Cursor, Claude, and Codex at this file with a one-line stub in
`CLAUDE.md` only. Do not grow `CLAUDE.md`.

**Review gate.** The operator reads the page once.

## What not to do in this program

- Do not mass-rename `loopprint-*` to `looptimal-*` in an unrelated PR.
  `CONTRIBUTING.md` already forbids that. Prototype `dispatch.py` shows it is
  not required to stop the wrong-tool class.
- Do not add a second product skill. `SKILL.md` is for users of Looptimal, not
  for agents that edit this repo.
- Do not merge PR #20 from this work. It is a separate contract fix.
- Do not publish to PyPI here. Issue #9 left that as an identity-bound step.

## Close

- [ ] PR-1 through PR-7 have the evidence this file names.
- [ ] A fresh agent, given only `AGENTS.md` and the dispatcher, runs the
      wrong lint on `examples/ci-triage/loop-spec.yaml` and is told to run
      `loopprint-lint`.
- [ ] `library-lint` is GREEN on `main`.
- [ ] Erik's review on a later agent PR is about the change, not the altitude.

## Appendix A. Prototype evidence

Throwaway scripts live in `prototypes/agent-friendly/`. They are not
production code.

### Wrong lint

Command. `python3 prototypes/agent-friendly/wrong_lint.py`

Observed. Neither error string contains the other lint name.

Decision. Architecture. A docs note cannot fix an error that misdiagnoses the
file.

### Missing-path docs

Command. `python3 prototypes/agent-friendly/docs_untracked_path.py`

Observed. Reconstructed `b9a1754` text. `looptimal-docs-check.py --root`
exits 0. A missing-path scan reports
`.claude/skills/looptimal-prepush-gate/SKILL.md`.

Decision. Grow the catalog. Do not write another "do not point at `.claude/`"
sentence.

### Dispatch without a rename

Command. `python3 prototypes/agent-friendly/dispatch.py`

Observed. Four real files classified from keys. Loop-spec and campaign go to
`loopprint-lint`. Mission goes to `looptimal-lint`. No overlap.

Decision. Keep both prefixes. Put the classifier at the boundary.

Unproven. Whether SkillSpector can key findings on symbols without a fork.
PR-6 treats that as a repo convention if the tool cannot.

## Appendix B. Alternatives that lost

**Mass rename of `loopprint-*`.** Loses git blame, breaks every published
`uvx` / script path, and still leaves two `lint` commands unless the
dispatcher exists. `CONTRIBUTING.md` already deferred this to a dedicated
minor release with shims.

**One mega CLI with hidden aliases only.** Grouped `looptimal` and `loopprint`
entry points already exist in `looptimal_cli`. They do not inspect the file.
Adding aliases without classification repeats the same failure.

**AGENTS.md first.** `CLAUDE.md` and `CONTRIBUTING.md` already contain the
prefix rule and the honesty rule. The prototypes still fail. Prose is the
wrong tier.

**Fix only `product-slice-ship`.** That is PR #20. It does not stop the next
nested-quote starter.

## Appendix C. Risks

- A dispatcher that is too eager will mis-classify a hybrid file. Mitigate by
  unknown-shape exit 2, not a guess.
- A missing-path docs check will flag legitimate mentions of
  `~/.claude/skills/looptimal` (a user home path, not a repo path). Limit the
  check to repo-relative paths that start with `.` or a tracked top-level dir.
- Changing `verifier.command` shape can RED existing example specs. Land the
  schema change with the example updates in the same PR.
- This plan must not mention private companion work. Public PRs stay on the
  public contract.

## Appendix D. Reading list

Read these before editing a later PR.

- `CONTRIBUTING.md` (invariants, prefix altitudes, DCO)
- `scripts/looptimal-docs-check.py` header (catalog rule)
- `looptimal_cli/__init__.py` (grouped CLIs)
- `scripts/loopprint-lint.py` and `scripts/looptimal-lint.py`
- `tests/golden/red/`
- [PR #11](https://github.com/Renn-Labs/Looptimal/pull/11)
- [PR #12](https://github.com/Renn-Labs/Looptimal/pull/12)
- Commit `b9a1754` (gitignored path)
- Commit `2061e89` (non-hermetic lint tests)
- Commit `446b7de` (pre-push gate, and the skill that must not be a public path)

PR-1 and PR-3 should run a `/how` pass on the lint pair before coding. PR-4
should run `/how` on `loopprint-ls.py`. PR-6 should run `/interrogate` if it
touches `scripts/_common.py` crypto or `safe_env`.
