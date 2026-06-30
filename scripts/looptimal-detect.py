#!/usr/bin/env python3
"""looptimal-detect.py — print the resolved Looptimal binding for this environment.

Resolution order (identical to the linter's): ./.looptimal/profile.yaml ->
~/.looptimal/profile.yaml -> the shipped profiles/*.example.yaml -> generic defaults.
It also name-maps a few harness markers to an ecosystem hint — it never embeds binding
VALUES (those come from the profile you own), only the ecosystem NAME. Stdlib-only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import TinyYamlError, as_dict, load_config  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MARKERS = [
    ("oh-my-claudecode", lambda: (Path.cwd() / ".omc").is_dir() or (Path.home() / ".claude" / "skills").is_dir()),
    ("oh-my-codex", lambda: (Path.cwd() / ".omx").is_dir() or (Path.home() / ".codex" / "skills").is_dir()),
    ("openclaw", lambda: (Path.home() / ".openclaw" / "skills").is_dir()),
    ("opencode", lambda: (Path.cwd() / ".opencode").is_dir() or (Path.home() / ".config" / "opencode").is_dir()),
]
GENERIC = {
    "harness": "generic", "state_dir": "loops/<slug>", "marker_path": "",
    "verifier": {"default": "scripts/verify-outcome.py (separate context)"},
    "dispatch": {"maker": "generic sub-agent", "checker": "separate generic sub-agent"},
    "runner": "run-this-loop.sh",
}


def resolve() -> tuple[dict, str]:
    for c in (Path.cwd() / ".looptimal" / "profile.yaml",
              Path.home() / ".looptimal" / "profile.yaml"):
        if c.is_file():
            try:
                return as_dict(load_config(c)), str(c)
            except (TinyYamlError, OSError):
                continue
    pdir = REPO / "profiles"
    # Prefer the orchestrator's own shipped profile; the merged repo also ships
    # the loop-design wizard's profiles in this dir, so fall back to any *.yaml.
    _shipped = (sorted(pdir.glob("looptimal*.yaml")) or sorted(pdir.glob("*.yaml"))) if pdir.is_dir() else []
    for c in _shipped:
        try:
            return as_dict(load_config(c)), f"{c} (shipped example — copy to ~/.looptimal/profile.yaml and edit)"
        except (TinyYamlError, OSError):
            continue
    return GENERIC, "generic defaults"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Show the resolved Looptimal binding.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    ecosystems = [name for name, probe in MARKERS if probe()]
    profile, source = resolve()
    if args.json:
        print(json.dumps({"ecosystems": ecosystems, "source": source, "profile": profile}, indent=2))
        return 0
    disp = as_dict(profile.get("dispatch"))
    print(f"ecosystem markers : {', '.join(ecosystems) or 'none detected'}")
    print(f"binding source    : {source}")
    print(f"state_dir         : {profile.get('state_dir')}")
    print(f"verifier.default  : {as_dict(profile.get('verifier')).get('default')}")
    print(f"dispatch.maker    : {disp.get('maker')}")
    print(f"dispatch.checker  : {disp.get('checker')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
