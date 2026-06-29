"""Tests for verifier.shape validation (ratchet) and critic-panel quorum/dir validation."""
from __future__ import annotations

import copy
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


# Minimal valid spec — passes all existing checks (goal, pattern, state, verifier, stop).
_BASE = {
    "goal": "Reduce lint findings to zero.",
    "pattern": "morty",
    "state": {"path": ".omc/state.md"},
    "verifier": {"command": "pytest -q"},
    "stop": {"max_iterations": 10},
}


def _spec(**overrides) -> dict:
    """Deep-copy _BASE and apply keyword overrides to nested keys via dot-path."""
    s = copy.deepcopy(_BASE)
    for key, val in overrides.items():
        parts = key.split(".")
        node = s
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = val
    return s


# --- ratchet without budget → must yield the ratchet-needs-budget finding ---

def test_ratchet_no_budget_yields_finding():
    # has_budget is False: stop only has max_iterations, no stop.budget
    s = _spec(**{"verifier.shape": "ratchet"})
    findings = lint_spec(s)
    shape_findings = [f for f in findings if "verifier.shape" in f and "ratchet" in f and "budget" in f]
    assert shape_findings, (
        f"Expected a ratchet-needs-budget finding but got none. All findings: {findings}"
    )


def test_ratchet_no_budget_finding_message():
    s = _spec(**{"verifier.shape": "ratchet"})
    findings = lint_spec(s)
    combined = " ".join(findings)
    assert "stop.budget" in combined, f"Finding should mention stop.budget. Got: {findings}"


# --- ratchet WITH a stop.budget → shape finding must be absent ---

def test_ratchet_with_budget_no_shape_finding():
    s = _spec(**{"verifier.shape": "ratchet", "stop.budget": {"wall_clock_minutes": 30}})
    findings = lint_spec(s)
    shape_findings = [f for f in findings if "verifier.shape" in f]
    assert not shape_findings, (
        f"Expected no verifier.shape finding when budget is set, got: {shape_findings}"
    )


# --- shape: gate → no shape finding ---

def test_gate_shape_no_finding():
    s = _spec(**{"verifier.shape": "gate"})
    findings = lint_spec(s)
    shape_findings = [f for f in findings if "verifier.shape" in f]
    assert not shape_findings, f"gate shape should produce no shape finding, got: {shape_findings}"


# --- shape absent → no shape finding ---

def test_absent_shape_no_finding():
    s = copy.deepcopy(_BASE)
    # No verifier.shape key at all
    assert "shape" not in s.get("verifier", {})
    findings = lint_spec(s)
    shape_findings = [f for f in findings if "verifier.shape" in f]
    assert not shape_findings, f"Absent shape should produce no shape finding, got: {shape_findings}"


# --- invalid shape → must yield the enum finding ---

def test_invalid_shape_yields_enum_finding():
    s = _spec(**{"verifier.shape": "waterfall"})
    findings = lint_spec(s)
    shape_findings = [f for f in findings if "verifier.shape" in f and "must be one of" in f]
    assert shape_findings, (
        f"Expected an enum finding for unknown shape but got none. All findings: {findings}"
    )


def test_invalid_shape_finding_lists_valid_values():
    s = _spec(**{"verifier.shape": "waterfall"})
    findings = lint_spec(s)
    combined = " ".join(findings)
    assert "gate" in combined and "ratchet" in combined, (
        f"Enum finding should list valid shapes. Got: {findings}"
    )
