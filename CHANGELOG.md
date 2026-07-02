# Changelog

All notable changes to Looptimal are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Note:** versions 1.x were released under the name **LoopPrint**. As of 2.0.0 the
> project is **Looptimal** — the loop-design wizard is now one mode inside a larger
> objective→outcome orchestrator. The repository was renamed `Renn-Labs/LoopPrint` →
> `Renn-Labs/Looptimal` (old links redirect).

## [2.1.0] — 2026-07-01

### Added
- **Cryptographic sealed-contract hardening** — `canonical_contract_hash()` gains an optional
  HMAC-SHA256 keyed mode (`--key-file` / `LOOPTIMAL_FRAMER_KEY`) that folds a manifest of every file
  under `sealed/` into the digest, closing the gap where oracle scripts had zero cryptographic
  binding to the contract hash. Unkeyed calls remain byte-identical to prior behavior.
- **Checker-only ("holdout") visibility tier** — `criteria[].visibility: maker-visible | checker-only`
  with a real `maker_safe_view()` redaction function; a soft advisory fires when a `sensitivity: high`
  mission has no framer key configured.
- **Hard/soft gate labeling** — `criteria[].gate_type: hard | soft` on every `verifier-library.yaml`
  recipe, with a soft advisory when a whole suite is soft-only.
- **Structured critic verdicts** — critic-panel scripts now emit `{score, reason}` JSON instead of a
  bare integer, safely parsed/re-serialized so a free-text reason can't corrupt `critics.jsonl`.
- **Judge-calibration recipe**, and cross-provider **judge-quorum** + sealed **tool-trajectory-match**
  oracles (`references/oracle-library.md`, patterns #14/#15).
- **Zero-clone quickstart** — `pyproject.toml` + `looptimal_cli/` (pure delegating wrappers over
  `scripts/*.py`) let `uvx --from git+...` run the tooling without a clone. Not yet on PyPI.
- **`looptimal-persona-promote.py`** — promotes a proven Tier-B synthesized Agent Foundry persona
  into the curated `personas/` library, at project or user scope.
- **`loopprint-ls.py --global`** — cross-repo loop portfolio / rot-radar view via an opt-in,
  local-only `~/.loopprint/index.jsonl`.
- **`scripts/check-no-network-imports.py`** — CI-enforced guard on the zero-network-in-core invariant.
- **Demo asset** — `assets/demo.gif` / `assets/demo.cast`: an honest `verify-outcome.py --selftest`
  GREEN round-trip followed by a deliberate tamper → RED.
- **20-item public roadmap** (`ROADMAP.md`) across three horizons, with a 2026-07-01
  status-reconciliation block.
- **`references/receipt.md`** — design spec for a public, re-derivable "verification receipt"
  (implementation tracked separately).
- **SKILL.md mode fork** — an upfront, one-question fork (single-pass / recurring loop /
  blueprint-only) asked before any Frame work starts, closing the gap where loop-worthiness was
  only judged deep in Stage 2. New **single-pass** degrade: Frame → light pre-mortem → Execute →
  Verify-outcome → Persist, for a single, non-recurring deliverable you still want proven.

### Changed
- README overhaul: real CI/license/star badges, a "Prove it in under a minute" block using
  `verify-outcome.py --selftest`, three sourced reward-hacking numbers (SpecBench, ImpossibleBench,
  Cursor) grounding the maker ≠ checker pitch, a "Where this fits" section positioning Looptimal
  against ralph loops / native Claude Code loops / spec-kit / Kiro, and an accurate present-tense
  description of the keyed-seal security model.
- `.github/ISSUE_TEMPLATE/bug_report.md` now requests diagnostic output from both
  `looptimal-doctor.py` and `loopprint-doctor.py`.
- `references/decision-gate.md` and `references/pipeline.md`'s REJECT/honest-alternative language
  now points at `single-pass` mode concretely, instead of a vague "one high-quality pass."

### Fixed
- Windows CI portability: `sed -i` GNU/BSD divergence, `USERPROFILE`-vs-`HOME` on `Path.home()`,
  native path separators in printed output, and non-UTF-8 default console encoding — four distinct
  cross-platform bugs found and fixed via the real 3-OS CI matrix.
- `looptimal-lint.py` tests made hermetic (no longer silently dependent on a real
  `~/.looptimal/profile.yaml` on the developer's machine).
- The `@v2.0.0`-pinned quickstart in README never actually worked end-to-end: the tag predates both
  `pyproject.toml` and the hardened verification core above. This release is the fix — every pinned
  command in this README now resolves against a tag that actually contains what it claims to run.

### Security
- The cryptographic framer hash-pin named as "planned" in `2.0.0`'s disclosed residual (see
  `SECURITY.md`) is now shipped, opt-in, and adversarially verified (tampering a sealed oracle
  script while leaving `contract_hash` untouched now goes RED). The unkeyed default carries the
  same disclosed residual as before: OS-permission sealing only, recomputable by anyone who can
  write `sealed/`. Key custody is the remaining residual once keyed. Not marketed as fully
  tamper-proof either way.
- **Pre-tag adversarial review found and closed a real bypass of the keyed mode above** before
  it ever shipped: `verify-outcome.py`'s subprocess environment sanitizer forwarded
  `LOOPTIMAL_FRAMER_KEY` straight into every oracle's environment — since every `external_check`
  runs maker-controlled code by definition, a maker could read the checker's own signing key
  back out and forge a keyed `contract_hash` in the documented, CI-recommended key-delivery mode
  (the key as an env var). Fixed by stripping the key (and any env-var name containing
  `framer_key`) before spawning an oracle subprocess, with an exploit-tested `--selftest` case
  proving an oracle that tries to exfiltrate the key gets nothing. Landed alongside three related
  hardening fixes found in the same pass: the "invoke a sealed oracle" check now requires the
  *executed program* to resolve sealed, not just any path-shaped argument in the command;
  contract-hash/HMAC comparisons use `hmac.compare_digest` instead of `!=`; an explicitly-provided
  but empty `--key-file`/`LOOPTIMAL_FRAMER_KEY` now fails closed instead of silently downgrading
  to unkeyed. A follow-up confirmation pass then caught one regression the `hmac.compare_digest`
  swap introduced — it raises `TypeError` on a non-ASCII maker-supplied hash instead of a clean
  RED — fixed by having `normalize_hash()` return `""` for anything that isn't a genuine 64-hex
  digest, restoring "the checker never crashes on hostile maker input." No real secret was ever
  exposed by any of this — every gap was caught before the CI-integration feature that would have
  exercised the vulnerable path shipped.

## [2.0.0] — 2026-06-30

### Changed
- **Rebranded LoopPrint → Looptimal** and absorbed the previously-private orchestrator
  ("LoopOptimal") into this repository as a single product. The loop-design wizard is
  preserved unchanged and is now Looptimal's **Stage-2 "Design-loop"** mode (also a direct
  `design` / blueprint fast-path). Install slug `loopprint@renn-labs` → `looptimal@renn-labs`.
  Tagline evolved to *"from objective to verified outcome."*

### Added
- **Outcome orchestration pipeline** (`SKILL.md`, `references/pipeline.md`): 0 Frame (hash-pinned
  **sealed** acceptance suite) → 1 Analyze (Capability Manifest) → 2 Design-loop → 3 Plan →
  4 **Simulate** (roll the plan forward N steps + pre-mortem + harden) → [human GO] → 5 Execute
  (dynamic domain-expert sub-agents, maker ≠ checker) → 6 **Verify-outcome** (a *separate* checker
  re-runs the sealed suite against live state, ignoring self-reported GREEN) → 7 Persist.
- **`looptimal-lint.py`** — plan-time gate for the outcome contract (sealed inputs, outcome-not-symptom
  criteria, maker ≠ checker at the outcome altitude), distinct from the loop-spec gate `loopprint-lint.py`.
- **`verify-outcome.py`** — Stage-6 sealed-suite re-runner with tamper→RED selftests, oracle-integrity
  checks, and interpreter env-injection stripping.
- **Agent Foundry** (`references/agent-foundry.md`, `personas/`): two-tier dynamic domain-expert
  resolution (native agent if a profile advertises one; otherwise a synthesized persona).
- **Worked example** (`examples/issue-to-pr-bugfix/`) that round-trips Frame → … → Verify-outcome.

### Security
- Documented an honest, disclosed residual in the sealing model (see `SECURITY.md`): anti-gaming
  rests on the checker controlling `--workdir` and the framer owning `sealed/` via OS permissions;
  a cryptographic framer hash-pin is planned for a later release. Not marketed as fully tamper-proof.

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

[2.0.0]: https://github.com/Renn-Labs/Looptimal/releases/tag/v2.0.0
[1.1.0]: https://github.com/Renn-Labs/Looptimal/releases/tag/v1.1.0
[1.0.0]: https://github.com/Renn-Labs/Looptimal/releases/tag/v1.0.0
