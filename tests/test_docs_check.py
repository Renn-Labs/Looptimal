"""Tests for looptimal-docs-check.py — the docs rot-radar release gate (sibling to
check-version-consistency.py). Proves the gate actually catches a REINTRODUCED instance of the
exact two bugs it exists to prevent (see CHANGELOG.md's [2.1.0] "### Fixed" section), not just
that it happens to pass against the current, already-fixed repo."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "looptimal-docs-check.py"


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
    )


def _seed_minimal_repo(tmp_path: Path, *, with_scripts: bool = False) -> None:
    """Copy just what looptimal-docs-check.py needs out of the real repo: README.md +
    CHANGELOG.md always; scripts/_common.py + scripts/verify-outcome.py only when a test
    exercises check 2's code-evidence gate (check 1 alone never touches scripts/)."""
    shutil.copy(REPO / "README.md", tmp_path / "README.md")
    shutil.copy(REPO / "CHANGELOG.md", tmp_path / "CHANGELOG.md")
    if with_scripts:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        shutil.copy(REPO / "scripts" / "_common.py", scripts_dir / "_common.py")
        shutil.copy(REPO / "scripts" / "verify-outcome.py", scripts_dir / "verify-outcome.py")


# --------------------------------------------------------------------------- #
# The two cases the task requires: a reintroduced stale pin FAILS, the real,
# current repo is GREEN.
# --------------------------------------------------------------------------- #
def test_green_on_the_real_current_repo():
    """The gate must pass clean against this repo's actual README.md/CHANGELOG.md/SECURITY.md
    as they stand today — if this ever goes RED, the docs have genuinely drifted."""
    proc = _run(REPO)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GREEN" in proc.stdout


def test_fails_on_a_reintroduced_stale_version_pin(tmp_path):
    """Reintroduce the exact v2.0.0 bug: change a README `@v2.1.0` pin to `@v2.0.0` so it no
    longer matches the top CHANGELOG version. Proves check 1 actually fires."""
    _seed_minimal_repo(tmp_path)
    readme = tmp_path / "README.md"
    original = readme.read_text(encoding="utf-8")
    assert "@v2.1.0" in original  # sanity: the repo still has the pin this test mutates
    readme.write_text(original.replace("@v2.1.0", "@v2.0.0"), encoding="utf-8")

    proc = _run(tmp_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "RED" in proc.stderr
    assert "README.md:30" in proc.stderr
    assert "@v2.0.0" in proc.stderr
    assert "2.1.0" in proc.stderr  # names the current CHANGELOG version it should have matched


def test_passes_when_pin_matches_current_changelog_version(tmp_path):
    """Control for the test above: an untouched copy of the real README.md/CHANGELOG.md must
    stay GREEN — proves the RED result is caused by the mutation, not the fixture itself."""
    _seed_minimal_repo(tmp_path)

    proc = _run(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GREEN" in proc.stdout


# --------------------------------------------------------------------------- #
# Extra coverage for check 2 (forward-reference catalog) — same "prove it
# actually fires" bar, applied to the other half of the gate.
# --------------------------------------------------------------------------- #
def test_fails_on_a_reintroduced_stale_forward_reference_phrase(tmp_path):
    """Reintroduce the exact keyed-HMAC bug (commit affbdae): prose calling an already-shipped
    feature future "(v1.1)" work. Proves check 2's catalog-driven scan fires against real,
    shipped code evidence (scripts/_common.py + scripts/verify-outcome.py)."""
    _seed_minimal_repo(tmp_path, with_scripts=True)
    readme = tmp_path / "README.md"
    text = readme.read_text(encoding="utf-8")
    marker = "The residual that remains even when keyed is key custody:"
    assert marker in text  # sanity: still targeting the real sentence this bug lived in
    stale = text.replace(
        marker,
        "A cryptographic framer hash-pin (v1.1) removes even that deployment-level trust. " + marker,
        1,
    )
    readme.write_text(stale, encoding="utf-8")

    proc = _run(tmp_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "RED" in proc.stderr
    assert "(v1.1)" in proc.stderr
    assert "keyed-hmac-seal" in proc.stderr


def test_forward_reference_phrase_is_not_flagged_when_code_shows_it_is_not_shipped(tmp_path):
    """Control: the identical stale phrase must NOT fire when the code-evidence check can't
    confirm the feature shipped — proves the catalog is evidence-gated, not a blind phrase grep
    that would also flag an honest, still-true 'planned' note about real future work."""
    _seed_minimal_repo(tmp_path, with_scripts=True)
    readme = tmp_path / "README.md"
    text = readme.read_text(encoding="utf-8")
    marker = "The residual that remains even when keyed is key custody:"
    stale = text.replace(
        marker,
        "A cryptographic framer hash-pin (v1.1) removes even that deployment-level trust. " + marker,
        1,
    )
    readme.write_text(stale, encoding="utf-8")

    # Simulate "not actually shipped yet" by removing the function the evidence check looks for.
    common = tmp_path / "scripts" / "_common.py"
    common.write_text(
        common.read_text(encoding="utf-8").replace(
            "def resolve_framer_key(", "def _not_yet_shipped_resolve_framer_key("
        ),
        encoding="utf-8",
    )

    proc = _run(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GREEN" in proc.stdout
