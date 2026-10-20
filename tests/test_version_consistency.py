from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "scripts" / "check-version-consistency.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_version_consistency", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = _load_guard()


def _repo(tmp_path: Path, *tags: str) -> Path:
    """A throwaway local repo. No network: git only ever reads refs on disk."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "base"],
        check=True,
    )
    for tag in tags:
        subprocess.run(["git", "-C", str(tmp_path), "tag", tag], check=True)
    return tmp_path


def test_existing_tag_passes(tmp_path):
    ok, msg = guard.check_release_tag_exists("2.1.0", _repo(tmp_path, "v2.1.0"))
    assert ok, msg


def test_missing_tag_is_red(tmp_path):
    # The phantom release: a version dated as shipped with no tag behind it.
    ok, msg = guard.check_release_tag_exists("2.2.0", _repo(tmp_path, "v2.1.0"))
    assert not ok
    assert "v2.2.0 does not exist" in msg
    assert "v2.1.0" in msg  # names the newest tag actually present


def test_tagless_checkout_fails_closed(tmp_path):
    # A shallow CI checkout has no tags. "I could not look" must not read as "it was fine" —
    # otherwise the guard rebuilds the blindness it exists to close.
    ok, msg = guard.check_release_tag_exists("2.2.0", _repo(tmp_path))
    assert not ok
    assert "no tags" in msg
    assert "fetch-tags" in msg


def test_unreadable_repo_fails_closed(tmp_path):
    ok, msg = guard.check_release_tag_exists("2.2.0", tmp_path / "nonexistent")
    assert not ok
    assert "cannot read git tags" in msg


@pytest.mark.parametrize(
    "heading,expected",
    [
        ("## [2.2.0] - 2026-07-08", True),
        ("## [2.2.0] — 2026-07-08", True),
        ("## [2.2.0]", False),
        ("## [Unreleased]", False),
    ],
)
def test_only_a_dated_section_obliges_a_tag(tmp_path, monkeypatch, heading, expected):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(f"# Changelog\n\n{heading}\n\n### Added\n- thing\n")
    monkeypatch.setattr(guard, "CHANGELOG", changelog)
    assert guard._changelog_marks_released("2.2.0") is expected
