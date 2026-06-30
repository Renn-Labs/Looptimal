# Troubleshooting — heal a broken Looptimal install

Looptimal can be installed four ways (Claude Code plugin, Claude folder skill, a Codex/OMX real-copy
bridge, a Grok/AGENTS.md pointer), and a broken install usually fails *quietly* — the wizard just
"isn't there", or a script won't run. This page is the repair map.

## Start here: run the doctor

```bash
python3 scripts/loopprint-doctor.py          # diagnose
python3 scripts/loopprint-doctor.py --fix    # also apply SAFE auto-repairs
python3 scripts/loopprint-doctor.py --json   # machine-readable (for an agent)
```

Read the output bottom-up. Each finding has a status and, when something's wrong, a `fix:` line you
can paste:

| Status | Meaning | What to do |
|-|-|-|
| `OK` | check passed | nothing |
| `WARN` | usable, but degraded | apply the `fix:` when convenient (or `--fix`) |
| `FAIL` | broken — the skill won't work right | apply the `fix:`, re-run until no FAIL |
| `SKIP` | not applicable here (e.g. that harness isn't installed) | nothing |
| `INFO` | context, not a problem | read it |

Exit code: `0` = healthy (warnings allowed), `1` = at least one FAIL, `2` = the doctor itself errored.

**`--fix` only does safe, reversible repairs** — `chmod +x` on the scripts, and relinking a *dangling*
symlink. It never re-clones, edits your config, or deletes anything. Everything riskier is printed as a
suggestion for you to run deliberately. (That's maker ≠ checker applied to the doctor: it diagnoses; you
authorize the risky repair.)

## The mental model: five layers, diagnosed bottom-up

A skill only works if every layer beneath it holds. Check from the bottom; a failure low down makes
everything above it look broken.

```
5. Generates valid loops   ── lint passes; the wizard emits a runnable package
4. Runs                     ── python + PyYAML present; scripts are executable
3. Activated                ── the agent actually triggers the skill on your words
2. Discovered               ── the harness sees SKILL.md (right place, valid frontmatter)
1. Installed                ── the files exist and are intact (no partial clone)
```

The doctor walks these in order. If layer 1 fails (missing files), fix that before trusting anything above.

---

## Symptom → cause → fix

### "The wizard isn't there / nothing happens when I ask for a loop"

This is a **discovery or activation** problem (layer 2–3). By install type:

**Claude Code — plugin install**
| Cause | Fix |
|-|-|
| Marketplace never added | `/plugin marketplace add Renn-Labs/loopprint` |
| Plugin not installed after adding | `/plugin install loopprint@renn-labs` |
| Installed but you're typing the wrong name | plugin skills are **namespaced**: invoke `/loopprint:loopprint` (or just say "design a loop for …") |
| Private repo, no git access | the install clones over your git credentials — make sure you can `git clone` the repo, or ask the owner for access / a public release |
| `marketplace.json` / `plugin.json` malformed | doctor `plugin_manifests` FAIL → restore them from a clean clone |

**Claude Code — folder skill (clone + symlink)**
| Cause | Fix |
|-|-|
| Symlink dangling (repo was moved/renamed) | doctor `claude_link` WARN → `--fix`, or `ln -sfn <repo> ~/.claude/skills/loopprint` |
| Symlinked to the wrong place | `ln -sfn <repo> ~/.claude/skills/loopprint` |
| Custom config dir | skills live under `$CLAUDE_CONFIG_DIR/skills` if that env var is set — link there instead of `~/.claude/skills` |
| `SKILL.md` frontmatter broken | doctor `skill_frontmatter` FAIL → the file must open with a `---` block containing `name:` and `description:` |
| Name collision with another `loopprint` skill | rename one of them |

**Codex / OMX (or any harness that *real-copies* skills)**
| Cause | Fix |
|-|-|
| The copy is stale after a repo update | re-run **your harness's** skill-sync step (the bridge owns this — Looptimal doesn't ship it) |
| The skill catalog entry is missing | re-run the sync so the harness re-registers it; confirm it appears in that harness's skill/agent index |

> Looptimal deliberately doesn't bundle a sync command for these — the copy-and-register step belongs to
> your harness (the same decoupling rule as profiles: Looptimal ships the skill, your harness owns how it's
> wired in). The doctor will *detect* the ecosystem and remind you, but the re-sync is yours to run.

**Grok / any AGENTS.md-pointer harness**
| Cause | Fix |
|-|-|
| The pointer section was edited away | re-add a short "Looptimal" pointer to that harness's `AGENTS.md` describing when to use it and where the folder lives |

**OpenCode / OpenClaw / Hermes (and any `~/.<harness>/skills/` agent)**
| Cause | Fix |
|-|-|
| Not linked into the harness's skills dir | `ln -s <repo> ~/.config/opencode/skills/loopprint` (OpenCode — which *also* auto-loads from `~/.claude/skills/`, so a Claude folder install already works), `ln -s <repo> ~/.openclaw/skills/loopprint` (OpenClaw), or `ln -s <repo> ~/.hermes/skills/loopprint` (Hermes; run `hermes skills` to confirm). These all discover folder-skills like Claude does |
| Dangling symlink / bad frontmatter / partial clone | identical to the Claude folder-skill rows above; `loopprint-doctor.py` covers these via its `contract_files` / frontmatter / exec-bit checks |

### "It triggers, but a script errors / the lint won't run"

A **runtime** problem (layer 4).

| Symptom | Cause | Fix |
|-|-|-|
| `Permission denied` running a script | not executable | `chmod +x scripts/*.py` (or doctor `--fix`) |
| `PyYAML required` / lint exits 2 | PyYAML missing | `pip install pyyaml` — `loopprint-lint.py` and profile parsing need it; the wizard otherwise runs on generic defaults |
| `SyntaxError` / f-string errors | Python too old | use Python 3.8+ (doctor `python` FAIL) |
| `No such file` for a template/reference | partial or corrupt clone | doctor `contract_files` FAIL → re-clone, or `git -C <repo> checkout -- .` |

### "It generates a blueprint, but the lint says RED"

That's **working as designed** (layer 5) — the linter is refusing a blueprint that violates the four-atom
contract. It is not an install bug. Common RED reasons and the fix:

| RED finding | Meaning | Fix |
|-|-|-|
| `verifier: no external gate` | the spec has no `verifier.command` or `verifier.reviewer` | add a real test/build/lint/repro/benchmark, or a *separate* named reviewer |
| `verifier… looks like self-grading` | the "verifier" is the maker grading itself | point it at something external (maker ≠ checker) |
| `verifier.command … is a no-op` | `true` / `exit 0` / empty | replace with a check that can actually fail |
| `stop: no safety limit` | no `max_iterations` or budget | add `stop.max_iterations` (positive int) and/or `stop.budget` |
| `… still contains a <placeholder>` | a template blank wasn't filled | fill it in |

If the doctor's own `lint_selftest` is RED on the *bundled* example, that's different — your copy of
`loopprint-lint.py` or the example is corrupt; re-clone.

### "Conforming to my harness isn't taking effect"

The **binding** isn't resolving. The wizard falls back to generic defaults (`loops/<slug>/`, `verify.sh`)
when no profile is found or it can't parse.

| Cause | Fix |
|-|-|
| No profile anywhere | expected — generic defaults are fine; to conform, drop a `profile.yaml` at `./.loopprint/` or `~/.loopprint/` (see [`profiles.md`](profiles.md)) |
| Profile present but malformed | doctor `profile` FAIL → fix the YAML, or delete it to fall back to generic |
| Profile present but PyYAML missing | `pip install pyyaml` so it can be read |
| Edited a profile, nothing changed | profile resolution is **first-found-wins**: `./.loopprint` shadows `~/.loopprint`. Check you edited the one that's actually winning (the doctor prints which source resolved) |

---

## How do I know it's actually working?

The green path, end to end:

1. `python3 scripts/loopprint-doctor.py` → `HEALTHY` (or only WARNs you understand), exit 0.
2. `python3 scripts/loopprint-detect.py` → prints a binding (`harness:` line) and where it came from.
3. `python3 scripts/loopprint-lint.py examples/ci-triage/loop-spec.yaml` → `GREEN`.
4. In your agent, say *"design a loop for X"* → it runs the decision gate and asks a few sharp questions
   (it doesn't silently dump files).

If all four hold, the install is good.

---

## A note for agents repairing this

If you're an agent reading doctor output: the `fix:` lines are machine-actionable. Apply the **safe**
ones directly (`chmod +x`, relinking a dangling symlink — these are exactly what `--fix` automates).
For anything that **re-clones, edits user config, or deletes** — surface it to the user and let them
authorize it. Don't loop on the doctor: it's a one-shot heal, not a loop verifier. Re-run once after
applying fixes to confirm GREEN, then stop.
