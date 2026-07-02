# Contributing to Looptimal

Thanks for your interest. Looptimal is a small, focused skill — contributions that keep it
**generic, dependency-light, and honest about its gates** are very welcome.

## Ground rules

- **Stay generic.** The core must work on plain Claude Code (or any `SKILL.md` agent) with zero
  config. Harness-specific behavior belongs in a `profile.yaml` (see [`references/profiles.md`](references/profiles.md)),
  never hardcoded in the repo. The detector may *name* a harness; it must never embed that harness's binding values.
- **Stdlib-only scripts.** `scripts/*.py` use the Python standard library. PyYAML is the one optional
  dependency, and the tools degrade gracefully without it. No network calls — CI's `no-network-imports`
  job (`scripts/check-no-network-imports.py`) fails the build if a network-capable import creeps in.
  That check is self-authored, not an independent audit — but CI's `skill-audit` job now closes that
  gap for real: it runs [NVIDIA/SkillSpector](https://github.com/NVIDIA/skillspector) (Apache-2.0,
  independently authored, no relation to Renn Labs or Anthropic) against `scripts/` in `--no-llm`
  mode, so it needs no API key, account, or paid tier. `.skillspector-baseline.yaml` records today's
  static-analysis-only findings (hand-reviewed, not real issues — see its `reason` fields); only a
  genuinely new finding fails the build.
- **Honest gates.** Don't add a verifier the maker can satisfy by self-assessment. Maker ≠ checker.

## Development

There is no build step. This repo has a tiered pre-push quality gate — wire up the fast tier once
per clone:

```bash
git config core.hooksPath hooks
```

That makes `hooks/pre-push` run automatically on every `git push`: `pytest`, both doctors, both
`--selftest`s, `check-version-consistency.py`, `looptimal-docs-check.py` — pure Python, no
network, seconds not minutes. A failing check blocks the push (bypass with `--no-verify` only if
you have a real reason).

For anything non-trivial — and *always* for anything touching `scripts/_common.py`'s crypto,
`verify-outcome.py`'s `safe_env`/subprocess execution, a new CLI flag, a release, or `SKILL.md`
itself — read `.claude/skills/looptimal-prepush-gate/SKILL.md` before pushing. It covers `pyright`,
a local `skillspector` scan (catches real security-scanner findings before CI does, not after),
single- and cross-model code review (`peer trio`), and cross-harness compliance checks for
`SKILL.md`/release changes. This is the actual review discipline this repo holds its own
maker-≠-checker principle to — don't skip it because "the tests pass."

```bash
python3 scripts/loopprint-detect.py    # sanity-check binding resolution, if you touched profiles/
```

Keep changes small and self-contained; one logical change per PR.

## Script naming: `loopprint-*` vs `looptimal-*`

Both prefixes are intentional — they mark two **altitudes**, not leftover rebrand debt:

| Prefix | Altitude | Examples |
|-|-|-|
| `loopprint-*` | **loop-spec** layer — the four-atom blueprint engine (formerly the standalone LoopPrint) | `loopprint-lint.py` (gates a `loop-spec.yaml`), `loopprint-doctor.py`, `loopprint-detect.py` |
| `looptimal-*` | **outcome** layer — the objective→outcome orchestrator | `looptimal-lint.py` (gates the outcome contract), `verify-outcome.py` |

The engine filenames were kept on the `loopprint-` prefix during the 2.0.0 rebrand to preserve git
blame and avoid a risky mass-rename; the `~/.loopprint/profile.yaml` path resolves via a compat
symlink to `~/.looptimal/`. A deliberate, test-covered rename to `looptimal-*` (with shims) is a
candidate for a future minor release — don't rename engine scripts ad hoc in an unrelated PR.

## Developer Certificate of Origin (DCO)

We use the [DCO](https://developercertificate.org/) rather than a CLA — a one-line sign-off
certifying you wrote the patch (or have the right to submit it). Add `-s` to every commit:

```bash
git commit -s -m "Fix the thing"
```

That appends a `Signed-off-by: Your Name <you@example.com>` trailer. PRs without a sign-off will be
asked to add one (`git commit --amend -s`, then force-push your branch). Contributions are accepted
under the project's license (**MIT**) — *inbound = outbound*.

## Issues & security

- **Bugs / ideas:** open a GitHub issue with steps to reproduce. For install problems, paste the output of
  `python3 scripts/loopprint-doctor.py --json`.
- **Security:** please report privately — see [SECURITY.md](SECURITY.md). Don't open a public issue for a
  vulnerability.
