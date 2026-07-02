#!/usr/bin/env python3
"""verify-outcome.py — Looptimal Stage 6: the OUTER, checker-owned outcome verifier.

It is deliberately hostile to the maker. Given only an evidence bundle, it:
  * loads the SEALED contract the bundle points at (it does NOT accept a maker-supplied
    contract) and refuses if that contract is not on a sealed, executor-unwritable path;
  * recomputes the canonical contract hash and FAILs on any mismatch (goal drift / tamper);
  * rechecks provenance == framer;
  * RE-RUNS every acceptance criterion's external check against live state, in a sanitized
    environment, repeated for quorum — the re-run is authoritative; the bundle's own
    acceptance_results / verifier_trace are advisory and can only LOSE, never win;
  * requires a real sha256 on every artifact and re-hashes it on disk;
  * requires the non-executable DoD fields to be present and structurally sound.

Exit 0 = GREEN (outcome independently confirmed), 1 = RED. Stdlib-only; shares hash /
sealed-path / no-op logic with the linter via _common.py. The verdict is written to an
explicit --out path (never silently into the maker-writable bundle directory).
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    FRAMER_KEY_ENV,
    TinyYamlError,
    as_dict,
    as_list,
    canonical_contract_hash,
    executed_program,
    executor_writable_roots,
    is_noop_command,
    is_sealed,
    is_traversing_ref,
    load_config,
    normalize_hash,
    read_plugin_version,
    resolve_framer_key,
)

DOD_FIELDS = ("contract_ref", "contract_hash", "accepted_plan_ref", "artifacts",
              "tool_receipts", "acceptance_results", "final_state_assertion",
              "unresolved_risks", "persisted_state_update_ref")

DANGEROUS_ENV = {"LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "PYTHONPATH",
                 "PYTHONSTARTUP", "BASH_ENV", "ENV", "IFS", "NODE_OPTIONS",
                 "NODE_PATH", "RUBYOPT", "RUBYLIB", "PERL5OPT", "PERLLIB",
                 FRAMER_KEY_ENV}


def safe_env() -> dict[str, str]:
    """Inherit the toolchain env (so real checks like pytest/node still run) but drop the
    env-injection vectors and put the system bin dirs first, so a maker-planted binary on
    PATH cannot shadow a system one. Full isolation (sandbox/container) is the operator's
    job; this defeats the common LD_*/PYTHONPATH/proxy hijacks.

    Also strips the framer's HMAC key (2026-07-01 adversarial review, finding 1 — BLOCK):
    every external_check runs maker-controlled code by definition (that's the entire point
    of an oracle), so forwarding LOOPTIMAL_FRAMER_KEY here handed the checker's signing key
    to the party it exists to check. The name-based check catches any lookalike env var a
    future call site might introduce, not just the exact constant."""
    env = {k: v for k, v in os.environ.items()
           if k not in DANGEROUS_ENV
           and not k.lower().endswith("_proxy")
           and "framer_key" not in k.lower()}
    env["PATH"] = "/usr/bin:/bin:" + env.get("PATH", "")
    env.setdefault("LC_ALL", "C")
    return env


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_check(external_check: Any, workdir: Path, repeat: int) -> tuple[bool, dict[str, Any]]:
    """Re-run an external check `repeat` times; PASS only if every run exits 0. No-op
    commands are rejected; the env is minimized to defeat PATH / LD_* / PYTHONPATH hijacks."""
    if is_noop_command(external_check):
        return False, {"error": "no-op or empty external_check"}
    cmd = external_check if isinstance(external_check, list) else [str(external_check)]
    cmd = [str(x) for x in cmd]
    exits: list[int] = []
    for _ in range(max(1, repeat)):
        try:
            proc = subprocess.run(cmd, cwd=str(workdir), env=safe_env(),
                                  capture_output=True, text=True, timeout=600)
            exits.append(proc.returncode)
        except (OSError, subprocess.SubprocessError) as exc:
            exits.append(-1)
            return False, {"cmd": cmd, "exits": exits, "error": str(exc)[:200]}
    return all(e == 0 for e in exits), {"cmd": cmd, "exits": exits}


def verify(bundle_path: Path, workdir: Path | None, repeat: int,
          key: bytes | None = None) -> tuple[bool, dict[str, Any]]:
    findings: list[str] = []
    advisories: list[str] = []  # non-blocking notes; never affect GREEN/RED
    checks: list[dict[str, Any]] = []
    bundle_path = bundle_path.resolve()
    bdir = bundle_path.parent
    workdir = (workdir or bdir).resolve()

    try:
        bundle = as_dict(load_config(bundle_path))
    except (TinyYamlError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, {"result": "RED", "findings": [f"cannot load bundle: {exc}"]}

    for f in DOD_FIELDS:
        if f not in bundle:
            findings.append(f"evidence-bundle missing DoD field: {f}")

    contract_ref = bundle.get("contract_ref")
    if not contract_ref:
        return False, {"result": "RED", "findings": findings + ["bundle has no contract_ref"]}
    cref = str(contract_ref).replace("\\", "/")
    if is_traversing_ref(contract_ref):
        return False, {"result": "RED", "findings": findings + [
            f"contract_ref must be a relative, non-traversing path inside the run dir: {contract_ref!r}"]}
    contract_path = (bdir / cref).resolve()
    try:
        contract = as_dict(load_config(contract_path))
    except (TinyYamlError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, {"result": "RED", "findings": findings + [f"sealed contract not loadable: {exc}"]}

    mission: dict[str, Any] = {}
    plan_ref = bundle.get("accepted_plan_ref")
    if plan_ref:
        pref = str(plan_ref).replace("\\", "/")
        if is_traversing_ref(plan_ref):
            findings.append(f"accepted_plan_ref must be a relative, non-traversing path: {plan_ref!r}")
        else:
            try:
                mission = as_dict(load_config((bdir / pref).resolve()))
            except (TinyYamlError, OSError, UnicodeDecodeError, json.JSONDecodeError):
                findings.append("accepted_plan_ref not loadable — cannot derive sealed roots")
    writable = executor_writable_roots(mission)
    suite = as_dict(contract.get("acceptance_suite"))

    def _sealed_vs_workdir(abs_path: Path) -> bool:
        # The sealed contract + suite MUST live inside the checker's --workdir, under a sealed
        # root the executor cannot write. A path resolving OUTSIDE the work tree is rejected
        # (RED): the verifier cannot distinguish a framer-owned external path from a
        # maker-controlled one without an independent framer record (a v1.1 pin). Conservative
        # = sound — this is what closes the "../evil" / absolute-path contract bypass.
        try:
            rel = os.path.relpath(abs_path, workdir).replace("\\", "/")
        except ValueError:
            return False
        if rel.startswith("..") or os.path.isabs(rel):
            return False
        return is_sealed(rel, writable)

    if not _sealed_vs_workdir(contract_path):
        findings.append(f"contract resolves to a non-sealed (executor-writable) path: {contract_path}")
    sp = suite.get("sealed_path")
    if not sp or not _sealed_vs_workdir((workdir / str(sp)).resolve()):
        findings.append(f"acceptance_suite.sealed_path is not sealed: {sp!r}")
    if str(suite.get("provenance") or "").strip().lower() != "framer":
        findings.append("acceptance_suite.provenance != framer")

    # sealed_dir-folding is coupled to `key` being set — the stronger mode is opt-in as a pair,
    # never applied unconditionally: an existing contract sealed under the plain unkeyed
    # algorithm (sealed_dir=None) must keep verifying identically when no key is configured.
    canonical = canonical_contract_hash(
        contract, key=key,
        sealed_dir=contract_path.parent if key else None,
        exclude=contract_path if key else None,
    )
    if not hmac.compare_digest(normalize_hash(contract.get("contract_hash")), canonical):
        findings.append("sealed contract_hash is not the canonical hash of the contract "
                        "(mismatch also fires if any file under the sealed/ directory was "
                        "modified — the hash now covers oracle-script bytes, not just contract text)")
    if not hmac.compare_digest(normalize_hash(bundle.get("contract_hash")), canonical):
        findings.append("bundle.contract_hash does not match the sealed contract (goal drift)")
    if key is None:
        advisories.append(
            "no framer key configured (--key-file / LOOPTIMAL_FRAMER_KEY) — using unkeyed "
            "sha256; a maker who can write the sealed contract can also recompute this hash. "
            "A keyed run is strongly recommended, especially for sensitivity: high missions.")

    def _oracle_sealed(external_check: Any) -> bool:
        # The check must invoke a SEALED, workdir-contained oracle script (resolved, so a
        # symlink escape is caught) — not a tautological system command (grep/make/uname) or a
        # writable / out-of-tree script the maker controls. The EXECUTED program (not just any
        # path-shaped argument — 2026-07-01 adversarial review, finding 2) must resolve sealed;
        # a sealed data file passed to a maker-writable program no longer satisfies this.
        prog = executed_program(external_check)
        if not prog:
            return False
        ap = Path(prog).resolve() if os.path.isabs(prog) else (workdir / prog).resolve()
        try:
            rel = os.path.relpath(ap, workdir).replace("\\", "/")
        except ValueError:
            return False
        return not rel.startswith("..") and not os.path.isabs(rel) and is_sealed(rel, writable)

    criteria = as_list(suite.get("criteria"))
    if not criteria:
        findings.append("sealed contract has no acceptance criteria")
    rerun_pass: dict[str, bool] = {}
    for raw in criteria:
        c = as_dict(raw)
        cid = str(c.get("id") or "?")
        if not _oracle_sealed(c.get("external_check")):
            rerun_pass[cid] = False
            checks.append({"criterion": cid, "passed": False,
                           "error": "external_check does not invoke a sealed oracle script"})
            findings.append(f"criterion {cid}: external_check must invoke a sealed, workdir-contained "
                            "oracle script (not a writable / out-of-tree / tautological command)")
            continue
        passed, detail = run_check(c.get("external_check"), workdir, repeat)
        rerun_pass[cid] = passed
        checks.append({"criterion": cid, "passed": passed, **detail})
        if not passed:
            findings.append(f"criterion {cid}: external re-run did NOT pass {detail.get('exits', detail.get('error'))}")

    for ar in as_list(bundle.get("acceptance_results")):
        ar = as_dict(ar)
        cid = str(ar.get("criterion") or "")
        claimed = str(ar.get("passed_by") or ar.get("value") or "").lower()
        if cid in rerun_pass and not rerun_pass[cid] and ("pass" in claimed or "green" in claimed):
            findings.append(f"criterion {cid}: bundle claims pass but external re-run failed (self-grade rejected)")

    for art in as_list(bundle.get("artifacts")):
        art = as_dict(art)
        rel = str(art.get("path") or "")
        expected = normalize_hash(art.get("sha256"))
        if not rel:
            findings.append("artifact entry has no path")
            continue
        if not expected:
            findings.append(f"artifact {rel}: missing/empty sha256 (integrity cannot be checked)")
            continue
        fpath = (workdir / rel).resolve()
        if not fpath.is_file():
            findings.append(f"artifact {rel}: file not found at {fpath}")
            continue
        actual = sha256_file(fpath)
        if actual != expected:
            findings.append(f"artifact {rel}: sha256 mismatch (expected {expected[:12]}, got {actual[:12]})")

    if not str(bundle.get("final_state_assertion") or "").strip():
        findings.append("final_state_assertion is empty")
    if not isinstance(bundle.get("unresolved_risks"), list):
        findings.append("unresolved_risks must be a list (use [] if none)")
    psr = bundle.get("persisted_state_update_ref")
    if psr and not (workdir / str(psr)).exists() and not (bdir / str(psr)).exists():
        findings.append(f"persisted_state_update_ref does not exist: {psr}")

    result = "GREEN" if not findings else "RED"
    verdict = {
        "result": result,
        "contract_hash": canonical,
        "criteria": checks,
        "findings": findings,
        "advisories": advisories,
        "repeat": repeat,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return (result == "GREEN"), verdict


def emit_receipt(receipt_path: Path, verdict: dict[str, Any], bundle_path: Path,
                 workdir: Path, *, key: bytes | None = None,
                 include_objective: bool = False) -> None:
    """Write a public verification receipt (references/receipt.md) for a GREEN live re-run.

    ONLY ever called after verify() returned ok == True (Emission semantics #1: only on GREEN — a
    receipt for a non-GREEN run must not exist). The load-bearing fields come from the checker's own
    VERDICT, never from the maker's self-report: `contract_hash`, `criteria_passed`, and `repeat` are
    copied out of `verdict`; `objective_hash` / the `*_ref` paths / `evidence_bundle_sha256` are
    re-derived from disk, resolving the contract exactly as verify() did (bundle-relative
    `contract_ref`). This re-derivation keeps verify() itself untouched — the hostile gate stays
    pristine — and mirrors what an independent re-checker would do.

    When a framer key is configured the receipt is keyed and HMAC-signed over its own canonical
    payload (the whole receipt MINUS the `signature` field), reusing canonical_contract_hash's exact
    json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True) discipline so the two
    serializations cannot drift. Unkeyed, the `signature` field is OMITTED entirely (absent, not
    null) so it is naturally excluded from any future signed payload without special-casing — and
    `contract_hash_keyed` is False, disambiguating the (identically shaped) contract_hash."""
    bundle_path = bundle_path.resolve()
    workdir = workdir.resolve()
    bundle = as_dict(load_config(bundle_path))
    contract_ref = str(bundle.get("contract_ref") or "").replace("\\", "/")
    # Re-assert verify()'s own traversal guard (2026-07-02 confirmation review, finding L1)
    # rather than relying on emit_receipt() only ever being called post-GREEN, when the same
    # bundle already passed it once: emit_receipt re-reads a maker-influenced ref independently,
    # and a future caller (e.g. a standalone re-check) could reach this code without verify()
    # having validated it first. Defense-in-depth, not a live hole today.
    if is_traversing_ref(contract_ref):
        raise ValueError(f"contract_ref must be a relative, non-traversing path: {contract_ref!r}")
    contract_path = (bundle_path.parent / contract_ref).resolve()
    objective_text = str(as_dict(load_config(contract_path)).get("objective") or "")

    try:
        bundle_ref = os.path.relpath(bundle_path, workdir).replace("\\", "/")
    except ValueError:  # e.g. different drive on Windows — fall back to the bare name
        bundle_ref = bundle_path.name

    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    ci_run_url = (f"{server}/{repo}/actions/runs/{run_id}"
                  if server and repo and run_id else None)

    try:
        looptimal_version = read_plugin_version()
    except (OSError, ValueError, json.JSONDecodeError):
        looptimal_version = "unknown"  # degrade rather than crash a GREEN emission

    receipt: dict[str, Any] = {
        "kind": "looptimal-receipt",
        "schema_version": 1,
        "objective_hash": "sha256:" + hashlib.sha256(objective_text.encode("utf-8")).hexdigest(),
    }
    if include_objective:  # opt-in; the receipt is public, so hash-only is the default (Decision 1)
        receipt["objective"] = objective_text
    receipt.update({
        "contract_ref": contract_ref,
        "contract_hash": verdict.get("contract_hash"),
        "contract_hash_keyed": key is not None,
        "evidence_bundle_ref": bundle_ref,
        "evidence_bundle_sha256": sha256_file(bundle_path),
        "verdict": "GREEN",
        "criteria_passed": [str(c.get("criterion")) for c in as_list(verdict.get("criteria"))
                            if c.get("passed")],
        "repeat": verdict.get("repeat"),
        "toolchain": {"looptimal": looptimal_version, "python": platform.python_version()},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ci_run_url": ci_run_url,
    })
    if key is not None:
        payload = {k: v for k, v in receipt.items() if k != "signature"}
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=True).encode("utf-8")
        receipt["signature"] = {"alg": "HMAC-SHA256",
                                "value": hmac.new(key, payload_bytes, hashlib.sha256).hexdigest()}

    receipt_path = Path(receipt_path)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def check_receipt(receipt_path: Path, workdir: Path | None, repeat: int,
                  key: bytes | None = None) -> tuple[bool, dict[str, Any]]:
    """Re-verify a public verification receipt (references/receipt.md, "Verification semantics").

    This is the counterpart to emit_receipt(): given only a receipt on disk (plus, for a keyed
    one, the framer key), independently re-derive everything the receipt asserts and RE-RUN the
    sealed suite live — exactly what a third party or CI job would do. The live re-run is
    authoritative; the receipt's recorded fields can only LOSE to it, never win. Steps mirror the
    spec 1:1 and any single failure is RED, reported with the exact step that failed.

    workdir: the live target-repo root the sealed suite is re-run against. Defaults to the
    receipt's OWN directory, because a receipt is emitted at <workdir>/looptimal-receipt.json by
    convention (emit_receipt / Emission semantics #4) — so the file's directory IS the workdir it
    was produced against, and evidence_bundle_ref (a relpath to that workdir) resolves cleanly
    from it. An explicit --workdir overrides this for a receipt that was moved away from its root.

    Returns (ok, report); report carries result/failed_step/reason plus a per-step `steps` log and
    non-blocking `advisories` (mirroring verify()'s verdict shape), so main() can print it as JSON
    the same way the Stage-6 verdict is printed."""
    steps: list[str] = []
    advisories: list[str] = []

    def red(step: str, reason: str) -> tuple[bool, dict[str, Any]]:
        return False, {"result": "RED", "failed_step": step, "reason": reason,
                       "steps": steps, "advisories": advisories,
                       "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    receipt_path = receipt_path.resolve()
    rdir = receipt_path.parent
    workdir = (workdir or rdir).resolve()

    # --- Step 1: load; kind / schema_version / verdict must be sound.
    try:
        receipt = as_dict(load_config(receipt_path))
    except (TinyYamlError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return red("1 (load)", f"cannot load receipt at {receipt_path}: {exc}")
    if receipt.get("kind") != "looptimal-receipt":
        return red("1 (kind)", f"kind != 'looptimal-receipt' (got {receipt.get('kind')!r})")
    sv = receipt.get("schema_version")
    if sv != 1:
        return red("1 (schema_version)",
                   f"unsupported schema_version {sv!r} — this checker understands 1 only; a receipt "
                   "from a newer Looptimal must be re-checked with a matching verify-outcome.py "
                   "(refusing rather than guessing)")
    if receipt.get("verdict") != "GREEN":
        return red("1 (verdict)",
                   f"verdict != 'GREEN' (got {receipt.get('verdict')!r}) — a receipt for a "
                   "non-GREEN run must never exist, so any other value is itself a failure")
    steps.append("1 ok: kind/schema_version/verdict sound")

    # --- Step 2: resolve refs, non-traversing, off the receipt's directory (== workdir by default).
    # evidence_bundle_ref is workdir-relative (emit_receipt stored a relpath to workdir); contract_ref
    # is resolved relative to the RESOLVED bundle's own dir, exactly as verify() resolves a bundle's
    # contract_ref — so the Step-4 hash re-derivation and the Step-6 live re-run agree on one and the
    # same contract file. The shared traversal guard keeps either ref from escaping its base.
    bundle_ref = receipt.get("evidence_bundle_ref")
    contract_ref = receipt.get("contract_ref")
    if not bundle_ref or is_traversing_ref(bundle_ref):
        return red("2 (evidence_bundle_ref)",
                   f"evidence_bundle_ref must be a relative, non-traversing path: {bundle_ref!r}")
    if not contract_ref or is_traversing_ref(contract_ref):
        return red("2 (contract_ref)",
                   f"contract_ref must be a relative, non-traversing path: {contract_ref!r}")
    bundle_path = (workdir / str(bundle_ref).replace("\\", "/")).resolve()
    contract_path = (bundle_path.parent / str(contract_ref).replace("\\", "/")).resolve()
    steps.append("2 ok: contract_ref / evidence_bundle_ref resolve inside the run dir")

    # --- Step 3: re-derive the evidence-bundle hash from the bytes on disk.
    if not bundle_path.is_file():
        return red("3 (evidence bundle)", f"evidence bundle not found at {bundle_path}")
    actual_bundle_sha = sha256_file(bundle_path)
    if not hmac.compare_digest(actual_bundle_sha, normalize_hash(receipt.get("evidence_bundle_sha256"))):
        return red("3 (evidence_bundle_sha256)",
                   f"evidence bundle bytes on disk do not match evidence_bundle_sha256 "
                   f"(recomputed {actual_bundle_sha[:12]}…)")
    steps.append("3 ok: evidence_bundle_sha256 matches the bundle bytes on disk")

    # --- Step 4: re-derive the contract hash in the mode the receipt declares. A keyed receipt
    # CANNOT be checked without the key — fail loud rather than silently downgrade to an unkeyed
    # check (which would "verify" a forgery). An unkeyed receipt is derived unkeyed even if a key
    # happens to be supplied, since that is how its contract_hash was sealed.
    keyed = bool(receipt.get("contract_hash_keyed"))
    if keyed and key is None:
        return red("4 (key required)",
                   "receipt declares contract_hash_keyed=true but no framer key was supplied "
                   f"(--key-file / {FRAMER_KEY_ENV}) — cannot verify a keyed receipt without the "
                   "key; refusing to downgrade to an unkeyed check")
    mode_key = key if keyed else None
    try:
        contract = as_dict(load_config(contract_path))
    except (TinyYamlError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return red("4 (contract load)", f"sealed contract not loadable at {contract_path}: {exc}")
    canonical = canonical_contract_hash(
        contract, key=mode_key,
        sealed_dir=contract_path.parent if mode_key else None,
        exclude=contract_path if mode_key else None,
    )
    if not hmac.compare_digest(normalize_hash(receipt.get("contract_hash")), canonical):
        return red("4 (contract_hash)",
                   "receipt.contract_hash does not match the canonical hash re-derived from the "
                   f"sealed contract on disk in {'keyed' if keyed else 'unkeyed'} mode "
                   "(also fires if any file under sealed/ changed when keyed)")
    steps.append(f"4 ok: contract_hash re-derives from the sealed contract ({'keyed' if keyed else 'unkeyed'})")

    # --- Step 5: signature. The key toggles BOTH the keyed contract_hash AND the receipt signature
    # as a pair (receipt.md, "The key toggles both") — reject the inconsistent shapes outright, then
    # recompute the HMAC over the receipt-minus-signature with the emitter's exact canonicalization.
    sig = receipt.get("signature")
    if keyed:
        assert key is not None  # established by the Step-4 guard above; not visible to the
        # type checker across the intervening `mode_key = key if keyed else None` rebinding.
        if not isinstance(sig, dict) or not sig.get("value"):
            return red("5 (signature)",
                       "keyed receipt (contract_hash_keyed=true) is missing a signature — a keyed "
                       "contract_hash with no signature is an invalid receipt")
        payload = {k: v for k, v in receipt.items() if k != "signature"}
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=True).encode("utf-8")
        expected = hmac.new(key, payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(sig.get("value")), expected):
            return red("5 (signature)",
                       "receipt signature does not match an HMAC re-computation over the receipt "
                       "payload with the supplied key — the receipt was altered or signed with a "
                       "different key")
        steps.append("5 ok: HMAC signature re-verifies against the receipt payload")
    else:
        if isinstance(sig, dict):
            return red("5 (signature)",
                       "unkeyed receipt (contract_hash_keyed=false) must not carry a signature — a "
                       "signature with no keyed hash is an invalid receipt")
        advisories.append(
            "unkeyed receipt: this check proves internal CONSISTENCY (hashes + live re-run agree), "
            "NOT authorship — an unkeyed receipt has no signature, so anyone could have authored it "
            "(references/receipt.md, Limits). Only a keyed receipt or a CI re-run proves authenticity.")
        steps.append("5 skipped: unkeyed receipt has no signature to check (consistency-only)")

    # --- Step 6: re-run the sealed suite LIVE — authoritative. Same mode as the receipt (mode_key),
    # so an unkeyed receipt re-runs unkeyed and a keyed one keyed. GREEN is required, and the set of
    # criterion IDs that pass live MUST equal the receipt's criteria_passed (a stale/forged subset or
    # superset is a fail — the live run wins, the recorded field can only lose to it).
    ok, verdict = verify(bundle_path, workdir, repeat, key=mode_key)
    if not ok:
        return red("6 (live re-run)",
                   "live re-run of the sealed suite did NOT return GREEN — the receipt cannot "
                   f"outlive the outcome it recorded. findings: {verdict.get('findings')}")
    live_passed = sorted(str(c.get("criterion")) for c in as_list(verdict.get("criteria")) if c.get("passed"))
    recorded_passed = sorted(str(x) for x in as_list(receipt.get("criteria_passed")))
    if live_passed != recorded_passed:
        return red("6 (criteria mismatch)",
                   f"live re-run passed {live_passed} but receipt.criteria_passed is "
                   f"{recorded_passed} — the live re-run is authoritative")
    steps.append(f"6 ok: live re-run GREEN and criteria_passed matches {live_passed}")

    # --- Step 7: verifies iff every step passed.
    return True, {"result": "GREEN", "failed_step": None, "reason": None,
                  "steps": steps, "advisories": advisories,
                  "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def run_selftest() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        run = root / "run"
        (run / "sealed").mkdir(parents=True)
        (run / "src").mkdir()
        (run / "sealed" / "check.py").write_text(
            "import sys, pathlib\n"
            "p = pathlib.Path('src/app.py')\n"
            "sys.exit(0 if p.exists() and 'fixed' in p.read_text() else 1)\n",
            encoding="utf-8")
        (run / "src" / "app.py").write_text("# fixed\nreturn 404\n", encoding="utf-8")
        contract = {
            "schema_version": 1, "objective": "fix it",
            "acceptance_suite": {
                "provenance": "framer", "sealed_path": "sealed/suite.json",
                "criteria": [{"id": "c1", "asserts": "outcome", "oracle": "repro",
                              "external_check": ["python3", str(run / "sealed" / "check.py")],
                              "green_means": "the sealed repro no longer reproduces the bug"}],
            }, "irreversibles": [],
        }
        contract["contract_hash"] = "sha256:" + canonical_contract_hash(contract)
        (run / "sealed" / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
        mission = {"schema_version": 1, "contract_ref": "sealed/contract.json",
                   "capability_manifest": {"backend": {"allowed_paths": ["src/"]}},
                   "lanes": [{"id": "L1", "archetype": "task"}]}
        (run / "mission.json").write_text(json.dumps(mission), encoding="utf-8")
        art_hash = sha256_file(run / "src" / "app.py")
        bundle = {
            "contract_ref": "sealed/contract.json", "accepted_plan_ref": "mission.json",
            "contract_hash": canonical_contract_hash(contract),
            "artifacts": [{"path": "src/app.py", "sha256": art_hash}],
            "tool_receipts": [{"cmd": "pytest", "exit": 0, "stdout_sha": art_hash, "ts": "t"}],
            "acceptance_results": [{"criterion": "c1", "passed_by": "external_rerun", "value": "pass"}],
            "final_state_assertion": "src/app.py returns 404 for the missing project",
            "unresolved_risks": [], "persisted_state_update_ref": "mission.json",
        }
        (run / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

        ok, verdict = verify(run / "bundle.json", workdir=run, repeat=2)
        if not ok:
            print("SELFTEST FAIL (honest bundle went RED):", verdict["findings"])
            return 1
        (run / "src" / "app.py").write_text("# broken\n", encoding="utf-8")
        bundle["artifacts"][0]["sha256"] = sha256_file(run / "src" / "app.py")
        (run / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        ok2, _ = verify(run / "bundle.json", workdir=run, repeat=2)
        if ok2:
            print("SELFTEST FAIL (tampered state still GREEN)")
            return 1

        # --- keyed hash-pin: proves the fix, not just documents it. Restore the honest state,
        # reseal with a demo HMAC key covering the sealed/ tree, then tamper an ORACLE SCRIPT
        # while leaving contract_hash untouched. Before this change, canonical_contract_hash()
        # never covered sealed/ file bytes, so this specific tamper would have gone undetected —
        # the whole point of this selftest case is that it no longer does.
        (run / "src" / "app.py").write_text("# fixed\nreturn 404\n", encoding="utf-8")
        key = b"\x00" * 32  # fixed, non-secret demo key — selftest only, never use a real key here
        contract["contract_hash"] = "sha256:" + canonical_contract_hash(
            contract, key=key, sealed_dir=run / "sealed", exclude=run / "sealed" / "contract.json")
        (run / "sealed" / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
        bundle["contract_hash"] = canonical_contract_hash(
            contract, key=key, sealed_dir=run / "sealed", exclude=run / "sealed" / "contract.json")
        bundle["artifacts"][0]["sha256"] = sha256_file(run / "src" / "app.py")
        (run / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        ok3, verdict3 = verify(run / "bundle.json", workdir=run, repeat=2, key=key)
        if not ok3:
            print("SELFTEST FAIL (honest keyed bundle went RED):", verdict3["findings"])
            return 1

        original_oracle = (run / "sealed" / "check.py").read_text(encoding="utf-8")
        assert "'fixed' in p.read_text()" in original_oracle, "fixture check.py text changed — update this tamper"
        (run / "sealed" / "check.py").write_text(
            original_oracle.replace("'fixed' in p.read_text()", "True"), encoding="utf-8")
        ok4, verdict4 = verify(run / "bundle.json", workdir=run, repeat=2, key=key)
        if ok4:
            print("SELFTEST FAIL (tampered sealed/ oracle script still GREEN under the hash-pin):",
                 verdict4)
            return 1

        # --- key-leak closure (2026-07-01 adversarial review, finding 1 — BLOCK). Every
        # external_check runs maker-controlled code by definition, so forwarding the checker's
        # signing key into that subprocess's environment let a maker read it back out and forge
        # a keyed contract_hash / receipt signature. Simulate the documented, CI-recommended key
        # delivery (LOOPTIMAL_FRAMER_KEY set on the checker's own process — see references/
        # receipt.md's Decisions) and confirm an oracle that TRIES to exfiltrate it gets nothing.
        leak_run = root / "leak"
        (leak_run / "sealed").mkdir(parents=True)
        (leak_run / "src").mkdir()
        leak_out = leak_run / "src" / "leaked_key.txt"
        (leak_run / "sealed" / "leak_check.py").write_text(
            "import os, pathlib\n"
            "pathlib.Path('src/leaked_key.txt')"
            ".write_text(os.environ.get('LOOPTIMAL_FRAMER_KEY', ''))\n",
            encoding="utf-8")
        leak_contract = {
            "schema_version": 1, "objective": "probe for framer-key leakage into an oracle",
            "acceptance_suite": {
                "provenance": "framer", "sealed_path": "sealed/suite.json",
                "criteria": [{"id": "c1", "asserts": "outcome", "oracle": "key-leak-probe",
                              "external_check": ["python3", str(leak_run / "sealed" / "leak_check.py")],
                              "green_means": "n/a -- this criterion only probes subprocess env"}],
            }, "irreversibles": [],
        }
        leak_contract["contract_hash"] = "sha256:" + canonical_contract_hash(
            leak_contract, key=key, sealed_dir=leak_run / "sealed",
            exclude=leak_run / "sealed" / "contract.json")
        (leak_run / "sealed" / "contract.json").write_text(json.dumps(leak_contract), encoding="utf-8")
        (leak_run / "mission.json").write_text(json.dumps({
            "schema_version": 1, "contract_ref": "sealed/contract.json",
            "capability_manifest": {"backend": {"allowed_paths": ["src/"]}},
            "lanes": [{"id": "L1", "archetype": "task"}],
        }), encoding="utf-8")
        leak_bundle = {
            "contract_ref": "sealed/contract.json", "accepted_plan_ref": "mission.json",
            "contract_hash": canonical_contract_hash(
                leak_contract, key=key, sealed_dir=leak_run / "sealed",
                exclude=leak_run / "sealed" / "contract.json"),
            "artifacts": [], "tool_receipts": [],
            "acceptance_results": [{"criterion": "c1", "passed_by": "external_rerun", "value": "pass"}],
            "final_state_assertion": "n/a", "unresolved_risks": [],
            "persisted_state_update_ref": "mission.json",
        }
        (leak_run / "bundle.json").write_text(json.dumps(leak_bundle), encoding="utf-8")
        prior_env_key = os.environ.get(FRAMER_KEY_ENV)
        os.environ[FRAMER_KEY_ENV] = key.hex()
        try:
            verify(leak_run / "bundle.json", workdir=leak_run, repeat=1, key=key)
        finally:
            if prior_env_key is None:
                os.environ.pop(FRAMER_KEY_ENV, None)
            else:
                os.environ[FRAMER_KEY_ENV] = prior_env_key
        leaked = leak_out.read_text(encoding="utf-8") if leak_out.exists() else ""
        if leaked:
            print("SELFTEST FAIL (framer key leaked into an oracle subprocess's environment)")
            return 1

        # --- receipt emission (references/receipt.md). Proves the emitter's core anti-forgery
        # claims mechanically: (a) a keyed GREEN --receipt writes a signed receipt whose signature
        # we INDEPENDENTLY recompute from the receipt's own fields (present AND correct, not merely
        # present); (b) an unkeyed GREEN --receipt writes an UNSIGNED receipt (signature absent, not
        # null); (c) a RED verify writes NO receipt at all (the GREEN-only gate). The ok4 tamper
        # left run/sealed/check.py broken, so restore it to the honest keyed state first.
        (run / "sealed" / "check.py").write_text(original_oracle, encoding="utf-8")
        ok5, verdict5 = verify(run / "bundle.json", workdir=run, repeat=2, key=key)
        if not ok5:
            print("SELFTEST FAIL (honest keyed bundle went RED before receipt emission):",
                  verdict5["findings"])
            return 1
        keyed_receipt = run / "looptimal-receipt.json"
        emit_receipt(keyed_receipt, verdict5, run / "bundle.json", run, key=key,
                     include_objective=False)
        if not keyed_receipt.is_file():
            print("SELFTEST FAIL (keyed --receipt wrote no receipt file)")
            return 1
        receipt = json.loads(keyed_receipt.read_text(encoding="utf-8"))
        expected_passed = [c["criterion"] for c in verdict5["criteria"] if c["passed"]]
        if (receipt.get("kind") != "looptimal-receipt"
                or receipt.get("contract_hash_keyed") is not True
                or receipt.get("verdict") != "GREEN"
                or receipt.get("criteria_passed") != expected_passed
                or not isinstance(receipt.get("signature"), dict)
                or not receipt["signature"].get("value")):
            print("SELFTEST FAIL (keyed receipt malformed — kind/keyed/criteria/signature):", receipt)
            return 1
        # Independently recompute the HMAC over the receipt-minus-signature with the same key and
        # the same canonicalization the emitter used; a match proves the signature is genuinely
        # correct, not just present.
        signed = {k: v for k, v in receipt.items() if k != "signature"}
        recomputed = hmac.new(key, json.dumps(signed, sort_keys=True, separators=(",", ":"),
                                              ensure_ascii=True).encode("utf-8"),
                              hashlib.sha256).hexdigest()
        if not hmac.compare_digest(recomputed, receipt["signature"]["value"]):
            print("SELFTEST FAIL (keyed receipt signature does not verify against its own fields)")
            return 1

        # (b) unkeyed GREEN: reseal run/ under the plain unkeyed sha256, emit, and confirm the
        # signature field is ABSENT entirely (not null) and contract_hash_keyed is false.
        contract["contract_hash"] = "sha256:" + canonical_contract_hash(contract)
        (run / "sealed" / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
        bundle["contract_hash"] = canonical_contract_hash(contract)
        bundle["artifacts"][0]["sha256"] = sha256_file(run / "src" / "app.py")
        (run / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        ok6, verdict6 = verify(run / "bundle.json", workdir=run, repeat=2)
        if not ok6:
            print("SELFTEST FAIL (honest unkeyed bundle went RED before receipt emission):",
                  verdict6["findings"])
            return 1
        unkeyed_receipt = run / "looptimal-receipt-unkeyed.json"
        emit_receipt(unkeyed_receipt, verdict6, run / "bundle.json", run, key=None,
                     include_objective=False)
        ur = json.loads(unkeyed_receipt.read_text(encoding="utf-8"))
        if ur.get("contract_hash_keyed") is not False or "signature" in ur:
            print("SELFTEST FAIL (unkeyed receipt must have contract_hash_keyed=false and NO "
                  "signature field):", ur)
            return 1

        # (c) RED gate: tamper live state so the sealed suite fails, point --receipt at a fresh
        # path, and confirm NO receipt is written — mirroring main()'s "emit iff GREEN" gate.
        red_receipt = run / "looptimal-receipt-red.json"
        (run / "src" / "app.py").write_text("# broken\n", encoding="utf-8")
        bundle["artifacts"][0]["sha256"] = sha256_file(run / "src" / "app.py")
        (run / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        ok7, verdict7 = verify(run / "bundle.json", workdir=run, repeat=2)
        if ok7:  # emit iff GREEN — a RED verify must never reach emit_receipt
            emit_receipt(red_receipt, verdict7, run / "bundle.json", run, key=None,
                         include_objective=False)
        if ok7 or red_receipt.exists():
            print("SELFTEST FAIL (RED verify emitted a receipt / unexpectedly went GREEN)")
            return 1

        # --- receipt VERIFICATION (references/receipt.md, "Verification semantics"). Proves the
        # checker's anti-forgery claims mechanically, mirroring the tamper-to-RED pattern above:
        # (a) an honest keyed receipt re-checks GREEN; (e) that same keyed receipt with NO key
        # fails loud (never a silent downgrade); (b) editing one cosmetic field breaks the HMAC
        # signature -> RED; (c) tampering live state after emission makes the live re-run fail -> RED
        # (the receipt cannot outlive the outcome it recorded, even though the signed file is
        # untouched); (d) an honest UNKEYED receipt re-checks GREEN but is reported consistency-only,
        # never silently upgraded to an authorship claim. Restore the honest keyed state first (the
        # RED gate above left app.py broken and the tree resealed unkeyed).
        (run / "src" / "app.py").write_text("# fixed\nreturn 404\n", encoding="utf-8")
        contract["contract_hash"] = "sha256:" + canonical_contract_hash(
            contract, key=key, sealed_dir=run / "sealed", exclude=run / "sealed" / "contract.json")
        (run / "sealed" / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
        bundle["contract_hash"] = canonical_contract_hash(
            contract, key=key, sealed_dir=run / "sealed", exclude=run / "sealed" / "contract.json")
        bundle["artifacts"][0]["sha256"] = sha256_file(run / "src" / "app.py")
        (run / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        ok8, verdict8 = verify(run / "bundle.json", workdir=run, repeat=2, key=key)
        if not ok8:
            print("SELFTEST FAIL (honest keyed bundle went RED before check-receipt):",
                  verdict8["findings"])
            return 1
        cr_keyed = run / "looptimal-receipt-check.json"
        emit_receipt(cr_keyed, verdict8, run / "bundle.json", run, key=key, include_objective=False)

        # (a) honest keyed receipt re-checks GREEN.
        ok_a, rep_a = check_receipt(cr_keyed, run, repeat=2, key=key)
        if not ok_a:
            print("SELFTEST FAIL (honest keyed receipt did not re-check GREEN):", rep_a)
            return 1
        # (e) a keyed receipt with NO key fails loud at Step 4 — never a silent unkeyed downgrade.
        ok_e, rep_e = check_receipt(cr_keyed, run, repeat=2, key=None)
        if ok_e or "key required" not in str(rep_e.get("failed_step", "")):
            print("SELFTEST FAIL (keyed receipt re-checked without a key / wrong step):", rep_e)
            return 1
        # (b) hand-edit one cosmetic field (ci_run_url) -> signature mismatch -> RED.
        tampered = json.loads(cr_keyed.read_text(encoding="utf-8"))
        tampered["ci_run_url"] = "https://example.com/forged/actions/runs/999"
        cr_tampered = run / "looptimal-receipt-check-tampered.json"
        cr_tampered.write_text(json.dumps(tampered, indent=2) + "\n", encoding="utf-8")
        ok_b, rep_b = check_receipt(cr_tampered, run, repeat=2, key=key)
        if ok_b or "signature" not in str(rep_b.get("failed_step", "")):
            print("SELFTEST FAIL (cosmetically-edited keyed receipt still verified / wrong step):",
                  rep_b)
            return 1
        # (c) tamper live state after emission -> the (still byte-for-byte honest, signed) receipt's
        # live re-run fails -> RED. Isolates that Step 6 is what catches outcome regression.
        (run / "src" / "app.py").write_text("# broken\n", encoding="utf-8")
        ok_c, rep_c = check_receipt(cr_keyed, run, repeat=2, key=key)
        if ok_c or "live re-run" not in str(rep_c.get("failed_step", "")):
            print("SELFTEST FAIL (receipt verified against tampered live state / wrong step):", rep_c)
            return 1
        (run / "src" / "app.py").write_text("# fixed\nreturn 404\n", encoding="utf-8")  # restore

        # (d) honest UNKEYED receipt re-checks GREEN and is reported consistency-only. Reseal the
        # tree under the plain unkeyed sha256 first (matches the unkeyed emission case above).
        contract["contract_hash"] = "sha256:" + canonical_contract_hash(contract)
        (run / "sealed" / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
        bundle["contract_hash"] = canonical_contract_hash(contract)
        bundle["artifacts"][0]["sha256"] = sha256_file(run / "src" / "app.py")
        (run / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        ok9, verdict9 = verify(run / "bundle.json", workdir=run, repeat=2)
        if not ok9:
            print("SELFTEST FAIL (honest unkeyed bundle went RED before check-receipt):",
                  verdict9["findings"])
            return 1
        cr_unkeyed = run / "looptimal-receipt-check-unkeyed.json"
        emit_receipt(cr_unkeyed, verdict9, run / "bundle.json", run, key=None, include_objective=False)
        ok_d, rep_d = check_receipt(cr_unkeyed, run, repeat=2, key=None)
        if not ok_d:
            print("SELFTEST FAIL (honest unkeyed receipt did not re-check GREEN):", rep_d)
            return 1
        if not any("consistency" in a.lower() for a in rep_d.get("advisories", [])):
            print("SELFTEST FAIL (unkeyed receipt re-check did not report consistency-only):", rep_d)
            return 1
    print("SELFTEST GREEN")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Looptimal Stage-6 outer outcome verifier.")
    ap.add_argument("--bundle", help="path to evidence-bundle.json")
    ap.add_argument("--workdir", help="live target-repo root the checks run against (default: bundle dir)")
    ap.add_argument("--repeat", type=int, default=3, help="re-run each check N times for quorum (default 3)")
    ap.add_argument("--out", help="write the verdict JSON here (must be outside the bundle dir)")
    ap.add_argument("--key-file", help="path to a hex-encoded framer HMAC key (checker-side "
                    f"only; alternative: the {FRAMER_KEY_ENV} env var). Omit to use the "
                    "original unkeyed sha256 (backward compatible, weaker).")
    ap.add_argument("--receipt", nargs="?", const="", default=None, metavar="PATH",
                    help="on GREEN only, write a public verification receipt (references/"
                    "receipt.md). Bare --receipt uses <workdir>/looptimal-receipt.json; pass a "
                    "PATH to override. Opt-in and explicit — never written on RED, never a silent "
                    "side effect. Keyed + HMAC-signed when a framer key is configured, unkeyed "
                    "(consistency-only) otherwise.")
    ap.add_argument("--receipt-include-objective", action="store_true",
                    help="include the clear-text objective in the receipt (default: objective_hash "
                    "only, since a receipt is public).")
    ap.add_argument("--check-receipt", metavar="PATH", default=None,
                    help="re-verify an existing public receipt (references/receipt.md, 'Verification "
                    "semantics'): re-derive its hashes, re-check its HMAC signature when keyed, and "
                    "RE-RUN the sealed suite live against --workdir (default: the receipt's own dir). "
                    "Standalone mode, separate from --bundle/--receipt. A keyed receipt REQUIRES a "
                    f"framer key (--key-file / {FRAMER_KEY_ENV}); refusing one is a hard fail, never a "
                    "silent downgrade. Exit 0 = GREEN, 1 = RED.")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return run_selftest()
    if args.check_receipt is not None:
        key = resolve_framer_key(args.key_file)
        ok, report = check_receipt(Path(args.check_receipt),
                                   Path(args.workdir).resolve() if args.workdir else None,
                                   args.repeat, key=key)
        print(json.dumps(report, indent=2))
        return 0 if ok else 1
    if not args.bundle:
        ap.error("--bundle is required (or use --check-receipt / --selftest)")
    key = resolve_framer_key(args.key_file)
    bundle_path = Path(args.bundle)
    workdir = Path(args.workdir).resolve() if args.workdir else bundle_path.resolve().parent
    ok, verdict = verify(bundle_path,
                         Path(args.workdir) if args.workdir else None,
                         args.repeat, key=key)
    blob = json.dumps(verdict, indent=2)
    if args.out:
        outp = Path(args.out).resolve()
        if outp.parent == bundle_path.resolve().parent:
            print("refusing to write the verdict into the maker-writable bundle directory; "
                  "choose --out elsewhere", file=sys.stderr)
            return 2
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(blob + "\n", encoding="utf-8")
    # Receipt emission is gated on GREEN (Emission semantics #1). On RED it is a no-op: no receipt
    # is written and any pre-existing receipt is deliberately left untouched.
    if args.receipt is not None:
        if ok:
            receipt_target = (Path(args.receipt) if args.receipt
                              else workdir / "looptimal-receipt.json")
            emit_receipt(receipt_target, verdict, bundle_path, workdir,
                         key=key, include_objective=args.receipt_include_objective)
            print(f"receipt: wrote {'keyed, signed' if key else 'unkeyed'} receipt to "
                  f"{receipt_target}", file=sys.stderr)
        else:
            print("receipt: verdict is RED — no receipt written (any pre-existing receipt "
                  "left untouched)", file=sys.stderr)
    print(blob)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
