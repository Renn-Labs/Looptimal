from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINT = ROOT / "scripts" / "loopprint-lint.py"


def _load_lint():
    spec = importlib.util.spec_from_file_location("loopprint_lint", LINT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lint_mod = _load_lint()
lint_spec = lint_mod.lint_spec


def _base_spec(**overrides):
    """Minimal valid critic-panel spec; caller may override individual fields."""
    s = {
        "slug": "test-critic",
        "pattern": "spec-driven",
        "goal": "The output passes the rubric with quorum.",
        "state": {"path": "loops/test-critic/state.md"},
        "verifier": {
            "kind": "critic-panel",
            "command": "bash verify.sh",
            "panel": {"n": 3, "quorum_k": 2, "threshold": 80},
        },
        "stop": {"max_iterations": 5},
    }
    s.update(overrides)
    return s


def test_valid_critic_panel_green():
    assert lint_spec(_base_spec()) == []


def test_quorum_k_gt_n_red():
    spec = _base_spec()
    spec["verifier"]["panel"]["quorum_k"] = 4  # 4 > n=3
    findings = lint_spec(spec)
    assert any("quorum_k" in f for f in findings)


def test_missing_n_red():
    spec = _base_spec()
    del spec["verifier"]["panel"]["n"]
    findings = lint_spec(spec)
    assert any("panel.n" in f for f in findings)


def test_threshold_out_of_range_red():
    spec = _base_spec()
    spec["verifier"]["panel"]["threshold"] = 101
    findings = lint_spec(spec)
    assert any("threshold" in f for f in findings)


def test_normal_gate_spec_unaffected():
    """A standard test-suite verifier must not be touched by critic-panel validation."""
    spec = {
        "slug": "normal-gate",
        "pattern": "morty",
        "goal": "The failing test passes.",
        "state": {"path": "loops/normal-gate/state.md"},
        "verifier": {"kind": "test", "command": "pytest -q"},
        "stop": {"max_iterations": 6},
    }
    assert lint_spec(spec) == []
