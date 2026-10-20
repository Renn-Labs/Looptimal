from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LINT = ROOT / "scripts" / "loopprint-lint.py"
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _run_lint(*paths: Path) -> subprocess.CompletedProcess:
    """Invoke the real linter the way the library-lint CI job does.

    Deliberately a subprocess over scripts/loopprint-lint.py rather than a call to
    lint_spec(): the break this covers happens at YAML parse time, before any spec
    dict exists, so an in-process rule check would never see it.
    """
    return subprocess.run(
        [sys.executable, str(LINT), *(str(p) for p in paths)],
        capture_output=True,
        text=True,
    )


def _ci_library_lint_patterns() -> list[str]:
    """Read the glob patterns straight out of the library-lint CI job.

    Hardcoding them here would let this test and CI drift apart silently, which is
    the failure this file exists to prevent. If the job is renamed or its command
    changes shape, this raises rather than quietly testing the wrong thing.
    """
    workflow = yaml.safe_load(CI.read_text())
    steps = workflow["jobs"]["library-lint"]["steps"]
    for step in steps:
        run = step.get("run", "")
        if "loopprint-lint.py" in run:
            args = run.split()
            marker = next(i for i, a in enumerate(args) if a.endswith("loopprint-lint.py"))
            return args[marker + 1 :]
    raise AssertionError("library-lint job has no loopprint-lint.py step")


def _library_specs() -> list[Path]:
    paths: list[Path] = []
    for pattern in _ci_library_lint_patterns():
        paths.extend(sorted(ROOT.glob(pattern)))
    return paths


def test_ci_patterns_match_specs():
    # Guards the test itself: an empty glob would make the GREEN case vacuous.
    patterns = _ci_library_lint_patterns()
    assert patterns, "library-lint job passes no paths to the linter"
    assert _library_specs(), f"CI patterns {patterns} matched no files"


def test_shipped_library_specs_lint_green():
    # Same linter, same paths as the library-lint job — both read from ci.yml above.
    result = _run_lint(*_library_specs())
    assert result.returncode == 0, result.stdout + result.stderr


def test_unparseable_spec_is_red(tmp_path):
    # Negative control: the nested-quote break that took main RED on 2026-07-26.
    # Without this, a linter that silently skipped unreadable files would pass above.
    broken = tmp_path / "loop-spec.yaml"
    broken.write_text(
        'schema_version: 1\n'
        'slug: broken-fixture\n'
        'goal: >\n'
        '  A deliberately unparseable spec.\n'
        'state:\n'
        '  path: loops/broken-fixture/state.md\n'
        'verifier:\n'
        '  kind: lint\n'
        '  command: "git status --porcelain | test -z "$(cat)""\n'
        'stop:\n'
        '  success: "verifier GREEN"\n'
        '  max_iterations: 5\n'
    )
    result = _run_lint(broken)
    assert result.returncode != 0, "unparseable spec must not lint GREEN"
    assert "cannot read/parse" in (result.stdout + result.stderr)
