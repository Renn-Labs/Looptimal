"""Tests for scripts/verify-outcome.py's receipt emission (references/receipt.md) —
`emit_receipt()` and the `--receipt` / `--receipt-include-objective` CLI flags.

Regression protection for this feature previously lived solely in verify-outcome.py's
own `--selftest` (exercised end-to-end via subprocess, but not part of a normal
`pytest tests/` run — the same gap test_looptimal_lint.py's docstring notes for
looptimal-lint.py). An independent security review (2026-07-02) flagged this LOW
severity: "regression protection lives solely in the selftest; a pytest case would
guard against changes that bypass the selftest path." This file closes that gap.

Every case except the path-traversal guard (7 — an internal safety property, not
end-to-end CLI behavior) drives the real CLI via subprocess the way an actual user
would invoke it, rather than calling emit_receipt() as a bare Python function. The
fixture builder mirrors run_selftest()'s own shape (a sealed oracle + honest source
file + framer contract + mission + evidence bundle) since that shape is already
proven to verify GREEN — see scripts/verify-outcome.py's run_selftest().
"""
import hashlib
import hmac
import importlib.util
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VERIFY_OUTCOME = REPO / "scripts" / "verify-outcome.py"


def _load(stem: str):
    path = REPO / "scripts" / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(stem.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


common = _load("_common")
vo = _load("verify-outcome")


# ---- fixture builder ---------------------------------------------------------------
def _write_fixture(run: Path, *, key: bytes | None,
                   objective: str = "the sealed repro no longer reproduces the missing-project 500") -> dict:
    """A sealed oracle + honest source file + framer contract + mission + evidence bundle
    that verify() confirms GREEN — optionally HMAC-keyed. Mirrors run_selftest()'s exact
    fixture shape (scripts/verify-outcome.py) rather than inventing a new one."""
    (run / "sealed").mkdir(parents=True)
    (run / "src").mkdir()
    (run / "sealed" / "check.py").write_text(
        "import sys, pathlib\n"
        "p = pathlib.Path('src/app.py')\n"
        "sys.exit(0 if p.exists() and 'fixed' in p.read_text() else 1)\n",
        encoding="utf-8")
    (run / "src" / "app.py").write_text("# fixed\nreturn 404\n", encoding="utf-8")
    contract: dict = {
        "schema_version": 1, "objective": objective,
        "acceptance_suite": {
            "provenance": "framer", "sealed_path": "sealed/suite.json",
            "criteria": [{"id": "c1", "asserts": "outcome", "oracle": "repro",
                          "external_check": ["python3", "sealed/check.py"],
                          "green_means": "the sealed repro no longer reproduces the bug"}],
        }, "irreversibles": [],
    }
    contract_path = run / "sealed" / "contract.json"
    sealed_dir = run / "sealed"
    # Computed once, before contract.json exists on disk: sealed_dir_materials() would skip
    # it anyway via `exclude` once written, so the same value is valid for both the contract's
    # own contract_hash and the bundle's (mirrors run_selftest()'s two call sites exactly).
    chash = common.canonical_contract_hash(
        contract, key=key, sealed_dir=sealed_dir if key else None,
        exclude=contract_path if key else None)
    contract["contract_hash"] = "sha256:" + chash
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    mission = {"schema_version": 1, "contract_ref": "sealed/contract.json",
               "capability_manifest": {"backend": {"allowed_paths": ["src/"]}},
               "lanes": [{"id": "L1", "archetype": "task"}]}
    (run / "mission.json").write_text(json.dumps(mission), encoding="utf-8")
    art_hash = vo.sha256_file(run / "src" / "app.py")
    bundle = {
        "contract_ref": "sealed/contract.json", "accepted_plan_ref": "mission.json",
        "contract_hash": chash,
        "artifacts": [{"path": "src/app.py", "sha256": art_hash}],
        "tool_receipts": [{"cmd": "pytest", "exit": 0, "stdout_sha": art_hash, "ts": "t"}],
        "acceptance_results": [{"criterion": "c1", "passed_by": "external_rerun", "value": "pass"}],
        "final_state_assertion": "src/app.py returns 404 for the missing project",
        "unresolved_risks": [], "persisted_state_update_ref": "mission.json",
    }
    bundle_path = run / "bundle.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    return {"run": run, "bundle_path": bundle_path, "contract_path": contract_path,
            "objective": objective}


def _break_live_state(run: Path, bundle_path: Path) -> None:
    """Tamper the live target state so the sealed oracle re-run fails (RED) — the same
    tamper run_selftest() uses: rewrite src/app.py without 'fixed', and keep the bundle's
    artifact hash honestly matching the new, broken content, so it is the LIVE RE-RUN of
    the oracle — not a stale-hash mismatch — that fails the criterion."""
    (run / "src" / "app.py").write_text("# broken\n", encoding="utf-8")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["artifacts"][0]["sha256"] = vo.sha256_file(run / "src" / "app.py")
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")


def _clean_env() -> dict:
    """Strip LOOPTIMAL_FRAMER_KEY from the subprocess env so an ambient value can never
    silently turn an "unkeyed" test case keyed. (--key-file always takes precedence per
    resolve_framer_key's precedence rule, so this only matters for the unkeyed cases —
    stripped unconditionally here so no call site has to remember which mode it's in.)"""
    return {k: v for k, v in os.environ.items() if k != common.FRAMER_KEY_ENV}


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    # encoding="utf-8" is required explicitly: relying on the platform default has bitten
    # this repo's Windows CI before (cp1252 default breaks on non-ASCII subprocess output).
    return subprocess.run(
        [sys.executable, str(VERIFY_OUTCOME), *args],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=_clean_env())


def _gen_key(tmp_path: Path) -> tuple:
    """A random, throwaway test-only HMAC key. Never the repo's real
    examples/issue-to-pr-bugfix/DEMO-KEY-NOT-SECRET.hex — that file is a fixed, published
    all-zero demo key, not meant to double as a test secret (or a production one)."""
    key_bytes = secrets.token_bytes(32)
    key_file = tmp_path / "test-framer-key.hex"
    key_file.write_text(key_bytes.hex(), encoding="utf-8")
    return key_bytes, key_file


# ---- 1 + 2: keyed GREEN --receipt: file + fields, and an independently-recomputed signature
def test_keyed_green_receipt_has_signed_fields_and_matching_criteria(tmp_path):
    key_bytes, key_file = _gen_key(tmp_path)
    run = tmp_path / "run"
    fx = _write_fixture(run, key=key_bytes)

    proc = _run_cli("--bundle", str(fx["bundle_path"]), "--workdir", str(run),
                    "--key-file", str(key_file), "--repeat", "1", "--receipt", cwd=run)
    assert proc.returncode == 0, proc.stderr  # GREEN

    receipt_path = run / "looptimal-receipt.json"
    assert receipt_path.is_file()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert receipt["kind"] == "looptimal-receipt"
    assert receipt["contract_hash_keyed"] is True
    assert receipt["verdict"] == "GREEN"
    assert receipt["criteria_passed"] == ["c1"]  # the honest run's one passing criterion
    assert isinstance(receipt.get("signature"), dict)
    assert receipt["signature"].get("alg") == "HMAC-SHA256"
    assert receipt["signature"].get("value")

    # case 2: the signature independently RE-VERIFIES against the receipt's own fields,
    # recomputed here with receipt.md's exact canonicalization — not merely "present".
    payload = {k: v for k, v in receipt.items() if k != "signature"}
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True).encode("utf-8")
    recomputed = hmac.new(key_bytes, payload_bytes, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(recomputed, receipt["signature"]["value"])


# ---- 3: unkeyed GREEN --receipt: contract_hash_keyed is false, signature key is ABSENT
def test_unkeyed_green_receipt_has_no_signature_key(tmp_path):
    run = tmp_path / "run"
    fx = _write_fixture(run, key=None)

    proc = _run_cli("--bundle", str(fx["bundle_path"]), "--workdir", str(run),
                    "--repeat", "1", "--receipt", cwd=run)
    assert proc.returncode == 0, proc.stderr  # GREEN

    receipt = json.loads((run / "looptimal-receipt.json").read_text(encoding="utf-8"))
    assert receipt["contract_hash_keyed"] is False
    assert "signature" not in receipt  # absent, not null


# ---- 4: RED run + --receipt <fresh path> writes NO receipt at all
def test_red_run_writes_no_receipt(tmp_path):
    run = tmp_path / "run"
    fx = _write_fixture(run, key=None)
    _break_live_state(run, fx["bundle_path"])

    fresh_receipt = run / "should-not-appear.json"
    assert not fresh_receipt.exists()
    proc = _run_cli("--bundle", str(fx["bundle_path"]), "--workdir", str(run),
                    "--repeat", "1", "--receipt", str(fresh_receipt), cwd=run)
    assert proc.returncode == 1  # RED
    assert not fresh_receipt.exists()


# ---- 5: --receipt-include-objective toggles the clear-text objective; objective_hash is
#         present unconditionally either way and equals sha256(objective_text).
def test_receipt_include_objective_flag(tmp_path):
    objective_text = "prove a cache miss for a missing project returns 404, not 500"
    run = tmp_path / "run"
    fx = _write_fixture(run, key=None, objective=objective_text)
    expected_hash = "sha256:" + hashlib.sha256(objective_text.encode("utf-8")).hexdigest()

    with_obj = run / "with-objective.json"
    proc1 = _run_cli("--bundle", str(fx["bundle_path"]), "--workdir", str(run),
                     "--repeat", "1", "--receipt", str(with_obj),
                     "--receipt-include-objective", cwd=run)
    assert proc1.returncode == 0, proc1.stderr
    r1 = json.loads(with_obj.read_text(encoding="utf-8"))
    assert r1.get("objective") == objective_text
    assert r1.get("objective_hash") == expected_hash

    without_obj = run / "without-objective.json"
    proc2 = _run_cli("--bundle", str(fx["bundle_path"]), "--workdir", str(run),
                     "--repeat", "1", "--receipt", str(without_obj), cwd=run)
    assert proc2.returncode == 0, proc2.stderr
    r2 = json.loads(without_obj.read_text(encoding="utf-8"))
    assert "objective" not in r2
    assert r2.get("objective_hash") == expected_hash


# ---- 6: bare --receipt (no path arg, and no --workdir either) defaults to
#         <bundle-dir-derived-workdir>/looptimal-receipt.json
def test_bare_receipt_flag_defaults_to_workdir_looptimal_receipt_json(tmp_path):
    run = tmp_path / "run"
    fx = _write_fixture(run, key=None)
    default_path = run / "looptimal-receipt.json"
    assert not default_path.exists()

    # No --workdir passed: main() derives workdir from the bundle's own parent dir, then
    # a bare --receipt defaults to <that workdir>/looptimal-receipt.json.
    proc = _run_cli("--bundle", str(fx["bundle_path"]), "--repeat", "1", "--receipt", cwd=run)
    assert proc.returncode == 0, proc.stderr
    assert default_path.is_file()


# ---- 7: path-traversal guard on contract_ref (2026-07-02 confirmation review, finding
#         L1) — a direct unit test of emit_receipt()'s own internal safety property (it
#         re-asserts verify()'s traversal guard independently), not end-to-end CLI behavior.
def test_emit_receipt_rejects_traversing_contract_ref(tmp_path):
    bundle_dir = tmp_path / "evil"
    bundle_dir.mkdir()
    bundle_path = bundle_dir / "bundle.json"
    bundle_path.write_text(json.dumps({"contract_ref": "../../outside/contract.json"}),
                           encoding="utf-8")

    fake_verdict = {"contract_hash": "deadbeef", "criteria": [], "repeat": 1}
    target = tmp_path / "should-not-be-written.json"
    with pytest.raises(ValueError, match="non-traversing"):
        vo.emit_receipt(target, fake_verdict, bundle_path, bundle_dir,
                        key=None, include_objective=False)
    assert not target.exists()
