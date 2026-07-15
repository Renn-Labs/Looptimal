#!/usr/bin/env bash
# run_demo.sh — deterministic offline first-30-minutes teaching demo.
#
# Default: controlled RED → durable state → resume → ACCEPTED → product receipt.
# Modes: accept | exhaust | block
# Never mutates tracked files; all evidence is written under --root (tmpdir default).
# Stdlib + bash only. No network.
#
# Governance: this script is a controlled maker/verifier *demonstration*. Its
# embedded subprocess is not the independent product approval authority;
# independent review happens outside this demo.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
export FIRST30_REPO_ROOT="${FIRST30_REPO_ROOT:-$REPO_ROOT}"
export FIRST30_EXAMPLE_DIR="${FIRST30_EXAMPLE_DIR:-$SCRIPT_DIR}"

exec python3 - "$SCRIPT_DIR" "$@" <<'PY'
"""First-30-minutes demo engine (embedded; stdlib only; offline)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
FULL_OID_RE = re.compile(r"^[0-9a-f]{40}$")
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


def git_run(*args: str, binary: bool = False) -> subprocess.CompletedProcess[Any]:
    """Local git object inspection only — never network operations."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_TRACE") and k not in {"http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"}
    }
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["LC_ALL"] = "C"
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=not binary,
        check=False,
        env=env,
    )


def resolve_head_commit_tree() -> tuple[str, str]:
    commit_proc = git_run("rev-parse", "--verify", "HEAD^{commit}")
    if commit_proc.returncode != 0:
        raise BlockedError(
            "unable to resolve local HEAD commit for immutable source pin "
            f"({(commit_proc.stderr or commit_proc.stdout or '').strip()})"
        )
    commit = str(commit_proc.stdout).strip()
    if not FULL_OID_RE.fullmatch(commit):
        raise BlockedError(f"HEAD did not resolve to a full commit object id: {commit!r}")
    tree_proc = git_run("rev-parse", "--verify", f"{commit}^{{tree}}")
    if tree_proc.returncode != 0:
        raise BlockedError("unable to resolve local HEAD tree object for source pin")
    tree = str(tree_proc.stdout).strip()
    if not FULL_OID_RE.fullmatch(tree):
        raise BlockedError(f"HEAD tree did not resolve to a full object id: {tree!r}")
    return commit, tree


def git_object_exists(oid: str, obj_type: str) -> bool:
    if not FULL_OID_RE.fullmatch(oid):
        return False
    probe = git_run("cat-file", "-t", oid)
    if probe.returncode != 0:
        return False
    return str(probe.stdout).strip() == obj_type


def git_blob_bytes(commit: str, relpath: str) -> bytes:
    proc = git_run("show", f"{commit}:{relpath}", binary=True)
    if proc.returncode != 0:
        raise BlockedError(f"unresolved source in pinned commit: {relpath}")
    assert isinstance(proc.stdout, (bytes, bytearray))
    return bytes(proc.stdout)


def build_source_pin(
    *,
    drop_source: bool = False,
    force_main: bool = False,
    omit_ref: bool = False,
    immutable_ref: str | None = None,
) -> dict[str, Any]:
    sources: list[dict[str, str]] = []
    commit: str | None = None
    tree: str | None = None

    if force_main:
        # Explicit forbidden label — verification must reject, never resolve to main tip.
        pin_ref = "main"
    elif omit_ref:
        pin_ref = None
    elif immutable_ref is not None:
        pin_ref = immutable_ref
    else:
        commit, tree = resolve_head_commit_tree()
        pin_ref = commit

    if commit is not None and tree is not None and not force_main and not omit_ref:
        for rel in PINNED_RELPATHS:
            blob = git_blob_bytes(commit, rel)
            sources.append({"path": rel, "sha256": sha256_bytes(blob)})
    else:
        # Incomplete pins (block/main tests) still declare paths but must not invent content.
        for rel in PINNED_RELPATHS:
            path = REPO_ROOT / rel
            if path.is_file() and not path.is_symlink():
                sources.append({"path": rel, "sha256": sha256_file(path)})
            else:
                sources.append({"path": rel, "sha256": "0" * 64})

    if drop_source and sources:
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
        "immutable_ref_kind": "git_commit",
    }
    if pin_ref is not None:
        pin["immutable_ref"] = pin_ref
    if tree is not None and not force_main and not omit_ref:
        pin["immutable_tree"] = tree
    return pin


def verify_source_pin(pin: dict[str, Any]) -> None:
    if not isinstance(pin, dict):
        raise BlockedError("missing or unresolved source pin; refusing silent main fallback")
    ref = pin.get("immutable_ref")
    if not isinstance(ref, str) or not ref.strip():
        raise BlockedError("missing or unresolved source pin; refusing silent main fallback")
    ref = ref.strip()
    if ref == "main" or pin.get("forbidden_fallback") != "main":
        if ref == "main":
            raise BlockedError(
                "source pin resolves to forbidden fallback 'main'; refusing silent main"
            )
        if pin.get("forbidden_fallback") != "main":
            raise BlockedError("source pin must declare forbidden_fallback=main")

    if pin.get("claim_ceiling") != CLAIM_CEILING:
        raise BlockedError("source pin claim ceiling drifted")
    if pin.get("immutable_ref_kind") not in {None, "git_commit"}:
        raise BlockedError("source pin immutable_ref_kind must be git_commit")

    # Fail closed: only full local commit object IDs are accepted (no unchecked tags).
    if not FULL_OID_RE.fullmatch(ref):
        raise BlockedError(
            "source pin immutable_ref must be a full 40-char local git commit object id "
            f"(got {ref!r}); tag labels and branch names are not immutable boundaries"
        )
    if not git_object_exists(ref, "commit"):
        raise BlockedError(f"source pin immutable_ref commit object is absent locally: {ref}")

    tree = pin.get("immutable_tree")
    if not isinstance(tree, str) or not FULL_OID_RE.fullmatch(tree.strip()):
        raise BlockedError("source pin missing immutable_tree full object id")
    tree = tree.strip()
    if not git_object_exists(tree, "tree"):
        raise BlockedError(f"source pin immutable_tree object is absent locally: {tree}")

    expected_tree_proc = git_run("rev-parse", "--verify", f"{ref}^{{tree}}")
    if expected_tree_proc.returncode != 0:
        raise BlockedError("unable to resolve tree for pinned commit")
    if str(expected_tree_proc.stdout).strip() != tree:
        raise BlockedError("source pin immutable_tree does not match pinned commit tree")

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
        try:
            blob = git_blob_bytes(ref, rel)
        except BlockedError as exc:
            raise BlockedError(f"unresolved source: {rel}") from exc
        expected = entry.get("sha256")
        actual = sha256_bytes(blob)
        if expected != actual:
            raise BlockedError(f"source pin drift against pinned git object: {rel}")


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

    # Attempt 1 deliberately omits lineage — a concrete defect the verifier rejects.
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
        # Concrete induced defect: attempt 1 has no prior-rejection lineage binding.
        return "RED", CONTROLLED_RED_REASON

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
    """Write a non-ACCEPTED terminal, or ACCEPTED only when receipt is already validated."""
    state["status"] = status
    state["stop"] = {"reason": reason, "attempt": attempt}
    atomic_json(state_path, state)
    write_state_md(run_root, state)
    terminal = {
        "schema_version": 1,
        "loop_id": LOOP_ID,
        "goal": GOAL,
        "status": status,
        "reason": reason,
        "attempt": attempt,
        "claim_ceiling": CLAIM_CEILING,
        "wall_time_measured": False,
        "elapsed_seconds": None,
        "attempt_count": len(prior_completed_attempts(state)),
    }
    if status == "ACCEPTED":
        attempts = prior_completed_attempts(state)
        if attempts:
            terminal["accepted_attempt"] = attempts[-1].get("attempt")
            terminal["accepted_artifact_sha256"] = attempts[-1].get("artifact_sha256")
            terminal["accepted_evidence_sha256"] = attempts[-1].get("evidence_sha256")
            if len(attempts) >= 1:
                terminal["prior_red_evidence_sha256"] = attempts[0].get("evidence_sha256")
    atomic_json(run_root / "terminal.json", terminal)
    print(json.dumps({"status": status, "reason": reason, "attempt": attempt}, sort_keys=True))
    return TERMINAL_EXIT[status]


def build_outcome_materials(run_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    """Build sealed outcome materials for verify-outcome. Does not mark ACCEPTED."""
    attempts = prior_completed_attempts(state)
    if len(attempts) < 2 or attempts[0].get("status") != "RED":
        raise ContractError("ACCEPTED path must retain the deliberate RED attempt")
    if attempts[-1].get("status") != "GREEN":
        raise ContractError("ACCEPTED path requires a final GREEN attempt")
    prior_sha = attempts[0].get("evidence_sha256")
    if not isinstance(prior_sha, str) or len(prior_sha) != 64:
        raise ContractError("ACCEPTED path missing attempt-1 evidence hash")
    green = attempts[-1]
    green_art = green.get("artifact_sha256")
    green_ev = green.get("evidence_sha256")
    if not isinstance(green_art, str) or not isinstance(green_ev, str):
        raise ContractError("ACCEPTED path missing GREEN attempt digests")

    outcome = run_root / "outcome"
    if outcome.exists() and state.get("status") != "ACCEPTED":
        # Rebuild from a prior failed commit attempt.
        shutil.rmtree(outcome)
    sealed = outcome / "sealed"
    src = outcome / "src"
    sealed.mkdir(parents=True, exist_ok=True)
    src.mkdir(parents=True, exist_ok=True)

    lineage_doc = {
        "prior_attempt_evidence_sha256": prior_sha,
        "accepted_attempt_evidence_sha256": green_ev,
        "accepted_artifact_sha256": green_art,
        "terminal": "ACCEPTED",
        "claim_ceiling": CLAIM_CEILING,
        "loop_id": LOOP_ID,
        "goal": GOAL,
        "verdict_sequence": [a.get("status") for a in attempts],
    }
    (src / "lineage.json").write_text(
        json.dumps(lineage_doc, indent=2, sort_keys=True) + "\n",
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
        "    and isinstance(data.get('accepted_attempt_evidence_sha256'), str)\n"
        "    and len(data['accepted_attempt_evidence_sha256']) == 64\n"
        "    and isinstance(data.get('accepted_artifact_sha256'), str)\n"
        "    and len(data['accepted_artifact_sha256']) == 64\n"
        "    and data.get('claim_ceiling') == 'INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF'\n"
        "    and data.get('loop_id') == 'first-30-minutes-lineage-close'\n"
        "    and data.get('verdict_sequence') == ['RED', 'GREEN']\n"
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
    return {
        "outcome": outcome,
        "bundle_path": bundle_path,
        "contract_hash": chash,
        "lineage_sha256": art_hash,
        "prior_sha": prior_sha,
        "green_evidence_sha256": green_ev,
        "green_artifact_sha256": green_art,
    }


def emit_outcome_receipt(run_root: Path, state: dict[str, Any]) -> Path:
    """Build and validate a complete receipt BEFORE any ACCEPTED terminal write."""
    if not VERIFY_OUTCOME.is_file():
        raise ContractError(f"product outcome verifier missing: {VERIFY_OUTCOME}")

    materials = build_outcome_materials(run_root, state)
    outcome: Path = materials["outcome"]
    bundle_path: Path = materials["bundle_path"]
    receipt_path = outcome / "looptimal-receipt.json"
    staging = outcome / f".looptimal-receipt.json.tmp-{os.getpid()}"

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
            str(staging),
        ],
        cwd=str(outcome),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={k: v for k, v in os.environ.items() if k != "LOOPTIMAL_FRAMER_KEY"},
        check=False,
    )
    if proc.returncode != 0:
        staging.unlink(missing_ok=True)
        raise ContractError(
            f"verify-outcome failed before ACCEPTED commit: {proc.stderr or proc.stdout}"
        )
    if not staging.is_file():
        raise ContractError("verify-outcome did not emit a staging receipt")

    receipt = load_object(staging, "staging outcome receipt")
    validate_receipt_object(
        receipt,
        run_root=run_root,
        state=state,
        materials=materials,
        receipt_path=staging,
    )
    # Only after full validation do we publish the receipt path used by ACCEPTED.
    os.replace(staging, receipt_path)
    return receipt_path


def validate_receipt_object(
    receipt: dict[str, Any],
    *,
    run_root: Path,
    state: dict[str, Any],
    materials: dict[str, Any] | None = None,
    receipt_path: Path | None = None,
) -> None:
    if receipt.get("kind") != "looptimal-receipt":
        raise ContractError("emitted receipt lacks kind=looptimal-receipt")
    if receipt.get("verdict") != "GREEN":
        raise ContractError("emitted receipt is not GREEN")
    if receipt.get("schema_version") != 1:
        raise ContractError("receipt schema_version invalid")
    criteria = receipt.get("criteria_passed")
    if not isinstance(criteria, list) or "c1" not in [str(c) for c in criteria]:
        raise ContractError("receipt missing required criterion c1")

    outcome = run_root / "outcome"
    bundle_ref = receipt.get("evidence_bundle_ref") or "bundle.json"
    bundle_path = outcome / str(bundle_ref)
    if not bundle_path.is_file():
        raise ContractError("receipt evidence bundle missing")
    bundle_sha = receipt.get("evidence_bundle_sha256")
    if bundle_sha != sha256_file(bundle_path):
        raise ContractError("receipt evidence_bundle_sha256 does not match bundle")

    contract_ref = receipt.get("contract_ref") or "sealed/contract.json"
    contract_path = outcome / str(contract_ref)
    if not contract_path.is_file():
        raise ContractError("receipt contract_ref missing")
    contract = load_object(contract_path, "outcome contract")
    chash = receipt.get("contract_hash")
    if not isinstance(chash, str) or not chash:
        raise ContractError("receipt missing contract_hash")
    # contract file may store sha256: prefix; receipt stores bare or prefixed.
    stored = contract.get("contract_hash")
    if isinstance(stored, str):
        bare_stored = stored.removeprefix("sha256:")
        bare_receipt = chash.removeprefix("sha256:")
        if bare_stored != bare_receipt:
            raise ContractError("receipt contract_hash does not match sealed contract")

    lineage_path = outcome / "src" / "lineage.json"
    if not lineage_path.is_file():
        raise ContractError("outcome lineage artifact missing")
    lineage = load_object(lineage_path, "outcome lineage")
    attempts = prior_completed_attempts(state)
    if not attempts:
        raise ContractError("receipt validation requires sealed attempts")
    if lineage.get("prior_attempt_evidence_sha256") != attempts[0].get("evidence_sha256"):
        raise ContractError("receipt lineage prior evidence digest mismatch")
    if lineage.get("loop_id") != LOOP_ID or lineage.get("goal") != GOAL:
        raise ContractError("receipt lineage loop/goal mismatch")
    if lineage.get("claim_ceiling") != CLAIM_CEILING:
        raise ContractError("receipt lineage claim ceiling mismatch")
    if lineage.get("terminal") != "ACCEPTED":
        raise ContractError("receipt lineage terminal is not ACCEPTED")
    if lineage.get("verdict_sequence") != [a.get("status") for a in attempts]:
        raise ContractError("receipt lineage verdict_sequence mismatch")
    if attempts[-1].get("status") == "GREEN":
        if lineage.get("accepted_attempt_evidence_sha256") != attempts[-1].get("evidence_sha256"):
            raise ContractError("receipt lineage accepted evidence digest mismatch")
        if lineage.get("accepted_artifact_sha256") != attempts[-1].get("artifact_sha256"):
            raise ContractError("receipt lineage accepted artifact digest mismatch")

    if materials is not None:
        if lineage.get("prior_attempt_evidence_sha256") != materials.get("prior_sha"):
            raise ContractError("receipt materials prior digest mismatch")
        if materials.get("lineage_sha256") != sha256_file(lineage_path):
            raise ContractError("lineage artifact hash drifted after write")

    # Live re-check through the product verifier when a published receipt path exists.
    if receipt_path is not None and receipt_path.name == "looptimal-receipt.json":
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
                f"live verify-outcome re-check failed: {proc.stderr or proc.stdout}"
            )


def commit_accepted(
    state: dict[str, Any],
    state_path: Path,
    run_root: Path,
    reason: str,
    attempt: int,
) -> int:
    """Transaction: validate full receipt first, then write ACCEPTED + terminal."""
    # Precondition: not yet ACCEPTED.
    if state.get("status") == "ACCEPTED":
        raise ContractError("commit_accepted called on already-ACCEPTED state")

    try:
        receipt_path = emit_outcome_receipt(run_root, state)
    except (ContractError, BlockedError, OSError, json.JSONDecodeError) as exc:
        # Failure before final commit: leave non-accepted recoverable state.
        if state.get("status") == "ACCEPTED":
            raise ContractError("internal error: ACCEPTED set before receipt success") from exc
        # Ensure no published receipt on failure.
        published = run_root / "outcome" / "looptimal-receipt.json"
        if published.is_file() and state.get("status") != "ACCEPTED":
            # Only remove if we never committed; staging failures should not leave ACCEPTED.
            pass
        raise ContractError(f"receipt generation failed; refusing ACCEPTED: {exc}") from exc

    if not receipt_path.is_file():
        raise ContractError("receipt missing after emit; refusing ACCEPTED")

    # Final commit: mutually consistent terminal + accepted state.
    code = set_terminal(state, state_path, run_root, "ACCEPTED", reason, attempt)
    # Re-validate post-commit consistency (receipt + terminal + state).
    try:
        assert_run_consistent(run_root, expected_status="ACCEPTED")
    except (ContractError, BlockedError) as exc:
        raise ContractError(f"post-commit consistency failed: {exc}") from exc
    print(
        json.dumps(
            {
                "outcome_receipt": "outcome/looptimal-receipt.json",
                "note": "emitted only via scripts/verify-outcome.py before ACCEPTED commit",
            },
            sort_keys=True,
        )
    )
    return code


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
        "loop_id": LOOP_ID,
        "goal": GOAL,
        "claim_ceiling": CLAIM_CEILING,
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

    completed_before = [
        a for a in state.get("attempts") or [] if isinstance(a, dict) and a.get("status") in {"RED", "GREEN", "BLOCKED"}
    ]
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
        "candidate_lineage": {
            "prior_attempt_count": max(0, attempt_number - 1),
            "prior_evidence_sha256": (
                completed_before[-1].get("evidence_sha256") if completed_before else None
            ),
            "verdict_sequence_prefix": [a.get("status") for a in completed_before] + [verdict],
        },
        "verifier_contract": {
            "mode": mode,
            "external_gate": "embedded-subprocess-demonstration-not-independent-authority",
            "product_receipt_gate": "scripts/verify-outcome.py",
        },
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
            "loop_id": LOOP_ID,
            "goal": GOAL,
            "claim_ceiling": CLAIM_CEILING,
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


def validate_attempt_semantics(run_root: Path, state: dict[str, Any]) -> None:
    """Semantic (not merely outer-hash) validation of attempt evidence + artifacts."""
    if state.get("loop_id") != LOOP_ID:
        raise ContractError("state loop_id mismatch")
    if state.get("goal") != GOAL:
        raise ContractError("state goal mismatch")
    if state.get("claim_ceiling") != CLAIM_CEILING:
        raise ContractError("state claim_ceiling mismatch")

    attempts = state.get("attempts")
    if not isinstance(attempts, list):
        raise ContractError("attempts is not a list")

    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, dict):
            raise ContractError(f"attempt record {index} invalid")
        status = attempt.get("status")
        if status == "STARTED":
            raise ContractError("in-flight STARTED attempt is not sealed")
        if status not in {"RED", "GREEN", "BLOCKED"}:
            raise ContractError(f"attempt {index} has invalid status {status!r}")

        if attempt.get("loop_id") not in {None, LOOP_ID}:
            # Older records may omit; when present must match.
            raise ContractError(f"attempt {index} loop_id mismatch")
        if attempt.get("goal") not in {None, GOAL}:
            raise ContractError(f"attempt {index} goal mismatch")
        if attempt.get("claim_ceiling") not in {None, CLAIM_CEILING}:
            raise ContractError(f"attempt {index} claim_ceiling mismatch")

        evidence_rel = attempt.get("evidence_path")
        if not isinstance(evidence_rel, str):
            raise ContractError(f"attempt {index} missing evidence_path")
        evidence_path = run_root / evidence_rel
        if not evidence_path.is_file():
            raise ContractError(f"missing {evidence_rel}")
        if sha256_file(evidence_path) != attempt.get("evidence_sha256"):
            raise ContractError(f"hash mismatch for {evidence_rel}")

        evidence = load_object(evidence_path, evidence_rel)
        if evidence.get("kind") != "attempt-evidence":
            raise ContractError(f"{evidence_rel} is not attempt-evidence")
        if evidence.get("kind") == "looptimal-receipt":
            raise ContractError("attempt evidence collides with outcome receipt kind")
        if evidence.get("loop_id") != LOOP_ID:
            raise ContractError(f"{evidence_rel} loop_id mismatch")
        if evidence.get("goal") != GOAL:
            raise ContractError(f"{evidence_rel} goal mismatch")
        if evidence.get("claim_ceiling") != CLAIM_CEILING:
            raise ContractError(f"{evidence_rel} claim_ceiling mismatch")
        if evidence.get("attempt") != attempt.get("attempt"):
            raise ContractError(f"{evidence_rel} attempt number mismatch")
        if evidence.get("verifier_verdict") != status:
            raise ContractError(f"{evidence_rel} verdict does not match sealed attempt status")
        if evidence.get("verifier_reason") != attempt.get("reason"):
            raise ContractError(f"{evidence_rel} reason does not match sealed attempt")
        if evidence.get("artifact_sha256") != attempt.get("artifact_sha256"):
            raise ContractError(f"{evidence_rel} artifact digest mismatch vs state")
        if evidence.get("not_an_outcome_receipt") is not True:
            raise ContractError(f"{evidence_rel} must declare not_an_outcome_receipt")

        artifact_rel = attempt.get("artifact_path")
        if not isinstance(artifact_rel, str):
            raise ContractError(f"attempt {index} missing artifact_path")
        artifact_path = run_root / artifact_rel
        if not artifact_path.is_file():
            raise ContractError(f"missing {artifact_rel}")
        if sha256_file(artifact_path) != attempt.get("artifact_sha256"):
            raise ContractError(f"artifact hash mismatch for {artifact_rel}")
        if sha256_file(artifact_path) != evidence.get("artifact_sha256"):
            raise ContractError(f"artifact hash mismatch vs evidence for {artifact_rel}")

        candidate = load_object(artifact_path, artifact_rel)
        if candidate.get("job_id") != LOOP_ID:
            raise ContractError(f"{artifact_rel} job_id mismatch")
        if candidate.get("claim_ceiling") != CLAIM_CEILING:
            raise ContractError(f"{artifact_rel} claim_ceiling mismatch")
        if candidate.get("attempt") != attempt.get("attempt"):
            raise ContractError(f"{artifact_rel} attempt number mismatch")

        lineage = evidence.get("candidate_lineage")
        if not isinstance(lineage, dict):
            raise ContractError(f"{evidence_rel} missing candidate_lineage binding")
        if lineage.get("prior_attempt_count") != max(0, int(attempt.get("attempt") or 0) - 1):
            raise ContractError(f"{evidence_rel} prior_attempt_count mismatch")
        prefix = lineage.get("verdict_sequence_prefix")
        if not isinstance(prefix, list) or not prefix or prefix[-1] != status:
            raise ContractError(f"{evidence_rel} verdict_sequence_prefix invalid")

        # Cross-attempt lineage for attempt >= 2
        if int(attempt.get("attempt") or 0) >= 2:
            prior = attempts[index - 1] if index >= 1 else None
            if not isinstance(prior, dict) or prior.get("status") != "RED":
                raise ContractError("attempt >=2 must follow a sealed RED")
            if lineage.get("prior_evidence_sha256") != prior.get("evidence_sha256"):
                raise ContractError(f"{evidence_rel} prior_evidence_sha256 mismatch")
            prior_bind = candidate.get("prior_rejection_evidence")
            if not isinstance(prior_bind, dict):
                raise ContractError(f"{artifact_rel} missing prior_rejection_evidence")
            if prior_bind.get("evidence_sha256") != prior.get("evidence_sha256"):
                raise ContractError(f"{artifact_rel} prior rejection digest mismatch")
            if prior_bind.get("verdict") != "RED":
                raise ContractError(f"{artifact_rel} prior rejection verdict mismatch")


def validate_terminal_document(run_root: Path, state: dict[str, Any]) -> None:
    status = state.get("status")
    if status not in TERMINAL_EXIT:
        raise ContractError(f"non-terminal status {status!r} has no valid terminal document requirement")
    terminal_path = run_root / "terminal.json"
    if not terminal_path.is_file():
        raise ContractError("terminal.json missing for terminal status")
    terminal = load_object(terminal_path, "terminal")
    if terminal.get("status") != status:
        raise ContractError("terminal.json status does not match state")
    if terminal.get("loop_id") != LOOP_ID:
        raise ContractError("terminal.json loop_id mismatch")
    if terminal.get("goal") not in {None, GOAL}:
        raise ContractError("terminal.json goal mismatch")
    if terminal.get("claim_ceiling") != CLAIM_CEILING:
        raise ContractError("terminal.json claim_ceiling mismatch")
    stop = state.get("stop")
    if not isinstance(stop, dict):
        raise ContractError("terminal state missing stop record")
    if terminal.get("reason") != stop.get("reason"):
        raise ContractError("terminal reason drifted from state.stop")
    if terminal.get("attempt") != stop.get("attempt"):
        raise ContractError("terminal attempt drifted from state.stop")
    if status == "ACCEPTED":
        attempts = prior_completed_attempts(state)
        if len(attempts) < 2:
            raise ContractError("ACCEPTED terminal requires RED then GREEN attempts")
        if [a.get("status") for a in attempts] != ["RED", "GREEN"]:
            raise ContractError("ACCEPTED verdict sequence must be RED then GREEN")
        if terminal.get("accepted_evidence_sha256") not in {
            None,
            attempts[-1].get("evidence_sha256"),
        }:
            # Prefer binding when present
            if terminal.get("accepted_evidence_sha256") != attempts[-1].get("evidence_sha256"):
                raise ContractError("terminal accepted_evidence_sha256 mismatch")
        if terminal.get("prior_red_evidence_sha256") not in {
            None,
            attempts[0].get("evidence_sha256"),
        }:
            if terminal.get("prior_red_evidence_sha256") != attempts[0].get("evidence_sha256"):
                raise ContractError("terminal prior_red_evidence_sha256 mismatch")


def assert_run_consistent(run_root: Path, *, expected_status: str | None = None) -> None:
    """Complete fail-closed verifier over pin, state, attempts, terminal, receipt."""
    run_root = run_root.resolve()
    state_path = run_root / "state" / "loop.json"
    pin_path = run_root / "source-pin.json"
    if not state_path.is_file():
        raise ContractError("missing state/loop.json")
    if not pin_path.is_file():
        raise BlockedError("missing source-pin.json")

    pin = load_object(pin_path, "source pin")
    verify_source_pin(pin)

    state = load_object(state_path, "state")
    status = state.get("status")
    if expected_status is not None and status != expected_status:
        raise ContractError(f"expected status {expected_status}, got {status}")

    if status in {"READY", "RUNNING"}:
        raise ContractError(f"verify-only rejects non-terminal status {status}")

    if status not in TERMINAL_EXIT:
        raise ContractError(f"unknown status {status!r}")

    validate_attempt_semantics(run_root, state)
    validate_terminal_document(run_root, state)

    receipt = run_root / "outcome" / "looptimal-receipt.json"
    if status == "ACCEPTED":
        if not receipt.is_file():
            raise ContractError("ACCEPTED run missing outcome receipt")
        data = load_object(receipt, "outcome receipt")
        validate_receipt_object(data, run_root=run_root, state=state, receipt_path=receipt)
    else:
        if receipt.exists():
            raise ContractError("non-ACCEPTED run must not have looptimal-receipt.json")
        # EXHAUSTED must be two REDs; BLOCKED may have zero attempts
        attempts = prior_completed_attempts(state)
        if status == "EXHAUSTED":
            if not attempts or any(a.get("status") != "RED" for a in attempts):
                raise ContractError("EXHAUSTED requires only RED attempts")
            if len(attempts) != MAX_ATTEMPTS:
                raise ContractError("EXHAUSTED attempt count mismatch")
        if status == "BLOCKED" and attempts:
            # Allowed to have attempts that ended BLOCKED, but no GREEN.
            if any(a.get("status") == "GREEN" for a in attempts):
                raise ContractError("BLOCKED run must not contain GREEN attempts")


def try_commit_green_if_pending(
    run_root: Path,
    state: dict[str, Any],
    state_path: Path,
) -> int | None:
    """If a GREEN attempt is sealed but ACCEPTED was not committed, finish the transaction."""
    if state.get("status") in TERMINAL_EXIT:
        return None
    completed = prior_completed_attempts(state)
    if not completed or completed[-1].get("status") != "GREEN":
        return None
    reason = str(completed[-1].get("reason") or "honest resume preserves RED attempt evidence and state lineage")
    attempt_number = int(completed[-1].get("attempt") or len(completed))
    return commit_accepted(state, state_path, run_root, reason, attempt_number)


def execute(run_root: Path, mode: str) -> int:
    run_root = run_root.resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    state_path = run_root / "state" / "loop.json"
    pin_path = run_root / "source-pin.json"

    # Terminal idempotency: existing terminal is untrusted input — full verify.
    if state_path.is_file():
        state = load_object(state_path, "state")
        status = state.get("status")
        if status in TERMINAL_EXIT:
            try:
                assert_run_consistent(run_root, expected_status=status)
            except BlockedError as exc:
                print(
                    json.dumps(
                        {
                            "status": "BLOCKED",
                            "reason": str(exc),
                            "idempotent_rerun": True,
                            "accepted": False,
                        },
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 3
            except ContractError as exc:
                print(
                    json.dumps(
                        {
                            "status": "RED",
                            "reason": str(exc),
                            "idempotent_rerun": True,
                            "accepted": False,
                        },
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 1
            print(
                json.dumps(
                    {
                        "status": status,
                        "stop": state.get("stop"),
                        "idempotent_rerun": True,
                        "attempt_count": len(state.get("attempts") or []),
                        "verified": True,
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
        shutil.copyfile(EXAMPLE_DIR / "state.md", run_root / "state.md")

    # Source pin: explicit full commit object id, fail closed, never silent main.
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
        return set_terminal(
            state,
            state_path,
            run_root,
            "BLOCKED",
            "block mode requires an unresolved source pin",
            None,
        )

    # Resume a GREEN-but-not-committed run (receipt failure recovery path).
    try:
        pending = try_commit_green_if_pending(run_root, state, state_path)
        if pending is not None:
            return pending
    except ContractError as exc:
        print(
            json.dumps({"status": "CONTRACT_ERROR", "reason": str(exc)}, sort_keys=True),
            file=sys.stderr,
        )
        return 64

    while len(state["attempts"]) < MAX_ATTEMPTS:
        # If a prior GREEN is somehow present, commit rather than overshoot.
        try:
            pending = try_commit_green_if_pending(run_root, state, state_path)
            if pending is not None:
                return pending
        except ContractError as exc:
            print(
                json.dumps({"status": "CONTRACT_ERROR", "reason": str(exc)}, sort_keys=True),
                file=sys.stderr,
            )
            return 64

        attempt_number = len(state["attempts"]) + 1
        verdict, reason = run_attempt(
            run_root=run_root,
            state=state,
            state_path=state_path,
            mode=mode,
            attempt_number=attempt_number,
        )
        if verdict == "GREEN":
            try:
                return commit_accepted(state, state_path, run_root, reason, attempt_number)
            except ContractError as exc:
                print(
                    json.dumps(
                        {"status": "CONTRACT_ERROR", "reason": str(exc)},
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                # Leave non-accepted state (READY with GREEN attempt sealed).
                return 64
        if verdict == "BLOCKED":
            return set_terminal(
                state, state_path, run_root, "BLOCKED", reason, attempt_number
            )
        # RED → continue until budget exhausts

    # Final GREEN pending? (should have returned above)
    try:
        pending = try_commit_green_if_pending(run_root, state, state_path)
        if pending is not None:
            return pending
    except ContractError as exc:
        print(
            json.dumps({"status": "CONTRACT_ERROR", "reason": str(exc)}, sort_keys=True),
            file=sys.stderr,
        )
        return 64

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
    try:
        state_path = run_root / "state" / "loop.json"
        if not state_path.is_file():
            print("verify-only: RED — missing state/loop.json", file=sys.stderr)
            return 1
        state = load_object(state_path, "state")
        status = state.get("status")
        assert_run_consistent(run_root)
        # BLOCKED terminals report exit 3 per verify.sh contract.
        if status == "BLOCKED":
            print(
                json.dumps(
                    {
                        "verdict": "GREEN",
                        "status": status,
                        "attempts": len(state.get("attempts") or []),
                        "note": "BLOCKED terminal consistent; install-level checks are separate",
                    },
                    sort_keys=True,
                )
            )
            return 3
        print(
            json.dumps(
                {
                    "verdict": "GREEN",
                    "status": status,
                    "attempts": len(state.get("attempts") or []),
                    "note": "lineage consistent; install-level checks are separate",
                },
                sort_keys=True,
            )
        )
        return 0
    except BlockedError as exc:
        print(f"verify-only: BLOCKED — {exc}", file=sys.stderr)
        return 3
    except ContractError as exc:
        print(f"verify-only: RED — {exc}", file=sys.stderr)
        return 1


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
