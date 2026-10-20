#!/usr/bin/env python3
"""check-version-consistency — guard against version drift across the release surface.

Always enforced (every push / PR):
  .claude-plugin/plugin.json  "version"   ==   top entry in CHANGELOG.md  (## [x.y.z])
  pyproject.toml              version     ==   that same version

Additionally enforced on a release (when --tag vX.Y.Z is passed, e.g. on a tag push):
  the tag (minus a leading 'v')           ==   that same version

Also always enforced: if the CHANGELOG marks that version as RELEASED (a dated section,
not [Unreleased]), a matching vX.Y.Z tag must actually exist. The --tag assertion above
cannot catch a version that was never tagged at all, because CI only passes --tag on a
tag push — so the tag it names always exists by construction. That blind spot is exactly
how a dated 2.2.0 section shipped while the newest tag was still v2.1.0.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import read_changelog_top_version, read_plugin_version  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
CHANGELOG = ROOT / "CHANGELOG.md"
PYPROJECT = ROOT / "pyproject.toml"


def _plugin_version() -> str:
    # Delegates to the shared _common.read_plugin_version so the version read lives in exactly one
    # place (receipt design, Decision 5) — this guard and the receipt emitter cannot drift apart.
    try:
        return read_plugin_version(PLUGIN)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.exit(f"FAIL: {exc}")


def _changelog_top_version() -> str:
    # Delegates to the shared _common.read_changelog_top_version so the "current version" read
    # lives in exactly one place, same pattern as _plugin_version() above — this guard and
    # looptimal-docs-check.py cannot drift on how the top CHANGELOG version is derived.
    try:
        return read_changelog_top_version(CHANGELOG)
    except (OSError, ValueError) as exc:
        sys.exit(f"FAIL: {exc}")


def read_pyproject_version(pyproject: Path) -> str | None:
    """The [project] version, or None when pyproject has none to compare.

    A third version surface this guard did not read. It drifts as easily as the other two,
    and it is what a zero-clone install resolves.
    """
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return m.group(1) if m else None


def _changelog_marks_released(version: str) -> bool:
    """True when the CHANGELOG heading for this version carries a date.

    `## [2.2.0] - 2026-07-08` is a claim that 2.2.0 shipped; a bare `## [2.2.0]` is not.
    Only the dated form obliges a tag to exist, so an in-progress version never trips
    the tag check.
    """
    try:
        text = CHANGELOG.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("## ") and f"[{version}]" in line:
            after = line.split(f"[{version}]", 1)[1]
            return bool(re.search(r"\d{4}-\d{2}-\d{2}", after))
    return False


def _git_tags(repo: Path) -> list[str] | None:
    """Tag names in a local checkout, or None if git cannot be read.

    Reads refs straight off disk — no network, and no subprocess either, so this guard
    spawns nothing. A shallow CI checkout has no tags at all unless the workflow asks for
    them; that case is a FAIL, never a skip, because "I could not look" must not read the
    same as "I looked and it was fine".
    """
    gitdir = repo / ".git"
    if gitdir.is_file():  # worktree or submodule: .git is a pointer file
        try:
            pointer = gitdir.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not pointer.startswith("gitdir:"):
            return None
        target = Path(pointer.split(":", 1)[1].strip())
        gitdir = target if target.is_absolute() else (repo / target)
    if not gitdir.is_dir():
        return None
    common = gitdir / "commondir"  # a worktree keeps shared refs in the main gitdir
    if common.is_file():
        try:
            gitdir = (gitdir / common.read_text(encoding="utf-8").strip()).resolve()
        except OSError:
            return None

    tags: set[str] = set()
    loose = gitdir / "refs" / "tags"
    if loose.is_dir():
        tags.update(p.relative_to(loose).as_posix() for p in loose.rglob("*") if p.is_file())
    packed = gitdir / "packed-refs"
    if packed.is_file():
        try:
            lines = packed.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        for line in lines:
            line = line.strip()
            if not line or line.startswith(("#", "^")):
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2 and parts[1].startswith("refs/tags/"):
                tags.add(parts[1][len("refs/tags/"):])
    return sorted(tags)


def check_release_tag_exists(version: str, repo: Path) -> tuple[bool, str]:
    """A version the CHANGELOG dates as released must have a tag to match."""
    expected = f"v{version}"
    tags = _git_tags(repo)
    if tags is None:
        return False, f"FAIL: cannot read git tags in {repo} — refusing to pass without evidence."
    if not tags:
        return False, (
            "FAIL: this checkout has no tags, so the release tag could not be verified.\n"
            "      In CI set `fetch-tags: true` on actions/checkout; locally run `git fetch --tags`."
        )
    if expected not in tags:
        return False, (
            f"FAIL: CHANGELOG dates {version} as released but tag {expected} does not exist "
            f"(newest seen: {sorted(tags)[-1]}).\n"
            f"      Either cut {expected}, or move that CHANGELOG section back under [Unreleased]."
        )
    return True, f"ok: release tag {expected} exists"


def main() -> int:
    ap = argparse.ArgumentParser(description="Guard release version consistency.")
    ap.add_argument("--tag", help="release tag to also assert, e.g. v2.0.0")
    ap.add_argument("--repo", type=Path, default=ROOT, help="checkout to read tags from (testing)")
    args = ap.parse_args()

    plugin_v = _plugin_version()
    changelog_v = _changelog_top_version()

    ok = True
    if plugin_v != changelog_v:
        print(f"FAIL: plugin.json version {plugin_v!r} != top CHANGELOG version {changelog_v!r}")
        ok = False
    else:
        print(f"ok: plugin.json == CHANGELOG == {plugin_v}")

    pyproject_v = read_pyproject_version(PYPROJECT)
    if pyproject_v is None:
        print("ok: pyproject.toml declares no version — nothing to drift")
    elif pyproject_v != plugin_v:
        print(f"FAIL: pyproject.toml version {pyproject_v!r} != plugin.json version {plugin_v!r}")
        ok = False
    else:
        print(f"ok: pyproject.toml == {pyproject_v}")

    released = _changelog_marks_released(changelog_v)
    if released:
        tag_ok, tag_msg = check_release_tag_exists(changelog_v, args.repo)
        print(tag_msg)
        ok = ok and tag_ok
    else:
        print(f"ok: {changelog_v} is not dated as released yet — no tag required")

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
