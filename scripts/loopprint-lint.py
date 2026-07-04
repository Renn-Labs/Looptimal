#!/usr/bin/env python3
"""loopprint-lint — gate a generated loop-spec.yaml against the four-atom contract.

LoopPrint preaches "every loop needs an EXTERNAL verifier and a safety limit". This is the check that holds
LoopPrint's own output to that standard, so a blueprint can't ship with an empty or self-grading verifier.

Usage:
    loopprint-lint.py <loop-spec.yaml> [<more.yaml> ...]

Exit code:
    0  GREEN — every spec satisfies the contract
    1  RED   — at least one spec has a blocking defect (printed)

Requires PyYAML (`pip install pyyaml`).
"""
from __future__ import annotations
import hashlib
import os
import sys
import re

try:
    import yaml
except ImportError:  # pragma: no cover
    print("loopprint-lint: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

VALID_PATTERNS = {"morty", "spec-driven", "performance", "hybrid"}
VALID_VERIFIER_SHAPES = {"gate", "ratchet"}
SCHEMA_VERSION = 1  # highest loop-spec schema version this linter understands
VALID_CHECKPOINT_MODES = {"before", "after"}
VALID_STAGE_SUCCESS = {"gate", "ratchet"}

# Phrases that mean "the maker graded its own work" — the defect LoopPrint exists to prevent.
SELF_GRADE = re.compile(
    r"\b(looks?\s+good|seems?\s+(ok|fine|good|right)|i\s+(think|believe|feel)|"
    r"self[-\s]?(assess|grad|review|check|verif)|"
    r"the\s+(agent|model|maker|llm|assistant)\s+(say|judg|think|decid|confirm)|"
    r"claude\s+says|trust\s+me|by\s+inspection|manual\s+eyeball|good\s+enough)\b",
    re.I,
)
PLACEHOLDER = re.compile(r"<[^>]+>")


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _as_dict(v) -> dict:
    """Coerce a subtree to a dict so a malformed spec (a string/list where a map is expected) can't crash us."""
    return v if isinstance(v, dict) else {}


def _positive_int(v) -> int | None:
    """Return v as a positive int, rejecting bool (a subclass of int) and malformed values."""
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None


# Commands that "pass" without testing anything — as useless as self-grading.
TRIVIAL_GATE = {"", "true", ":", "exit 0", "exit0", "/bin/true"}


def _real_text(v):
    """A usable external-gate string: a non-blank scalar with no <placeholder>. A list/map is NOT a gate."""
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s or PLACEHOLDER.search(s):
        return None
    return s


def lint_spec(spec: dict) -> list[str]:
    """Return a list of blocking findings ([] == GREEN)."""
    f: list[str] = []

    # Goal — present, filled, not a placeholder.
    goal = spec.get("goal")
    if _is_blank(goal):
        f.append("goal: missing or empty.")
    elif PLACEHOLDER.search(str(goal)):
        f.append("goal: still contains a <placeholder> — fill it in.")

    # Pattern.
    pat = spec.get("pattern")
    if pat not in VALID_PATTERNS:
        f.append(f"pattern: '{pat}' not one of {sorted(VALID_PATTERNS)}.")

    # schema_version — optional for back-compat; if present it must be an int this linter understands.
    sv = spec.get("schema_version")
    if sv is not None:
        if not (isinstance(sv, int) and not isinstance(sv, bool) and sv >= 1):
            f.append(f"schema_version: '{sv}' is not a positive integer.")
        elif sv > SCHEMA_VERSION:
            f.append(f"schema_version: {sv} is newer than this linter supports ({SCHEMA_VERSION}) — upgrade loopprint.")

    # checkpoint_mode — optional; 'before' = authorize each step, 'after' = review each result.
    cm = spec.get("checkpoint_mode")
    if cm is not None and str(cm).strip().lower() not in VALID_CHECKPOINT_MODES:
        f.append(f"checkpoint_mode: '{cm}' must be one of {sorted(VALID_CHECKPOINT_MODES)}.")

    # State — needs a durable path.
    state = _as_dict(spec.get("state"))
    if _is_blank(state.get("path")) or PLACEHOLDER.search(str(state.get("path", ""))):
        f.append("state.path: missing or placeholder — the loop needs a durable state artifact.")

    # Verifier — the heart. Must be EXTERNAL: a real command string OR a named reviewer, and not self-grading.
    v = _as_dict(spec.get("verifier"))
    cmd = _real_text(v.get("command"))
    rev = _real_text(v.get("reviewer"))
    if not cmd and not rev:
        f.append("verifier: no external gate — set verifier.command (a test/build/lint/repro/benchmark) "
                 "or verifier.reviewer (a SEPARATE agent), as a string. A loop without an external verifier "
                 "is not a loop.")
    if cmd and cmd.lower() in TRIVIAL_GATE:
        f.append(f"verifier.command: '{cmd}' is a no-op that always passes — that's not a gate.")
    for label, val in (("verifier.command", cmd), ("verifier.reviewer", rev)):
        if val and SELF_GRADE.search(val):
            f.append(f"{label}: looks like self-grading ('{val[:50]}'). "
                     "The maker cannot be the checker — point this at an external gate.")

    # critic-panel quorum config validation (only when kind == "critic-panel").
    if v.get("kind") == "critic-panel":
        panel = _as_dict(v.get("panel"))
        n = _positive_int(panel.get("n"))
        qk = _positive_int(panel.get("quorum_k"))
        thr = panel.get("threshold")
        if n is None:
            f.append("verifier.panel.n: must be a positive integer (required for kind: critic-panel).")
        else:
            if qk is None:
                f.append("verifier.panel.quorum_k: must be a positive integer (required for kind: critic-panel).")
            elif qk > n:
                f.append(f"verifier.panel.quorum_k: {qk} > panel.n ({n}) — quorum cannot exceed the number of critics.")
        if thr is not None:
            if not (isinstance(thr, int) and not isinstance(thr, bool) and 0 <= thr <= 100):
                f.append(f"verifier.panel.threshold: '{thr}' must be an integer 0–100.")

    # Stop — must have a safety limit (max_iterations or a budget), not just a success condition.
    stop = _as_dict(spec.get("stop"))
    mi = stop.get("max_iterations")
    budget = _as_dict(stop.get("budget"))
    has_budget = any(not _is_blank(budget.get(k)) and str(budget.get(k)).lower() != "null"
                     for k in ("tokens", "wall_clock_minutes"))
    # bool is a subclass of int — reject `max_iterations: true` which would otherwise read as 1.
    mi_ok = isinstance(mi, int) and not isinstance(mi, bool) and mi > 0
    if not mi_ok and not has_budget:
        f.append("stop: no safety limit — set stop.max_iterations (positive int) and/or stop.budget. "
                 "Every loop needs a limit that ends it even if the goal is never met.")
    if mi is not None and not mi_ok:
        f.append(f"stop.max_iterations: '{mi}' is not a positive integer.")

    # Verifier shape — optional; must be a known archetype if given.
    shape = v.get("shape")
    if shape is not None:
        if str(shape).strip().lower() not in VALID_VERIFIER_SHAPES:
            f.append(f"verifier.shape: '{shape}' must be one of {sorted(VALID_VERIFIER_SHAPES)}.")
        elif str(shape).strip().lower() == "ratchet" and not has_budget:
            f.append("verifier.shape: ratchet has no finish gate — set stop.budget "
                     "(a ratchet runs until budget, not until GREEN).")

    return f


_EXEC_MAKER_RE = re.compile(
    r"(bash\s+maker\.sh|exec\s+\S*maker\.sh|source\s+maker\.sh|\.\s+maker\.sh)"
)
_PROV_RE = re.compile(r"PROVIDER\s*=\s*['\"]?(\w+)['\"]?")
_AGENT_RE = re.compile(r"\b(claude|codex|grok|gemini|aider|cursor-agent)\b")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _provider_tokens(path: str) -> set:
    try:
        txt = open(path).read()
    except OSError:
        return set()
    toks = {m.group(1).lower() for m in _PROV_RE.finditer(txt)}
    toks |= {m.group(1).lower() for m in _AGENT_RE.finditer(txt)}
    return toks


def lint_critic_panel_dir(spec_path: str, spec: dict) -> tuple:
    """Check filesystem judge≠maker integrity for critic-panel specs.

    Returns (blocking, advisory) — both empty if verifier.kind != 'critic-panel'.
    blocking entries are added to findings (RED); advisory are printed as '   ~ <msg>'
    without affecting exit code.
    """
    v = _as_dict(spec.get("verifier"))
    if v.get("kind") != "critic-panel":
        return [], []

    panel = _as_dict(v.get("panel"))
    n = _positive_int(panel.get("n"))

    blocking: list = []
    advisory: list = []

    d = os.path.dirname(os.path.abspath(spec_path))

    # Discover critic scripts (sorted, basenames only).
    try:
        critic_names = sorted(
            f for f in os.listdir(d) if re.match(r"critic-.*\.sh$", f)
        )
    except OSError:
        critic_names = []

    # BLOCKING: fewer than panel.n critics present (skip if n invalid — S2 already flags it).
    if n is not None and len(critic_names) < n:
        blocking.append(
            f"critic-panel: found {len(critic_names)} critic-*.sh but panel.n={n} "
            f"— need {n} distinct critic scripts."
        )

    maker_path = os.path.join(d, "maker.sh")
    maker_exists = os.path.isfile(maker_path)
    maker_realpath = os.path.realpath(maker_path) if maker_exists else None
    try:
        maker_sha = _sha256(maker_path) if maker_exists else None
    except OSError:
        maker_sha = None
    maker_providers = _provider_tokens(maker_path) if maker_exists else set()

    seen_shas: dict = {}  # sha -> first critic basename (identical-critics check)

    for name in critic_names:
        path = os.path.join(d, name)
        is_maker_violation = False

        # Compute sha once per critic.
        try:
            sha = _sha256(path)
        except OSError:
            sha = None

        if maker_exists:
            # BLOCKING: realpath == maker.sh (symlink alias).
            if os.path.realpath(path) == maker_realpath:
                blocking.append(
                    f"{name} is/runs maker.sh — maker cannot be its own checker."
                )
                is_maker_violation = True
            # BLOCKING: content sha == maker.sh.
            elif sha and sha == maker_sha:
                blocking.append(
                    f"{name} is/runs maker.sh — maker cannot be its own checker."
                )
                is_maker_violation = True
            else:
                # BLOCKING: script calls/execs/sources maker.sh.
                try:
                    content = open(path).read()
                except OSError:
                    content = ""
                if _EXEC_MAKER_RE.search(content):
                    blocking.append(
                        f"{name} is/runs maker.sh — maker cannot be its own checker."
                    )
                    is_maker_violation = True

        # BLOCKING: two critics identical (only for non-maker-violation critics).
        if not is_maker_violation and sha:
            if sha in seen_shas:
                blocking.append(
                    f"{seen_shas[sha]} and {name} are identical "
                    f"— critics must be independent."
                )
            else:
                seen_shas[sha] = name

        # ADVISORY: critic shares provider with maker (skip if already a maker violation).
        if not is_maker_violation and maker_exists and maker_providers:
            cp = _provider_tokens(path)
            common = cp & maker_providers
            if common:
                prov_str = ", ".join(sorted(common))
                advisory.append(
                    f"{name} uses the same provider as maker.sh "
                    f"({prov_str} — single-provider panel — weaker independence; "
                    f"point a critic at a different provider via dispatch.checker if available)."
                )

    return blocking, advisory


def lint_loop_dir(spec_path: str, spec: dict) -> tuple[list[str], list[str]]:
    """Return (blocking, advisory) findings for the loop directory containing spec_path.

    Only active when verifier.shape == 'ratchet'. Gate specs are untouched (returns [], []).
    Blocking findings cause RED. Advisory findings are informational only and do not affect exit code.
    """
    v = _as_dict(spec.get("verifier"))
    shape = str(v.get("shape", "")).strip().lower()
    if shape != "ratchet":
        return [], []

    d = os.path.dirname(os.path.abspath(spec_path))
    blocking: list[str] = []
    advisory: list[str] = []

    # --- BLOCKING: required ratchet artifacts must exist on disk ---
    baseline_path = os.path.join(d, "baseline")
    advance_path = os.path.join(d, "ratchet-advance.sh")

    if not os.path.isfile(baseline_path):
        blocking.append(
            "ratchet: no sibling 'baseline' file — commit a baseline so the gate is honest."
        )
    if not os.path.isfile(advance_path):
        blocking.append(
            "ratchet: no sibling 'ratchet-advance.sh' — ratchet needs an advance script."
        )

    # --- ADVISORY: verify.sh / maker.sh must not write the baseline ---
    # Broad pattern: any write operator on the same line as 'baseline' or '$BASELINE'.
    _WRITES_BASELINE = re.compile(
        r'(?:>>?|tee|mv|cp|sed\s+-i)[^\n]*(?:baseline|\$BASELINE)',
        re.IGNORECASE,
    )
    for name in ("verify.sh", "maker.sh"):
        path = os.path.join(d, name)
        if os.path.isfile(path):
            try:
                with open(path) as fh:
                    content = fh.read()
                if _WRITES_BASELINE.search(content):
                    advisory.append(
                        f"{name} may write baseline; only ratchet-advance.sh should "
                        f"(maker/checker must not move the bar)."
                    )
            except OSError:
                pass

    # --- ADVISORY: duplicate scripts (same realpath or identical content hash) ---
    def _sha256(path: str) -> str | None:
        try:
            with open(path, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            return None

    all_scripts = ["verify.sh", "maker.sh", "ratchet-advance.sh"]
    present = {n: os.path.join(d, n) for n in all_scripts if os.path.isfile(os.path.join(d, n))}
    names = list(present)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            same = False
            try:
                same = os.path.samefile(present[a], present[b])
            except OSError:
                pass
            if not same:
                ha, hb = _sha256(present[a]), _sha256(present[b])
                if ha and hb and ha == hb:
                    same = True
            if same:
                advisory.append(
                    f"{a} and {b} are the same script; "
                    f"maker != checker != advance must be distinct."
                )

    # --- ADVISORY: ratchet-advance.sh must not invoke an agent ---
    _AGENT_TOKEN = re.compile(r'\b(?:claude|codex|llm|gpt|aider|cursor)\b', re.IGNORECASE)
    if os.path.isfile(advance_path):
        try:
            with open(advance_path) as fh:
                content = fh.read()
            if _AGENT_TOKEN.search(content):
                advisory.append(
                    "ratchet-advance.sh must be deterministic, not an agent call."
                )
        except OSError:
            pass

    return blocking, advisory


def lint_campaign_spec(spec_path: str, spec: dict) -> tuple:
    """Validate a campaign-spec.yaml. Returns (blocking, advisory).

    Called when kind=='campaign' OR a top-level 'stages' key is detected.
    Never crashes on malformed input — returns a clean RED instead.
    """
    blocking: list[str] = []
    advisory: list[str] = []

    # kind must be "campaign"
    kind = spec.get("kind")
    if kind != "campaign":
        blocking.append(
            f"kind: must be 'campaign' (got {kind!r}) — use kind: campaign in campaign-spec.yaml."
        )

    # goal non-empty
    goal = spec.get("goal")
    if _is_blank(goal):
        blocking.append("goal: missing or empty.")

    # autonomy == checkpoint (enforced; a campaign without inter-stage checkpoints is a shell for-loop)
    autonomy = spec.get("autonomy")
    if autonomy != "checkpoint":
        blocking.append(
            f"autonomy: must be 'checkpoint' for a campaign (got {autonomy!r}); "
            "a campaign without inter-stage checkpoints is a shell for-loop, not Autopilot."
        )

    # plan file must exist on disk
    plan = spec.get("plan")
    if _is_blank(plan):
        blocking.append(
            "plan: missing — campaigns require a human plan artifact (plan.md or similar)."
        )
    else:
        spec_dir = os.path.dirname(os.path.abspath(spec_path))
        plan_path = os.path.join(spec_dir, str(plan))
        if not os.path.isfile(plan_path):
            blocking.append(
                f"plan: '{plan}' not found relative to this spec — create the campaign plan file."
            )

    # stages must be a non-empty list
    stages = spec.get("stages")
    if not isinstance(stages, list) or len(stages) == 0:
        blocking.append("stages: must be a non-empty list of stage objects.")
        return blocking, advisory  # can't validate individual stages further

    spec_dir = os.path.dirname(os.path.abspath(spec_path))
    seen_slugs: set = set()

    for i, stage in enumerate(stages):
        if not isinstance(stage, dict):
            blocking.append(
                f"stages[{i}]: must be a mapping, got {type(stage).__name__}."
            )
            continue
        label = f"stages[{i}]"

        slug = stage.get("slug")
        stage_goal = stage.get("goal")
        loop_dir = stage.get("loop_dir")
        stage_success = stage.get("stage_success")

        # slug
        if _is_blank(slug):
            blocking.append(f"{label}: 'slug' is missing or empty.")
        else:
            slug_str = str(slug)
            if slug_str in seen_slugs:
                blocking.append(
                    f"{label}: slug '{slug_str}' is not unique within this campaign "
                    "— each stage needs a distinct slug."
                )
            seen_slugs.add(slug_str)

        # goal
        if _is_blank(stage_goal):
            blocking.append(f"{label}: 'goal' is missing or empty.")

        # loop_dir — must resolve to a real leaf loop dir
        if _is_blank(loop_dir):
            blocking.append(f"{label}: 'loop_dir' is missing.")
        else:
            loop_path = os.path.join(spec_dir, str(loop_dir))
            if not os.path.isdir(loop_path):
                blocking.append(
                    f"{label}: loop_dir '{loop_dir}' does not resolve to a directory "
                    "— each stage must be a real leaf loop."
                )
            else:
                if not os.path.isfile(os.path.join(loop_path, "loop-spec.yaml")):
                    blocking.append(
                        f"{label}: loop_dir '{loop_dir}' is missing loop-spec.yaml "
                        "— each stage must be a real leaf loop."
                    )
                if not os.path.isfile(os.path.join(loop_path, "verify.sh")):
                    blocking.append(
                        f"{label}: loop_dir '{loop_dir}' is missing verify.sh "
                        "— each stage must be a real leaf loop."
                    )
                # advisory: verifier.shape / stage_success mismatch
                if (not _is_blank(stage_success)
                        and stage_success in VALID_STAGE_SUCCESS):
                    leaf_spec_path = os.path.join(loop_path, "loop-spec.yaml")
                    try:
                        with open(leaf_spec_path) as _fh:
                            leaf = yaml.safe_load(_fh)
                        if isinstance(leaf, dict):
                            leaf_shape = str(
                                _as_dict(leaf.get("verifier", {})).get("shape", "")
                            ).strip().lower()
                            if leaf_shape == "ratchet" and stage_success != "ratchet":
                                advisory.append(
                                    f"{label}: leaf loop '{loop_dir}' has verifier.shape: ratchet "
                                    f"but stage_success is '{stage_success}' — consider "
                                    f"stage_success: ratchet (OK on exit 2|6) for consistency."
                                )
                            elif leaf_shape == "gate" and stage_success == "ratchet":
                                advisory.append(
                                    f"{label}: leaf loop '{loop_dir}' has verifier.shape: gate "
                                    f"but stage_success is 'ratchet' — gate loops exit 0 on success; "
                                    f"consider stage_success: gate."
                                )
                    except Exception:
                        pass  # never crash on a malformed leaf spec

        # stage_success
        if _is_blank(stage_success):
            blocking.append(f"{label}: 'stage_success' is missing.")
        elif stage_success not in VALID_STAGE_SUCCESS:
            blocking.append(
                f"{label}: stage_success '{stage_success}' must be one of "
                f"{sorted(VALID_STAGE_SUCCESS)}."
            )

    # schema_version forward-compat advisory
    sv = spec.get("schema_version")
    if sv is not None:
        try:
            sv_int = int(sv)
            if sv_int > SCHEMA_VERSION:
                advisory.append(
                    f"schema_version: {sv_int} is newer than this linter supports "
                    f"({SCHEMA_VERSION}) — upgrade loopprint for full campaign validation."
                )
        except (TypeError, ValueError):
            pass  # type errors on schema_version are informational only for campaigns

    return blocking, advisory


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths:
        print("usage: loopprint-lint.py <loop-spec.yaml> [<more.yaml> ...]", file=sys.stderr)
        return 2
    bad = 0
    slugs: dict[str, str] = {}  # slug -> first spec path that used it (collision = shared loops/<slug>/ dir)
    for p in paths:
        try:
            with open(p) as fh:
                spec = yaml.safe_load(fh)
        except Exception as e:
            print(f"RED  {p}: cannot read/parse ({e})")
            bad += 1
            continue
        if not isinstance(spec, dict):
            print(f"RED  {p}: not a YAML mapping")
            bad += 1
            continue
        # Route campaign specs before standard loop linting.
        if spec.get("kind") == "campaign" or "stages" in spec:
            cb, ca = lint_campaign_spec(p, spec)
            if cb:
                bad += 1
                print(f"RED  {p}:")
                for x in cb:
                    print(f"   - {x}")
            else:
                print(f"GREEN {p}: campaign manifest valid — stages, plan, and autonomy present.")
            for adv in ca:
                print(f"   ~ {adv}")
            continue

        findings = lint_spec(spec)
        # Slug uniqueness across the specs given in one run — two loops sharing a slug collide on loops/<slug>/.
        slug = spec.get("slug")
        if isinstance(slug, str) and slug.strip():
            if slug in slugs:
                findings = findings + [f"slug: '{slug}' is not unique — also used by {slugs[slug]}. "
                                       "Each loop needs its own slug (and its own directory)."]
            else:
                slugs[slug] = p
        # Dir-level integrity: ratchet baseline wiring + critic-panel judge≠maker (advisory is non-failing).
        lb, la = lint_loop_dir(p, spec)
        cb, ca = lint_critic_panel_dir(p, spec)
        findings += lb + cb
        if findings:
            bad += 1
            print(f"RED  {p}:")
            for x in findings:
                print(f"   - {x}")
        else:
            print(f"GREEN {p}: four atoms present, verifier is external, safety limit set.")
        for adv in la + ca:
            print(f"   ~ {adv}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
