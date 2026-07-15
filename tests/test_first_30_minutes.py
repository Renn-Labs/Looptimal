"""Focused coverage for examples/first-30-minutes — the product first-30-minutes
teaching contract (S1-C / RBS-006 learning port).

Proves, offline and deterministically:
  * explicit source pin as full local git commit/tree object ids; missing/unresolved/main → BLOCKED
  * attempt one is a controlled RED with inspectable attempt-evidence (not a receipt)
  * state persists; resume increments lineage once
  * ACCEPTED / EXHAUSTED / BLOCKED terminals
  * ACCEPTED is transactional (receipt validated before ACCEPTED commit)
  * terminal rerun is fail-closed idempotent (stable hashes, no new attempts)
  * only ACCEPTED emits looptimal-receipt.json via scripts/verify-outcome.py
  * README vocabulary distinguishes install / attempt / verifier / outcome receipt
  * no forbidden product-proof claims; demo is controlled, not independent approval
  * adversarial forgeries and non-terminal verify-only paths fail closed
"""
from __future__ import annotations

import hashlib
import json
import os
import re
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
CONTROLLED_RED_REASON = (
    "controlled rejection: prior rejection attempt evidence lineage is absent"
)
FULL_OID_RE = re.compile(r"^[0-9a-f]{40}$")


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
    reason="first-30-minutes demo needs a POSIX bash (skipped on Windows CI)",
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


def _parse_last_json(stdout: str) -> dict[str, Any]:
    lines = [ln for ln in stdout.splitlines() if ln.strip().startswith("{")]
    assert lines, f"no JSON lines in stdout:\n{stdout}"
    return json.loads(lines[-1])


def _evidence_hashes(run_root: Path) -> dict[str, str]:
    evidence_dir = run_root / "attempt-evidence"
    if not evidence_dir.is_dir():
        return {}
    return {p.name: _sha256(p) for p in sorted(evidence_dir.glob("*.json"))}


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"},
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _head_commit_tree() -> tuple[str, str]:
    commit = _git("rev-parse", "--verify", "HEAD^{commit}")
    tree = _git("rev-parse", "--verify", "HEAD^{tree}")
    assert FULL_OID_RE.fullmatch(commit)
    assert FULL_OID_RE.fullmatch(tree)
    return commit, tree


def _git_blob_sha256(commit: str, relpath: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{commit}:{relpath}"],
        capture_output=True,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"},
    )
    assert proc.returncode == 0, proc.stderr
    return hashlib.sha256(proc.stdout).hexdigest()


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


def _rehash_evidence(run_root: Path, evidence_path: Path, state: dict[str, Any]) -> None:
    """Recompute outer evidence sha256 after mutating evidence JSON (adversarial)."""
    new_hash = _sha256(evidence_path)
    for attempt in state.get("attempts") or []:
        if attempt.get("evidence_path") == str(evidence_path.relative_to(run_root)):
            attempt["evidence_sha256"] = new_hash
    _dump(run_root / "state" / "loop.json", state)


# --------------------------------------------------------------------------- #
# Package shape + claim ceiling
# --------------------------------------------------------------------------- #
def test_example_package_files_exist():
    for name in (
        "README.md",
        "loop-spec.yaml",
        "state.md",
        "verify.sh",
        "run_demo.sh",
    ):
        assert (EXAMPLE / name).is_file(), name


def test_readme_distinguishes_four_verdict_terms():
    text = (EXAMPLE / "README.md").read_text(encoding="utf-8").lower()
    assert "install" in text or "doctor" in text
    assert "attempt evidence" in text or "attempt-evidence" in text
    assert "verifier verdict" in text or "verifier" in text
    assert "looptimal-receipt" in text
    assert "accepted outcome receipt" in text or "outcome receipt" in text


def test_readme_forbids_product_proof_claims():
    text = (EXAMPLE / "README.md").read_text(encoding="utf-8").lower()
    for forbidden in (
        "product market fit",
        "product-market fit",
        "customer accepted",
        "production ready",
        "verified corpus",
        "hosted service",
        "marketplace",
        "completed in 30 minutes",
    ):
        assert forbidden not in text, forbidden
    assert "instructional" in text
    assert "controlled" in text
    assert "independent" in text
    # Must not claim the scripted RED is independently discovered.
    assert "authentic red" not in text
    assert "independently discovered" not in text
    root = (REPO / "README.md").read_text(encoding="utf-8").lower()
    assert "first 30 minutes" in root
    assert "instructional" in root or "operator budget" in root
    assert "controlled" in root


def test_structural_verify_sh_is_green_without_run_root():
    proc = subprocess.run(
        ["bash", str(VERIFY)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_env(),
        check=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    combined = proc.stdout + proc.stderr
    assert "GREEN" in combined
    assert "not an accepted outcome receipt" in combined.lower() or "not an accepted" in combined.lower()


def test_loop_spec_lints_green():
    lint = REPO / "scripts" / "loopprint-lint.py"
    proc = subprocess.run(
        [sys.executable, str(lint), str(EXAMPLE / "loop-spec.yaml")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_env(),
        check=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GREEN" in proc.stdout


def test_no_grokprint_artifacts_in_candidate_tree():
    """Packaging: fail if .grokprint or *.grokprint exists anywhere (incl. empty dirs)."""
    hits: list[str] = []
    for path in REPO.rglob("*"):
        rel_parts = path.relative_to(REPO).parts
        if ".git" in rel_parts:
            continue
        if path.name == ".grokprint" or path.name.endswith(".grokprint"):
            hits.append(str(path.relative_to(REPO)))
        if any(part == ".grokprint" or part.endswith(".grokprint") for part in rel_parts):
            hits.append(str(path.relative_to(REPO)))
    assert hits == [], f"forbidden grokprint paths: {hits}"


# --------------------------------------------------------------------------- #
# Accept path: RED → resume → ACCEPTED + outcome receipt
# --------------------------------------------------------------------------- #
def test_accept_path_red_then_green_emits_outcome_receipt_only(tmp_path: Path):
    root = tmp_path / "accept"
    proc = _run_demo("--mode", "accept", "--root", str(root))
    assert proc.returncode == 0, proc.stderr + proc.stdout

    state = _load(root / "state" / "loop.json")
    assert state["status"] == "ACCEPTED"
    assert [a["status"] for a in state["attempts"]] == ["RED", "GREEN"]
    assert state["attempts"][0]["reason"] == CONTROLLED_RED_REASON

    evidence1 = _load(root / "attempt-evidence" / "attempt-001.json")
    assert evidence1["kind"] == "attempt-evidence"
    assert evidence1["kind"] != "looptimal-receipt"
    assert evidence1.get("not_an_outcome_receipt") is True
    assert evidence1["verifier_verdict"] == "RED"
    assert evidence1["loop_id"] == state["loop_id"]
    assert evidence1["goal"] == state["goal"]

    evidence2 = _load(root / "attempt-evidence" / "attempt-002.json")
    assert evidence2["kind"] == "attempt-evidence"
    assert evidence2["verifier_verdict"] == "GREEN"
    assert evidence2["candidate_lineage"]["prior_evidence_sha256"] == state["attempts"][0][
        "evidence_sha256"
    ]

    candidate2 = _load(root / "work" / "candidate-attempt-002.json")
    prior = candidate2["prior_rejection_evidence"]
    assert prior["evidence_sha256"] == state["attempts"][0]["evidence_sha256"]
    assert prior["verdict"] == "RED"
    assert candidate2["state_lineage"]["prior_attempt_count"] == 1

    receipt = root / "outcome" / "looptimal-receipt.json"
    assert receipt.is_file()
    receipt_data = _load(receipt)
    assert receipt_data["kind"] == "looptimal-receipt"
    assert receipt_data["verdict"] == "GREEN"

    pin = _load(root / "source-pin.json")
    assert FULL_OID_RE.fullmatch(pin["immutable_ref"])
    assert FULL_OID_RE.fullmatch(pin["immutable_tree"])

    terminal = _load(root / "terminal.json")
    assert terminal["status"] == "ACCEPTED"
    assert terminal["loop_id"] == state["loop_id"]

    for path in (root / "attempt-evidence").glob("*.json"):
        assert _load(path)["kind"] == "attempt-evidence"


def test_resume_reads_attempt_one_state_and_increments_lineage_once(tmp_path: Path):
    """Simulate a stop after attempt 1, then resume into attempt 2."""
    root = tmp_path / "resume"
    proc = _run_demo("--mode", "accept", "--root", str(root))
    assert proc.returncode == 0, proc.stderr

    state = _load(root / "state" / "loop.json")
    assert len(state["attempts"]) == 2
    assert state["attempts"][0]["prior_state_sha256"] is not None
    assert state["attempts"][1]["prior_state_sha256"] is not None
    assert state["attempts"][1]["prior_state_sha256"] != state["attempts"][0]["prior_state_sha256"]
    candidate2 = _load(root / "work" / "candidate-attempt-002.json")
    assert candidate2["state_lineage"]["prior_attempt_count"] == 1
    assert candidate2["prior_rejection_evidence"]["attempt"] == 1


# --------------------------------------------------------------------------- #
# Exhaust / Block
# --------------------------------------------------------------------------- #
def test_exhaust_path_two_reds_no_outcome_receipt(tmp_path: Path):
    root = tmp_path / "exhaust"
    proc = _run_demo("--mode", "exhaust", "--root", str(root))
    assert proc.returncode == 2, proc.stderr + proc.stdout

    state = _load(root / "state" / "loop.json")
    assert state["status"] == "EXHAUSTED"
    assert [a["status"] for a in state["attempts"]] == ["RED", "RED"]
    assert state["attempts"][0]["reason"] == CONTROLLED_RED_REASON
    assert "may not be invented" in state["attempts"][1]["reason"]

    assert not (root / "outcome" / "looptimal-receipt.json").exists()
    assert not (root / "looptimal-receipt.json").exists()
    for path in (root / "attempt-evidence").glob("*.json"):
        assert _load(path)["kind"] == "attempt-evidence"


def test_block_path_missing_source_pin_no_outcome_receipt(tmp_path: Path):
    root = tmp_path / "block"
    proc = _run_demo("--mode", "block", "--root", str(root))
    assert proc.returncode == 3, proc.stderr + proc.stdout

    state = _load(root / "state" / "loop.json")
    assert state["status"] == "BLOCKED"
    terminal = _load(root / "terminal.json")
    assert terminal["status"] == "BLOCKED"
    reason = str(state.get("stop", {}).get("reason") or terminal.get("reason") or "")
    assert "source pin" in reason.lower() or "main" in reason.lower() or "unresolved" in reason.lower()

    assert state["attempts"] == []
    assert not (root / "outcome" / "looptimal-receipt.json").exists()
    assert not list((root / "attempt-evidence").glob("*.json")) if (root / "attempt-evidence").exists() else True


def test_main_fallback_source_pin_is_blocked(tmp_path: Path):
    root = tmp_path / "main-pin"
    root.mkdir()
    (root / "state").mkdir()
    pin = {
        "schema_version": 1,
        "packet_id": "first-30-minutes",
        "claim_ceiling": "INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF",
        "forbidden_fallback": "main",
        "immutable_ref": "main",
        "immutable_ref_kind": "git_commit",
        "sources": [
            {
                "path": "examples/first-30-minutes/loop-spec.yaml",
                "sha256": _sha256(EXAMPLE / "loop-spec.yaml"),
            }
        ],
        "scope_interpretation": "instructional_budget_not_observed_duration",
        "wall_time_measured": False,
        "elapsed_seconds": None,
        "intended_operator_budget_minutes": 30,
    }
    _dump(root / "source-pin.json", pin)
    _dump(
        root / "state" / "loop.json",
        {
            "schema_version": 1,
            "loop_id": "first-30-minutes-lineage-close",
            "goal": "x",
            "status": "READY",
            "attempts": [],
            "stop": None,
            "claim_ceiling": "INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF",
            "max_attempts": 2,
        },
    )
    shutil.copyfile(EXAMPLE / "state.md", root / "state.md")

    proc = _run_demo("--mode", "accept", "--root", str(root))
    assert proc.returncode == 3, proc.stderr + proc.stdout
    state = _load(root / "state" / "loop.json")
    assert state["status"] == "BLOCKED"
    reason = str(state["stop"]["reason"]).lower()
    assert "main" in reason
    assert state["attempts"] == []
    assert not (root / "outcome" / "looptimal-receipt.json").exists()


def test_unresolved_source_path_is_blocked(tmp_path: Path):
    root = tmp_path / "missing-source"
    root.mkdir()
    (root / "state").mkdir()
    commit, tree = _head_commit_tree()
    pin = {
        "schema_version": 1,
        "packet_id": "first-30-minutes",
        "claim_ceiling": "INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF",
        "forbidden_fallback": "main",
        "immutable_ref": commit,
        "immutable_tree": tree,
        "immutable_ref_kind": "git_commit",
        "sources": [
            {
                "path": "examples/first-30-minutes/DOES-NOT-EXIST.pin",
                "sha256": "0" * 64,
            }
        ],
        "scope_interpretation": "instructional_budget_not_observed_duration",
        "wall_time_measured": False,
        "elapsed_seconds": None,
        "intended_operator_budget_minutes": 30,
    }
    _dump(root / "source-pin.json", pin)
    _dump(
        root / "state" / "loop.json",
        {
            "schema_version": 1,
            "loop_id": "first-30-minutes-lineage-close",
            "goal": "x",
            "status": "READY",
            "attempts": [],
            "stop": None,
            "claim_ceiling": "INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF",
            "max_attempts": 2,
        },
    )
    shutil.copyfile(EXAMPLE / "state.md", root / "state.md")

    proc = _run_demo("--mode", "accept", "--root", str(root))
    assert proc.returncode == 3, proc.stderr + proc.stdout
    state = _load(root / "state" / "loop.json")
    assert state["status"] == "BLOCKED"
    assert "unresolved source" in state["stop"]["reason"]
    assert state["attempts"] == []


def test_nonexistent_immutable_ref_is_blocked(tmp_path: Path):
    root = tmp_path / "bad-ref"
    root.mkdir()
    (root / "state").mkdir()
    bogus = "a" * 40
    pin = {
        "schema_version": 1,
        "packet_id": "first-30-minutes",
        "claim_ceiling": "INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF",
        "forbidden_fallback": "main",
        "immutable_ref": bogus,
        "immutable_tree": "b" * 40,
        "immutable_ref_kind": "git_commit",
        "sources": [
            {
                "path": "examples/first-30-minutes/loop-spec.yaml",
                "sha256": "0" * 64,
            }
        ],
        "scope_interpretation": "instructional_budget_not_observed_duration",
        "wall_time_measured": False,
        "elapsed_seconds": None,
        "intended_operator_budget_minutes": 30,
    }
    _dump(root / "source-pin.json", pin)
    _dump(
        root / "state" / "loop.json",
        {
            "schema_version": 1,
            "loop_id": "first-30-minutes-lineage-close",
            "goal": "x",
            "status": "READY",
            "attempts": [],
            "stop": None,
            "claim_ceiling": "INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF",
            "max_attempts": 2,
        },
    )
    shutil.copyfile(EXAMPLE / "state.md", root / "state.md")
    proc = _run_demo("--mode", "accept", "--root", str(root))
    assert proc.returncode == 3, proc.stderr + proc.stdout
    state = _load(root / "state" / "loop.json")
    assert state["status"] == "BLOCKED"
    assert "absent" in state["stop"]["reason"].lower() or "unresolved" in state["stop"]["reason"].lower()


def test_mutated_immutable_ref_fails_verify(tmp_path: Path):
    root = tmp_path / "mut-ref"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0
    pin = _load(root / "source-pin.json")
    original = pin["immutable_ref"]
    # Flip last hex nibble in a way that almost certainly is not a real object.
    flipped = original[:-1] + ("0" if original[-1] != "0" else "1")
    pin["immutable_ref"] = flipped
    _dump(root / "source-pin.json", pin)
    second = _run_demo("--mode", "accept", "--root", str(root))
    assert second.returncode != 0, second.stdout + second.stderr
    vo = _verify_only(root)
    assert vo.returncode != 0


def test_source_content_mismatch_against_pinned_git_object_fails(tmp_path: Path):
    root = tmp_path / "pin-drift"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0
    pin = _load(root / "source-pin.json")
    pin["sources"][0]["sha256"] = "0" * 64
    _dump(root / "source-pin.json", pin)
    second = _run_demo("--mode", "accept", "--root", str(root))
    assert second.returncode != 0
    assert _verify_only(root).returncode != 0


def test_tag_label_immutable_ref_is_rejected(tmp_path: Path):
    """Unchecked tag labels are not immutable boundaries."""
    root = tmp_path / "tag-label"
    root.mkdir()
    (root / "state").mkdir()
    pin = {
        "schema_version": 1,
        "packet_id": "first-30-minutes",
        "claim_ceiling": "INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF",
        "forbidden_fallback": "main",
        "immutable_ref": "v2.2.0",
        "immutable_tree": "c" * 40,
        "immutable_ref_kind": "git_commit",
        "sources": [
            {
                "path": "examples/first-30-minutes/loop-spec.yaml",
                "sha256": _git_blob_sha256(_head_commit_tree()[0], "examples/first-30-minutes/loop-spec.yaml"),
            }
        ],
        "scope_interpretation": "instructional_budget_not_observed_duration",
        "wall_time_measured": False,
        "elapsed_seconds": None,
        "intended_operator_budget_minutes": 30,
    }
    _dump(root / "source-pin.json", pin)
    _dump(
        root / "state" / "loop.json",
        {
            "schema_version": 1,
            "loop_id": "first-30-minutes-lineage-close",
            "goal": "x",
            "status": "READY",
            "attempts": [],
            "stop": None,
            "claim_ceiling": "INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF",
            "max_attempts": 2,
        },
    )
    shutil.copyfile(EXAMPLE / "state.md", root / "state.md")
    proc = _run_demo("--mode", "accept", "--root", str(root))
    assert proc.returncode == 3
    reason = _load(root / "state" / "loop.json")["stop"]["reason"].lower()
    assert "full" in reason or "object id" in reason or "tag" in reason


# --------------------------------------------------------------------------- #
# Terminal idempotency
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "mode,exit_code,status",
    [
        ("accept", 0, "ACCEPTED"),
        ("exhaust", 2, "EXHAUSTED"),
        ("block", 3, "BLOCKED"),
    ],
)
def test_terminal_rerun_is_idempotent(tmp_path: Path, mode: str, exit_code: int, status: str):
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
        assert _sha256(receipt) == before_receipt
    else:
        assert not receipt.exists()

    state = _load(root / "state" / "loop.json")
    assert state["status"] == status
    if mode == "block":
        assert state["attempts"] == []
    else:
        assert len(state["attempts"]) == 2


# --------------------------------------------------------------------------- #
# Default demo entrypoint + verify-only on a finished run
# --------------------------------------------------------------------------- #
def test_run_demo_default_entrypoint_exits_zero():
    proc = _run_demo()
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "ACCEPTED" in proc.stdout
    assert "controlled rejection" in proc.stdout
    assert "looptimal-receipt" in proc.stdout


def test_verify_only_on_accepted_run(tmp_path: Path):
    root = tmp_path / "vo-accept"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0
    proc = _verify_only(root)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "GREEN" in proc.stdout


def test_verify_only_rejects_non_accepted_receipt(tmp_path: Path):
    root = tmp_path / "vo-exhaust"
    assert _run_demo("--mode", "exhaust", "--root", str(root)).returncode == 2
    forged = root / "outcome"
    forged.mkdir(parents=True, exist_ok=True)
    (forged / "looptimal-receipt.json").write_text(
        json.dumps({"kind": "looptimal-receipt", "verdict": "GREEN"}) + "\n",
        encoding="utf-8",
    )
    proc = _verify_only(root)
    assert proc.returncode == 1, proc.stdout + proc.stderr


def test_red_path_never_writes_looptimal_receipt_filename_as_attempt_evidence(tmp_path: Path):
    root = tmp_path / "names"
    assert _run_demo("--mode", "exhaust", "--root", str(root)).returncode == 2
    names = {p.name for p in root.rglob("*") if p.is_file()}
    assert "attempt-001.json" in names
    assert "attempt-002.json" in names
    assert "looptimal-receipt.json" not in names


def test_no_network_behavior_uses_local_git_only(tmp_path: Path):
    """Offline contract: demo succeeds with proxy/env pollution stripped by the engine."""
    root = tmp_path / "offline"
    env = _env()
    env["http_proxy"] = "http://127.0.0.1:9"
    env["https_proxy"] = "http://127.0.0.1:9"
    env["ALL_PROXY"] = "socks5://127.0.0.1:9"
    env["GIT_TERMINAL_PROMPT"] = "0"
    proc = subprocess.run(
        ["bash", str(DEMO), "--mode", "accept", "--root", str(root)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    pin = _load(root / "source-pin.json")
    assert FULL_OID_RE.fullmatch(pin["immutable_ref"])
    # Object must exist locally.
    assert (
        subprocess.run(
            ["git", "-C", str(REPO), "cat-file", "-t", pin["immutable_ref"]],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        == "commit"
    )


# --------------------------------------------------------------------------- #
# Adversarial: transactional acceptance + forged terminals
# --------------------------------------------------------------------------- #
def test_receipt_failure_cannot_leave_accepted(tmp_path: Path):
    """If receipt generation cannot complete, state must not be ACCEPTED."""
    root = tmp_path / "recv-fail"
    root.mkdir()
    # Block outcome/ directory creation by planting a file at that path.
    (root / "outcome").write_text("not-a-directory\n", encoding="utf-8")
    proc = _run_demo("--mode", "accept", "--root", str(root))
    assert proc.returncode != 0, proc.stdout + proc.stderr
    state_path = root / "state" / "loop.json"
    assert state_path.is_file()
    state = _load(state_path)
    assert state["status"] != "ACCEPTED"
    assert not (root / "terminal.json").exists() or _load(root / "terminal.json").get("status") != "ACCEPTED"
    # GREEN may be sealed, but acceptance must not have committed.
    if state.get("attempts"):
        assert state["status"] in {"READY", "RUNNING", "BLOCKED", "EXHAUSTED"}


def test_accepted_state_without_receipt_fails_on_rerun(tmp_path: Path):
    root = tmp_path / "accept-no-receipt"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0
    receipt = root / "outcome" / "looptimal-receipt.json"
    assert receipt.is_file()
    before_state = _sha256(root / "state" / "loop.json")
    before_evidence = _evidence_hashes(root)
    receipt.unlink()
    second = _run_demo("--mode", "accept", "--root", str(root))
    assert second.returncode != 0, second.stdout + second.stderr
    # Fail-closed: no mutation of evidence on rejected idempotent rerun.
    assert _sha256(root / "state" / "loop.json") == before_state
    assert _evidence_hashes(root) == before_evidence
    assert _verify_only(root).returncode != 0


def test_fully_forged_preseeded_accepted_fails(tmp_path: Path):
    root = tmp_path / "forged-accepted"
    root.mkdir()
    (root / "state").mkdir()
    _dump(
        root / "state" / "loop.json",
        {
            "schema_version": 1,
            "loop_id": "wrong-loop",
            "goal": "forged goal",
            "status": "ACCEPTED",
            "attempts": [],
            "stop": {"reason": "forged", "attempt": None},
            "claim_ceiling": "INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF",
            "max_attempts": 2,
        },
    )
    # No pin, no terminal, no receipt, no attempts.
    proc = _run_demo("--mode", "accept", "--root", str(root))
    assert proc.returncode != 0, proc.stdout + proc.stderr
    # Must not treat as success.
    assert "idempotent_rerun" not in proc.stdout or proc.returncode != 0
    state = _load(root / "state" / "loop.json")
    # Untrusted terminal input: either still forged ACCEPTED (rejected) or not rewritten to success.
    assert proc.returncode != 0
    assert not (root / "outcome" / "looptimal-receipt.json").exists()


def test_verify_only_rejects_ready_and_running(tmp_path: Path):
    root = tmp_path / "nonterm"
    # Build a real pin + READY state via partial setup: run block? better plant.
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0
    state = _load(root / "state" / "loop.json")
    state["status"] = "READY"
    state["stop"] = None
    _dump(root / "state" / "loop.json", state)
    assert _verify_only(root).returncode != 0

    state["status"] = "RUNNING"
    _dump(root / "state" / "loop.json", state)
    assert _verify_only(root).returncode != 0


def test_terminal_drift_or_omission_fails(tmp_path: Path):
    root = tmp_path / "term-drift"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0
    # Omission
    (root / "terminal.json").unlink()
    assert _verify_only(root).returncode != 0
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode != 0

    # Restore via fresh run in sibling
    root2 = tmp_path / "term-drift2"
    assert _run_demo("--mode", "accept", "--root", str(root2)).returncode == 0
    terminal = _load(root2 / "terminal.json")
    terminal["reason"] = "drifted reason"
    _dump(root2 / "terminal.json", terminal)
    assert _verify_only(root2).returncode != 0
    assert _run_demo("--mode", "accept", "--root", str(root2)).returncode != 0


def test_inner_attempt_mutation_fails_even_when_outer_hashes_recomputed(tmp_path: Path):
    root = tmp_path / "inner-mut"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0
    state = _load(root / "state" / "loop.json")
    evidence_path = root / "attempt-evidence" / "attempt-002.json"
    evidence = _load(evidence_path)

    # Mutate semantic fields that outer hashing alone would miss if only hashing state.
    evidence["loop_id"] = "mutated-loop"
    evidence["goal"] = "mutated goal"
    evidence["verifier_verdict"] = "RED"  # contradicts GREEN attempt
    evidence["candidate_lineage"]["prior_evidence_sha256"] = "f" * 64
    _dump(evidence_path, evidence)
    _rehash_evidence(root, evidence_path, state)

    # Outer evidence hash now matches mutated file; semantic verify must still fail.
    assert _verify_only(root).returncode != 0
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode != 0


def test_inner_lineage_mutation_on_candidate_fails(tmp_path: Path):
    root = tmp_path / "cand-mut"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0
    state = _load(root / "state" / "loop.json")
    artifact = root / "work" / "candidate-attempt-002.json"
    cand = _load(artifact)
    cand["prior_rejection_evidence"]["evidence_sha256"] = "e" * 64
    cand["job_id"] = "mutated"
    _dump(artifact, cand)
    # Keep state artifact_sha256 wrong first — also fails. Recompute outer hashes to isolate semantic check.
    new_art = _sha256(artifact)
    state["attempts"][1]["artifact_sha256"] = new_art
    evidence_path = root / "attempt-evidence" / "attempt-002.json"
    evidence = _load(evidence_path)
    evidence["artifact_sha256"] = new_art
    _dump(evidence_path, evidence)
    _rehash_evidence(root, evidence_path, state)
    assert _verify_only(root).returncode != 0


@pytest.mark.parametrize(
    "mutator",
    [
        "minimal",
        "stale_bundle_hash",
        "wrong_artifact",
        "wrong_contract",
        "wrong_verdict",
    ],
)
def test_forged_receipts_fail(tmp_path: Path, mutator: str):
    root = tmp_path / f"receipt-{mutator}"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0
    receipt_path = root / "outcome" / "looptimal-receipt.json"
    receipt = _load(receipt_path)
    lineage_path = root / "outcome" / "src" / "lineage.json"

    if mutator == "minimal":
        _dump(receipt_path, {"kind": "looptimal-receipt", "verdict": "GREEN"})
    elif mutator == "stale_bundle_hash":
        receipt["evidence_bundle_sha256"] = "0" * 64
        _dump(receipt_path, receipt)
    elif mutator == "wrong_artifact":
        lineage = _load(lineage_path)
        lineage["accepted_artifact_sha256"] = "1" * 64
        _dump(lineage_path, lineage)
        # Receipt still points at old bundle hash — either path fails.
    elif mutator == "wrong_contract":
        receipt["contract_hash"] = "2" * 64
        _dump(receipt_path, receipt)
    elif mutator == "wrong_verdict":
        receipt["verdict"] = "RED"
        _dump(receipt_path, receipt)
    else:
        raise AssertionError(mutator)

    assert _verify_only(root).returncode != 0
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode != 0


def test_source_pin_binds_git_object_not_only_working_tree(tmp_path: Path):
    """Pin hashes must match git show <commit>:<path>, not merely whatever is on disk."""
    root = tmp_path / "git-bind"
    assert _run_demo("--mode", "accept", "--root", str(root)).returncode == 0
    pin = _load(root / "source-pin.json")
    commit = pin["immutable_ref"]
    for entry in pin["sources"]:
        assert entry["sha256"] == _git_blob_sha256(commit, entry["path"])
