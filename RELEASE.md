# Release Checklist

Use this before tagging or changing repository visibility. Looptimal ships as a standalone
Renn Labs repository (private first); making it public or tagging is a human-approved step.

## Non-negotiable boundaries
- Do not make the repository public or tag `v0.1.0` without explicit maintainer approval.
- Do not publish secrets, local config, private handoff notes, generated run artifacts, or customer data.
- Keep the security claims **honest**. The sealing model relies on (a) the *checker* controlling
  `--workdir` (= the real target repo, never the maker's bundle dir) and (b) the *framer* owning the
  `sealed/` directory via OS filesystem permissions. Do **not** market the gate as fully tamper-proof
  against a maker who can write the sealed dir — that is the disclosed v1.1 hardening (a cryptographic
  framer hash-pin for the sealed contract).

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
