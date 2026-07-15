#!/usr/bin/env bash
# run_demo.sh — deterministic offline first-30-minutes teaching demo.
#
# Default: authentic RED → durable state → resume → ACCEPTED → product receipt.
# Modes: accept | exhaust | block
# Never mutates tracked files; all evidence is written under --root (tmpdir default).
# Stdlib + bash only. No network.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
export FIRST30_REPO_ROOT="${FIRST30_REPO_ROOT:-$REPO_ROOT}"
export FIRST30_EXAMPLE_DIR="${FIRST30_EXAMPLE_DIR:-$SCRIPT_DIR}"

exec python3 - "$SCRIPT_DIR" "$@" <<'PY'
"""First-30-minutes demo engine (embedded; stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

EXAMPLE_DIR = Path(sys.argv[1]).resolve()
REPO_ROOT = Path(os.environ.get("FIRST30_REPO_ROOT", EXAMPLE_DIR.parent.parent)).resolve()
VERIFY_OUTCOME = REPO_ROOT / "scripts" / "verify-outcome.py"

LOOP_ID = "first-30-minutes-lineage-close"
GOAL = (
    "A controlled first attempt is rejected by an external check, the rejection "
    "is recorded in durable state, and the next attempt either binds that "
    "attempt evidence honestly (ACCEPTED), exhausts the retry budget without "
    "inventing a pass (EXHAUSTED), or stops on a missing/unresolved source pin "
    "without fabricating progress (BLOCKED)."
)
MAX_ATTEMPTS = 2
CLAIM_CEILING = "INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF"
CONTROLLED_RED_REASON = (
    "controlled rejection: prior rejection attempt evidence lineage is absent"
)
FORGED_LINEAGE_RED_REASON = "first attempt cannot claim prior rejection lineage"
EXHAUST_RED_REASON = (
    "source URL is missing and may not be invented: DEMO-SRC-002"
)
PINNED_RELPATHS = [
    "examples/first-30-minutes/README.md",
    "examples/first-30-minutes/loop-spec.yaml",
    "examples/first-30-minutes/state.md",
    "examples/first-30-minutes/verify.sh",
    "examples/first-30-minutes/run_demo.sh",
]
TERMINAL_EXIT = {"ACCEPTED": 0, "EXHAUSTED": 2, "BLOCKED": 3}
FORBIDDEN_CLAIM_SNIPPETS = (
    "product market fit",
    "product-market fit",
    "customer accepted",
    "production ready",
    "verified corpus",
    "hosted service",
    "marketplace",
    "completed in 30 minutes",
)


class BlockedError(Exception):
    """Fail-closed stop before or during the loop."""


class ContractError(Exception):
    """Definition or runtime contract violation."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def create_once_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"{label} is not readable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be a JSON object")
    return value


def build_source_pin(
    *,
    immutable_ref: str = "v2.2.0",
    drop_source: bool = False,
    force_main: bool = False,
    omit_ref: bool = False,
) -> dict[str, Any]:
    sources: list[dict[str, str]] = []
    for rel in PINNED_RELPATHS:
        path = REPO_ROOT / rel
        if not path.is_file() or path.is_symlink():
            raise BlockedError(f"unresolved source: {rel}")
        sources.append({"path": rel, "sha256": sha256_file(path)})
    if drop_source and sources:
        # Keep the path declaration but point at a non-existent file so the pin
        # is explicit yet unresolvable — fail closed, never invent content.
        sources[0] = {
            "path": "examples/first-30-minutes/DOES-NOT-EXIST.pin",
            "sha256": "0" * 64,
        }
    pin: dict[str, Any] = {
        "schema_version": 1,
        "packet_id": "first-30-minutes",
        "claim_ceiling": CLAIM_CEILING,
        "forbidden_fallback": "main",
        "sources": sources,
        "scope_interpretation": "instructional_budget_not_observed_duration",
        "wall_time_measured": False,
        "elapsed_seconds": None,
        "intended_operator_budget_minutes": 30,
    }
    if force_main:
        pin["immutable_ref"] = "main"
    elif not omit_ref:
        pin["immutable_ref"] = immutable_ref
    # omit_ref leaves immutable_ref absent → unresolved
    return pin


def verify_source_pin(pin: dict[str, Any]) -> None:
    if not isinstance(pin, dict):
        raise BlockedError("missing or unresolved source pin; refusing silent main fallback")
    ref = pin.get("immutable_ref")
    if not isinstance(ref, str) or not ref.strip():
        raise BlockedError("missing or unresolved source pin; refusing silent main fallback")
    if ref.strip() == "main":
        raise BlockedError(
            "source pin resolves to forbidden fallback 'main'; refusing silent main"
        )
    if pin.get("forbidden_fallback") != "main":
        raise BlockedError("source pin must declare forbidden_fallback=main")
    if pin.get("claim_ceiling") != CLAIM_CEILING:
        raise BlockedError("source pin claim ceiling drifted")
    sources = pin.get("sources")
    if not isinstance(sources, list) or not sources:
        raise BlockedError("source pin has no sources")
    seen: set[str] = set()
    for index, entry in enumerate(sources):
        if not isinstance(entry, dict):
            raise BlockedError(f"source pin entry {index} is invalid")
        rel = entry.get("path")
        if not isinstance(rel, str) or not rel or rel in seen:
            raise BlockedError(f"source pin entry {index} path missing or duplicated")
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise BlockedError(f"source pin entry {index} path escapes the repository")
        seen.add(rel)
        path = REPO_ROOT / rel
        if not path.is_file() or path.is_symlink():
            raise BlockedError(f"unresolved source: {rel}")
        expected = entry.get("sha256")
        actual = sha256_file(path)
        if expected != actual:
            raise BlockedError(f"source pin drift: {rel}")


def new_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "loop_id": LOOP_ID,
        "goal": GOAL,
        "status": "READY",
        "attempts": [],
        "stop": None,
        "claim_ceiling": CLAIM_CEILING,
        "max_attempts": MAX_ATTEMPTS,
    }


def write_state_md(run_root: Path, state: dict[str, Any]) -> None:
    lines = [
        "# Loop state — first-30-minutes (run root)",
        "",
        "> Durable record for this run. Append-only until terminal.",
        "",
        f"- **Goal:** {GOAL}",
        f"- **Status:** {state.get('status')}",
        f"- **Claim ceiling:** {CLAIM_CEILING}",
        f"- **Attempts:** {len(state.get('attempts') or [])}",
        "",
        "## Vocabulary",
        "",
        "- Install / doctor verdict ≠ attempt evidence ≠ verifier verdict ≠ accepted outcome receipt",
        "- Attempt evidence kind is `attempt-evidence`, never `looptimal-receipt`",
        "",
        "## Iteration log",
        "",
        "| # | verdict | reason | evidence sha256 |",
        "|-|-|-|-|",
    ]
    for attempt in state.get("attempts") or []:
        if not isinstance(attempt, dict):
            continue
        lines.append(
            "| {n} | {v} | {r} | `{h}` |".format(
                n=attempt.get("attempt"),
                v=attempt.get("status"),
                r=str(attempt.get("reason", ""))[:80],
                h=str(attempt.get("evidence_sha256", ""))[:16],
            )
        )
    stop = state.get("stop")
    if isinstance(stop, dict):
        lines.extend(
            [
                "",
                "## Terminal",
                "",
                f"- status: `{state.get('status')}`",
                f"- reason: {stop.get('reason')}",
                f"- attempt: {stop.get('attempt')}",
            ]
        )
    lines.append("")
    (run_root / "state.md").write_text("\n".join(lines), encoding="utf-8")


def prior_completed_attempts(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return sealed attempts only (exclude the in-flight STARTED record)."""
    out: list[dict[str, Any]] = []
    for item in state.get("attempts") or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") in {"RED", "GREEN", "BLOCKED"}:
            out.append(item)
    return out


def make_candidate(
    *,
    attempt: int,
    mode: str,
    state: dict[str, Any],
    run_root: Path,
) -> dict[str, Any]:
    prior_evidence: dict[str, Any] | None = None
    if attempt >= 2:
        completed = prior_completed_attempts(state)
        if len(completed) < 1:
            raise ContractError("resume requires attempt-one state")
        prior = completed[-1]
        if prior.get("status") != "RED":
            raise ContractError("prior durable attempt is not RED")
        evidence_rel = prior.get("evidence_path")
        if not isinstance(evidence_rel, str):
            raise ContractError("prior attempt missing evidence_path")
        evidence_path = (run_root / evidence_rel).resolve()
        evidence_path.relative_to(run_root.resolve())
        if not evidence_path.is_file():
            raise ContractError("prior attempt evidence missing on disk")
        evidence = load_object(evidence_path, "prior attempt evidence")
        if evidence.get("kind") != "attempt-evidence":
            raise ContractError("prior artifact is not attempt evidence")
        if evidence.get("kind") == "looptimal-receipt":
            raise ContractError("prior artifact must not be an outcome receipt")
        prior_evidence = {
            "attempt": prior.get("attempt"),
            "evidence_path": evidence_rel,
            "evidence_sha256": prior.get("evidence_sha256"),
            "verdict": evidence.get("verifier_verdict"),
            "reason": evidence.get("verifier_reason"),
        }

    # Attempt 1 deliberately omits lineage (authentic controlled RED).
    # Attempt 2 binds lineage. Exhaust mode keeps a non-inventable defect.
    candidate: dict[str, Any] = {
        "schema_version": 1,
        "job_id": LOOP_ID,
        "attempt": attempt,
        "claim_ceiling": CLAIM_CEILING,
        "classification": "instructional_demo_not_product_proof",
        "authority": {
            "action_executed": False,
            "external_authority_delta": 0,
            "external_demand_delta": 0,
        },
        "prior_rejection_evidence": prior_evidence if attempt >= 2 else None,
        "state_lineage": {
            "attempt": attempt,
            "prior_attempt_count": max(0, attempt - 1),
        },
    }
    if mode == "exhaust":
        # Even with lineage, a required source URL stays missing and must not be invented.
        candidate["sources"] = [
            {"source_id": "DEMO-SRC-001", "url": "https://example.invalid/demo"},
            {"source_id": "DEMO-SRC-002", "url": None},
        ]
    else:
        candidate["sources"] = [
            {"source_id": "DEMO-SRC-001", "url": "https://example.invalid/demo"},
        ]
    return candidate


def verify_candidate(
    candidate: dict[str, Any],
    *,
    attempt: int,
    mode: str,
    state: dict[str, Any],
    run_root: Path,
    artifact_path: Path,
    artifact_sha256: str,
) -> tuple[str, str]:
    if sha256_file(artifact_path) != artifact_sha256:
        return "BLOCKED", "artifact changed after the runner hashed it"
    if candidate.get("job_id") != LOOP_ID:
        return "BLOCKED", "candidate job_id does not match the frozen loop id"
    if candidate.get("claim_ceiling") != CLAIM_CEILING:
        return "BLOCKED", "claim ceiling drifted"
    if candidate.get("classification") != "instructional_demo_not_product_proof":
        return "RED", "candidate is not explicitly instructional"
    authority = candidate.get("authority")
    if not isinstance(authority, dict) or authority.get("action_executed") is not False:
        return "BLOCKED", "candidate claims an external action"
    if authority.get("external_authority_delta") != 0 or authority.get("external_demand_delta") != 0:
        return "BLOCKED", "candidate moves external authority or demand counters"

    prior = candidate.get("prior_rejection_evidence")
    if attempt == 1:
        if prior is not None:
            return "RED", FORGED_LINEAGE_RED_REASON
        return "RED", CONTROLLED_RED_REASON

    # attempt >= 2 — read sealed prior attempts only (ignore in-flight STARTED).
    completed = prior_completed_attempts(state)
    if len(completed) < 1:
        return "RED", "attempt 2 did not find durable prior attempt state"
    prior_attempt = completed[-1]
    evidence_rel = prior_attempt.get("evidence_path")
    if not isinstance(evidence_rel, str):
        return "RED", "durable prior attempt lacks evidence_path"
    evidence_path = (run_root / evidence_rel).resolve()
    try:
        evidence_path.relative_to(run_root.resolve())
    except ValueError:
        return "BLOCKED", "prior evidence path escapes the run root"
    if not evidence_path.is_file():
        return "RED", "prior attempt evidence file is missing"
    evidence = load_object(evidence_path, "prior attempt evidence")
    if evidence.get("kind") != "attempt-evidence":
        return "RED", "prior artifact is not attempt evidence"
    if not isinstance(prior, dict):
        return "RED", "attempt 2 did not carry durable prior rejection evidence"
    if prior.get("evidence_sha256") != sha256_file(evidence_path):
        return "RED", "prior rejection evidence hash is not exact"
    if prior.get("evidence_sha256") != prior_attempt.get("evidence_sha256"):
        return "RED", "prior rejection evidence hash does not match durable state"
    if prior.get("verdict") != "RED" or prior.get("reason") != evidence.get("verifier_reason"):
        return "RED", "prior rejection verdict or reason does not match sealed attempt evidence"
    lineage = candidate.get("state_lineage")
    if not isinstance(lineage, dict) or lineage.get("prior_attempt_count") != 1:
        return "RED", "attempt 2 does not bind a single prior attempt in lineage"

    if mode == "exhaust":
        sources = candidate.get("sources")
        if not isinstance(sources, list):
            return "RED", "sources missing on exhaust path"
        missing = [
            item.get("source_id")
            for item in sources
            if isinstance(item, dict) and not item.get("url")
        ]
        if missing:
            return "RED", f"source URL is missing and may not be invented: {missing[0]}"
        return "RED", EXHAUST_RED_REASON

    return "GREEN", "honest resume preserves RED attempt evidence and state lineage"


def set_terminal(
    state: dict[str, Any],
    state_path: Path,
    run_root: Path,
    status: str,
    reason: str,
    attempt: int | None,
) -> int:
    state["status"] = status
    state["stop"] = {"reason": reason, "attempt": attempt}
    atomic_json(state_path, state)
    write_state_md(run_root, state)
    terminal = {
        "schema_version": 1,
        "loop_id": LOOP_ID,
        "status": status,
        "reason": reason,
        "attempt": attempt,
        "claim_ceiling": CLAIM_CEILING,
        "wall_time_measured": False,
        "elapsed_seconds": None,
    }
    atomic_json(run_root / "terminal.json", terminal)
    print(json.dumps({"status": status, "reason": reason, "attempt": attempt}, sort_keys=True))
    return TERMINAL_EXIT[status]


def emit_outcome_receipt(run_root: Path, state: dict[str, Any]) -> None:
    """Only ACCEPTED may call the product outcome verifier and write a receipt."""
    if state.get("status") != "ACCEPTED":
        raise ContractError("outcome receipt requires ACCEPTED terminal")
    if not VERIFY_OUTCOME.is_file():
        raise ContractError(f"product outcome verifier missing: {VERIFY_OUTCOME}")

    attempts = state.get("attempts") or []
    if len(attempts) < 2 or attempts[0].get("status") != "RED":
        raise ContractError("ACCEPTED path must retain the deliberate RED attempt")
    prior_sha = attempts[0].get("evidence_sha256")
    if not isinstance(prior_sha, str) or not prior_sha:
        raise ContractError("ACCEPTED path missing attempt-1 evidence hash")

    outcome = run_root / "outcome"
    sealed = outcome / "sealed"
    src = outcome / "src"
    sealed.mkdir(parents=True, exist_ok=True)
    src.mkdir(parents=True, exist_ok=True)

    (src / "lineage.json").write_text(
        json.dumps(
            {
                "prior_attempt_evidence_sha256": prior_sha,
                "terminal": "ACCEPTED",
                "claim_ceiling": CLAIM_CEILING,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (sealed / "check.py").write_text(
        "import json, pathlib, sys\n"
        "p = pathlib.Path('src/lineage.json')\n"
        "if not p.is_file():\n"
        "    sys.exit(1)\n"
        "data = json.loads(p.read_text(encoding='utf-8'))\n"
        "ok = (\n"
        "    data.get('terminal') == 'ACCEPTED'\n"
        "    and isinstance(data.get('prior_attempt_evidence_sha256'), str)\n"
        "    and len(data['prior_attempt_evidence_sha256']) == 64\n"
        "    and data.get('claim_ceiling') == 'INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF'\n"
        ")\n"
        "sys.exit(0 if ok else 1)\n",
        encoding="utf-8",
    )
    objective = (
        "the accepted first-30-minutes resume binds the deliberate RED attempt "
        "evidence hash without inventing demand or authority"
    )
    contract: dict[str, Any] = {
        "schema_version": 1,
        "objective": objective,
        "acceptance_suite": {
            "provenance": "framer",
            "sealed_path": "sealed/suite.json",
            "criteria": [
                {
                    "id": "c1",
                    "asserts": "outcome",
                    "oracle": "repro",
                    "external_check": ["python3", "sealed/check.py"],
                    "green_means": "lineage file binds the RED attempt evidence hash",
                }
            ],
        },
        "irreversibles": [],
    }
    # Unkeyed contract hash (stdlib): matches verify-outcome's unkeyed mode.
    # Import the product helper so the hash algorithm cannot drift.
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from _common import canonical_contract_hash  # type: ignore

    contract_path = sealed / "contract.json"
    chash = canonical_contract_hash(contract)
    contract["contract_hash"] = "sha256:" + chash
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outcome / "mission.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contract_ref": "sealed/contract.json",
                "capability_manifest": {"demo": {"allowed_paths": ["src/"]}},
                "lanes": [{"id": "L1", "archetype": "task"}],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    art_hash = sha256_file(src / "lineage.json")
    bundle = {
        "contract_ref": "sealed/contract.json",
        "accepted_plan_ref": "mission.json",
        "contract_hash": chash,
        "artifacts": [{"path": "src/lineage.json", "sha256": art_hash}],
        "tool_receipts": [
            {"cmd": "first-30-minutes-demo", "exit": 0, "stdout_sha": art_hash, "ts": "t"}
        ],
        "acceptance_results": [
            {"criterion": "c1", "passed_by": "external_rerun", "value": "pass"}
        ],
        "final_state_assertion": "src/lineage.json binds the deliberate RED attempt evidence",
        "unresolved_risks": [],
        "persisted_state_update_ref": "mission.json",
    }
    bundle_path = outcome / "bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    receipt_path = outcome / "looptimal-receipt.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(VERIFY_OUTCOME),
            "--bundle",
            str(bundle_path),
            "--workdir",
            str(outcome),
            "--repeat",
            "1",
            "--receipt",
            str(receipt_path),
        ],
        cwd=str(outcome),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={k: v for k, v in os.environ.items() if k != "LOOPTIMAL_FRAMER_KEY"},
        check=False,
    )
    if proc.returncode != 0:
        raise ContractError(
            f"verify-outcome failed on ACCEPTED path: {proc.stderr or proc.stdout}"
        )
    if not receipt_path.is_file():
        raise ContractError("ACCEPTED path did not emit looptimal-receipt.json")
    receipt = load_object(receipt_path, "outcome receipt")
    if receipt.get("kind") != "looptimal-receipt":
        raise ContractError("emitted receipt lacks kind=looptimal-receipt")
    if receipt.get("verdict") != "GREEN":
        raise ContractError("emitted receipt is not GREEN")


def run_attempt(
    *,
    run_root: Path,
    state: dict[str, Any],
    state_path: Path,
    mode: str,
    attempt_number: int,
) -> tuple[str, str]:
    workdir = run_root / "work"
    evidence_dir = run_root / "attempt-evidence"
    workdir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    prior_state_sha256 = sha256_file(state_path) if state_path.is_file() else None
    attempt_record: dict[str, Any] = {
        "attempt": attempt_number,
        "status": "STARTED",
        "prior_state_sha256": prior_state_sha256,
    }
    state["attempts"].append(attempt_record)
    state["status"] = "RUNNING"
    atomic_json(state_path, state)

    candidate = make_candidate(
        attempt=attempt_number, mode=mode, state=state, run_root=run_root
    )
    artifact_name = f"candidate-attempt-{attempt_number:03d}.json"
    artifact_path = workdir / artifact_name
    with artifact_path.open("x", encoding="utf-8") as handle:
        json.dump(candidate, handle, indent=2, sort_keys=True)
        handle.write("\n")
    artifact_sha256 = sha256_file(artifact_path)

    # Re-load candidate from disk so the verifier path matches product practice
    # (checker reads the artifact the maker wrote, not an in-memory twin).
    on_disk = load_object(artifact_path, "candidate artifact")
    verdict, reason = verify_candidate(
        on_disk,
        attempt=attempt_number,
        mode=mode,
        state=state,
        run_root=run_root,
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
    )
    if verdict not in {"GREEN", "RED", "BLOCKED"}:
        raise ContractError(f"invalid verifier verdict: {verdict}")

    evidence = {
        "schema_version": 1,
        "kind": "attempt-evidence",  # never looptimal-receipt
        "loop_id": LOOP_ID,
        "goal": GOAL,
        "attempt": attempt_number,
        "prior_state_sha256": prior_state_sha256,
        "artifact_path": f"work/{artifact_name}",
        "artifact_sha256": artifact_sha256,
        "verifier_verdict": verdict,
        "verifier_reason": reason,
        "claim_ceiling": CLAIM_CEILING,
        "not_an_outcome_receipt": True,
    }
    evidence_path = evidence_dir / f"attempt-{attempt_number:03d}.json"
    create_once_json(evidence_path, evidence)
    evidence_sha256 = sha256_file(evidence_path)

    attempt_record.update(
        {
            "status": verdict,
            "reason": reason,
            "evidence_path": f"attempt-evidence/attempt-{attempt_number:03d}.json",
            "evidence_sha256": evidence_sha256,
            "artifact_path": f"work/{artifact_name}",
            "artifact_sha256": artifact_sha256,
        }
    )
    state["status"] = "READY"
    atomic_json(state_path, state)
    write_state_md(run_root, state)
    print(
        json.dumps(
            {
                "attempt": attempt_number,
                "verdict": verdict,
                "reason": reason,
                "evidence_sha256": evidence_sha256,
            },
            sort_keys=True,
        )
    )
    return verdict, reason


def execute(run_root: Path, mode: str) -> int:
    run_root = run_root.resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    state_path = run_root / "state" / "loop.json"
    pin_path = run_root / "source-pin.json"

    # Terminal idempotency: re-entering a finished run creates no new attempts.
    if state_path.is_file():
        state = load_object(state_path, "state")
        status = state.get("status")
        if status in TERMINAL_EXIT:
            print(
                json.dumps(
                    {
                        "status": status,
                        "stop": state.get("stop"),
                        "idempotent_rerun": True,
                        "attempt_count": len(state.get("attempts") or []),
                    },
                    sort_keys=True,
                )
            )
            return TERMINAL_EXIT[status]
        if status == "RUNNING":
            return set_terminal(
                state,
                state_path,
                run_root,
                "BLOCKED",
                "prior attempt has no sealed terminal evidence; inspect before resuming",
                len(state.get("attempts") or []),
            )
    else:
        state = new_state()
        atomic_json(state_path, state)
        # Seed human-readable state from the committed template once.
        shutil.copyfile(EXAMPLE_DIR / "state.md", run_root / "state.md")

    # Source pin: explicit, fail closed, never silent main.
    if not pin_path.exists():
        if mode == "block":
            pin = build_source_pin(omit_ref=True)
        else:
            pin = build_source_pin()
        create_once_json(pin_path, pin)
    else:
        pin = load_object(pin_path, "source pin")

    try:
        verify_source_pin(pin)
    except BlockedError as exc:
        return set_terminal(state, state_path, run_root, "BLOCKED", str(exc), None)

    if mode == "block":
        # Mode requests a blocked terminal via unresolved pin; if the pin was
        # already valid (resume), still refuse to invent attempts.
        return set_terminal(
            state,
            state_path,
            run_root,
            "BLOCKED",
            "block mode requires an unresolved source pin",
            None,
        )

    while len(state["attempts"]) < MAX_ATTEMPTS:
        attempt_number = len(state["attempts"]) + 1
        verdict, reason = run_attempt(
            run_root=run_root,
            state=state,
            state_path=state_path,
            mode=mode,
            attempt_number=attempt_number,
        )
        if verdict == "GREEN":
            code = set_terminal(
                state, state_path, run_root, "ACCEPTED", reason, attempt_number
            )
            emit_outcome_receipt(run_root, state)
            print(
                json.dumps(
                    {
                        "outcome_receipt": "outcome/looptimal-receipt.json",
                        "note": "emitted only via scripts/verify-outcome.py after ACCEPTED",
                    },
                    sort_keys=True,
                )
            )
            return code
        if verdict == "BLOCKED":
            return set_terminal(
                state, state_path, run_root, "BLOCKED", reason, attempt_number
            )
        # RED → continue until budget exhausts

    return set_terminal(
        state,
        state_path,
        run_root,
        "EXHAUSTED",
        f"maximum attempts reached ({MAX_ATTEMPTS}) without acceptance",
        len(state["attempts"]),
    )


def verify_only(run_root: Path) -> int:
    """External re-check of an existing run root (used by verify.sh)."""
    run_root = run_root.resolve()
    state_path = run_root / "state" / "loop.json"
    pin_path = run_root / "source-pin.json"
    if not state_path.is_file():
        print("verify-only: RED — missing state/loop.json", file=sys.stderr)
        return 1
    if not pin_path.is_file():
        print("verify-only: BLOCKED — missing source-pin.json", file=sys.stderr)
        return 3
    try:
        pin = load_object(pin_path, "source pin")
        verify_source_pin(pin)
    except BlockedError as exc:
        print(f"verify-only: BLOCKED — {exc}", file=sys.stderr)
        return 3
    except ContractError as exc:
        print(f"verify-only: RED — {exc}", file=sys.stderr)
        return 1

    state = load_object(state_path, "state")
    status = state.get("status")
    attempts = state.get("attempts") or []
    if not isinstance(attempts, list):
        print("verify-only: RED — attempts is not a list", file=sys.stderr)
        return 1

    for attempt in attempts:
        if not isinstance(attempt, dict):
            print("verify-only: RED — attempt record invalid", file=sys.stderr)
            return 1
        rel = attempt.get("evidence_path")
        if not isinstance(rel, str):
            print("verify-only: RED — attempt missing evidence_path", file=sys.stderr)
            return 1
        path = run_root / rel
        if not path.is_file():
            print(f"verify-only: RED — missing {rel}", file=sys.stderr)
            return 1
        if sha256_file(path) != attempt.get("evidence_sha256"):
            print(f"verify-only: RED — hash mismatch for {rel}", file=sys.stderr)
            return 1
        evidence = load_object(path, rel)
        if evidence.get("kind") != "attempt-evidence":
            print(f"verify-only: RED — {rel} is not attempt-evidence", file=sys.stderr)
            return 1
        if evidence.get("kind") == "looptimal-receipt":
            print(f"verify-only: RED — attempt evidence collides with outcome receipt kind", file=sys.stderr)
            return 1

    receipt = run_root / "outcome" / "looptimal-receipt.json"
    if status == "ACCEPTED":
        if not receipt.is_file():
            print("verify-only: RED — ACCEPTED run missing outcome receipt", file=sys.stderr)
            return 1
        data = load_object(receipt, "outcome receipt")
        if data.get("kind") != "looptimal-receipt" or data.get("verdict") != "GREEN":
            print("verify-only: RED — outcome receipt invalid", file=sys.stderr)
            return 1
    else:
        if receipt.exists():
            print(
                "verify-only: RED — non-ACCEPTED run must not have looptimal-receipt.json",
                file=sys.stderr,
            )
            return 1

    print(
        json.dumps(
            {
                "verdict": "GREEN",
                "status": status,
                "attempts": len(attempts),
                "note": "lineage consistent; install-level checks are separate",
            },
            sort_keys=True,
        )
    )
    return 0


def assert_no_forbidden_claims() -> None:
    text = (EXAMPLE_DIR / "README.md").read_text(encoding="utf-8").lower()
    for snippet in FORBIDDEN_CLAIM_SNIPPETS:
        if snippet in text:
            raise ContractError(f"README contains forbidden claim language: {snippet}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        help="Run-state root (created if missing). Defaults to a fresh temp dir.",
    )
    parser.add_argument(
        "--mode",
        choices=("accept", "exhaust", "block"),
        default="accept",
        help="accept=RED then GREEN; exhaust=RED then RED; block=unresolved pin",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Re-check an existing run root; do not create attempts.",
    )
    parser.add_argument(
        "--print-root",
        action="store_true",
        help="Print the run root path on stdout as a final line.",
    )
    args = parser.parse_args(argv)

    try:
        assert_no_forbidden_claims()
        if args.verify_only:
            if args.root is None:
                raise ContractError("--verify-only requires --root")
            return verify_only(args.root)

        if args.root is None:
            run_root = Path(tempfile.mkdtemp(prefix="first30-"))
        else:
            run_root = args.root
            run_root.mkdir(parents=True, exist_ok=True)

        # For block mode on a fresh root, write an unresolved pin first.
        if args.mode == "block" and not (run_root / "source-pin.json").exists():
            create_once_json(run_root / "source-pin.json", build_source_pin(omit_ref=True))
            state_path = run_root / "state" / "loop.json"
            if not state_path.exists():
                atomic_json(state_path, new_state())
                shutil.copyfile(EXAMPLE_DIR / "state.md", run_root / "state.md")

        code = execute(run_root, args.mode)
        if args.print_root or args.root is None:
            print(json.dumps({"run_root": str(run_root.resolve())}, sort_keys=True))
        return code
    except BlockedError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 3
    except ContractError as exc:
        print(json.dumps({"status": "CONTRACT_ERROR", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 64


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[2:]))
PY
