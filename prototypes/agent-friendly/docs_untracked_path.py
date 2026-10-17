#!/usr/bin/env python3
"""Prove that docs-check misses the gitignored-path class from commit b9a1754.

Question. Does looptimal-docs-check.py fail when tracked prose points at a path
that is gitignored and not in the tree?

Decision rule. Add a catalog check if the historical text stays GREEN under
today's docs-check and RED under a path-exists check.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_CHECK = ROOT / "scripts" / "looptimal-docs-check.py"
HISTORICAL = (
    "See `.claude/skills/looptimal-prepush-gate/SKILL.md` before pushing.\n"
)


def run_docs_check(tree: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(DOCS_CHECK), "--root", str(tree)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def untracked_path_hits(text: str, tree: Path) -> list[str]:
    """Fail a line that names a repo-relative path which is not a real file."""
    hits: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for token in line.replace("`", " ").replace("'", " ").split():
            if "/" not in token:
                continue
            if not token.startswith("."):
                continue
            candidate = token.strip(",;:)")
            path = tree / candidate
            if path.exists():
                continue
            hits.append(f"CONTRIBUTING.md:{lineno}: points at missing path {candidate}")
    return hits


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tree = Path(raw)
        (tree / "README.md").write_text("# fixture\n", encoding="utf-8")
        (tree / "CHANGELOG.md").write_text("## [2.2.0]\n", encoding="utf-8")
        (tree / "SECURITY.md").write_text("# security\n", encoding="utf-8")
        (tree / "CONTRIBUTING.md").write_text(HISTORICAL, encoding="utf-8")
        scripts = tree / "scripts"
        scripts.mkdir()
        (scripts / "_common.py").write_text(
            "def read_changelog_top_version(root):\n    return '2.2.0'\n"
            "def resolve_framer_key():\n    return None\n"
            "def canonical_contract_hash(payload, key=None):\n    return 'x'\n",
            encoding="utf-8",
        )
        (scripts / "verify-outcome.py").write_text(
            "from _common import resolve_framer_key, canonical_contract_hash\n",
            encoding="utf-8",
        )

        code, out = run_docs_check(tree)
        proposed = untracked_path_hits(HISTORICAL, tree)

        print("HISTORICAL TEXT")
        print(HISTORICAL.strip())
        print()
        print(f"docs-check exit={code}")
        print(out or "(no output)")
        print()
        print("proposed untracked-path hits")
        print("\n".join(proposed) if proposed else "(none)")
        print()

        if code == 0 and proposed:
            print(
                "DECISION. Expand docs-check. The b9a1754 class is still GREEN "
                "under today's catalog and RED under a missing-path check."
            )
            return 0

        print("DECISION. Unexpected. Revisit the catalog before adding a check.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
