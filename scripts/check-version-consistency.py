#!/usr/bin/env python3
"""check-version-consistency — guard against version drift across the release surface.

Always enforced (every push / PR):
  .claude-plugin/plugin.json  "version"   ==   top entry in CHANGELOG.md  (## [x.y.z])

Additionally enforced on a release (when --tag vX.Y.Z is passed, e.g. on a tag push):
  the tag (minus a leading 'v')           ==   that same version

This is the check that would have caught the "phantom v2.0.0" — manifests declaring 2.0.0
while the newest git tag was still v1.1.0. Stdlib-only; no third-party deps.

Usage:
  python3 scripts/check-version-consistency.py            # manifest <-> changelog
  python3 scripts/check-version-consistency.py --tag v2.0.0   # also assert the release tag
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
CHANGELOG = ROOT / "CHANGELOG.md"
_SEMVER = re.compile(r"^\[(\d+\.\d+\.\d+)\]")  # "## [2.0.0] — ..." -> 2.0.0


def _plugin_version() -> str:
    data = json.loads(PLUGIN.read_text(encoding="utf-8"))
    v = data.get("version")
    if not v:
        sys.exit(f"FAIL: no \"version\" in {PLUGIN.relative_to(ROOT)}")
    return str(v).strip()


def _changelog_top_version() -> str:
    for line in CHANGELOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("## "):
            m = _SEMVER.match(line[3:].strip())
            if m:
                return m.group(1)
    sys.exit(f"FAIL: no '## [x.y.z]' release heading found in {CHANGELOG.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Guard release version consistency.")
    ap.add_argument("--tag", help="release tag to also assert, e.g. v2.0.0")
    args = ap.parse_args()

    plugin_v = _plugin_version()
    changelog_v = _changelog_top_version()

    ok = True
    if plugin_v != changelog_v:
        print(f"FAIL: plugin.json version {plugin_v!r} != top CHANGELOG version {changelog_v!r}")
        ok = False
    else:
        print(f"ok: plugin.json == CHANGELOG == {plugin_v}")

    if args.tag:
        tag_v = args.tag[1:] if args.tag.startswith("v") else args.tag
        if tag_v != plugin_v:
            print(f"FAIL: release tag {args.tag!r} (={tag_v}) != plugin.json version {plugin_v!r}")
            ok = False
        else:
            print(f"ok: release tag {args.tag} matches version {plugin_v}")

    if not ok:
        print(
            "\nFix: align .claude-plugin/plugin.json, the top CHANGELOG.md heading, and the git tag.\n"
            "A new release means: bump plugin.json, add the CHANGELOG section, THEN tag vX.Y.Z.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
