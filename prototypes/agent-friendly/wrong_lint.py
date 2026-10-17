#!/usr/bin/env python3
"""Observe what today's lints print when an agent picks the wrong altitude.

Question. If an agent runs looptimal-lint on a loop-spec, or loopprint-lint on
a mission, does the error name the other tool?

Decision rule. Architecture work is needed if neither error names the matching
lint. A docs-only fix is enough if both errors already name the other command.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOOP_SPEC = ROOT / "examples" / "ci-triage" / "loop-spec.yaml"
MISSION = ROOT / "examples" / "issue-to-pr-bugfix" / "mission.yaml"
LOOPTIMAL_LINT = ROOT / "scripts" / "looptimal-lint.py"
LOOPPRINT_LINT = ROOT / "scripts" / "loopprint-lint.py"


def run(script: Path, target: Path) -> str:
    proc = subprocess.run(
        [sys.executable, str(script), str(target)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return (proc.stdout + proc.stderr).strip()


def names_other_tool(text: str, other: str) -> bool:
    return other in text.lower()


def main() -> int:
    outcome_on_loop = run(LOOPTIMAL_LINT, LOOP_SPEC)
    loop_on_mission = run(LOOPPRINT_LINT, MISSION)

    print("CASE 1. looptimal-lint on examples/ci-triage/loop-spec.yaml")
    print(outcome_on_loop)
    print()
    print("CASE 2. loopprint-lint on examples/issue-to-pr-bugfix/mission.yaml")
    print(loop_on_mission)
    print()

    case1_names = names_other_tool(outcome_on_loop, "loopprint-lint")
    case2_names = names_other_tool(loop_on_mission, "looptimal-lint")
    print(f"case1_names_loopprint_lint={case1_names}")
    print(f"case2_names_looptimal_lint={case2_names}")

    if case1_names and case2_names:
        print("DECISION. Docs are enough. Both errors already name the other lint.")
        return 0

    print(
        "DECISION. Architecture is needed. The wrong lint fails as if the file "
        "were a broken document of its own kind. It never names the other lint."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
