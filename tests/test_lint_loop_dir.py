"""Tests for lint_loop_dir — Step 3 of the ratchet vertical (loop-dir integrity lint)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LINT = ROOT / "scripts" / "loopprint-lint.py"


def _load_lint():
    spec = importlib.util.spec_from_file_location("loopprint_lint", LINT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lint_mod = _load_lint()
lint_loop_dir = lint_mod.lint_loop_dir

# Minimal valid ratchet spec — passes lint_spec cleanly.
_RATCHET_SPEC = {
    "goal": "Reduce debt count to zero.",
    "pattern": "performance",
    "state": {"path": ".omc/state.md"},
    "verifier": {"command": "bash verify.sh", "shape": "ratchet"},
    "stop": {"budget": {"wall_clock_minutes": 30}, "max_iterations": 50},
    "slug": "test-ratchet-loop-dir",
}

# Minimal valid gate spec — no shape field.
_GATE_SPEC = {
    "goal": "Fix all lint errors.",
    "pattern": "morty",
    "state": {"path": ".omc/state.md"},
    "verifier": {"command": "pytest -q"},
    "stop": {"max_iterations": 10},
    "slug": "test-gate-loop-dir",
}


def _write_ratchet_dir(
    tmp_path: Path,
    *,
    baseline: bool = True,
    advance: bool = True,
    advance_content: str | None = None,
    maker_content: str | None = None,
    verify_content: str | None = None,
) -> Path:
    """Write a ratchet loop dir into tmp_path and return the spec file path."""
    spec_file = tmp_path / "loop-spec.yaml"
    with open(spec_file, "w") as fh:
        yaml.dump(_RATCHET_SPEC, fh)
    if baseline:
        (tmp_path / "baseline").write_text("5\n")
    if advance:
        content = advance_content or "#!/bin/bash\nset -e\ncount=$(cat baseline)\necho $count\n"
        (tmp_path / "ratchet-advance.sh").write_text(content)
    if maker_content is not None:
        (tmp_path / "maker.sh").write_text(maker_content)
    if verify_content is not None:
        (tmp_path / "verify.sh").write_text(verify_content)
    return spec_file


def _run_lint(spec_file: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LINT), str(spec_file)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


# ---------------------------------------------------------------------------
# Unit tests on lint_loop_dir directly
# ---------------------------------------------------------------------------

def test_clean_ratchet_no_blocking(tmp_path):
    spec_file = _write_ratchet_dir(tmp_path)
    blocking, _ = lint_loop_dir(str(spec_file), _RATCHET_SPEC)
    assert blocking == []


def test_clean_ratchet_no_advisory(tmp_path):
    spec_file = _write_ratchet_dir(tmp_path)
    _, advisory = lint_loop_dir(str(spec_file), _RATCHET_SPEC)
    assert advisory == []


def test_missing_baseline_blocking(tmp_path):
    spec_file = _write_ratchet_dir(tmp_path, baseline=False)
    blocking, _ = lint_loop_dir(str(spec_file), _RATCHET_SPEC)
    assert any("baseline" in b for b in blocking), f"Expected baseline finding, got: {blocking}"


def test_missing_advance_blocking(tmp_path):
    spec_file = _write_ratchet_dir(tmp_path, advance=False)
    blocking, _ = lint_loop_dir(str(spec_file), _RATCHET_SPEC)
    assert any("ratchet-advance.sh" in b for b in blocking), f"Expected advance finding, got: {blocking}"


def test_maker_writes_baseline_advisory(tmp_path):
    maker = "#!/bin/bash\necho 5 > baseline\n"
    spec_file = _write_ratchet_dir(tmp_path, maker_content=maker)
    _, advisory = lint_loop_dir(str(spec_file), _RATCHET_SPEC)
    assert any("maker.sh" in a and "baseline" in a for a in advisory), (
        f"Expected maker.sh baseline-write advisory, got: {advisory}"
    )


def test_verify_writes_baseline_advisory(tmp_path):
    verify = "#!/bin/bash\ncount=$(grep -c . findings.txt)\necho $count > baseline\n"
    spec_file = _write_ratchet_dir(tmp_path, verify_content=verify)
    _, advisory = lint_loop_dir(str(spec_file), _RATCHET_SPEC)
    assert any("verify.sh" in a and "baseline" in a for a in advisory), (
        f"Expected verify.sh baseline-write advisory, got: {advisory}"
    )


def test_advance_agent_token_advisory(tmp_path):
    advance = "#!/bin/bash\nclaude -p 'fix the issues' > output.txt\n"
    spec_file = _write_ratchet_dir(tmp_path, advance_content=advance)
    _, advisory = lint_loop_dir(str(spec_file), _RATCHET_SPEC)
    assert any("ratchet-advance.sh" in a and "deterministic" in a for a in advisory), (
        f"Expected agent-token advisory, got: {advisory}"
    )


def test_advance_codex_token_advisory(tmp_path):
    advance = "#!/bin/bash\ncodex exec 'reduce debt'\n"
    spec_file = _write_ratchet_dir(tmp_path, advance_content=advance)
    _, advisory = lint_loop_dir(str(spec_file), _RATCHET_SPEC)
    assert any("deterministic" in a for a in advisory)


def test_duplicate_scripts_advisory(tmp_path):
    shared = "#!/bin/bash\nset -e\necho same\n"
    spec_file = _write_ratchet_dir(tmp_path, advance_content=shared)
    (tmp_path / "verify.sh").write_text(shared)
    _, advisory = lint_loop_dir(str(spec_file), _RATCHET_SPEC)
    assert any("same script" in a for a in advisory), (
        f"Expected duplicate-scripts advisory, got: {advisory}"
    )


def test_gate_spec_is_noop(tmp_path):
    spec_file = tmp_path / "loop-spec.yaml"
    with open(spec_file, "w") as fh:
        yaml.dump(_GATE_SPEC, fh)
    blocking, advisory = lint_loop_dir(str(spec_file), _GATE_SPEC)
    assert blocking == [] and advisory == []


def test_no_shape_is_noop(tmp_path):
    spec = {**_GATE_SPEC}
    spec.pop("slug", None)
    spec_file = tmp_path / "loop-spec.yaml"
    with open(spec_file, "w") as fh:
        yaml.dump(spec, fh)
    blocking, advisory = lint_loop_dir(str(spec_file), spec)
    assert blocking == [] and advisory == []


# ---------------------------------------------------------------------------
# Integration tests via subprocess (exit codes + stdout content)
# ---------------------------------------------------------------------------

def test_subprocess_clean_ratchet_exit0(tmp_path):
    spec_file = _write_ratchet_dir(tmp_path)
    result = _run_lint(spec_file)
    assert result.returncode == 0
    assert "GREEN" in result.stdout


def test_subprocess_missing_baseline_exit1(tmp_path):
    spec_file = _write_ratchet_dir(tmp_path, baseline=False)
    result = _run_lint(spec_file)
    assert result.returncode == 1
    assert "RED" in result.stdout
    assert "baseline" in result.stdout


def test_subprocess_missing_advance_exit1(tmp_path):
    spec_file = _write_ratchet_dir(tmp_path, advance=False)
    result = _run_lint(spec_file)
    assert result.returncode == 1
    assert "RED" in result.stdout
    assert "ratchet-advance.sh" in result.stdout


def test_subprocess_maker_writes_baseline_advisory_exit0(tmp_path):
    """Advisory does not fail lint — exit 0 with a ~ warning line."""
    maker = "#!/bin/bash\necho 5 > baseline\n"
    spec_file = _write_ratchet_dir(tmp_path, maker_content=maker)
    result = _run_lint(spec_file)
    assert result.returncode == 0, f"stdout: {result.stdout}"
    assert "GREEN" in result.stdout
    assert "~" in result.stdout
    assert "maker.sh" in result.stdout


def test_subprocess_advance_agent_token_advisory_exit0(tmp_path):
    """Agent token in advance is advisory only — exit 0."""
    advance = "#!/bin/bash\nclaude -p 'fix stuff'\n"
    spec_file = _write_ratchet_dir(tmp_path, advance_content=advance)
    result = _run_lint(spec_file)
    assert result.returncode == 0, f"stdout: {result.stdout}"
    assert "GREEN" in result.stdout
    assert "~" in result.stdout
    assert "ratchet-advance.sh" in result.stdout
