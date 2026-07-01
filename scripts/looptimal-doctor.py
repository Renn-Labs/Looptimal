#!/usr/bin/env python3
"""looptimal-doctor — stdlib-only install health check for Looptimal.

Bottom-up checks: required files present -> script exec bits -> script self-tests
-> the bundled example lints GREEN. It is a ONE-SHOT heal, not a loop verifier:
run it, apply the safe fixes, re-run once to confirm, then stop.

Exit 0 = HEALTHY, 1 = warnings (non-fatal), 2 = broken (a hard check failed).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

REQUIRED = [
    "SKILL.md", "LICENSE", "README.md",
    ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
    "scripts/looptimal-lint.py", "scripts/verify-outcome.py",
    "profiles/looptimal.example.yaml",
    "references/pipeline.md", "references/evidence-bundle.md",
    "references/agent-foundry.md", "references/roles.md",
    "references/simulate.md", "references/oracle-library.md",
    "templates/contract.yaml", "templates/mission.yaml",
    "templates/evidence-bundle.json",
    "scripts/_common.py", "scripts/looptimal-detect.py",
    "examples/issue-to-pr-bugfix/mission.yaml",
    "examples/issue-to-pr-bugfix/sealed/contract.yaml",
    "examples/issue-to-pr-bugfix/DEMO-KEY-NOT-SECRET.hex",
]
SCRIPTS = [
    "scripts/looptimal-lint.py",
    "scripts/verify-outcome.py",
    "scripts/looptimal-doctor.py",
    "scripts/looptimal-detect.py",
]


def run_checks(fix: bool) -> list[tuple[str, str, str | None]]:
    findings: list[tuple[str, str, str | None]] = []

    for rel in REQUIRED:
        if not (REPO / rel).is_file():
            findings.append(("FAIL", f"missing required file: {rel}", None))

    for rel in SCRIPTS:
        p = REPO / rel
        if p.is_file() and not os.access(p, os.X_OK):
            if fix:
                p.chmod(p.stat().st_mode | 0o111)
                findings.append(("FIXED", f"chmod +x {rel}", None))
            else:
                findings.append(("WARN", f"not executable: {rel}", f"chmod +x {rel}"))

    for rel in ("scripts/looptimal-lint.py", "scripts/verify-outcome.py"):
        p = REPO / rel
        if not p.is_file():
            continue
        r = subprocess.run([sys.executable, str(p), "--selftest"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            findings.append(("FAIL", f"{rel} --selftest failed (exit {r.returncode})",
                             (r.stdout + r.stderr).strip()[-300:]))

    lint = REPO / "scripts/looptimal-lint.py"
    example = REPO / "examples/issue-to-pr-bugfix/mission.yaml"
    # The bundled example seals its contract with a loudly-marked, non-secret DEMO key (see
    # examples/issue-to-pr-bugfix/DEMO-KEY-NOT-SECRET.hex) to demonstrate the HMAC-keyed
    # hash-pin end-to-end — its contract_hash is genuinely not the plain unkeyed sha256.
    demo_key = REPO / "examples/issue-to-pr-bugfix/DEMO-KEY-NOT-SECRET.hex"
    if lint.is_file() and example.is_file():
        cmd = [sys.executable, str(lint), str(example)]
        if demo_key.is_file():
            cmd += ["--key-file", str(demo_key)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            findings.append(("FAIL", "bundled example does not lint GREEN",
                             (r.stdout + r.stderr).strip()[-300:]))

    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Looptimal install doctor (one-shot heal).")
    ap.add_argument("--fix", action="store_true",
                    help="apply SAFE repairs only (chmod +x on scripts)")
    ap.add_argument("--json", action="store_true", help="machine-readable findings")
    args = ap.parse_args(argv)

    findings = run_checks(args.fix)
    fails = [f for f in findings if f[0] == "FAIL"]
    warns = [f for f in findings if f[0] == "WARN"]

    if args.json:
        print(json.dumps({
            "repo": str(REPO),
            "healthy": not fails and not warns,
            "findings": [{"level": lvl, "msg": msg, "detail": det} for lvl, msg, det in findings],
        }, indent=2))
    else:
        if not findings:
            print("Looptimal doctor: HEALTHY — all checks passed.")
        for level, msg, hint in findings:
            print(f"[{level}] {msg}")
            if hint and level in ("WARN", "FAIL"):
                print(f"    fix: {hint}")

    if fails:
        return 2
    if warns:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
