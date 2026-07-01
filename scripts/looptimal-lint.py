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
    VALID_GATE_TYPES,
    VALID_VISIBILITIES,
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
    resolve_framer_key,
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


def lint(mission_path: Path, repo_root: Path | None = None,
        framer_key: bytes | None = None) -> tuple[bool, list[str], list[str]]:
    """Returns (ok, findings, advisories). `findings` are blocking (RED); `advisories` are
    non-blocking nudges (never affect `ok`) — same distinction verify-outcome.py's own
    `advisories` field uses, and the blocking/advisory split loopprint-lint.py already
    established for critic-panel checks."""
    repo_root = (repo_root or Path(__file__).resolve().parent.parent).resolve()
    findings: list[str] = []
    advisories: list[str] = []
    mission_path = mission_path.resolve()

    try:
        mission = as_dict(load_config(mission_path))
    except (TinyYamlError, OSError) as exc:
        return False, [f"cannot parse mission: {exc}"], []

    for key in REQUIRED_MISSION_KEYS:
        if key not in mission:
            findings.append(f"mission missing required key: {key}")

    contract_ref = mission.get("contract_ref")
    if not contract_ref:
        return False, findings + ["mission has no contract_ref"], advisories
    contract_path = (mission_path.parent / str(contract_ref)).resolve()
    if ".." in str(contract_ref).replace("\\", "/").split("/"):
        findings.append(f"contract_ref must not traverse upward: {contract_ref}")
    try:
        contract = as_dict(load_config(contract_path))
    except (TinyYamlError, OSError) as exc:
        return False, findings + [f"referenced contract not loadable ({contract_path}): {exc}"], advisories

    # --- contract_hash is the canonical hash of the sealed contract (no tampering) ---
    # sealed_dir-folding is coupled to framer_key being set, same rule verify-outcome.py
    # follows — an unkeyed check must keep validating a contract sealed the old way.
    canonical = canonical_contract_hash(
        contract, key=framer_key,
        sealed_dir=contract_path.parent if framer_key else None,
        exclude=contract_path if framer_key else None,
    )
    if normalize_hash(contract.get("contract_hash")) != canonical:
        findings.append("contract.contract_hash is not the canonical hash of the contract "
                        "(tampered, drifted, or unstamped)")
    if normalize_hash(mission.get("contract_hash")) != canonical:
        findings.append("mission.contract_hash does not match the canonical contract hash")
    if framer_key is None and str(contract.get("sensitivity") or "").strip().lower() == "high":
        advisories.append(
            "sensitivity: high with no --key-file / LOOPTIMAL_FRAMER_KEY configured — the "
            "contract hash is an unkeyed sha256 self-digest; a maker who can write the sealed "
            "contract can also recompute it. A keyed run is strongly recommended here.")

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
        vis = c.get("visibility")
        if vis is not None and str(vis).strip().lower() not in VALID_VISIBILITIES:
            findings.append(f"criterion {cid}: visibility must be one of "
                            f"{VALID_VISIBILITIES} (got {vis!r})")
        gt = c.get("gate_type")
        if gt is not None and str(gt).strip().lower() not in VALID_GATE_TYPES:
            findings.append(f"criterion {cid}: gate_type must be one of "
                            f"{VALID_GATE_TYPES} (got {gt!r})")

    # sensitivity: high missions get a soft nudge toward at least one holdout criterion — never
    # a REJECT (that stays reserved for the Tier-0 loop-worthiness gate), just a nudge: a maker
    # that can read every criterion tends to aim at the gate, not the fix.
    if str(contract.get("sensitivity") or "").strip().lower() == "high":
        checker_only = sum(
            1 for raw in criteria
            if str(as_dict(raw).get("visibility") or "maker-visible").strip().lower() == "checker-only"
        )
        if checker_only == 0:
            advisories.append(
                "sensitivity: high with zero checker-only criteria — every acceptance check is "
                "maker-visible. Consider marking at least one criterion visibility: checker-only "
                "so Stage-5 Execute context-assembly can hold it back from the maker (see "
                "references/pipeline.md).")

    # A suite where every criterion explicitly declares gate_type: soft has no deterministic
    # floor at all — an unset gate_type defaults to hard, so this only fires when the framer
    # went out of their way to mark ALL of them soft (a rubric/human-vote-only suite is a real,
    # legitimate pattern for subjective quality — just one worth a nudge, not a REJECT).
    if criteria and all(
        str(as_dict(raw).get("gate_type") or "hard").strip().lower() == "soft" for raw in criteria
    ):
        advisories.append(
            "every criterion in this suite is gate_type: soft — no deterministic/re-runnable "
            "gate at all. A soft-only suite (rubric/human-vote judgment) is legitimate for "
            "subjective quality, but has no floor a maker's self-report can't also satisfy by "
            "coincidence. Consider pairing at least one hard gate if any part of the goal is "
            "machine-checkable — see templates/verifier-library.yaml's gate_type notes.")

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

    return (len(findings) == 0), findings, advisories


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

        ok, findings, advisories = lint(run / "mission.yaml", repo_root=root)
        if not ok:
            print("SELFTEST FAIL (good plan flagged):", findings)
            return 1
        if advisories:
            print("SELFTEST FAIL (non-sensitive mission produced an advisory — should be silent):",
                 advisories)
            return 1

        # sensitivity: high + no key must produce the advisory prominently, and a keyed run
        # (with sealed_dir folded in) must clear it while still passing.
        sensitive = dict(contract); sensitive["sensitivity"] = "high"
        chash_s = canonical_contract_hash(sensitive)
        sensitive["contract_hash"] = f"sha256:{chash_s}"
        (run / "sealed" / "contract.yaml").write_text(_json.dumps(sensitive), encoding="utf-8")
        m_s = dict(mission); m_s["contract_hash"] = chash_s
        (run / "mission.yaml").write_text(_json.dumps(m_s), encoding="utf-8")
        _, _, adv_high = lint(run / "mission.yaml", repo_root=root)
        if not any("no --key-file" in a for a in adv_high):
            print("SELFTEST FAIL (sensitivity: high with no key produced no key advisory):", adv_high)
            return 1
        if not any("zero checker-only criteria" in a for a in adv_high):
            print("SELFTEST FAIL (sensitivity: high with no checker-only criteria produced no "
                 "holdout advisory):", adv_high)
            return 1
        demo_key = b"\x11" * 32
        chash_keyed = canonical_contract_hash(sensitive, key=demo_key,
                                              sealed_dir=(run / "sealed"),
                                              exclude=(run / "sealed" / "contract.yaml"))
        sensitive_keyed = dict(sensitive); sensitive_keyed["contract_hash"] = f"sha256:{chash_keyed}"
        (run / "sealed" / "contract.yaml").write_text(_json.dumps(sensitive_keyed), encoding="utf-8")
        m_keyed = dict(mission); m_keyed["contract_hash"] = chash_keyed
        (run / "mission.yaml").write_text(_json.dumps(m_keyed), encoding="utf-8")
        ok_keyed, findings_keyed, adv_keyed = lint(run / "mission.yaml", repo_root=root,
                                                   framer_key=demo_key)
        if not ok_keyed:
            print("SELFTEST FAIL (honest keyed contract flagged):", findings_keyed)
            return 1
        if any("no --key-file" in a for a in adv_keyed):
            print("SELFTEST FAIL (keyed run still advised about a missing key):", adv_keyed)
            return 1
        # the checker-only-criteria advisory is orthogonal to the key advisory and correctly
        # still fires here — this fixture has zero checker-only criteria regardless of keying.
        if not any("zero checker-only criteria" in a for a in adv_keyed):
            print("SELFTEST FAIL (expected the still-orthogonal holdout advisory to persist):",
                 adv_keyed)
            return 1

        # restore the plain (non-sensitive, unkeyed) contract, then tamper it — must be caught.
        (run / "sealed" / "contract.yaml").write_text(_json.dumps(contract), encoding="utf-8")
        (run / "mission.yaml").write_text(_json.dumps(mission), encoding="utf-8")
        bad = dict(contract)
        bad["acceptance_suite"] = dict(contract["acceptance_suite"])
        bad["acceptance_suite"]["criteria"] = [dict(contract["acceptance_suite"]["criteria"][0])]
        bad["acceptance_suite"]["criteria"][0]["external_check"] = ["/bin/true"]
        bad["contract_hash"] = f"sha256:{canonical_contract_hash(bad)}"
        (run / "sealed" / "contract.yaml").write_text(_json.dumps(bad), encoding="utf-8")
        m2 = dict(mission); m2["contract_hash"] = canonical_contract_hash(bad)
        (run / "mission.yaml").write_text(_json.dumps(m2), encoding="utf-8")
        ok2, _, _ = lint(run / "mission.yaml", repo_root=root)
        if ok2:
            print("SELFTEST FAIL (no-op external_check passed)")
            return 1

    print("SELFTEST GREEN")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a Looptimal mission.yaml and its sealed contract.")
    ap.add_argument("path", nargs="?", help="Path to mission.yaml")
    ap.add_argument("--selftest", action="store_true", help="Run built-in self-test")
    ap.add_argument("--key-file", help="path to a hex-encoded framer HMAC key (checker-side "
                    "only; alternative: the LOOPTIMAL_FRAMER_KEY env var). Omit to use the "
                    "original unkeyed sha256 (backward compatible, weaker).")
    args = ap.parse_args(argv)
    if args.selftest:
        return run_selftest()
    if not args.path:
        ap.error("path to mission.yaml is required (or use --selftest)")
    framer_key = resolve_framer_key(args.key_file)
    ok, findings, advisories = lint(Path(args.path), framer_key=framer_key)
    for a in advisories:
        print(f"   ~ {a}")
    if ok:
        print("GREEN\nmission and contract passed Looptimal lint")
        return 0
    print("RED")
    for f in findings:
        print(f"RED: {f}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
