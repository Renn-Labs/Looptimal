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

_LOOPTIMAL_SUBCOMMANDS = {
    "detect": ("looptimal-detect", False),
    "doctor": ("looptimal-doctor", False),
    "frame-ingest": ("looptimal-frame-ingest", False),
    "graph": ("looptimal-graph", True),
    "library": ("loopprint-library", True),
    "lint": ("looptimal-lint", False),
    "persona-promote": ("looptimal-persona-promote", False),
    "verify-outcome": ("verify-outcome", False),
}

_LOOPPRINT_SUBCOMMANDS = {
    "detect": ("loopprint-detect", True),
    "doctor": ("loopprint-doctor", True),
    "library": ("loopprint-library", True),
    "lint": ("loopprint-lint", True),
    "ls": ("loopprint-ls", True),
    "report": ("loopprint-report", False),
    "skillify": ("loopprint-skillify", True),
    "update": ("loopprint-update", True),
}


def _load(script_stem: str):
    path = _SCRIPTS_DIR / f"{script_stem}.py"
    spec = importlib.util.spec_from_file_location(script_stem.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path} (not found or not a valid module)")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _print_group_usage(binary: str, commands: dict[str, tuple[str, bool]], examples: list[str]) -> None:
    joined = ", ".join(sorted(commands))
    body = "\n".join(f"  {example}" for example in examples)
    print(
        f"usage: {binary} <command> [args...]\n"
        f"commands: {joined}\n\n"
        "Examples:\n"
        f"{body}"
    )


def _run_no_arg(script_stem: str) -> None:
    """For scripts whose main() takes no argument (argparse reads sys.argv itself)."""
    raise SystemExit(_load(script_stem).main())


def _run_with_argv(script_stem: str) -> None:
    """For scripts whose main(argv) explicitly takes sys.argv — replicates each
    script's own `if __name__ == "__main__":` call convention exactly."""
    raise SystemExit(_load(script_stem).main(sys.argv))


def _print_loopprint_usage() -> None:
    _print_group_usage(
        "loopprint",
        _LOOPPRINT_SUBCOMMANDS,
        [
            "loopprint ls",
            "loopprint library search secret",
            "loopprint lint examples/ci-triage/loop-spec.yaml",
            "loopprint doctor",
        ],
    )


def _print_looptimal_usage() -> None:
    _print_group_usage(
        "looptimal",
        _LOOPTIMAL_SUBCOMMANDS,
        [
            "looptimal graph starters",
            "looptimal graph init my-graph --starter verified-code-change",
            "looptimal verify-outcome --selftest",
            "looptimal library search secret",
            "looptimal lint mission.yaml",
            "looptimal doctor",
        ],
    )


def _run_script_with_args(script_stem: str, args: list[str], *, takes_argv: bool) -> None:
    """Run a script as if its own console binary had received args."""
    old_argv = sys.argv[:]
    sys.argv = [script_stem, *args]
    try:
        module = _load(script_stem)
        if takes_argv:
            raise SystemExit(module.main(sys.argv))
        raise SystemExit(module.main())
    finally:
        sys.argv = old_argv


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


def looptimal() -> None:
    args = sys.argv[1:]
    if not args:
        _print_looptimal_usage()
        raise SystemExit(2)
    if args[0] in {"-h", "--help"}:
        _print_looptimal_usage()
        raise SystemExit(0)

    command = args[0]
    try:
        script_stem, takes_argv = _LOOPTIMAL_SUBCOMMANDS[command]
    except KeyError:
        print(f"looptimal: unknown command {command!r}", file=sys.stderr)
        _print_looptimal_usage()
        raise SystemExit(2)

    _run_script_with_args(script_stem, args[1:], takes_argv=takes_argv)


# --- grouped loopprint CLI: `loopprint ls`, `loopprint lint`, ... ---
def loopprint() -> None:
    args = sys.argv[1:]
    if not args:
        _print_loopprint_usage()
        raise SystemExit(2)
    if args[0] in {"-h", "--help"}:
        _print_loopprint_usage()
        raise SystemExit(0)

    command = args[0]
    try:
        script_stem, takes_argv = _LOOPPRINT_SUBCOMMANDS[command]
    except KeyError:
        print(f"loopprint: unknown command {command!r}", file=sys.stderr)
        _print_loopprint_usage()
        raise SystemExit(2)

    _run_script_with_args(script_stem, args[1:], takes_argv=takes_argv)


# --- loopprint-* (loop-design/wizard layer): main(argv) takes sys.argv ---
def loopprint_detect() -> None:
    _run_with_argv("loopprint-detect")


def loopprint_doctor() -> None:
    _run_with_argv("loopprint-doctor")


def loopprint_lint() -> None:
    _run_with_argv("loopprint-lint")


def loopprint_library() -> None:
    _run_with_argv("loopprint-library")


def loopprint_ls() -> None:
    _run_with_argv("loopprint-ls")


def loopprint_skillify() -> None:
    _run_with_argv("loopprint-skillify")


def loopprint_report() -> None:
    _run_no_arg("loopprint-report")


def loopprint_update() -> None:
    _run_with_argv("loopprint-update")
