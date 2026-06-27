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
import sys
import re

try:
    import yaml
except ImportError:  # pragma: no cover
    print("loopprint-lint: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

VALID_PATTERNS = {"morty", "spec-driven", "performance", "hybrid"}
SCHEMA_VERSION = 1  # highest loop-spec schema version this linter understands
VALID_CHECKPOINT_MODES = {"before", "after"}

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

    return f


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
        findings = lint_spec(spec)
        # Slug uniqueness across the specs given in one run — two loops sharing a slug collide on loops/<slug>/.
        slug = spec.get("slug")
        if isinstance(slug, str) and slug.strip():
            if slug in slugs:
                findings = findings + [f"slug: '{slug}' is not unique — also used by {slugs[slug]}. "
                                       "Each loop needs its own slug (and its own directory)."]
            else:
                slugs[slug] = p
        if findings:
            bad += 1
            print(f"RED  {p}:")
            for x in findings:
                print(f"   - {x}")
        else:
            print(f"GREEN {p}: four atoms present, verifier is external, safety limit set.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
