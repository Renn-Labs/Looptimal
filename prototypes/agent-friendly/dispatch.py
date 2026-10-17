#!/usr/bin/env python3
"""Classify a YAML file by its keys and name the lint that owns it.

Question. Can a boundary parse choose the right lint without a mass rename?

Decision rule. Keep the two script prefixes if key shapes already separate
loop-spec, mission, and campaign files. A rename is only required if the
shapes overlap.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SAMPLES = {
    ROOT / "examples" / "ci-triage" / "loop-spec.yaml": "loopprint-lint",
    ROOT / "examples" / "issue-to-pr-bugfix" / "mission.yaml": "looptimal-lint",
    ROOT / "examples" / "campaign-staged-remediation" / "campaign-spec.yaml": "loopprint-lint",
    ROOT / "library" / "secret-scan" / "loop-spec.yaml": "loopprint-lint",
}


def load_mapping(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError:
        return _tiny_keys(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _tiny_keys(path: Path) -> dict:
    keys: dict[str, bool] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line[0] in {" ", "\t", "#"}:
            continue
        if ":" in line:
            keys[line.split(":", 1)[0].strip()] = True
    return keys


def classify(doc: dict) -> str:
    keys = set(doc)
    if "contract_ref" in keys and "lanes" in keys:
        return "looptimal-lint"
    if doc.get("kind") == "campaign" or "stages" in keys:
        return "loopprint-lint"
    if "goal" in keys and ("verifier" in keys or "stop" in keys):
        return "loopprint-lint"
    return "unknown"


def main() -> int:
    rows: list[tuple[str, str, str, bool]] = []
    for path, expected in SAMPLES.items():
        got = classify(load_mapping(path))
        rows.append((str(path.relative_to(ROOT)), expected, got, got == expected))

    overlap = False
    print("path expected got ok")
    for path, expected, got, ok in rows:
        print(f"{path} {expected} {got} {ok}")
        if not ok:
            overlap = True
    print()

    if overlap:
        print("DECISION. Shapes overlap. A rename or a richer parser is required.")
        return 1

    print(
        "DECISION. Keep both prefixes. A boundary parse can name the right lint "
        "from keys, so a mass rename is not required to stop the wrong-tool class."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
