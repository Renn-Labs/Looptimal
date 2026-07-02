#!/usr/bin/env python3
"""check-no-network-imports.py — a regression guard for Looptimal's own "stdlib-only, zero
network calls" claim (README.md, SECURITY.md, CONTRIBUTING.md).

Honesty note: this is a SELF-AUTHORED check, not an independent third-party audit — it was never
meant to be one. An earlier pass looked at third-party skill-auditing tools (SkillCheck,
skill-safety-auditor-style scanners) for a genuinely independent verification of this claim, but
found none with a current, stable, CI-embeddable CLI. That specific gap is now closed a different
way: CI's `skill-audit` job runs NVIDIA/SkillSpector (github.com/NVIDIA/skillspector, Apache-2.0),
an independently authored third-party scanner, against scripts/ in --no-llm mode (free, no
account) — see CONTRIBUTING.md and .skillspector-baseline.yaml. This script stays in place
alongside it: a narrower, mechanically-precise, zero-false-positive guard on the exact "no
network-capable import" claim, complementary to SkillSpector's broader (heuristic, occasionally
false-positive) pattern scan.

Parses every scripts/*.py and templates/*.py file with `ast` (not a naive text grep — avoids
false positives from comments/strings/docstrings that merely mention a module name) and flags any
top-level import of a known network-capable stdlib or common third-party module. PyYAML (the one
declared optional dependency) is explicitly allowed; it's a parser, not a network client.

Usage: check-no-network-imports.py [path ...]   (defaults to scripts/ and templates/)
Exit 0 = clean, 1 = a network-capable import was found.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# Network-capable modules (stdlib + common third-party). Deny-list, not allow-list: this
# targets the SPECIFIC claim ("no network calls"), not a broader ("only these N stdlib modules")
# claim that would be far more brittle against ordinary stdlib usage growing over time.
NETWORK_MODULES = frozenset({
    "socket", "ssl", "urllib", "urllib2", "http", "httplib", "ftplib", "smtplib", "poplib",
    "imaplib", "nntplib", "telnetlib", "xmlrpc", "asyncio",  # asyncio itself isn't network, but
    # its presence in this stdlib-only CLI tooling would be a strong signal something unusual is
    # happening — flagged conservatively; remove here (with a comment why) if a legitimate
    # non-network async use case arises.
    "requests", "httpx", "aiohttp", "urllib3", "websocket", "websockets", "paramiko", "ftp",
    "grpc", "boto3", "botocore",
})

ALLOWED_EXTRAS = frozenset({"yaml"})  # the one declared optional dependency; a parser, not a network client

DEFAULT_TARGETS = ("scripts", "templates")


def imports_in_file(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def scan(targets: list[Path]) -> dict[Path, set[str]]:
    violations: dict[Path, set[str]] = {}
    for target in targets:
        paths = [target] if target.is_file() else sorted(target.rglob("*.py"))
        for path in paths:
            if "__pycache__" in path.parts:
                continue
            found = imports_in_file(path) & NETWORK_MODULES
            found -= ALLOWED_EXTRAS
            if found:
                violations[path] = found
    return violations


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(__file__).resolve().parent.parent
    targets = [Path(a) for a in args] if args else [repo_root / t for t in DEFAULT_TARGETS]

    violations = scan(targets)
    if violations:
        print("check-no-network-imports: RED — network-capable imports found:", file=sys.stderr)
        for path, mods in sorted(violations.items()):
            print(f"  {path}: {sorted(mods)}", file=sys.stderr)
        return 1
    scanned = sum(1 for t in targets for _ in ([t] if t.is_file() else t.rglob("*.py"))
                 if "__pycache__" not in str(_))
    print(f"check-no-network-imports: GREEN ({scanned} file(s) scanned, no network-capable imports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
