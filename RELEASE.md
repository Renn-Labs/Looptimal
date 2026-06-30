# Release Checklist

Use this before tagging a release. `Renn-Labs/Looptimal` is a **public** repository; cutting a tag
and publishing a GitHub Release is a **human-approved** step gated on a signed disclosure boundary.

> Versions **1.x** were released as **LoopPrint**; **2.0.0+** is **Looptimal** (the loop-design
> wizard is now one mode inside the objective→outcome orchestrator). Old `LoopPrint` links redirect.

## Non-negotiable boundaries
- **Sign the disclosure boundary first.** The version's block in [`release-boundary.md`](release-boundary.md)
  must be reviewed and **signed** by the maintainer before tagging — confirming what is OPEN (MIT) vs
  WITHHELD, and that nothing proprietary is on a public branch.
- **No announcement without a separate maintainer "go".** Tagging a release is not the same as
  announcing it. Until the maintainer says go, the public-facing reply surface stays the last
  ratified release.
- Do not publish secrets, local config, private handoff notes, generated run artifacts, or customer data.
- Keep the security claims **honest** (see `SECURITY.md`). The sealing model relies on (a) the *checker*
  controlling `--workdir` (the real target repo, never the maker's bundle dir) and (b) the *framer*
  owning the `sealed/` directory via OS filesystem permissions. Do **not** market the gate as fully
  tamper-proof against a maker who can write the sealed dir — that is the disclosed residual (a
  cryptographic framer hash-pin is the planned hardening).

## Version consistency (enforced in CI)
The release surfaces must agree, or the release is "phantom" (manifests claim a version no tag backs):
```bash
python3 scripts/check-version-consistency.py              # plugin.json == top CHANGELOG entry
python3 scripts/check-version-consistency.py --tag vX.Y.Z  # the tag must match too (run before tagging)
```
CI runs this on every push/PR (manifest ↔ CHANGELOG) and on every `v*` tag (tag ↔ version). A new
release means: bump `.claude-plugin/plugin.json`, add the `CHANGELOG.md` section, **then** tag.

## Offline gates (run from a clean tree)
```bash
python3 -m py_compile scripts/*.py
python3 scripts/looptimal-lint.py --selftest
python3 scripts/verify-outcome.py --selftest
python3 scripts/looptimal-doctor.py
python3 scripts/looptimal-detect.py
python3 scripts/looptimal-lint.py examples/issue-to-pr-bugfix/mission.yaml
python3 scripts/verify-outcome.py --bundle examples/issue-to-pr-bugfix/evidence-bundle.json \
  --workdir examples/issue-to-pr-bugfix --repeat 3
```
Lint/verify self-tests must print GREEN, doctor must be HEALTHY, and the example must round-trip
(its sealed behavioral criteria are re-run against live state).

## Launch hazard scan
```bash
! git grep -nE 'AKIA[0-9A-Z]{16}|gh[po]_[A-Za-z0-9_]{36}|-----BEGIN .*PRIVATE KEY-----'
! git grep -nE '/home/[a-z]+/|oh-my-claudecode|fleet-fuse|\.omc/' -- ':!profiles/*.example.yaml'
! git grep -niE 'HANDOFF|private repo|do not (publish|share)'
```
Generic files must not hardcode a harness/agent name or a local path. The only place a concrete
binding name appears is `profiles/looptimal.example.yaml`, clearly marked illustrative.

## Documentation claims
- README first screen shows what Looptimal does + the install path; the security model and its
  disclosed residual are stated accurately, not over-claimed.
- maker ≠ checker is described at two altitudes: the lint **binding-layer** check (distinct
  executor/checker/verifier agents in the profile) and the **Stage-6 outer verifier** (re-runs the
  sealed suite). Runtime agent identity is enforced by the harness at dispatch.
- The worked example is illustrative; its sealed oracles are **behavioral** (import + exercise), not
  static greps, so they cannot be gamed by a dead comment.
- Python support: 3.10+ (uses `X | None` unions); stdlib-only, no third-party dependencies.

## Review gate
- Run an independent, adversarial code review of the enforcement scripts (`looptimal-lint.py`,
  `verify-outcome.py`, `_common.py`) for gaming bypasses. Every demonstrated bypass must be closed
  **and exploit-tested** before tagging.
- Any privacy, over-claim, or launch-boundary issue is a blocker.
- Update `CHANGELOG.md` before the release tag.

## Tag & publish (after all gates pass + boundary signed)
```bash
git tag -s vX.Y.Z -m "Looptimal vX.Y.Z"        # signed tag (needs a configured signing key)
git push origin vX.Y.Z
gh release create vX.Y.Z -F release-notes-vX.Y.Z.md --title "Looptimal vX.Y.Z"
```
