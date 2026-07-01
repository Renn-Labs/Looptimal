"""Tests for scripts/looptimal-lint.py and _common.py's outcome-layer helpers — the
sealed-contract lint (contract_hash, HMAC keying) and the checker-only visibility tier.

No prior test file covers this layer directly (tests/ otherwise only imports
loopprint-detect/doctor/lint, the loop-spec-layer scripts) — looptimal-lint.py's own
--selftest exercises an end-to-end round-trip via subprocess, but isn't part of a normal
`pytest tests/` run. This file adds real pytest-native coverage of the newer pieces.
"""
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load(stem: str):
    path = REPO / "scripts" / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(stem.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


common = _load("_common")
looptimal_lint = _load("looptimal-lint")


def _base_contract(**overrides):
    contract = {
        "schema_version": 1,
        "objective": "test",
        "sensitivity": "low",
        "acceptance_suite": {
            "provenance": "framer",
            "sealed_path": "sealed/",
            "criteria": [
                {"id": "c1", "asserts": "outcome", "oracle": "repro",
                 "external_check": ["python3", "sealed/check.py"],
                 "green_means": "the sealed repro no longer reproduces the bug"},
            ],
        },
        "irreversibles": [],
    }
    contract.update(overrides)
    return contract


def _seal(root: Path, contract: dict, key: bytes | None = None) -> dict:
    (root / "sealed").mkdir(parents=True, exist_ok=True)
    (root / "sealed" / "check.py").write_text("import sys; sys.exit(0)\n", encoding="utf-8")
    contract_path = root / "sealed" / "contract.json"
    chash = common.canonical_contract_hash(
        contract, key=key,
        sealed_dir=(root / "sealed") if key else None,
        exclude=contract_path if key else None,
    )
    sealed_contract = dict(contract)
    sealed_contract["contract_hash"] = f"sha256:{chash}"
    contract_path.write_text(json.dumps(sealed_contract), encoding="utf-8")
    mission = {"schema_version": 1, "contract_ref": "sealed/contract.json", "contract_hash": chash,
              "capability_manifest": {}, "human_go_gate": True, "lanes": [], "tasks": []}
    mission_path = root / "mission.json"
    mission_path.write_text(json.dumps(mission), encoding="utf-8")
    return {"mission_path": mission_path}


# ---- maker_safe_view ---------------------------------------------------------------
def test_maker_safe_view_redacts_checker_only_criteria():
    contract = _base_contract()
    contract["acceptance_suite"]["criteria"].append({
        "id": "c2", "category": "holdout", "asserts": "outcome", "oracle": "holdout-check",
        "external_check": ["python3", "sealed/secret_check.py"],
        "green_means": "the thing a maker shouldn't be able to read and game",
        "visibility": "checker-only",
    })
    view = common.maker_safe_view(contract)
    criteria = view["acceptance_suite"]["criteria"]
    assert criteria[0] == contract["acceptance_suite"]["criteria"][0]  # maker-visible: unchanged
    assert criteria[1] == {"id": "c2", "category": "holdout"}  # checker-only: redacted
    assert "external_check" not in criteria[1]
    assert "green_means" not in criteria[1]


def test_maker_safe_view_defaults_to_maker_visible_when_field_absent():
    contract = _base_contract()
    view = common.maker_safe_view(contract)
    assert view["acceptance_suite"]["criteria"][0].get("external_check") == ["python3", "sealed/check.py"]


def test_maker_safe_view_noop_on_contract_with_no_suite():
    contract = {"schema_version": 1, "objective": "no suite here"}
    assert common.maker_safe_view(contract) == contract


# ---- looptimal-lint.py: visibility enum validation --------------------------------
def test_lint_rejects_invalid_visibility_value(tmp_path):
    contract = _base_contract()
    contract["acceptance_suite"]["criteria"][0]["visibility"] = "totally-invisible"
    fx = _seal(tmp_path, contract)
    ok, findings, _ = looptimal_lint.lint(fx["mission_path"], repo_root=tmp_path)
    assert not ok
    assert any("visibility" in f and "totally-invisible" in f for f in findings)


def test_lint_accepts_both_valid_visibility_values(tmp_path):
    for value in ("maker-visible", "checker-only"):
        contract = _base_contract()
        contract["acceptance_suite"]["criteria"][0]["visibility"] = value
        fx = _seal(tmp_path, contract)
        ok, findings, _ = looptimal_lint.lint(fx["mission_path"], repo_root=tmp_path)
        assert ok, f"visibility={value!r} should lint clean, got {findings}"


# ---- looptimal-lint.py: sensitivity: high holdout advisory -------------------------
def test_sensitivity_high_with_no_checker_only_criteria_advises(tmp_path):
    contract = _base_contract(sensitivity="high")
    fx = _seal(tmp_path, contract)
    ok, _findings, advisories = looptimal_lint.lint(fx["mission_path"], repo_root=tmp_path)
    assert ok  # advisory only — never blocking
    assert any("zero checker-only criteria" in a for a in advisories)


def test_sensitivity_high_with_a_checker_only_criterion_is_silent(tmp_path):
    contract = _base_contract(sensitivity="high")
    contract["acceptance_suite"]["criteria"][0]["visibility"] = "checker-only"
    fx = _seal(tmp_path, contract)
    ok, _findings, advisories = looptimal_lint.lint(fx["mission_path"], repo_root=tmp_path)
    assert ok
    assert not any("zero checker-only criteria" in a for a in advisories)


def test_sensitivity_low_never_advises_about_checker_only(tmp_path):
    contract = _base_contract(sensitivity="low")
    fx = _seal(tmp_path, contract)
    _, _, advisories = looptimal_lint.lint(fx["mission_path"], repo_root=tmp_path)
    assert not any("checker-only" in a for a in advisories)


# ---- looptimal-lint.py: gate_type validation + soft-only-suite advisory -----------
def test_lint_rejects_invalid_gate_type_value(tmp_path):
    contract = _base_contract()
    contract["acceptance_suite"]["criteria"][0]["gate_type"] = "squishy"
    fx = _seal(tmp_path, contract)
    ok, findings, _ = looptimal_lint.lint(fx["mission_path"], repo_root=tmp_path)
    assert not ok
    assert any("gate_type" in f and "squishy" in f for f in findings)


def test_unset_gate_type_defaults_to_hard_no_advisory(tmp_path):
    contract = _base_contract()  # no gate_type set at all
    fx = _seal(tmp_path, contract)
    ok, _findings, advisories = looptimal_lint.lint(fx["mission_path"], repo_root=tmp_path)
    assert ok
    assert not any("gate_type: soft" in a for a in advisories)


def test_single_hard_criterion_among_softs_silences_advisory(tmp_path):
    contract = _base_contract()
    contract["acceptance_suite"]["criteria"][0]["gate_type"] = "hard"
    contract["acceptance_suite"]["criteria"].append({
        "id": "c2", "asserts": "outcome", "oracle": "rubric-judge", "gate_type": "soft",
        "external_check": ["python3", "sealed/judge.py"], "green_means": "scores >= 80",
    })
    fx = _seal(tmp_path, contract)
    _, _, advisories = looptimal_lint.lint(fx["mission_path"], repo_root=tmp_path)
    assert not any("gate_type: soft" in a for a in advisories)


def test_all_soft_suite_advises(tmp_path):
    contract = _base_contract()
    contract["acceptance_suite"]["criteria"][0]["gate_type"] = "soft"
    fx = _seal(tmp_path, contract)
    ok, _findings, advisories = looptimal_lint.lint(fx["mission_path"], repo_root=tmp_path)
    assert ok  # advisory only — never blocking
    assert any("gate_type: soft" in a for a in advisories)
