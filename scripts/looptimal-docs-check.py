#!/usr/bin/env python3
"""looptimal-docs-check — release gate against ONE narrow class of doc staleness: prose that
silently stops matching shipped reality.

This is a SIBLING to check-version-consistency.py (which guards plugin.json <-> CHANGELOG.md
<-> git tag), not a replacement — that script guards manifest/version surfaces; this one guards
DOC PROSE against two specific ways it rotted in this repo's own history (see CHANGELOG.md's
[2.1.0] "### Fixed" / "### Security" sections):

  1. A `@vX.Y.Z` git-ref pin in README.md (e.g. in a
     `uvx --from git+https://github.com/Renn-Labs/Looptimal@vX.Y.Z` quickstart command) that
     names a tag OLDER than the code it claims to run — the v2.0.0 bug: the tag predated both
     pyproject.toml and the hardened verification core the quickstart exercised, so the
     quickstart never actually worked end-to-end at that tag.

  2. Forward-reference prose ("(v1.1)", "planned for a later release", "is planned") describing
     a feature as future work in README.md/SECURITY.md when the code shows it has ALREADY
     shipped — the keyed-HMAC bug: README called the keyed-seal hardening future "(v1.1)" work
     after it had already shipped in scripts/_common.py.

This is intentionally NOT a general prose/grammar linter — it does not check spelling, tone, or
broken links. It checks exactly these two things, because these are the two ways this repo's own
docs have actually gone stale-but-still-shipped-a-claim. Check 2 is a small, reusable catalog of
{doc phrase(s), code-evidence check} pairs (FORWARD_REFERENCE_CATALOG below) — a phrase only
fires when its paired code-evidence check proves the feature has already shipped, so a genuinely
not-yet-shipped feature described as future work is never a false positive. Add a new entry to
the catalog for a future instance of this same bug class; don't hardcode a second special case.

Usage:
  python3 scripts/looptimal-docs-check.py                # scan the real repo (default)
  python3 scripts/looptimal-docs-check.py --root DIR      # scan a different tree (tests only)

Exit 0 = GREEN (no doc rot found), 1 = RED (see the printed FAIL lines for doc:line specifics).
Stdlib-only; no third-party deps, no network.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import read_changelog_top_version  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Check 1 — every "@vX.Y.Z" git-ref pin in README.md must match the CURRENT
# top CHANGELOG.md version (the v2.0.0 phantom-quickstart bug).
# --------------------------------------------------------------------------- #
_VERSION_PIN_RE = re.compile(r"@v(\d+\.\d+\.\d+)\b")


def check_readme_version_pins(root: Path, current_version: str) -> list[str]:
    """Every `@vX.Y.Z` pin in README.md (quickstart commands, prose mentions of the pin) must
    equal `current_version` (CHANGELOG.md's top entry). A pin naming an OLDER tag is exactly the
    v2.0.0 bug: the README's quickstart resolved against a tag that predated the code it ran.
    Returns a list of FAIL message strings (empty if clean)."""
    readme = root / "README.md"
    if not readme.is_file():
        return [f"README.md: file not found at {readme}"]
    failures: list[str] = []
    for lineno, line in enumerate(readme.read_text(encoding="utf-8").splitlines(), start=1):
        for m in _VERSION_PIN_RE.finditer(line):
            pinned = m.group(1)
            if pinned != current_version:
                failures.append(
                    f"README.md:{lineno}: pinned ref '@v{pinned}' does not match the current "
                    f"top CHANGELOG.md version '{current_version}' — line reads: {line.strip()!r}"
                )
    return failures


# --------------------------------------------------------------------------- #
# Check 2 — a catalog of {forward-reference phrases, code-evidence check} pairs.
# A phrase describing a feature as future work is stale prose once the paired
# code-evidence check proves the feature has ALREADY shipped (the keyed-HMAC bug).
# --------------------------------------------------------------------------- #
def _keyed_hmac_seal_has_shipped(root: Path) -> bool:
    """Objective, checkable evidence that the keyed-HMAC contract-hash hardening has shipped:
    scripts/_common.py defines resolve_framer_key() and a canonical_contract_hash() that accepts
    a `key` parameter, AND scripts/verify-outcome.py actually imports/calls resolve_framer_key()
    — proof the feature is wired into a real code path, not just present as dead code. This is
    deliberately about CODE, not prose — the whole point is to catch prose that has drifted from
    what the code actually does. Returns False (treated as "not confirmed shipped", i.e. this
    catalog entry is skipped) if either source file is missing/unreadable, so this never crashes
    a minimal test fixture that only cares about exercising check 1."""
    try:
        common_src = (root / "scripts" / "_common.py").read_text(encoding="utf-8")
        verify_src = (root / "scripts" / "verify-outcome.py").read_text(encoding="utf-8")
    except OSError:
        return False
    defines_resolver = "def resolve_framer_key(" in common_src
    canonical_takes_key = re.search(
        r"def canonical_contract_hash\(.*?\bkey\b", common_src, re.DOTALL
    ) is not None
    wired_into_checker = (
        "resolve_framer_key(" in verify_src and "canonical_contract_hash(" in verify_src
    )
    return defines_resolver and canonical_takes_key and wired_into_checker


@dataclass(frozen=True)
class ForwardReferenceEntry:
    """One {doc phrase(s), code-evidence check} pair — the reusable shape for "a feature shipped
    but the docs still call it future work." `shipped(root)` is the objective code-evidence
    check; the catalog entry only fires when it returns True, so genuinely not-yet-shipped work
    described as future work is never flagged."""

    id: str
    description: str
    phrases: tuple[str, ...]
    proximity_terms: tuple[str, ...]
    docs: tuple[str, ...]
    shipped: Callable[[Path], bool]


FORWARD_REFERENCE_CATALOG: tuple[ForwardReferenceEntry, ...] = (
    ForwardReferenceEntry(
        id="keyed-hmac-seal",
        description=(
            "cryptographic keyed-HMAC contract-hash hardening "
            "(scripts/_common.py resolve_framer_key()/canonical_contract_hash())"
        ),
        phrases=("(v1.1)", "planned for a later release", "is planned"),
        proximity_terms=("keyed", "hmac", "cryptographic"),
        docs=("README.md", "SECURITY.md"),
        shipped=_keyed_hmac_seal_has_shipped,
    ),
    # Add a new entry here for a future instance of the SAME bug class (a feature ships, prose
    # still calls it future work) — don't hand-roll a second special case in the check functions.
)


def _iter_paragraphs(text: str) -> Iterator[tuple[int, list[str]]]:
    """Yield (1-indexed start line, lines) for each run of consecutive non-blank lines in
    `text`. A forward-reference phrase and its proximity term must land in the same paragraph to
    count as a hit — this mirrors how the actual bug read (one sentence naming both the
    mechanism and the "planned"/"(v1.1)" qualifier), without requiring a fragile same-line or
    character-window match that markdown's hand-wrapped paragraphs would break."""
    start: int | None = None
    buf: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            if start is None:
                start = lineno
            buf.append(line)
        else:
            if buf:
                assert start is not None
                yield start, buf
            start, buf = None, []
    if buf:
        assert start is not None
        yield start, buf


def check_forward_references(root: Path) -> list[str]:
    """Check every FORWARD_REFERENCE_CATALOG entry against its target docs. An entry only fires
    when its `shipped` code-evidence check returns True. Returns a list of FAIL message strings
    (empty if clean)."""
    failures: list[str] = []
    for entry in FORWARD_REFERENCE_CATALOG:
        if not entry.shipped(root):
            continue  # genuinely still future work -- the forward-reference language is honest
        for doc_name in entry.docs:
            doc_path = root / doc_name
            if not doc_path.is_file():
                continue
            text = doc_path.read_text(encoding="utf-8")
            for start_line, lines in _iter_paragraphs(text):
                para_low = "\n".join(lines).lower()
                phrase_hit = next((p for p in entry.phrases if p.lower() in para_low), None)
                term_hit = next((t for t in entry.proximity_terms if t.lower() in para_low), None)
                if not (phrase_hit and term_hit):
                    continue
                # Prefer the specific physical line the phrase itself sits on over the
                # paragraph's first line, so the FAIL message points at an exact line.
                hit_line, hit_text = start_line, lines[0]
                for offset, line in enumerate(lines):
                    if phrase_hit.lower() in line.lower():
                        hit_line, hit_text = start_line + offset, line
                        break
                failures.append(
                    f"{doc_name}:{hit_line}: stale forward-reference language for "
                    f"'{entry.description}' — found {phrase_hit!r} near {term_hit!r} in the "
                    f"same paragraph, but the code shows this feature has already shipped "
                    f"(catalog id: {entry.id!r}). Line reads: {hit_text.strip()!r}"
                )
    return failures


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(
        description="Guard README.md/SECURITY.md against two specific classes of doc rot.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--root",
        help="repo root to scan (default: this script's own repo — override only for tests)",
    )
    parsed = ap.parse_args(args)
    root = Path(parsed.root).resolve() if parsed.root else ROOT

    try:
        current_version = read_changelog_top_version(root / "CHANGELOG.md")
    except (OSError, ValueError) as exc:
        print(f"looptimal-docs-check: RED — {exc}", file=sys.stderr)
        return 1

    failures: list[str] = []
    failures += check_readme_version_pins(root, current_version)
    failures += check_forward_references(root)

    if failures:
        print(
            f"looptimal-docs-check: RED — {len(failures)} doc-rot issue(s) found "
            f"(current version: {current_version}):",
            file=sys.stderr,
        )
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    print(
        f"looptimal-docs-check: GREEN — README.md version pins match CHANGELOG "
        f"{current_version}; no stale forward-reference language found"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
