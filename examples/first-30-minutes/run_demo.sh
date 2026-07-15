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
    "A controlled first attempt is rejected by an external check because its "
    "source_manifest_sha256 does not match the digest recomputed from the "
    "immutable source pin, the rejection is recorded in durable state, and the "
    "next attempt either repairs that invariant and binds the prior RED evidence "
    "(ACCEPTED), exhausts the retry budget without inventing a pass (EXHAUSTED), "
    "or stops on a missing/unresolved source pin without fabricating progress "
    "(BLOCKED)."
)
MAX_ATTEMPTS = 2
CLAIM_CEILING = "INSTRUCTIONAL_DEMO_NOT_PRODUCT_PROOF"
STALE_CANDIDATE_PATH = EXAMPLE_DIR / "stale-candidate.json"
# Prefix for the invariant-driven first RED (reason names concrete digests).
STALE_MANIFEST_RED_PREFIX = "source_manifest_sha256 mismatch:"
EXHAUST_RED_REASON = (
    "source URL is missing and may not be invented: DEMO-SRC-002"
)
PINNED_RELPATHS = [
    "examples/first-30-minutes/README.md",
    "examples/first-30-minutes/loop-spec.yaml",
    "examples/first-30-minutes/state.md",
    "examples/first-30-minutes/verify.sh",
    "examples/first-30-minutes/run_demo.sh",
    "examples/first-30-minutes/stale-candidate.json",
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


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def compute_source_manifest_digest(pin: dict[str, Any]) -> str:
    """Recomputable digest over the immutable pin identity used by candidates.

    Internal run provenance only — not a claim of external cryptographic authorship.
    """
    if not isinstance(pin, dict):
        raise ContractError("source pin required to compute source_manifest_sha256")
    ref = pin.get("immutable_ref")
    tree = pin.get("immutable_tree")
    sources = pin.get("sources")
    if not isinstance(ref, str) or not FULL_OID_RE.fullmatch(ref.strip()):
        raise ContractError("source_manifest_sha256 requires a full-commit immutable_ref")
    if not isinstance(tree, str) or not FULL_OID_RE.fullmatch(tree.strip()):
        raise ContractError("source_manifest_sha256 requires a full-tree immutable_tree")
    if not isinstance(sources, list) or not sources:
        raise ContractError("source_manifest_sha256 requires a non-empty sources list")
    normalized_sources = []
    for entry in sources:
        if not isinstance(entry, dict):
            raise ContractError("source pin entry invalid for manifest digest")
        path = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise ContractError("source pin entry missing path/sha256 for manifest digest")
        normalized_sources.append({"path": path, "sha256": digest})
    normalized_sources.sort(key=lambda item: item["path"])
    payload = {
        "claim_ceiling": pin.get("claim_ceiling"),
        "immutable_ref": ref.strip(),
        "immutable_tree": tree.strip(),
        "packet_id": pin.get("packet_id"),
        "sources": normalized_sources,
    }
    return sha256_bytes(canonical_json_bytes(payload))


def source_pin_file_digest(run_root: Path) -> str:
    pin_path = run_root / "source-pin.json"
    if not pin_path.is_file():
        raise ContractError("source-pin.json missing for provenance binding")
    return sha256_file(pin_path)


def load_stale_candidate_fixture() -> dict[str, Any]:
    if not STALE_CANDIDATE_PATH.is_file():
        raise ContractError(f"missing stale candidate fixture: {STALE_CANDIDATE_PATH}")
    fixture = load_object(STALE_CANDIDATE_PATH, "stale candidate fixture")
    digest = fixture.get("source_manifest_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ContractError("stale candidate fixture lacks a 64-char source_manifest_sha256")
    if fixture.get("fixture_kind") != "stale-source-manifest":
        raise ContractError("stale candidate fixture_kind must be stale-source-manifest")
    return fixture


def derive_stop_cause_kind(
    status: str, reason: str, attempt: int | None, attempt_count: int
) -> str:
    if status == "ACCEPTED":
        return "accepted_after_red_green_lineage"
    if status == "EXHAUSTED":
        return "retry_budget_exhausted"
    if status == "BLOCKED":
        if attempt_count == 0 or attempt is None:
            return "source_pin_failure"
        return "attempt_blocked"
    raise ContractError(f"unknown terminal status for stop cause: {status}")


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
    """Build a candidate artifact.

    First sealed attempt uses the committed stale-candidate fixture digest
    (wrong source_manifest_sha256). After a durable RED, the candidate carries
    the recomputed correct digest and binds prior rejection evidence.
    """
    pin = load_object(run_root / "source-pin.json", "source pin")
    correct_digest = compute_source_manifest_digest(pin)
    completed = prior_completed_attempts(state)
    prior_evidence: dict[str, Any] | None = None

    if not completed:
        # Frozen inspectable defect: wrong source-manifest digest from fixture.
        fixture = load_stale_candidate_fixture()
        manifest_digest = str(fixture["source_manifest_sha256"])
        if manifest_digest == correct_digest:
            raise ContractError(
                "stale candidate fixture digest accidentally matches live pin; "
                "fixture must remain a stable mismatch"
            )
    else:
        prior = completed[-1]
        if prior.get("status") != "RED":
            raise ContractError("resume requires a durable prior RED attempt")
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
        # Repair the same invariant the first RED named.
        manifest_digest = correct_digest

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
        "source_manifest_sha256": manifest_digest,
        "prior_rejection_evidence": prior_evidence,
        "state_lineage": {
            "attempt": attempt,
            "prior_attempt_count": len(completed),
        },
    }
    if mode == "exhaust":
        # Exhaust keeps a second independently recomputable defect after the first RED.
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
    """Same invariant checks for every attempt — no attempt-number RED branch."""
    del attempt  # attempt number is not a verifier branch; state + artifact decide
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

    pin = load_object(run_root / "source-pin.json", "source pin")
    try:
        expected_manifest = compute_source_manifest_digest(pin)
    except ContractError as exc:
        return "BLOCKED", f"unable to recompute source_manifest_sha256: {exc}"

    claimed = candidate.get("source_manifest_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        return "RED", "candidate missing source_manifest_sha256"
    if claimed != expected_manifest:
        return (
            "RED",
            f"{STALE_MANIFEST_RED_PREFIX} candidate has {claimed}, "
            f"recomputed from source pin is {expected_manifest}",
        )

    prior = candidate.get("prior_rejection_evidence")
    completed = prior_completed_attempts(state)

    if not completed:
        # No durable prior RED: claiming prior rejection evidence is forged.
        if prior is not None:
            return "RED", "prior_rejection_evidence present without durable prior RED"
    else:
        prior_attempt = completed[-1]
        if prior_attempt.get("status") != "RED":
            return "RED", "durable prior attempt is not RED"
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
            return "RED", "candidate did not carry durable prior rejection evidence"
        if prior.get("evidence_sha256") != sha256_file(evidence_path):
            return "RED", "prior rejection evidence hash is not exact"
        if prior.get("evidence_sha256") != prior_attempt.get("evidence_sha256"):
            return "RED", "prior rejection evidence hash does not match durable state"
        if prior.get("verdict") != "RED" or prior.get("reason") != evidence.get("verifier_reason"):
            return "RED", "prior rejection verdict or reason does not match sealed attempt evidence"
        lineage = candidate.get("state_lineage")
        if not isinstance(lineage, dict) or lineage.get("prior_attempt_count") != len(completed):
            return "RED", "candidate state_lineage prior_attempt_count does not match durable state"

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

    # Correct manifest (+ prior RED binding when required) is the GREEN invariant.
    if completed:
        return "GREEN", "honest resume preserves RED attempt evidence and repaired source_manifest_sha256"
    return "GREEN", "source_manifest_sha256 matches recomputed source pin digest"


def set_terminal(
    state: dict[str, Any],
    state_path: Path,
    run_root: Path,
    status: str,
    reason: str,
    attempt: int | None,
) -> int:
    """Write a non-ACCEPTED terminal, or ACCEPTED only when receipt is already validated.

    Every terminal binds the exact source-pin file digest and a derivable stop cause.
    This is internal run provenance under CLAIM_CEILING — not external authorship.
    """
    completed = prior_completed_attempts(state)
    pin_path = run_root / "source-pin.json"
    if not pin_path.is_file():
        raise ContractError("refusing terminal without source-pin.json")
    pin = load_object(pin_path, "source pin")
    pin_sha = sha256_file(pin_path)
    manifest_sha: str | None
    try:
        manifest_sha = compute_source_manifest_digest(pin)
    except ContractError:
        # Incomplete/invalid pins (zero-attempt BLOCKED) have no full manifest digest.
        manifest_sha = None

    state["status"] = status
    state["stop"] = {
        "reason": reason,
        "attempt": attempt,
        "source_pin_sha256": pin_sha,
        "source_manifest_sha256": manifest_sha,
        "stop_cause_kind": derive_stop_cause_kind(status, reason, attempt, len(completed)),
    }
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
        "attempt_count": len(completed),
        "source_pin_sha256": pin_sha,
        "source_manifest_sha256": manifest_sha,
        "stop_cause_kind": state["stop"]["stop_cause_kind"],
        "provenance_note": "internal_run_provenance_not_external_authorship",
    }
    if status == "ACCEPTED":
        attempts = completed
        if attempts:
            terminal["accepted_attempt"] = attempts[-1].get("attempt")
            terminal["accepted_artifact_sha256"] = attempts[-1].get("artifact_sha256")
            terminal["accepted_evidence_sha256"] = attempts[-1].get("evidence_sha256")
            if len(attempts) >= 1:
                terminal["prior_red_evidence_sha256"] = attempts[0].get("evidence_sha256")
    elif status == "EXHAUSTED":
        terminal["red_evidence_sha256s"] = [
            a.get("evidence_sha256") for a in completed if a.get("status") == "RED"
        ]
    elif status == "BLOCKED" and completed:
        last = completed[-1]
        terminal["blocked_attempt"] = last.get("attempt")
        terminal["blocked_evidence_sha256"] = last.get("evidence_sha256")
        terminal["blocked_artifact_sha256"] = last.get("artifact_sha256")
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
        # Explicitly remove any uncommitted published receipt — no masking pass.
        published = run_root / "outcome" / "looptimal-receipt.json"
        if published.is_file():
            published.unlink()
        staging_dir = run_root / "outcome"
        if staging_dir.is_dir():
            for leftover in staging_dir.glob(".looptimal-receipt.json.tmp-*"):
                leftover.unlink(missing_ok=True)
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
        # Recompute the same source-manifest invariant the live verifier used.
        pin = load_object(run_root / "source-pin.json", "source pin")
        expected_manifest = compute_source_manifest_digest(pin)
        claimed_manifest = candidate.get("source_manifest_sha256")
        if status == "RED" and isinstance(attempt.get("reason"), str) and attempt["reason"].startswith(
            STALE_MANIFEST_RED_PREFIX
        ):
            if claimed_manifest == expected_manifest:
                raise ContractError(
                    f"{artifact_rel} claims RED for source_manifest mismatch but digest matches pin"
                )
        elif status in {"GREEN", "RED", "BLOCKED"}:
            # GREEN must match; non-manifest REDs (exhaust) must also carry the correct digest.
            if status == "GREEN" and claimed_manifest != expected_manifest:
                raise ContractError(f"{artifact_rel} GREEN source_manifest_sha256 mismatch")
            if status == "RED" and not (
                isinstance(attempt.get("reason"), str)
                and attempt["reason"].startswith(STALE_MANIFEST_RED_PREFIX)
            ):
                if claimed_manifest != expected_manifest:
                    raise ContractError(
                        f"{artifact_rel} non-manifest RED must still carry correct source_manifest_sha256"
                    )

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

    pin_sha = source_pin_file_digest(run_root)
    if terminal.get("source_pin_sha256") != pin_sha:
        raise ContractError("terminal source_pin_sha256 does not match source-pin.json")
    if stop.get("source_pin_sha256") not in {None, pin_sha}:
        if stop.get("source_pin_sha256") != pin_sha:
            raise ContractError("state.stop source_pin_sha256 does not match source-pin.json")
    if terminal.get("source_pin_sha256") != stop.get("source_pin_sha256"):
        # When stop lacks the field (legacy), require terminal binding only; else exact match.
        if stop.get("source_pin_sha256") is not None:
            raise ContractError("terminal/state source_pin_sha256 binding mismatch")

    expected_kind = derive_stop_cause_kind(
        status,
        str(terminal.get("reason") or ""),
        terminal.get("attempt") if isinstance(terminal.get("attempt"), int) or terminal.get("attempt") is None else None,
        len(prior_completed_attempts(state)),
    )
    if terminal.get("stop_cause_kind") != expected_kind:
        raise ContractError(
            f"terminal stop_cause_kind {terminal.get('stop_cause_kind')!r} "
            f"does not match derivable cause {expected_kind!r}"
        )
    if stop.get("stop_cause_kind") not in {None, expected_kind}:
        if stop.get("stop_cause_kind") != expected_kind:
            raise ContractError("state.stop stop_cause_kind does not match terminal")

    pin = load_object(run_root / "source-pin.json", "source pin")
    try:
        manifest_sha = compute_source_manifest_digest(pin)
    except ContractError:
        manifest_sha = None
    if terminal.get("source_manifest_sha256") != manifest_sha:
        raise ContractError("terminal source_manifest_sha256 does not match recomputed pin digest")
    if stop.get("source_manifest_sha256") not in {None, manifest_sha}:
        if stop.get("source_manifest_sha256") != manifest_sha:
            raise ContractError("state.stop source_manifest_sha256 mismatch")

    attempts = prior_completed_attempts(state)
    if status == "ACCEPTED":
        if len(attempts) < 2:
            raise ContractError("ACCEPTED terminal requires RED then GREEN attempts")
        if [a.get("status") for a in attempts] != ["RED", "GREEN"]:
            raise ContractError("ACCEPTED verdict sequence must be RED then GREEN")
        if terminal.get("accepted_evidence_sha256") != attempts[-1].get("evidence_sha256"):
            raise ContractError("terminal accepted_evidence_sha256 mismatch")
        if terminal.get("accepted_artifact_sha256") != attempts[-1].get("artifact_sha256"):
            raise ContractError("terminal accepted_artifact_sha256 mismatch")
        if terminal.get("prior_red_evidence_sha256") != attempts[0].get("evidence_sha256"):
            raise ContractError("terminal prior_red_evidence_sha256 mismatch")
        if manifest_sha is None:
            raise ContractError("ACCEPTED requires a complete source_manifest_sha256")
    elif status == "EXHAUSTED":
        if len(attempts) != MAX_ATTEMPTS or any(a.get("status") != "RED" for a in attempts):
            raise ContractError("EXHAUSTED requires two independently sealed RED attempts")
        reds = terminal.get("red_evidence_sha256s")
        expected_reds = [a.get("evidence_sha256") for a in attempts]
        if reds != expected_reds:
            raise ContractError("EXHAUSTED terminal red_evidence_sha256s mismatch")
    elif status == "BLOCKED":
        if not attempts:
            # Zero-attempt BLOCKED: reason must match independently recomputed pin failure.
            if terminal.get("attempt") is not None:
                raise ContractError("zero-attempt BLOCKED must not bind an attempt number")
            try:
                verify_source_pin(pin)
            except BlockedError as pin_exc:
                if str(pin_exc) != terminal.get("reason") or str(pin_exc) != stop.get("reason"):
                    raise ContractError(
                        "zero-attempt BLOCKED reason does not match recomputed source-pin failure"
                    ) from pin_exc
            else:
                raise ContractError(
                    "zero-attempt BLOCKED with a valid source pin is not a trusted terminal"
                )
        else:
            last = attempts[-1]
            if last.get("status") != "BLOCKED":
                raise ContractError("attempt-backed BLOCKED requires a sealed BLOCKED attempt")
            if last.get("reason") != terminal.get("reason") or last.get("reason") != stop.get("reason"):
                raise ContractError("attempt-backed BLOCKED reason does not match sealed attempt")
            if terminal.get("blocked_evidence_sha256") != last.get("evidence_sha256"):
                raise ContractError("attempt-backed BLOCKED evidence binding mismatch")
            if terminal.get("blocked_artifact_sha256") != last.get("artifact_sha256"):
                raise ContractError("attempt-backed BLOCKED artifact binding mismatch")
            if terminal.get("attempt") != last.get("attempt"):
                raise ContractError("attempt-backed BLOCKED attempt binding mismatch")
            # Pin must still be valid for attempt-backed blocked paths.
            verify_source_pin(pin)


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
    state = load_object(state_path, "state")
    status = state.get("status")
    if expected_status is not None and status != expected_status:
        raise ContractError(f"expected status {expected_status}, got {status}")

    if status in {"READY", "RUNNING"}:
        raise ContractError(f"verify-only rejects non-terminal status {status}")

    if status not in TERMINAL_EXIT:
        raise ContractError(f"unknown status {status!r}")

    # ACCEPTED / EXHAUSTED require a valid pin up front. BLOCKED may have an
    # invalid pin (zero-attempt) — validate_terminal_document re-derives that.
    if status in {"ACCEPTED", "EXHAUSTED"}:
        verify_source_pin(pin)
    elif status == "BLOCKED":
        attempts = prior_completed_attempts(state)
        if attempts:
            # Attempt-backed BLOCKED still requires a valid pin + sealed attempt.
            verify_source_pin(pin)
            if any(a.get("status") == "GREEN" for a in attempts):
                raise ContractError("BLOCKED run must not contain GREEN attempts")
        # else: pin failure is reproduced inside validate_terminal_document

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
        attempts = prior_completed_attempts(state)
        if status == "EXHAUSTED":
            if not attempts or any(a.get("status") != "RED" for a in attempts):
                raise ContractError("EXHAUSTED requires only RED attempts")
            if len(attempts) != MAX_ATTEMPTS:
                raise ContractError("EXHAUSTED attempt count mismatch")


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
