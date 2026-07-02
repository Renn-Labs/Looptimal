"""Thin, pure-delegating console-script wrappers around scripts/*.py.

Looptimal ships as a self-contained folder of hyphenated script files
(scripts/looptimal-doctor.py etc.) so it works as a zero-config Claude Code
folder-skill with no import machinery. Hyphens aren't valid Python module
names, so pyproject.toml's [project.scripts] can't point at them directly.

This package exists ONLY to bridge that gap: each function here loads the
real script via importlib (the same technique tests/ already uses) and
calls its documented entry point, exactly as its own `if __name__ ==
"__main__":` block would. No logic lives here — scripts/*.py stays the
single source of truth. See CONTRIBUTING.md's loopprint-*/looptimal-*
naming-altitude note; this wrapper does not rename or duplicate either.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _load(script_stem: str):
    path = _SCRIPTS_DIR / f"{script_stem}.py"
    spec = importlib.util.spec_from_file_location(script_stem.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path} (not found or not a valid module)")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_no_arg(script_stem: str) -> None:
    """For scripts whose main() takes no argument (argparse reads sys.argv itself)."""
    raise SystemExit(_load(script_stem).main())


def _run_with_argv(script_stem: str) -> None:
    """For scripts whose main(argv) explicitly takes sys.argv — replicates each
    script's own `if __name__ == "__main__":` call convention exactly."""
    raise SystemExit(_load(script_stem).main(sys.argv))


# --- looptimal-* (outcome-orchestration layer): main() takes no argument ---
def doctor() -> None:
    _run_no_arg("looptimal-doctor")


def lint() -> None:
    _run_no_arg("looptimal-lint")


def detect() -> None:
    _run_no_arg("looptimal-detect")


def verify_outcome() -> None:
    _run_no_arg("verify-outcome")


def persona_promote() -> None:
    _run_no_arg("looptimal-persona-promote")


def frame_ingest() -> None:
    _run_no_arg("looptimal-frame-ingest")


# --- loopprint-* (loop-design/wizard layer): main(argv) takes sys.argv ---
def loopprint_detect() -> None:
    _run_with_argv("loopprint-detect")


def loopprint_doctor() -> None:
    _run_with_argv("loopprint-doctor")


def loopprint_lint() -> None:
    _run_with_argv("loopprint-lint")


def loopprint_ls() -> None:
    _run_with_argv("loopprint-ls")


def loopprint_skillify() -> None:
    _run_with_argv("loopprint-skillify")


def loopprint_report() -> None:
    _run_no_arg("loopprint-report")


def loopprint_update() -> None:
    _run_with_argv("loopprint-update")
