# Contributing to Looptimal

Thanks for your interest. Looptimal is a small, focused skill — contributions that keep it
**generic, dependency-light, and honest about its gates** are very welcome.

## Ground rules

- **Stay generic.** The core must work on plain Claude Code (or any `SKILL.md` agent) with zero
  config. Harness-specific behavior belongs in a `profile.yaml` (see [`references/profiles.md`](references/profiles.md)),
  never hardcoded in the repo. The detector may *name* a harness; it must never embed that harness's binding values.
- **Stdlib-only scripts.** `scripts/*.py` use the Python standard library. PyYAML is the one optional
  dependency, and the tools degrade gracefully without it. No network calls.
- **Honest gates.** Don't add a verifier the maker can satisfy by self-assessment. Maker ≠ checker.

## Development

There is no build step. Before opening a PR, run:

```bash
python3 scripts/loopprint-lint.py examples/ci-triage/loop-spec.yaml   # expect: GREEN
python3 scripts/loopprint-doctor.py                                   # expect: HEALTHY (exit 0)
python3 scripts/loopprint-detect.py                                   # sanity-check binding resolution
python3 scripts/check-version-consistency.py                          # plugin.json == top CHANGELOG entry
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
