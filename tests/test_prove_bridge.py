"""G45-01 product prove bridge — objective-gate tests.

Focused, cold-runnable coverage of the starter→receipt path at
examples/first-30-minutes (instructional demo) + scripts/verify-outcome.py:

  1. GREEN path emits looptimal-receipt.json that product --check-receipt re-derives GREEN
  2. RED / BLOCKED emit no committed receipt; receipt-generation failure cleans leftovers
  3. Forged / stale receipts are rejected (demo re-verify + product --check-receipt)
  4. Idempotent terminal rerun preserves hashes and does not invent new attempts

Layers that must not be collapsed (docs + output):
  smoke (install/structural) ≠ verifier result (GREEN/RED/BLOCKED) ≠ receipt (looptimal-receipt)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "first-30-minutes"
DEMO = EXAMPLE / "run_demo.sh"
VERIFY = EXAMPLE / "verify.sh"
VERIFY_OUTCOME = REPO / "scripts" / "verify-outcome.py"


def _bash_ok() -> bool:
    if sys.platform.startswith("win"):
        return False
    b = shutil.which("bash")
    if not b:
        return False
    try:
        out = subprocess.run(
            [b, "-c", "echo ok"], capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() == "ok"
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _bash_ok(),
    reason="prove bridge needs a POSIX bash (skipped on Windows CI)",
)


def _env() -> dict[str, str]:
    value = os.environ.copy()
    value["PYTHONDONTWRITEBYTECODE"] = "1"
    value.pop("LOOPTIMAL_FRAMER_KEY", None)
    return value


def _run_demo(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(DEMO), *args],
        cwd=str(cwd or REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_env(),
        check=False,
        timeout=120,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _dump(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _check_receipt(receipt: Path, workdir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VERIFY_OUTCOME),
            "--check-receipt",
            str(receipt),
            "--workdir",
            str(workdir),
            "--repeat",
            "1",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_env(),
        check=False,
        timeout=60,
    )


def _evidence_hashes(run_root: Path) -> dict[str, str]:
    evidence_dir = run_root / "attempt-evidence"
    if not evidence_dir.is_dir():
        return {}
    return {p.name: _sha256(p) for p in sorted(evidence_dir.glob("*.json"))}


def _verify_only(run_root: Path) -> subprocess.CompletedProcess[str]:
    env = _env()
    env["FIRST30_RUN_ROOT"] = str(run_root)
    return subprocess.run(
        ["bash", str(VERIFY)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
        timeout=60,
    )


# --------------------------------------------------------------------------- #
# 1. GREEN receipt verification (product --check-receipt)
# --------------------------------------------------------------------------- #
def test_green_path_emits_receipt_that_check_receipt_rederives(tmp_path: Path):
    """Cold GREEN path: only after verifier GREEN is a product-verifiable receipt committed."""
    root = tmp_path / "green"
    proc = _run_demo("--mode", "accept", "--root", str(root))
    assert proc.returncode == 0, proc.stderr + proc.stdout

    # Layer labels: smoke / verifier / receipt must appear distinctly in docs+stdout.
    combined = (proc.stdout + proc.stderr).lower()
    assert "verdict" in combined or '"status": "accepted"' in combined
    assert "looptimal-receipt" in combined or "outcome_receipt" in combined

    state = _load(root / "state" / "loop.json")
    assert state["status"] == "ACCEPTED"
    assert [a["status"] for a in state["attempts"]] == ["RED", "GREEN"]

    receipt = root / "outcome" / "looptimal-receipt.json"
    assert receipt.is_file(), "GREEN/ACCEPTED must commit outcome/looptimal-receipt.json"
    data = _load(receipt)
    assert data["kind"] == "looptimal-receipt"
    assert data["verdict"] == "GREEN"
    assert data["schema_version"] == 1

    # Product prove: independent --check-receipt re-derives GREEN from first principles.
    check = _check_receipt(receipt, root / "outcome")
    assert check.returncode == 0, check.stdout + check.stderr
    report = json.loads(check.stdout)
    assert report.get("result") == "GREEN"
    assert report.get("failed_step") is None

    # Attempt evidence is never the outcome receipt.
    for path in (root / "attempt-evidence").glob("*.json"):
        evidence = _load(path)
        assert evidence["kind"] == "attempt-evidence"
        assert evidence["kind"] != "looptimal-receipt"


# --------------------------------------------------------------------------- #
# 2. RED / BLOCKED — no committed receipt; failure cleans leftovers
# --------------------------------------------------------------------------- #
def test_red_and_blocked_emit_no_committed_receipt(tmp_path: Path):
    for mode, code in (("exhaust", 2), ("block", 3)):
        root = tmp_path / f"no-receipt-{mode}"
        proc = _run_demo("--mode", mode, "--root", str(root))
        assert proc.returncode == code, proc.stderr + proc.stdout
        assert not (root / "outcome" / "looptimal-receipt.json").exists()
        assert not (root / "looptimal-receipt.json").exists()
        # No accidental receipt filename anywhere under the run root.
        names = {p.name for p in root.rglob("*") if p.is_file()}
        assert "looptimal-receipt.json" not in names


def test_receipt_generation_failure_cleans_uncommitted_receipt(tmp_path: Path):
    """Receipt failure must not leave ACCEPTED or a published outcome receipt."""
    root = tmp_path / "cleanup"
    root.mkdir()
    # Block outcome/ as a directory so materials + receipt emission fail.
    (root / "outcome").write_text("not-a-directory\n", encoding="utf-8")
    proc = _run_demo("--mode", "accept", "--root", str(root))
    assert proc.returncode != 0, proc.stdout + proc.stderr
    state = _load(root / "state" / "loop.json")
    assert state["status"] != "ACCEPTED"
    if (root / "outcome").is_dir():
        assert not (root / "outcome" / "looptimal-receipt.json").exists()
    else:
        assert (root / "outcome").is_file()
    if (root / "terminal.json").exists():
        assert _load(root / "terminal.json").get("status") != "ACCEPTED"


# --------------------------------------------------------------------------- #
# 3. Forged / stale receipt rejection
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "mutator",
    [
        "minimal_forged",
        "stale_bundle_hash",
        "wrong_verdict",
        "tamper_lineage_artifact",
    ],
)
def test_forged_or_stale_receipt_rejected(tmp_path: Path, mutator: str):
    root = tmp_path / f"forged-{mutator}"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0
    receipt_path = root / "outcome" / "looptimal-receipt.json"
    receipt = _load(receipt_path)
    lineage_path = root / "outcome" / "src" / "lineage.json"

    if mutator == "minimal_forged":
        _dump(receipt_path, {"kind": "looptimal-receipt", "verdict": "GREEN"})
    elif mutator == "stale_bundle_hash":
        receipt["evidence_bundle_sha256"] = "0" * 64
        _dump(receipt_path, receipt)
    elif mutator == "wrong_verdict":
        receipt["verdict"] = "RED"
        _dump(receipt_path, receipt)
    elif mutator == "tamper_lineage_artifact":
        lineage = _load(lineage_path)
        lineage["accepted_artifact_sha256"] = "1" * 64
        _dump(lineage_path, lineage)
    else:
        raise AssertionError(mutator)

    # Demo re-verify (fail-closed).
    env = _env()
    env["FIRST30_RUN_ROOT"] = str(root)
    vo = subprocess.run(
        ["bash", str(VERIFY)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
        timeout=60,
    )
    assert vo.returncode != 0, vo.stdout + vo.stderr

    # Product --check-receipt also rejects (or cannot re-derive GREEN).
    check = _check_receipt(receipt_path, root / "outcome")
    assert check.returncode != 0, check.stdout + check.stderr

    # Terminal rerun must not re-accept forged evidence.
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode != 0


# --------------------------------------------------------------------------- #
# 4. Idempotent terminal rerun
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "mode,exit_code",
    [
        ("accept", 0),
        ("exhaust", 2),
        ("block", 3),
    ],
)
def test_idempotent_rerun_preserves_hashes(tmp_path: Path, mode: str, exit_code: int):
    root = tmp_path / f"idem-{mode}"
    first = _run_demo("--mode", mode, "--root", str(root))
    assert first.returncode == exit_code, first.stderr + first.stdout

    before_evidence = _evidence_hashes(root)
    before_state = _sha256(root / "state" / "loop.json")
    before_terminal = _sha256(root / "terminal.json")
    receipt = root / "outcome" / "looptimal-receipt.json"
    before_receipt = _sha256(receipt) if receipt.is_file() else None

    second = _run_demo("--mode", mode, "--root", str(root))
    assert second.returncode == exit_code, second.stderr + second.stdout
    assert _evidence_hashes(root) == before_evidence
    assert _sha256(root / "state" / "loop.json") == before_state
    assert _sha256(root / "terminal.json") == before_terminal
    if before_receipt is not None:
        assert receipt.is_file()
        assert _sha256(receipt) == before_receipt
        # Re-check still GREEN after idempotent pass.
        check = _check_receipt(receipt, root / "outcome")
        assert check.returncode == 0, check.stdout + check.stderr
    else:
        assert not receipt.exists()


# --------------------------------------------------------------------------- #
# 5. State-derived evidence_path / artifact_path containment
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", ["evidence_path", "artifact_path"])
def test_state_path_rejects_exact_byte_outside_symlink(tmp_path: Path, field: str):
    """Symlink substitution of exact outside bytes must fail before read/hash."""
    root = tmp_path / f"symlink-{field}"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0

    state = _load(root / "state" / "loop.json")
    attempt = state["attempts"][0]
    rel = attempt[field]
    assert isinstance(rel, str) and not Path(rel).is_absolute()
    in_root = root / rel
    assert in_root.is_file() and not in_root.is_symlink()

    # Outside file carries the *exact same bytes* as the legitimate in-root path.
    outside = tmp_path / f"outside-{field}.json"
    outside.write_bytes(in_root.read_bytes())
    assert _sha256(outside) == _sha256(in_root)
    assert attempt[field.replace("_path", "_sha256")] == _sha256(outside)

    # Replace the in-root leaf with a symlink to the outside twin.
    in_root.unlink()
    in_root.symlink_to(outside)
    assert in_root.is_symlink()
    assert in_root.resolve() == outside.resolve()
    # Exact-byte substitution would satisfy a naive open+hash; confinement must still fail.
    assert _sha256(in_root) == attempt[field.replace("_path", "_sha256")]

    vo = _verify_only(root)
    assert vo.returncode != 0, vo.stdout + vo.stderr
    combined = (vo.stdout + vo.stderr).lower()
    assert "symlink" in combined or field in combined or "escape" in combined

    rerun = _run_demo("--mode", "accept", "--root", str(root))
    assert rerun.returncode != 0, rerun.stdout + rerun.stderr


@pytest.mark.parametrize("field", ["evidence_path", "artifact_path"])
def test_state_path_rejects_dotdot_outside_traversal(tmp_path: Path, field: str):
    """State field rewritten to ../outside must fail before read/hash."""
    root = tmp_path / f"dotdot-{field}"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0

    state = _load(root / "state" / "loop.json")
    attempt = state["attempts"][0]
    original_rel = attempt[field]
    in_root = root / original_rel
    assert in_root.is_file()

    outside_dir = tmp_path / "outside-payload"
    outside_dir.mkdir()
    outside_name = f"escaped-{field}.json"
    outside = outside_dir / outside_name
    outside.write_bytes(in_root.read_bytes())
    assert _sha256(outside) == attempt[field.replace("_path", "_sha256")]

    # Hostile relative path: from run root, ../outside-payload/<file> leaves the root.
    hostile_rel = f"../outside-payload/{outside_name}"
    # Prove the join really escapes before the gate rejects it.
    joined = (root / hostile_rel).resolve()
    assert joined == outside.resolve()
    assert not str(joined).startswith(str(root.resolve()) + os.sep)

    attempt[field] = hostile_rel
    # Outer hash still matches the outside twin — only path containment must reject.
    _dump(root / "state" / "loop.json", state)

    vo = _verify_only(root)
    assert vo.returncode != 0, vo.stdout + vo.stderr
    combined = (vo.stdout + vo.stderr).lower()
    assert (
        ".." in combined
        or "travers" in combined
        or "escape" in combined
        or "relative" in combined
        or field in combined
    )

    rerun = _run_demo("--mode", "accept", "--root", str(root))
    assert rerun.returncode != 0, rerun.stdout + rerun.stderr


def test_valid_in_root_state_paths_still_verify(tmp_path: Path):
    """Legitimate relative in-root evidence_path / artifact_path remain accepted."""
    root = tmp_path / "valid-paths"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0
    state = _load(root / "state" / "loop.json")
    for attempt in state["attempts"]:
        for field in ("evidence_path", "artifact_path"):
            rel = attempt[field]
            assert isinstance(rel, str)
            assert not Path(rel).is_absolute()
            assert ".." not in Path(rel).parts
            path = root / rel
            assert path.is_file()
            assert not path.is_symlink()
            assert path.resolve().is_relative_to(root.resolve())
    assert _verify_only(root).returncode == 0
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0


# --------------------------------------------------------------------------- #
# Layer vocabulary + product gate wiring
# --------------------------------------------------------------------------- #
def test_docs_and_smoke_distinguish_smoke_verifier_receipt():
    readme = (EXAMPLE / "README.md").read_text(encoding="utf-8").lower()
    assert "smoke" in readme or "install" in readme or "structural" in readme
    assert "verifier" in readme
    assert "looptimal-receipt" in readme
    assert "attempt-evidence" in readme or "attempt evidence" in readme

    # Structural smoke is GREEN without a run root and is not a receipt.
    smoke = subprocess.run(
        ["bash", str(VERIFY)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_env(),
        check=False,
        timeout=30,
    )
    assert smoke.returncode == 0, smoke.stderr
    text = (smoke.stdout + smoke.stderr).lower()
    assert "green" in text
    assert "not an accepted" in text or "not an accepted outcome receipt" in text

    # Engine source must product-prove the receipt via --check-receipt before ACCEPTED.
    engine = DEMO.read_text(encoding="utf-8")
    assert "--check-receipt" in engine
    assert "looptimal-receipt" in engine
    assert "def resolve_state_path(" in engine
    assert "resolve_state_path(" in engine
    # Both state-derived fields go through the single helper before read/hash.
    assert engine.count("resolve_state_path(") >= 4
