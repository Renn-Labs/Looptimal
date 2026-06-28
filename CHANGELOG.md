# Changelog

All notable changes to LoopPrint are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] — 2026-06-27

### Added
- **`dual_registration` doctor check** (`loopprint-doctor.py`): detects when LoopPrint is registered
  twice on Claude Code — an enabled `loopprint@<marketplace>` plugin **and** the
  `~/.claude/skills/loopprint` folder-skill symlink — which makes the skill appear twice in the skill
  list (`loopprint:loopprint` from the plugin plus bare `loopprint` from the folder skill). Emits a
  WARN with keep-one guidance: on a dev machine keep the symlink and disable the plugin; on a user
  machine keep the plugin and remove the symlink. Keys on the plugin's *enabled* state (merged across
  `settings.json` + `settings.local.json`), so the warning self-clears once you pick one mechanism.

## [1.0.0] — 2026-06-27

First public release. LoopPrint turns a vague goal into a runnable loop **blueprint** — the four atoms
(Goal / durable State / external Verifier / Stop) made concrete and generated as a self-linted artifact
package. Maker ≠ checker throughout, including on LoopPrint's own output.

### Added
- **Loop-design wizard** (`SKILL.md`): a Tier-0 decision gate ("is this even a loop?"), goal refinement,
  primitive enforcement, pattern selection (MORTY / spec-driven / performance / hybrid), and artifact
  generation into `loops/<slug>/`.
- **Runtime + observability**: engine-agnostic `run-this-loop.sh` (emits per-iteration `metrics.jsonl` +
  `state.jsonl`), a separate `maker.sh` (maker ≠ checker), `loopprint-report.py` (cost-per-accepted-change),
  and `loopprint-skillify.py` (promote a GREEN loop into a reusable skill).
- **Rot radar** (`loopprint-ls.py`): a repo-local loop-health view — HEALTHY / RUNNING / PENDING / ROTTEN /
  STALE / UNKNOWN — with `--exit-nonzero-if-rotten` for CI/cron. Stdlib-only, no network.
- **Binding-aware install**: `loopprint-detect.py` resolves the harness profile; per-harness install for
  Claude Code (plugin + folder skill), OpenCode, Pi, OpenClaw/EClaw, Hermes, Codex/OMX, and grok build.
- **Self-healing**: `loopprint-doctor.py` (bottom-up install diagnosis with a copy-pasteable fix per problem)
  and `loopprint-lint.py` (gates the generated spec — rejects an empty or self-grading verifier, a missing
  safety limit, or an unfilled placeholder).
- **Cross-platform**: `.gitattributes` (LF), a macOS/Windows CI matrix plus a runner-smoke job, and Windows
  install notes (WSL / junction / symlink / copy / plugin).
- **Distribution**: ships as a Claude Code plugin (`.claude-plugin/plugin.json` + `marketplace.json`),
  installable via `/plugin marketplace add Renn-Labs/LoopPrint`.

[1.1.0]: https://github.com/Renn-Labs/LoopPrint/releases/tag/v1.1.0
[1.0.0]: https://github.com/Renn-Labs/LoopPrint/releases/tag/v1.0.0
