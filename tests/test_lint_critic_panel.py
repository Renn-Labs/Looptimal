from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
LINT = ROOT / "scripts" / "loopprint-lint.py"


def _load_lint():
    spec = importlib.util.spec_from_file_location("loopprint_lint", LINT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lint_mod = _load_lint()
lint_critic_panel_dir = lint_mod.lint_critic_panel_dir


def _base_spec(n=3):
    return {
        "slug": "critic-test",
        "pattern": "spec-driven",
        "goal": "Output passes rubric with quorum.",
        "state": {"path": "loops/critic-test/state.md"},
        "verifier": {
            "kind": "critic-panel",
            "command": "bash verify.sh",
            "panel": {"n": n, "quorum_k": 2, "threshold": 80},
        },
        "stop": {"max_iterations": 5},
    }


def _write_yaml(path, data):
    with open(path, "w") as f:
        yaml.dump(data, f)


def _write_sh(path, content):
    p = Path(path)
    p.write_text(content)
    p.chmod(0o755)


# ---------------------------------------------------------------------------
# Core blocking / advisory checks via lint_critic_panel_dir
# ---------------------------------------------------------------------------

def test_distinct_critics_green(tmp_path):
    """3 distinct critics + maker with a different provider → no blocking, no advisory."""
    _write_yaml(tmp_path / "loop-spec.yaml", _base_spec())
    _write_sh(tmp_path / "maker.sh",   "#!/bin/bash\nPROVIDER=claude\n./work.sh\n")
    _write_sh(tmp_path / "critic-1.sh", "#!/bin/bash\nPROVIDER=codex\necho 90\n")
    _write_sh(tmp_path / "critic-2.sh", "#!/bin/bash\nPROVIDER=grok\necho 85\n")
    _write_sh(tmp_path / "critic-3.sh", "#!/bin/bash\nPROVIDER=gemini\necho 88\n")
    blocking, advisory = lint_critic_panel_dir(str(tmp_path / "loop-spec.yaml"), _base_spec())
    assert blocking == []
    assert advisory == []


def test_too_few_critics_red(tmp_path):
    """panel.n=3 but only 2 critic scripts → blocking."""
    _write_yaml(tmp_path / "loop-spec.yaml", _base_spec())
    _write_sh(tmp_path / "critic-1.sh", "#!/bin/bash\necho 90\n")
    _write_sh(tmp_path / "critic-2.sh", "#!/bin/bash\necho 85\n")
    blocking, _ = lint_critic_panel_dir(str(tmp_path / "loop-spec.yaml"), _base_spec())
    assert any("found 2" in b and "panel.n=3" in b for b in blocking)


def test_critic_identical_to_maker_red(tmp_path):
    """A critic whose content sha equals maker.sh → blocking."""
    shared = "#!/bin/bash\necho 90\n"
    _write_yaml(tmp_path / "loop-spec.yaml", _base_spec())
    _write_sh(tmp_path / "maker.sh",    shared)
    _write_sh(tmp_path / "critic-1.sh", shared)          # identical content
    _write_sh(tmp_path / "critic-2.sh", "#!/bin/bash\nPROVIDER=codex\necho 85\n")
    _write_sh(tmp_path / "critic-3.sh", "#!/bin/bash\nPROVIDER=grok\necho 88\n")
    blocking, _ = lint_critic_panel_dir(str(tmp_path / "loop-spec.yaml"), _base_spec())
    assert any("maker" in b for b in blocking)


def test_two_identical_critics_red(tmp_path):
    """Two critics with the same content sha → blocking."""
    same = "#!/bin/bash\nPROVIDER=codex\necho 90\n"
    _write_yaml(tmp_path / "loop-spec.yaml", _base_spec())
    _write_sh(tmp_path / "maker.sh",    "#!/bin/bash\nPROVIDER=claude\n./work.sh\n")
    _write_sh(tmp_path / "critic-1.sh", same)
    _write_sh(tmp_path / "critic-2.sh", same)            # identical to critic-1
    _write_sh(tmp_path / "critic-3.sh", "#!/bin/bash\nPROVIDER=grok\necho 88\n")
    blocking, _ = lint_critic_panel_dir(str(tmp_path / "loop-spec.yaml"), _base_spec())
    assert any("identical" in b for b in blocking)


def test_same_provider_advisory_nonfailing(tmp_path):
    """Critic sharing maker's PROVIDER= token → advisory present, exit 0."""
    spec = _base_spec()
    _write_yaml(tmp_path / "loop-spec.yaml", spec)
    _write_sh(tmp_path / "maker.sh",    "#!/bin/bash\nPROVIDER=claude\n./work.sh\n")
    _write_sh(tmp_path / "critic-1.sh", "#!/bin/bash\nPROVIDER=claude\necho 90\n")  # same provider
    _write_sh(tmp_path / "critic-2.sh", "#!/bin/bash\nPROVIDER=grok\necho 85\n")
    _write_sh(tmp_path / "critic-3.sh", "#!/bin/bash\nPROVIDER=gemini\necho 88\n")

    blocking, advisory = lint_critic_panel_dir(str(tmp_path / "loop-spec.yaml"), spec)
    assert blocking == []
    assert any("same provider" in a for a in advisory)

    # Full pipeline: advisory must not bump exit code.
    result = subprocess.run(
        [sys.executable, str(LINT), str(tmp_path / "loop-spec.yaml")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert "~" in result.stdout


def test_non_critic_panel_noop(tmp_path):
    """Non-critic-panel spec → lint_critic_panel_dir returns ([], [])."""
    spec = {
        "slug": "gate-spec",
        "pattern": "morty",
        "goal": "The failing test passes.",
        "state": {"path": "loops/gate-spec/state.md"},
        "verifier": {"kind": "test", "command": "pytest -q"},
        "stop": {"max_iterations": 5},
    }
    _write_yaml(tmp_path / "loop-spec.yaml", spec)
    blocking, advisory = lint_critic_panel_dir(str(tmp_path / "loop-spec.yaml"), spec)
    assert blocking == []
    assert advisory == []


def test_zero_critics_no_traceback(tmp_path):
    """Zero critic scripts with kind:critic-panel → clean RED, not a traceback."""
    _write_yaml(tmp_path / "loop-spec.yaml", _base_spec())
    # no critic-*.sh files placed
    blocking, _ = lint_critic_panel_dir(str(tmp_path / "loop-spec.yaml"), _base_spec())
    assert any("found 0" in b for b in blocking)


# ---------------------------------------------------------------------------
# Existing examples must remain GREEN (lint_critic_panel_dir is a no-op for them)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("example_dir", [
    "ci-triage", "hybrid", "perf-optimization", "spec-driven-remediation",
])
def test_existing_examples_dir_noop(example_dir):
    """Existing (non-critic-panel) example specs produce no blocking or advisory."""
    spec_path = ROOT / "examples" / example_dir / "loop-spec.yaml"
    with open(spec_path) as fh:
        spec = yaml.safe_load(fh)
    blocking, advisory = lint_critic_panel_dir(str(spec_path), spec)
    assert blocking == []
    assert advisory == []
