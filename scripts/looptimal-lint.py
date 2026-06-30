#!/usr/bin/env python3
"""looptimal-lint.py — plan-time gate for a Looptimal mission + its sealed contract.

Run before any autonomous execution (Stage 3 -> Stage 4). It RED-fails a plan that
could be gamed past the outcome gate. Stdlib-only; shares its hash / sealed-path /
heuristic logic with verify-outcome.py via _common.py so the two gates always agree.

Exit 0 = GREEN (safe to proceed to Simulate/Execute), 1 = RED (findings printed).

What it enforces:
  * contract_hash is the canonical hash of the sealed contract (no tampering / drift);
  * the acceptance suite + every per-lane oracle live on a SEALED path the executor
    lanes cannot write to (maker can't edit the gate mid-loop);
  * acceptance has >=1 criterion; each binds an oracle, names a NON-no-op external
    check, and states an OUTCOME (not a maker-controlled symptom / self-grade);
  * provenance == framer;
  * a resolvable profile binds DISTINCT executor / checker / outer-verifier agents
    (binding-layer maker != checker; runtime identity is enforced by the harness at
    dispatch, and re-checked by verify-outcome at Stage 6);
  * no concrete native-agent id is hardcoded in the (generic) mission;
  * autonomy:full + irreversibles requires a human GO gate;
  * persistent-ratchet lanes pin a scope; self-referential / meta loops are rejected.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    SELF_GRADE_RE,
    SYMPTOM_PATTERN,
    NATIVE_AGENT_RE,
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
    text_tree,
)

REQUIRED_MISSION_KEYS = ("schema_version", "contract_ref", "contract_hash",
                         "capability_manifest", "human_go_gate", "lanes", "tasks")
META_RE = ("looptimal", "meta-orchestrat", "auto-merge", "verify itself",
           "approve itself", "self-referential")


def resolve_profile(mission: dict[str, Any], mission_path: Path, repo_root: Path):
    """Resolve the active binding profile, harness-order: explicit -> repo-local ->
    home -> the repo's shipped example. Returns (profile_dict|None, source|None)."""
    candidates: list[Path] = []
    explicit = mission.get("profile")
    if explicit:
        candidates.append((mission_path.parent / str(explicit)).resolve())
    candidates += [
        Path.cwd() / ".looptimal" / "profile.yaml",
        Path.home() / ".looptimal" / "profile.yaml",
    ]
    _pdir = repo_root / "profiles"
    if _pdir.is_dir():
        # Prefer the orchestrator's own shipped profile; the merged repo also ships
        # the loop-design wizard's profiles here, so fall back to any *.yaml.
        candidates += sorted(_pdir.glob("looptimal*.yaml")) or sorted(_pdir.glob("*.yaml"))
    for c in candidates:
        try:
            if c.is_file():
                return as_dict(load_config(c)), c
        except (TinyYamlError, OSError):
            continue
    return None, None


def capability_profiles(mission: dict[str, Any], mission_dir: Path, repo_root: Path) -> set[str]:
    profiles: set[str] = set()
    cm = mission.get("capability_manifest")
    if isinstance(cm, dict):
        profiles.update(str(k) for k in cm.keys())
    else:
        for entry in as_list(cm):
            if isinstance(entry, str):
                profiles.add(entry)
            elif isinstance(entry, dict):
                for key in ("id", "name", "capability", "profile"):
                    if entry.get(key):
                        profiles.add(str(entry[key]))
    for root in {repo_root, mission_dir}:
        personas = root / "personas"
        if personas.is_dir():
            for p in personas.iterdir():
                if p.is_file():
                    profiles.add(p.stem)
    pdir = repo_root / "profiles"
    if pdir.is_dir():
        for pf in pdir.glob("*.yaml"):
            try:
                reg = as_dict(as_dict(load_config(pf)).get("registry"))
            except (TinyYamlError, OSError):
                continue
            profiles.update(str(k) for k in reg.keys())
    return profiles


def human_gate_required(mission: dict[str, Any]) -> bool:
    g = mission.get("human_go_gate")
    if isinstance(g, bool):
        return g
    if isinstance(g, dict):
        return bool(g.get("required"))
    return False


def lint(mission_path: Path, repo_root: Path | None = None) -> tuple[bool, list[str]]:
    repo_root = (repo_root or Path(__file__).resolve().parent.parent).resolve()
    findings: list[str] = []
    mission_path = mission_path.resolve()

    try:
        mission = as_dict(load_config(mission_path))
    except (TinyYamlError, OSError) as exc:
        return False, [f"cannot parse mission: {exc}"]

    for key in REQUIRED_MISSION_KEYS:
        if key not in mission:
            findings.append(f"mission missing required key: {key}")

    contract_ref = mission.get("contract_ref")
    if not contract_ref:
        return False, findings + ["mission has no contract_ref"]
    contract_path = (mission_path.parent / str(contract_ref)).resolve()
    if ".." in str(contract_ref).replace("\\", "/").split("/"):
        findings.append(f"contract_ref must not traverse upward: {contract_ref}")
    try:
        contract = as_dict(load_config(contract_path))
    except (TinyYamlError, OSError) as exc:
        return False, findings + [f"referenced contract not loadable ({contract_path}): {exc}"]

    # --- contract_hash is the canonical hash of the sealed contract (no tampering) ---
    canonical = canonical_contract_hash(contract)
    if normalize_hash(contract.get("contract_hash")) != canonical:
        findings.append("contract.contract_hash is not the canonical hash of the contract "
                        "(tampered, drifted, or unstamped)")
    if normalize_hash(mission.get("contract_hash")) != canonical:
        findings.append("mission.contract_hash does not match the canonical contract hash")

    suite = as_dict(contract.get("acceptance_suite"))
    if str(suite.get("provenance") or "").strip().lower() != "framer":
        findings.append("acceptance_suite.provenance must be 'framer'")

    writable = executor_writable_roots(mission)
    if not is_sealed(suite.get("sealed_path"), writable):
        findings.append(f"acceptance_suite.sealed_path is not sealed (executor-writable or missing): "
                        f"{suite.get('sealed_path')!r}")
    if not is_sealed(contract_ref, writable):
        findings.append(f"contract_ref is not on a sealed path: {contract_ref!r}")

    criteria = as_list(suite.get("criteria"))
    if not criteria:
        findings.append("acceptance_suite has no criteria (>=1 required)")
    seen_ids: set[str] = set()
    for idx, raw in enumerate(criteria):
        c = as_dict(raw)
        cid = str(c.get("id") or f"criteria[{idx}]")
        if cid in seen_ids:
            findings.append(f"duplicate criterion id: {cid}")
        seen_ids.add(cid)
        if is_noop_command(c.get("external_check")):
            findings.append(f"criterion {cid}: external_check is missing or a no-op command")
        elif not any(is_sealed(p, writable) for p in candidate_paths(c.get("external_check"))):
            findings.append(f"criterion {cid}: external_check must invoke a sealed oracle script "
                            "(no sealed path argument)")
        if not c.get("oracle"):
            findings.append(f"criterion {cid}: no oracle bound (every criterion must bind an oracle)")
        gm = str(c.get("green_means") or "")
        if not gm:
            findings.append(f"criterion {cid}: green_means is empty")
        elif SYMPTOM_PATTERN.search(gm) or SELF_GRADE_RE.search(gm):
            findings.append(f"criterion {cid}: green_means asserts a symptom/self-grade, not an outcome: {gm!r}")
        if str(c.get("asserts") or "").strip().lower() not in {"outcome", ""}:
            findings.append(f"criterion {cid}: asserts must be 'outcome'")

    # --- per-lane oracle sealing + ratchet scope ---
    for lane in as_list(mission.get("lanes")):
        ln = as_dict(lane)
        lid = ln.get("id", "<lane>")
        oracle = as_dict(ln.get("oracle"))
        if oracle.get("sealed_path") and not is_sealed(oracle.get("sealed_path"), writable):
            findings.append(f"lane {lid}: oracle.sealed_path is executor-writable, not sealed: "
                            f"{oracle.get('sealed_path')!r}")
        if str(ln.get("archetype") or "").strip().lower() == "persistent-ratchet":
            scope = ln.get("scope") or oracle.get("baseline") or oracle.get("scope")
            if not scope:
                findings.append(f"lane {lid}: persistent-ratchet must pin a scope/baseline")

    # --- self-grade scan over the FULL serialized mission + contract ---
    blob = text_tree(mission) + "\n" + text_tree(contract)
    if SELF_GRADE_RE.search(blob):
        m = SELF_GRADE_RE.search(blob)
        findings.append(f"self-grading language in mission/contract: {m.group(0)!r}")

    # --- no hardcoded native-agent id in the generic mission (profiles may bind them) ---
    nm = NATIVE_AGENT_RE.search(text_tree(mission))
    if nm:
        findings.append(f"mission hardcodes a native-agent id (bind via profile instead): {nm.group(1)!r}")

    # --- capability resolution ---
    resolvable = capability_profiles(mission, mission_path.parent, repo_root)
    for t in as_list(mission.get("tasks")):
        cap = str(as_dict(t).get("capability") or "").strip()
        if cap and cap not in resolvable:
            findings.append(f"task {as_dict(t).get('id', '?')}: capability {cap!r} resolves to no persona or registry entry")

    # --- binding-layer maker != checker (executor != checker != outer-verifier) ---
    profile, _ = resolve_profile(mission, mission_path, repo_root)
    if profile is None:
        findings.append("no binding profile resolved — cannot confirm maker != checker agent binding")
    else:
        roles = as_dict(profile.get("roles"))
        lanes_cfg = as_dict(profile.get("lanes"))
        disp = as_dict(profile.get("dispatch"))

        def _agent_id(v: Any) -> str:
            if isinstance(v, dict):
                v = v.get("agent")
            return str(v or "").strip().lower()

        verifier_agent = (str(as_dict(roles.get("verifier")).get("agent") or "").strip()
                          or str(as_dict(profile.get("verifier")).get("default") or "").strip())
        mk, ck = _agent_id(disp.get("maker")), _agent_id(disp.get("checker"))
        if mk and mk == ck:
            findings.append("profile dispatch.maker == dispatch.checker (no independent checker)")
        for lane in as_list(mission.get("lanes")):
            arch = str(as_dict(lane).get("archetype") or "").strip().lower()
            lc = None
            for k, v in lanes_cfg.items():
                if str(k).strip().lower() == arch:
                    lc = as_dict(v)
                    break
            lc = lc or {}
            ea = str(as_dict(roles.get(lc.get("executor_role"))).get("agent") or "").strip()
            ca = str(as_dict(roles.get(lc.get("checker_role"))).get("agent") or "").strip()
            lid = as_dict(lane).get("id", "<lane>")
            if not (ea and ca):
                findings.append(f"lane {lid} ({arch}): profile does not bind both an executor and checker role")
                continue
            if ea == ca:
                findings.append(f"lane {lid}: executor agent == checker agent ({ea})")
            if verifier_agent and ea == verifier_agent:
                findings.append(f"lane {lid}: executor agent == outer-verifier agent ({ea})")

    # --- autonomy / irreversibles / human gate ---
    autonomy = str(mission.get("autonomy") or as_dict(mission.get("budget")).get("autonomy") or "").strip().lower()
    irreversibles = as_list(contract.get("irreversibles")) or as_list(mission.get("irreversibles"))
    if autonomy == "full" and irreversibles and not human_gate_required(mission):
        findings.append("autonomy:full with irreversible actions but no required human GO gate")

    # --- reject self-referential / meta loops ---
    obj = " ".join(str(x) for x in (contract.get("objective"), mission.get("objective"),
                                    contract.get("world_class_definition")) if x).lower()
    if any(tok in obj for tok in META_RE):
        findings.append("self-referential / meta loop (Looptimal verifying or approving itself) — Tier-0 REJECT")

    return (len(findings) == 0), findings


def run_selftest() -> int:
    """Hermetic: build a tmp repo with a profile + personas, assert a good plan is GREEN
    and that each tampering makes it RED."""
    import json as _json
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "personas").mkdir()
        (root / "personas" / "backend.md").write_text("persona", encoding="utf-8")
        (root / "profiles").mkdir()
        (root / "profiles" / "p.example.yaml").write_text(
            'harness: test\n'
            'dispatch:\n  maker: agent-x\n  checker: agent-y\n'
            'roles:\n  exec:\n    agent: agent-x\n  check:\n    agent: agent-y\n'
            '  verifier:\n    agent: agent-z\n'
            'lanes:\n  task:\n    executor_role: exec\n    checker_role: check\n',
            encoding="utf-8")
        run = root / "run"
        run.mkdir()
        (run / "sealed").mkdir()
        contract = {
            "schema_version": 1, "objective": "fix the broken thing",
            "autonomy": "checkpoint",
            "acceptance_suite": {
                "provenance": "framer",
                "sealed_path": "sealed/suite.json",
                "criteria": [{"id": "c1", "asserts": "outcome", "oracle": "repro",
                              "external_check": ["python3", "/sealed/check.py"],
                              "green_means": "the reported bug no longer reproduces under the sealed repro"}],
            },
            "irreversibles": [],
        }
        chash = canonical_contract_hash(contract)
        contract["contract_hash"] = f"sha256:{chash}"
        (run / "sealed" / "contract.yaml").write_text(_json.dumps(contract), encoding="utf-8")
        mission = {
            "schema_version": 1, "contract_ref": "sealed/contract.yaml", "contract_hash": chash,
            "capability_manifest": {"backend": {"allowed_paths": ["src/"]}},
            "human_go_gate": {"required": True}, "autonomy": "checkpoint",
            "lanes": [{"id": "L1", "archetype": "task", "oracle": {}}],
            "tasks": [{"id": "T1", "lane": "L1", "capability": "backend", "acceptance": ["c1"]}],
        }
        (run / "mission.yaml").write_text(_json.dumps(mission), encoding="utf-8")

        ok, findings = lint(run / "mission.yaml", repo_root=root)
        if not ok:
            print("SELFTEST FAIL (good plan flagged):", findings)
            return 1

        # tampering must be caught
        bad = dict(contract)
        bad["acceptance_suite"] = dict(contract["acceptance_suite"])
        bad["acceptance_suite"]["criteria"] = [dict(contract["acceptance_suite"]["criteria"][0])]
        bad["acceptance_suite"]["criteria"][0]["external_check"] = ["/bin/true"]
        bad["contract_hash"] = f"sha256:{canonical_contract_hash(bad)}"
        (run / "sealed" / "contract.yaml").write_text(_json.dumps(bad), encoding="utf-8")
        m2 = dict(mission); m2["contract_hash"] = canonical_contract_hash(bad)
        (run / "mission.yaml").write_text(_json.dumps(m2), encoding="utf-8")
        ok2, _ = lint(run / "mission.yaml", repo_root=root)
        if ok2:
            print("SELFTEST FAIL (no-op external_check passed)")
            return 1

    print("SELFTEST GREEN")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a Looptimal mission.yaml and its sealed contract.")
    ap.add_argument("path", nargs="?", help="Path to mission.yaml")
    ap.add_argument("--selftest", action="store_true", help="Run built-in self-test")
    args = ap.parse_args(argv)
    if args.selftest:
        return run_selftest()
    if not args.path:
        ap.error("path to mission.yaml is required (or use --selftest)")
    ok, findings = lint(Path(args.path))
    if ok:
        print("GREEN\nmission and contract passed Looptimal lint")
        return 0
    print("RED")
    for f in findings:
        print(f"RED: {f}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
