#!/usr/bin/env python3
"""loopprint-library — search, smoke-verify, and install loops from the library/ catalog.

Loop-spec altitude tooling (loopprint- prefix): shells out to existing gates, never reimplements them.
Stdlib plus optional PyYAML only; no network imports. Uses subprocess for git and bash only.

Subcommands:
  search [query] [--dir DIR]   Walk */loop-spec.yaml; substring-match slug, goal, pattern.
  verify SLUG_OR_DIR           Smoke-run verify.sh once against the consumer repo root.
  install SLUG --dest DIR      Lint-gate, smoke-verify, then copy the bundle into DEST/SLUG/.

Exit codes:
    0  success — search printed results; verify/install classified GREEN or RED (a real verdict)
    1  refusal or failure — lint findings; CANT_EXECUTE; destination exists without --force
    2  usage error or missing PyYAML

Trust boundary: ``verify`` runs a loop's verify.sh with no lint pre-check; containment relies on
trusting the library source (first-party catalog only). ``install`` adds loop-spec lint and a
``bash -n`` syntax gate before smoke-running verify.sh.

The install-verdict.json written by ``install`` is a LOCAL smoke-run result for this environment.
It is explicitly NOT the signed receipt from references/receipt.md (that pins a sealed Stage-6
evidence bundle; this record only captures one verify.sh exit against DEST's repo root).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


def _load_lint_spec():
    lint_path = Path(__file__).resolve().parent / "loopprint-lint.py"
    spec = importlib.util.spec_from_file_location("loopprint_lint", lint_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load lint module from {lint_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.lint_spec


def _script_repo() -> Path:
    return Path(__file__).resolve().parent.parent


def _consumer_repo_root(start: Path) -> Path:
    """Nearest git worktree root above start, else start resolved."""
    resolved = start.resolve()
    cur = resolved if resolved.is_dir() else resolved.parent
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    return resolved


def _library_roots(dir_arg: str | None = None) -> list[Path]:
    cwd = Path.cwd()
    script_repo = _script_repo()
    candidates: list[Path] = []
    if dir_arg:
        p = Path(dir_arg)
        candidates.append(p if p.is_absolute() else cwd / p)
    candidates.append(cwd / "library")
    candidates.append(script_repo / "library")
    seen: set[Path] = set()
    roots: list[Path] = []
    for c in candidates:
        resolved = c.resolve()
        if resolved not in seen:
            seen.add(resolved)
            roots.append(resolved)
    return roots


def _scan_library(base: Path) -> list[dict]:
    """slug -> metadata for each immediate child dir holding loop-spec.yaml (loopprint-ls idiom)."""
    rows: list[dict] = []
    if not base.is_dir():
        return rows
    for sub in sorted(base.iterdir()):
        if not sub.is_dir():
            continue
        spec_path = sub / "loop-spec.yaml"
        if not spec_path.is_file():
            continue
        spec = _read_spec(spec_path)
        if spec is None:
            continue
        slug = str(spec.get("slug") or sub.name).strip() or sub.name
        rows.append({
            "slug": slug,
            "goal": _one_line(spec.get("goal")),
            "pattern": str(spec.get("pattern") or ""),
            "dir": str(sub.resolve()),
            "spec_path": str(spec_path.resolve()),
        })
    return rows


def _one_line(text: object) -> str:
    if text is None:
        return ""
    return " ".join(str(text).split())


def _read_spec(spec_path: Path) -> dict | None:
    if yaml is None:
        print("loopprint-library: PyYAML required (pip install pyyaml)", file=sys.stderr)
        sys.exit(2)
    try:
        with open(spec_path, encoding="utf-8") as fh:
            spec = yaml.safe_load(fh)
    except Exception as exc:
        print(f"loopprint-library: cannot read/parse {spec_path} ({exc})", file=sys.stderr)
        return None
    return spec if isinstance(spec, dict) else None


def _resolve_loop_dir(target: str, *, library_dir: str | None = None) -> Path | None:
    p = Path(target)
    if p.is_dir() and (p / "loop-spec.yaml").is_file():
        return p.resolve()
    for base in _library_roots(library_dir):
        cand = base / target
        if cand.is_dir() and (cand / "loop-spec.yaml").is_file():
            return cand.resolve()
    return None


def _classify_verify_exit(code: int) -> str:
    if code == 0:
        return "GREEN"
    if 1 <= code <= 125:
        return "RED"
    return "CANT_EXECUTE"


def _smoke_verify(loop_dir: Path, consumer_cwd: Path) -> tuple[int, str]:
    """Run verify.sh once with cwd = consumer repo root; classify per run-this-loop.sh --check."""
    verify_sh = loop_dir / "verify.sh"
    if not verify_sh.is_file():
        return 127, "CANT_EXECUTE"
    try:
        syntax = subprocess.run(
            ["bash", "-n", str(verify_sh)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if syntax.returncode != 0:
            return 126, "CANT_EXECUTE"
        r = subprocess.run(
            ["bash", str(verify_sh)],
            cwd=str(consumer_cwd),
            capture_output=True,
            text=True,
            timeout=300,
        )
        code = r.returncode
    except (OSError, subprocess.TimeoutExpired):
        return 126, "CANT_EXECUTE"
    return code, _classify_verify_exit(code)


def _scaffold_bundle(loop_dir: Path, dest: Path) -> None:
    """Copy loop bundle files into dest (temp dir for smoke, or DEST/SLUG for install)."""
    dest.mkdir(parents=True, exist_ok=True)
    for item in loop_dir.iterdir():
        target = dest / item.name
        if item.is_file():
            shutil.copy2(item, target)
        elif item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)


def _cmd_search(args: argparse.Namespace) -> int:
    base = Path(args.dir)
    if not base.is_absolute():
        base = Path.cwd() / base
    rows = _scan_library(base.resolve())
    if args.query:
        q = args.query.lower()
        rows = [
            r for r in rows
            if q in r["slug"].lower()
            or q in r["goal"].lower()
            or q in r["pattern"].lower()
        ]
    if args.json:
        print(json.dumps({"dir": str(base.resolve()), "loops": rows}, indent=2))
        return 0
    if not rows:
        print(f"No loops found under {base.resolve()}.")
        return 0
    print(f"{'SLUG':<24} {'PATTERN':<14} GOAL")
    for r in rows:
        goal = r["goal"]
        if len(goal) > 56:
            goal = goal[:53] + "..."
        print(f"{r['slug']:<24} {r['pattern']:<14} {goal}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    loop_dir = _resolve_loop_dir(args.target)
    if loop_dir is None:
        print(f"loopprint-library: cannot resolve loop: {args.target!r}", file=sys.stderr)
        return 2
    consumer = _consumer_repo_root(Path.cwd())
    exit_code, verdict = _smoke_verify(loop_dir, consumer)
    print(f"{verdict}  exit={exit_code}  loop={loop_dir}")
    return 1 if verdict == "CANT_EXECUTE" else 0


def _cmd_install(args: argparse.Namespace) -> int:
    loop_dir = _resolve_loop_dir(args.slug)
    if loop_dir is None:
        print(f"loopprint-library: cannot resolve loop slug: {args.slug!r}", file=sys.stderr)
        return 2

    spec_path = loop_dir / "loop-spec.yaml"
    spec = _read_spec(spec_path)
    if spec is None:
        return 1

    try:
        lint_spec = _load_lint_spec()
    except Exception as exc:
        print(f"loopprint-library: cannot import lint gate ({exc})", file=sys.stderr)
        return 2

    findings = lint_spec(spec)
    if findings:
        print(f"REFUSE  {spec_path}: loop-spec lint findings — fix before install.")
        for item in findings:
            print(f"   - {item}")
        return 1

    slug = str(spec.get("slug") or args.slug).strip() or args.slug
    if slug != Path(slug).name or slug in ("", ".", ".."):
        print(
            f"REFUSE  invalid install slug {slug!r} — must be a single path segment.",
            file=sys.stderr,
        )
        return 1
    dest_root = Path(args.dest).resolve()
    dest_slug_dir = dest_root / slug
    resolved = dest_slug_dir.resolve()
    if dest_root not in resolved.parents and resolved != dest_root:
        print(
            f"REFUSE  install slug {slug!r} escapes destination {dest_root}.",
            file=sys.stderr,
        )
        return 1
    if dest_slug_dir.exists() and any(dest_slug_dir.iterdir()) and not args.force:
        print(f"REFUSE  {dest_slug_dir} already exists (use --force to overwrite).", file=sys.stderr)
        return 1

    consumer = _consumer_repo_root(dest_root)

    with tempfile.TemporaryDirectory(prefix="loopprint-library-") as tmp:
        scaffold = Path(tmp)
        _scaffold_bundle(loop_dir, scaffold)
        exit_code, verdict = _smoke_verify(scaffold, consumer)

    if verdict == "CANT_EXECUTE":
        print(
            f"REFUSE  verify.sh could not execute in {consumer} (exit {exit_code} > 125). "
            "Nothing written to dest.",
            file=sys.stderr,
        )
        return 1

    if dest_slug_dir.exists() and args.force:
        shutil.rmtree(dest_slug_dir)
    _scaffold_bundle(loop_dir, dest_slug_dir)

    # LOCAL smoke-run record — NOT references/receipt.md's signed Stage-6 receipt.
    record = {
        "slug": slug,
        "verify_exit": exit_code,
        "verdict": verdict,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cwd": str(consumer),
    }
    verdict_path = dest_slug_dir / "install-verdict.json"
    verdict_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    if verdict == "GREEN":
        print(f"install: {slug} — gate passes in this environment ({consumer}).")
    else:
        print(f"install: {slug} — installed with RED on arrival (work to do); see {verdict_path}.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="loopprint-library.py",
        description="Search, smoke-verify, and install loops from library/.",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    sp_search = sub.add_parser("search", help="search library loops by slug, goal, or pattern")
    sp_search.add_argument("query", nargs="?", default="", help="substring filter (optional)")
    sp_search.add_argument("--dir", default="library/", help="library root (default: library/)")
    sp_search.add_argument("--json", action="store_true", help="machine-readable output")

    sp_verify = sub.add_parser("verify", help="smoke-run verify.sh against the consumer repo")
    sp_verify.add_argument("target", help="loop slug or path to loop directory")

    sp_install = sub.add_parser("install", help="lint-gate, smoke-verify, copy bundle to --dest")
    sp_install.add_argument("slug", help="loop slug (under library/)")
    sp_install.add_argument("--dest", required=True, help="consumer repo directory")
    sp_install.add_argument("--force", action="store_true", help="overwrite an existing DEST/SLUG")

    args = ap.parse_args(argv[1:])

    if yaml is None and args.command in ("search", "install"):
        print("loopprint-library: PyYAML required (pip install pyyaml)", file=sys.stderr)
        return 2

    if args.command == "search":
        return _cmd_search(args)
    if args.command == "verify":
        return _cmd_verify(args)
    if args.command == "install":
        return _cmd_install(args)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
