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
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    TinyYamlError,
    as_dict,
    as_list,
    candidate_paths,
    canonical_contract_hash,
    executor_writable_roots,
    is_noop_command,
    is_sealed,
    load_config,
    normalize_hash,
)

DOD_FIELDS = ("contract_ref", "contract_hash", "accepted_plan_ref", "artifacts",
              "tool_receipts", "acceptance_results", "final_state_assertion",
              "unresolved_risks", "persisted_state_update_ref")

DANGEROUS_ENV = {"LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "PYTHONPATH",
                 "PYTHONSTARTUP", "BASH_ENV", "ENV", "IFS", "NODE_OPTIONS",
                 "NODE_PATH", "RUBYOPT", "RUBYLIB", "PERL5OPT", "PERLLIB"}


def safe_env() -> dict[str, str]:
    """Inherit the toolchain env (so real checks like pytest/node still run) but drop the
    env-injection vectors and put the system bin dirs first, so a maker-planted binary on
    PATH cannot shadow a system one. Full isolation (sandbox/container) is the operator's
    job; this defeats the common LD_*/PYTHONPATH/proxy hijacks."""
    env = {k: v for k, v in os.environ.items()
           if k not in DANGEROUS_ENV and not k.lower().endswith("_proxy")}
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


def verify(bundle_path: Path, workdir: Path | None, repeat: int) -> tuple[bool, dict[str, Any]]:
    findings: list[str] = []
    checks: list[dict[str, Any]] = []
    bundle_path = bundle_path.resolve()
    bdir = bundle_path.parent
    workdir = (workdir or bdir).resolve()

    try:
        bundle = as_dict(load_config(bundle_path))
    except (TinyYamlError, OSError, json.JSONDecodeError) as exc:
        return False, {"result": "RED", "findings": [f"cannot load bundle: {exc}"]}

    for f in DOD_FIELDS:
        if f not in bundle:
            findings.append(f"evidence-bundle missing DoD field: {f}")

    contract_ref = bundle.get("contract_ref")
    if not contract_ref:
        return False, {"result": "RED", "findings": findings + ["bundle has no contract_ref"]}
    cref = str(contract_ref).replace("\\", "/")
    if cref.startswith("/") or os.path.isabs(cref) or ".." in cref.split("/"):
        return False, {"result": "RED", "findings": findings + [
            f"contract_ref must be a relative, non-traversing path inside the run dir: {contract_ref!r}"]}
    contract_path = (bdir / cref).resolve()
    try:
        contract = as_dict(load_config(contract_path))
    except (TinyYamlError, OSError, json.JSONDecodeError) as exc:
        return False, {"result": "RED", "findings": findings + [f"sealed contract not loadable: {exc}"]}

    mission: dict[str, Any] = {}
    plan_ref = bundle.get("accepted_plan_ref")
    if plan_ref:
        pref = str(plan_ref).replace("\\", "/")
        if pref.startswith("/") or os.path.isabs(pref) or ".." in pref.split("/"):
            findings.append(f"accepted_plan_ref must be a relative, non-traversing path: {plan_ref!r}")
        else:
            try:
                mission = as_dict(load_config((bdir / pref).resolve()))
            except (TinyYamlError, OSError, json.JSONDecodeError):
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

    canonical = canonical_contract_hash(contract)
    if normalize_hash(contract.get("contract_hash")) != canonical:
        findings.append("sealed contract_hash is not the canonical hash of the contract")
    if normalize_hash(bundle.get("contract_hash")) != canonical:
        findings.append("bundle.contract_hash does not match the sealed contract (goal drift)")

    def _oracle_sealed(external_check: Any) -> bool:
        # The check must invoke a SEALED, workdir-contained oracle script (resolved, so a
        # symlink escape is caught) — not a tautological system command (grep/make/uname) or a
        # writable / out-of-tree script the maker controls. >=1 path arg must resolve sealed.
        for a in candidate_paths(external_check):
            ap = Path(a).resolve() if os.path.isabs(a) else (workdir / a).resolve()
            try:
                rel = os.path.relpath(ap, workdir).replace("\\", "/")
            except ValueError:
                continue
            if not rel.startswith("..") and not os.path.isabs(rel) and is_sealed(rel, writable):
                return True
        return False

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
        "repeat": repeat,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return (result == "GREEN"), verdict


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
    print("SELFTEST GREEN")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Looptimal Stage-6 outer outcome verifier.")
    ap.add_argument("--bundle", help="path to evidence-bundle.json")
    ap.add_argument("--workdir", help="live target-repo root the checks run against (default: bundle dir)")
    ap.add_argument("--repeat", type=int, default=3, help="re-run each check N times for quorum (default 3)")
    ap.add_argument("--out", help="write the verdict JSON here (must be outside the bundle dir)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return run_selftest()
    if not args.bundle:
        ap.error("--bundle is required (or use --selftest)")
    ok, verdict = verify(Path(args.bundle),
                         Path(args.workdir) if args.workdir else None,
                         args.repeat)
    blob = json.dumps(verdict, indent=2)
    if args.out:
        outp = Path(args.out).resolve()
        if outp.parent == Path(args.bundle).resolve().parent:
            print("refusing to write the verdict into the maker-writable bundle directory; "
                  "choose --out elsewhere", file=sys.stderr)
            return 2
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(blob + "\n", encoding="utf-8")
    print(blob)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
