#!/usr/bin/env python3
"""loopprint-detect — resolve the active harness binding (or generic defaults).

Precedence (first found wins):
  1. ./.loopprint/profile.yaml      (repo-local binding)
  2. ~/.loopprint/profile.yaml      (your personal binding for this machine)
  3. runtime detection              (probe ecosystem MARKERS -> name a likely harness; suggest its example profile)
  4. generic defaults               (pure portable behavior)

Decoupling rule: detection maps a marker -> an ecosystem NAME (stable signal). It NEVER embeds an
ecosystem -> binding VALUES table (volatile) — those live in profiles you own. So LoopPrint needs no
release when oh-my-claudecode / OMX / SuperPowers change their conventions.

Usage: loopprint-detect.py [--cwd DIR]
Prints the effective binding and where it came from. Profile files need PyYAML; detection/defaults don't.
"""
from __future__ import annotations
import sys
import shutil
from pathlib import Path

GENERIC = {
    "harness": "generic",
    "state_dir": "loops/<slug>",
    "marker_path": "",
    "verifier": {"default": "verify.sh (a test/build/lint/repro gate)"},
    "dispatch": {"maker": "your maker step", "checker": "a SEPARATE reviewer (maker != checker)"},
    "runner": "run-this-loop.sh",
    "banner": "",
}

# Agent provider CLIs the user might have. Probed via which; purely informational.
PROVIDERS = [
    ("claude", "claude"),
    ("codex", "codex"),
    ("grok", "grok"),
    ("gemini", "gemini"),
    ("aider", "aider"),
    ("cursor-agent", "cursor-agent"),
]

# marker test -> ecosystem NAME only. Stable signals; NO binding values here.
MARKERS = [
    ("oh-my-claudecode", lambda cwd: (cwd / ".omc").is_dir() or _on_path("omc")
                                     or (Path.home() / ".claude" / "skills").is_dir()),
    ("oh-my-codex",      lambda cwd: (cwd / ".omx").is_dir() or (Path.home() / ".codex" / "skills").is_dir()),
    ("openclaw",         lambda _: _on_path("openclaw") or (Path.home() / ".openclaw" / "skills").is_dir()),
    ("hermes",           lambda _: _on_path("hermes") or (Path.home() / ".hermes" / "skills").is_dir()),
    ("opencode",         lambda cwd: (cwd / ".opencode").is_dir() or _on_path("opencode")
                                     or (Path.home() / ".config" / "opencode").is_dir()
                                     or (Path.home() / ".opencode" / "skills").is_dir()),
]


def _on_path(binary: str) -> bool:
    return shutil.which(binary) is not None


def _load_yaml(path: Path):
    try:
        import yaml
    except ImportError:
        return None
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


def resolve(cwd: Path):
    for src, p in (("repo-local .loopprint/profile.yaml", cwd / ".loopprint" / "profile.yaml"),
                   ("~/.loopprint/profile.yaml", Path.home() / ".loopprint" / "profile.yaml")):
        if p.is_file():
            data = _load_yaml(p)
            if data is None:
                return GENERIC, f"{src} found, but could not parse (PyYAML missing?) — using generic"
            if not isinstance(data, dict):
                return GENERIC, f"{src} is not a mapping — using generic"
            return data, src
    seen = [name for name, test in MARKERS if test(cwd)]
    if seen:
        return GENERIC, (f"detection: no profile, but this looks like [{', '.join(seen)}] — "
                         f"copy profiles/{seen[0]}.example.yaml to ~/.loopprint/profile.yaml to conform "
                         f"(using generic defaults until you do)")
    return GENERIC, "generic defaults (no profile, no known harness detected)"


def main(argv) -> int:
    cwd = Path.cwd()
    if "--cwd" in argv:
        cwd = Path(argv[argv.index("--cwd") + 1])
    binding, src = resolve(cwd)
    print(f"# source: {src}")
    for k in ("harness", "state_dir", "marker_path", "runner", "banner"):
        print(f"{k}: {binding.get(k, '')}")
    v = binding.get("verifier", {})
    print(f"verifier.default: {v.get('default', '') if isinstance(v, dict) else v}")
    d = binding.get("dispatch", {})
    if isinstance(d, dict):
        print(f"dispatch.maker: {d.get('maker', '')}")
        print(f"dispatch.checker: {d.get('checker', '')}")
    available = [label for label, binary in PROVIDERS if shutil.which(binary) is not None]
    print(f"provider.available: {', '.join(available) if available else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
