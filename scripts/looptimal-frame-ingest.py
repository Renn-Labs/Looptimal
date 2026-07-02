#!/usr/bin/env python3
"""looptimal-frame-ingest.py — optional Stage-0 Frame helper: surface GitHub spec-kit / AWS
Kiro artifacts already present in a target repo as CANDIDATE objective/acceptance-criteria
text. Roadmap item #17a.

Scope (precise, per ROADMAP.md item #17a — nothing else is scanned):
  GitHub spec-kit : .specify/memory/constitution.md, specs/<feature>/spec.md
  AWS Kiro        : .kiro/steering/*.md, .kiro/specs/*/requirements.md (EARS notation)

This is a PURE content-ingestion helper, by design:
  - It never imports or touches looptimal-detect.py's harness-resolution logic (no shared
    import, no shared state — this script has zero dependency on it or on scripts/_common.py).
  - It never writes a real mission/contract file. --out refuses contract.yaml / mission.yaml /
    acceptance-suite.yaml (the reserved sealed-contract filenames this repo itself uses — see
    templates/contract.yaml, templates/mission.yaml, references/pipeline.md's Stage-0 outputs).
  - It never seals anything and never invokes Frame. Everything printed/written is explicitly
    CANDIDATE text — folding any of it into a real contract's acceptance_suite.criteria[] (see
    references/schema.md) is a separate, manual, human action, every single time.

It does not implement a full EARS parser (Easy Approach to Requirements Syntax — Mavin et al.,
2009; the notation Kiro's requirements.md is written in: "WHEN <trigger> THE <system> SHALL
<response>", plus IF/WHILE/WHERE variants and the ubiquitous "<system> SHALL <response>" form
with no trigger). It extracts requirement-shaped lines with a reasonable regex catalog — EARS
trigger + SHALL/MUST, bare SHALL/MUST lines, spec-kit's FR-/SC-/NFR-NNN: ... lines, and "As a
..., I want ..., so that ..." user stories — plus, for prose-heavy documents that state intent
without itemized requirement lines (constitution.md, steering/*.md), a header+lead-line outline
as a softer fallback signal. None of it is validated, sealed, or bound to an oracle.

Exit 0 always for a scan: finding nothing is a graceful no-op, not an error, and a malformed or
unreadable artifact file is skipped (noted, not raised) rather than crashing the run. The only
non-zero exits are usage errors: an unusable directory argument, or a refused/unwritable --out
target. Stdlib-only, zero network calls.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple, TypedDict

# --------------------------------------------------------------------------------------- #
# Discovery — exactly the artifact paths ROADMAP.md item #17a names. Nothing else is
# scanned; this stays a narrow, precisely-scoped helper, not a generic markdown crawler.
# --------------------------------------------------------------------------------------- #
class SpecKitArtifacts(TypedDict):
    constitution: Path | None
    specs: list[Path]


class KiroArtifacts(TypedDict):
    steering: list[Path]
    requirements: list[Path]


def find_spec_kit_artifacts(root: Path) -> SpecKitArtifacts:
    """GitHub spec-kit: .specify/memory/constitution.md (at most one) and
    specs/<feature>/spec.md (any number of feature dirs)."""
    constitution = root / ".specify" / "memory" / "constitution.md"
    specs_dir = root / "specs"
    specs = sorted(specs_dir.glob("*/spec.md")) if specs_dir.is_dir() else []
    return {"constitution": constitution if constitution.is_file() else None, "specs": specs}


def find_kiro_artifacts(root: Path) -> KiroArtifacts:
    """AWS Kiro: .kiro/steering/*.md (any number) and .kiro/specs/*/requirements.md
    (any number of feature dirs, EARS notation)."""
    steering_dir = root / ".kiro" / "steering"
    steering = sorted(steering_dir.glob("*.md")) if steering_dir.is_dir() else []
    kiro_specs_dir = root / ".kiro" / "specs"
    requirements = sorted(kiro_specs_dir.glob("*/requirements.md")) if kiro_specs_dir.is_dir() else []
    return {"steering": steering, "requirements": requirements}


# --------------------------------------------------------------------------------------- #
# Reasonable (not exhaustive) requirement-shaped text extraction.
# --------------------------------------------------------------------------------------- #
_FENCE_RE = re.compile(r"^\s*```")
_HEADER_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
_LIST_PREFIX_RE = re.compile(r"^\s*(?:\d+[.)]\s+|[-*]\s+)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

# EARS trigger keywords (event/state/optional-feature forms) per Mavin et al.'s "Easy Approach
# to Requirements Syntax" — the notation Kiro's requirements.md is written in.
_EARS_TRIGGER_RE = re.compile(r"^(WHEN|IF|WHILE|WHERE)\b", re.IGNORECASE)
_SHALL_MUST_RE = re.compile(r"\b(SHALL|MUST)\b", re.IGNORECASE)
# spec-kit's own template shape: "FR-001: System MUST ..." / "SC-001: ..." (list markers and
# bold are already stripped by the time this runs — see _strip_list_prefix_and_bold).
_FR_ID_RE = re.compile(r"^(FR|SC|NFR)-\d+\s*:", re.IGNORECASE)
_USER_STORY_RE = re.compile(r"\bAs an?\s+.+?,\s*I want\s+.+?,\s*so that\s+.+", re.IGNORECASE)


def _strip_list_prefix_and_bold(line: str) -> str:
    line = _LIST_PREFIX_RE.sub("", line.strip())
    return _BOLD_RE.sub(r"\1", line).strip()


def extract_requirement_lines(text: str) -> list[str]:
    """Requirement-shaped lines: EARS trigger + SHALL/MUST, ubiquitous SHALL/MUST lines,
    spec-kit FR-/SC-/NFR-NNN: lines, and 'As a ..., I want ..., so that ...' user stories.
    Not a full EARS parser — a reasonable regex catalog over the documented notation. Skips
    fenced code blocks so a pasted command/config example is never mistaken for a requirement."""
    out: list[str] = []
    in_fence = False
    for raw in text.splitlines():
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = _strip_list_prefix_and_bold(raw)
        if not stripped:
            continue
        is_ears = bool(_EARS_TRIGGER_RE.match(stripped) and _SHALL_MUST_RE.search(stripped))
        is_fr = bool(_FR_ID_RE.match(stripped))
        is_ubiquitous = bool(_SHALL_MUST_RE.search(stripped))
        is_story = bool(_USER_STORY_RE.search(stripped))
        if is_ears or is_fr or is_ubiquitous or is_story:
            out.append(stripped)
    return out


def extract_section_outline(text: str) -> list[tuple[str, str]]:
    """(header, lead-line) pairs for every '##'/'###' section — the fallback signal for
    prose-heavy documents (constitution.md, steering/*.md) that state intent/principles as
    prose rather than itemized requirement lines. A header with no body text before the next
    header/fence contributes an empty lead — callers typically drop those."""
    lines = text.splitlines()
    out: list[tuple[str, str]] = []
    in_fence = False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADER_RE.match(line)
        if not m:
            continue
        title = m.group(2).strip()
        lead = ""
        for j in range(i + 1, len(lines)):
            if _FENCE_RE.match(lines[j]) or _HEADER_RE.match(lines[j]):
                break
            candidate = lines[j].strip()
            if candidate:
                lead = _strip_list_prefix_and_bold(candidate)
                break
        out.append((title, lead))
    return out


# --------------------------------------------------------------------------------------- #
# Per-artifact ingestion
# --------------------------------------------------------------------------------------- #
class Candidate(NamedTuple):
    # NamedTuple, not @dataclass: this module is loaded via importlib.util.spec_from_file_location
    # by looptimal_cli/__init__.py's console-script wrapper WITHOUT registering sys.modules first
    # -- on Python 3.12, dataclasses' string-annotation resolution (triggered by this file's own
    # `from __future__ import annotations`) needs sys.modules[cls.__module__], which is absent
    # under that loading path and raises AttributeError at class-definition time. NamedTuple has
    # no such dependency and loads fine either way.
    source: str  # display path, relative to the scan root when possible
    kind: str    # "requirement" | "user-story" | "principle" | "context"
    text: str


def _read_text(path: Path) -> str | None:
    """Defensive read: a malformed or unreadable artifact must never crash this tool — it is
    skipped (the caller then reports zero candidates for it) instead of raising."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _classify(line: str) -> str:
    return "user-story" if _USER_STORY_RE.search(line) else "requirement"


def ingest_requirement_doc(path: Path, root: Path) -> list[Candidate]:
    """specs/<feature>/spec.md and .kiro/specs/*/requirements.md: prefer itemized
    requirement-shaped lines; fall back to the section outline when a file has none (e.g. a
    spec still written as free prose)."""
    text = _read_text(path)
    if text is None:
        return []
    src = _rel(path, root)
    candidates = [Candidate(src, _classify(ln), ln) for ln in extract_requirement_lines(text)]
    if not candidates:
        candidates = [Candidate(src, "context", f"{title}: {lead}")
                      for title, lead in extract_section_outline(text) if lead]
    return candidates


def ingest_principle_doc(path: Path, root: Path) -> list[Candidate]:
    """.specify/memory/constitution.md and .kiro/steering/*.md: prose/principle documents.
    The section outline is the primary signal; any incidental requirement-shaped lines (a
    steering doc can legitimately contain a SHALL/MUST sentence) are added as a bonus."""
    text = _read_text(path)
    if text is None:
        return []
    src = _rel(path, root)
    candidates = [Candidate(src, "principle", f"{title}: {lead}")
                  for title, lead in extract_section_outline(text) if lead]
    candidates += [Candidate(src, _classify(ln), ln) for ln in extract_requirement_lines(text)]
    return candidates


# --------------------------------------------------------------------------------------- #
# Scan orchestration
# --------------------------------------------------------------------------------------- #
class ScanResult(NamedTuple):
    # NamedTuple for the same reason as Candidate above.
    root: Path
    spec_kit: SpecKitArtifacts
    kiro: KiroArtifacts
    candidates: list[Candidate]

    @property
    def found_anything(self) -> bool:
        return bool(self.spec_kit["constitution"] or self.spec_kit["specs"]
                     or self.kiro["steering"] or self.kiro["requirements"])


def scan(root: Path) -> ScanResult:
    spec_kit = find_spec_kit_artifacts(root)
    kiro = find_kiro_artifacts(root)
    candidates: list[Candidate] = []

    if spec_kit["constitution"] is not None:
        candidates += ingest_principle_doc(spec_kit["constitution"], root)
    for spec in spec_kit["specs"]:
        candidates += ingest_requirement_doc(spec, root)
    for steering_doc in kiro["steering"]:
        candidates += ingest_principle_doc(steering_doc, root)
    for req in kiro["requirements"]:
        candidates += ingest_requirement_doc(req, root)

    return ScanResult(root=root, spec_kit=spec_kit, kiro=kiro, candidates=candidates)


# --------------------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------------------- #
_BANNER = "Looptimal Frame Ingest -- CANDIDATE acceptance-criteria text (NOT sealed)"
_NOT_FOUND_MSG = (
    "No GitHub spec-kit or AWS Kiro artifacts found -- nothing to surface.\n"
    "(Looked for .specify/memory/constitution.md, specs/*/spec.md, .kiro/steering/*.md, "
    ".kiro/specs/*/requirements.md.) This is a no-op, not an error."
)
_FOOTER = (
    "Nothing above is a sealed acceptance suite. No contract.yaml / mission.yaml was read,\n"
    "written, or modified, and Stage 0 Frame was not invoked. Review each candidate, then\n"
    "manually copy/edit what belongs into your real contract's acceptance_suite.criteria[] --\n"
    "each real criterion still needs a bound oracle + external_check (see\n"
    "templates/contract.yaml and references/schema.md). Nothing here is accepted until a\n"
    "human puts it there."
)


def _file_block(path: Path, root: Path, candidates: list[Candidate]) -> list[str]:
    src = _rel(path, root)
    lines = [src]
    items = [c for c in candidates if c.source == src]
    if not items:
        lines.append("  (no requirement-shaped lines or section text extracted -- "
                      "review the file by hand)")
    for c in items:
        lines.append(f"  [{c.kind}] {c.text}")
    return lines


def render_report(result: ScanResult) -> str:
    lines = [_BANNER, "=" * len(_BANNER), f"scanned: {result.root}", ""]

    if not result.found_anything:
        lines.append(_NOT_FOUND_MSG)
        return "\n".join(lines) + "\n"

    if result.spec_kit["constitution"] or result.spec_kit["specs"]:
        lines.append("GitHub spec-kit")
        lines.append("-" * len("GitHub spec-kit"))
        if result.spec_kit["constitution"] is not None:
            lines += _file_block(result.spec_kit["constitution"], result.root, result.candidates)
        for spec in result.spec_kit["specs"]:
            lines += _file_block(spec, result.root, result.candidates)
        lines.append("")

    if result.kiro["steering"] or result.kiro["requirements"]:
        lines.append("AWS Kiro")
        lines.append("-" * len("AWS Kiro"))
        for steering_doc in result.kiro["steering"]:
            lines += _file_block(steering_doc, result.root, result.candidates)
        for req in result.kiro["requirements"]:
            lines += _file_block(req, result.root, result.candidates)
        lines.append("")

    lines.append("=" * len(_BANNER))
    lines.append(_FOOTER)
    return "\n".join(lines) + "\n"


def result_to_json(result: ScanResult) -> dict[str, object]:
    spec_kit = result.spec_kit
    kiro = result.kiro
    constitution = spec_kit["constitution"]
    return {
        "root": str(result.root),
        "found_anything": result.found_anything,
        "sealed": False,
        "note": "CANDIDATE text only -- never auto-sealed into a contract; folding this into "
                "a real acceptance suite is a manual, human action.",
        "spec_kit": {
            "constitution": _rel(constitution, result.root) if constitution else None,
            "specs": [_rel(p, result.root) for p in spec_kit["specs"]],
        },
        "kiro": {
            "steering": [_rel(p, result.root) for p in kiro["steering"]],
            "requirements": [_rel(p, result.root) for p in kiro["requirements"]],
        },
        "candidates": [{"source": c.source, "kind": c.kind, "text": c.text}
                        for c in result.candidates],
    }


# --------------------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------------------- #
# Reserved sealed-contract filenames this repo itself uses (templates/contract.yaml,
# templates/mission.yaml, references/pipeline.md's sealed/acceptance-suite.yaml output) --
# refusing to let --out silently double as one of these is the concrete enforcement of "never
# auto-modify a real mission/contract file" for the one write path this script has.
_RESERVED_OUT_NAMES = {"contract.yaml", "mission.yaml", "acceptance-suite.yaml"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Surface GitHub spec-kit / AWS Kiro artifacts as CANDIDATE Stage-0 Frame "
                     "objective/acceptance-criteria text. Never writes or seals a real contract."
    )
    ap.add_argument("directory", nargs="?", default=Path("."), type=Path,
                     help="Directory to scan for spec-kit / Kiro artifacts (default: cwd)")
    ap.add_argument("--out", type=Path, default=None,
                     help="Write the candidate summary to this path instead of stdout")
    ap.add_argument("--json", action="store_true",
                     help="Emit machine-readable JSON instead of the human-readable summary")
    args = ap.parse_args(argv)

    root = args.directory.resolve()
    if not root.is_dir():
        print(f"RED: not a directory: {root}", file=sys.stderr)
        return 2

    if args.out is not None and args.out.name.lower() in _RESERVED_OUT_NAMES:
        print(
            f"RED: refusing to write to {args.out} -- {args.out.name!r} is a reserved sealed-"
            "contract filename in this repo's own convention (see templates/contract.yaml, "
            "templates/mission.yaml). This tool only ever produces CANDIDATE text; pick a "
            "different --out path and fold the result into your real contract by hand.",
            file=sys.stderr,
        )
        return 2

    result = scan(root)
    output = (json.dumps(result_to_json(result), indent=2) + "\n") if args.json \
        else render_report(result)

    if args.out is not None:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(output, encoding="utf-8")
        except OSError as exc:
            print(f"RED: could not write {args.out}: {exc}", file=sys.stderr)
            return 1
        print(f"wrote candidate summary to {args.out} ({len(result.candidates)} candidate(s))")
    else:
        sys.stdout.write(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
