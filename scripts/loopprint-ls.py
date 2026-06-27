#!/usr/bin/env python3
"""loopprint-ls — repo-local loop health view ("rot radar").

Enumerates the loops in this repo and reports each one's health from its OWN run history, so you can
answer one question at a glance: *is any of my automation silently broken?*

  HEALTHY  — ran recently and has gone GREEN
  RUNNING  — a run is live (the runner holds a .running lock) and wrote within --running-grace
  PENDING  — ran recently but has never gone GREEN yet (not chronically failing)
  ROTTEN   — failing repeatedly: red_streak >= K (default 3), recent, and not currently running
  STALE    — no run in > N days (default 14): the automation went quiet
  UNKNOWN  — can't assess (reason: never_run | no_verdict | no_timestamp | parse_error | no_data)

Discovery is BINDING-AWARE: it asks loopprint-detect.py where this harness keeps loop state (state_dir),
then falls back to loops/ and .omc/loops/. It NEVER hardcodes a per-harness matrix; the binding owns the path.

Health source ladder (first that has data wins): metrics.jsonl -> state.jsonl -> the verifier marker. Streaks
are counted in FILE APPEND ORDER, never by sorting timestamps (clocks skew; the runner appends in order).

This tool only READS state. It never executes a loop, a maker, or a verifier. Stdlib only — no PyYAML, no
network. Exit code is 0 unless --exit-nonzero-if-rotten is set and at least one loop is ROTTEN (a CI/cron hook).

Usage:
  loopprint-ls.py [--dir DIR ...] [--stale-days N] [--rot-streak K] [--running-grace SECONDS]
                  [--json] [--rotten] [--exit-nonzero-if-rotten]
"""
from __future__ import annotations
import sys, re, json, argparse, subprocess
from pathlib import Path
from datetime import datetime, timezone

DEFAULT_ROOTS = ["loops", ".omc/loops"]


def _detect_binding(script_dir: Path, cwd: Path) -> dict:
    """Ask loopprint-detect.py for the binding (state_dir, marker_path). Empty dict if unavailable."""
    detect = script_dir / "loopprint-detect.py"
    if not detect.is_file():
        return {}
    try:
        out = subprocess.run([sys.executable, str(detect), "--cwd", str(cwd)],
                             capture_output=True, text=True, timeout=10)
    except Exception:
        return {}
    binding = {}
    for line in out.stdout.splitlines():
        if line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        binding[k.strip()] = v.strip()
    return binding


def _root_from_state_dir(state_dir: str):
    """'loops/<slug>' -> 'loops'; '.omc/loops/<slug>' -> '.omc/loops'. Handles both / and \\ separators."""
    parts = [p for p in re.split(r"[\\/]+", state_dir.strip()) if p != ""]
    while parts and ("<slug>" in parts[-1] or "{slug}" in parts[-1]):
        parts.pop()
    return "/".join(parts) if parts else None


def _scan_roots(script_dir: Path, cwd: Path, extra_dirs: list[str]) -> tuple[list[str], str]:
    # LOOPPRINT_ROOT is the *clone* path (for invoking the scripts), NOT a loops dir — do not scan it,
    # or the clone's own templates/ surfaces as a phantom loop. Custom loop locations come from the
    # harness binding (state_dir) or an explicit --dir.
    roots: list[str] = []
    binding = _detect_binding(script_dir, cwd)
    r = _root_from_state_dir(binding.get("state_dir", ""))
    if r:
        roots.append(r)
    roots.extend(extra_dirs or [])
    roots.extend(DEFAULT_ROOTS)
    # de-dupe, preserve order
    seen, ordered = set(), []
    for r in roots:
        if r and r not in seen:
            seen.add(r)
            ordered.append(r)
    return ordered, binding.get("marker_path", "")


def _find_loops(roots: list[str], cwd: Path) -> dict:
    """slug -> loop dir. A loop dir holds loop-spec.yaml OR metrics.jsonl OR state.jsonl. First root wins."""
    found: dict[str, Path] = {}
    for root in roots:
        base = cwd / root
        if not base.is_dir():
            continue
        for sub in sorted(base.iterdir()):
            if not sub.is_dir():
                continue
            if (sub / "loop-spec.yaml").is_file() or (sub / "metrics.jsonl").is_file() or (sub / "state.jsonl").is_file():
                found.setdefault(sub.name, sub)
    return found


def _read_jsonl_results(path: Path):
    """Stream a JSONL file. Returns (results, malformed_count, other_count):
       results = [(verifier_result, ts)] in FILE (append) ORDER, GREEN/RED only;
       malformed_count = unparseable lines; other_count = valid records that weren't GREEN/RED (e.g. SKIP)."""
    results, bad, other = [], 0, 0
    try:
        with path.open() as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    obj = json.loads(ln)
                except Exception:
                    bad += 1
                    continue
                vr = obj.get("verifier_result")
                if vr in ("GREEN", "RED"):
                    results.append((vr, obj.get("ts")))
                else:
                    other += 1
    except Exception:
        pass
    return results, bad, other


def _resolve_marker(marker_tmpl: str, slug: str, cwd: Path):
    """Resolve a verifier-marker path by substituting this loop's slug into the binding's template.
       EXACT match only — a fuzzy glob would match another loop's marker (slug 'ci' -> 'pricing-verifier.json')."""
    if not marker_tmpl:
        return None
    cand = re.sub(r"<\w+>|\{\w+\}", slug, marker_tmpl)   # <mode> / <slug> / {slug} -> this slug
    p = cwd / cand
    return p if p.is_file() else None


def _from_results(results, source: str) -> dict:
    last_result, last_ts = results[-1]
    streak = 0
    for vr, _ in reversed(results):       # append order: count trailing REDs
        if vr == "RED":
            streak += 1
        else:
            break
    return {
        "last_result": last_result,
        "last_ts": last_ts,
        "red_streak": streak,
        "green_ever": any(vr == "GREEN" for vr, _ in results),
        "iters": len(results),
        "source": source,
    }


def _health(loop_dir: Path, marker_tmpl: str, slug: str, cwd: Path):
    """Return (health_dict | None, reason | None) via the source ladder."""
    parse_failed = ran_no_verdict = False
    for fn in ("metrics.jsonl", "state.jsonl"):
        p = loop_dir / fn
        if p.is_file():
            results, bad, other = _read_jsonl_results(p)
            if results:
                return _from_results(results, fn), None
            if bad:
                parse_failed = True          # corrupt source: keep going, a later source may be readable
            elif other:
                ran_no_verdict = True         # ran but emitted no GREEN/RED (e.g. a dry-run's SKIP lines)
    marker = _resolve_marker(marker_tmpl, slug, cwd)
    if marker:
        try:
            m = json.loads(marker.read_text())
            res = m.get("result")
            if res in ("GREEN", "RED"):
                return _from_results([(res, m.get("ts"))], "marker"), None
        except Exception:
            parse_failed = True
    if parse_failed:
        return None, "parse_error"
    if ran_no_verdict:
        return None, "no_verdict"
    if (loop_dir / "loop-spec.yaml").is_file():
        return None, "never_run"
    return None, "no_data"


def _parse_ts(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _classify(h, reason, now, N, K, grace, running_lock):
    if h is None:
        return "UNKNOWN", reason
    last_ts = _parse_ts(h["last_ts"])
    age_sec = (now - last_ts).total_seconds() if last_ts else None
    if age_sec is None:
        return "UNKNOWN", "no_timestamp"      # a time-aware radar can't classify a run it can't date
    age_days = age_sec / 86400
    # RUNNING: an actual run is live (the runner holds a lock) and wrote recently. A *terminal* RED loop
    # (no lock) is NOT masked -> it can reach ROTTEN, which is the whole point of --exit-nonzero-if-rotten.
    if running_lock and age_sec < grace:
        return "RUNNING", None
    if age_days > N:
        return "STALE", None
    if h["red_streak"] >= K or (h["source"] == "marker" and h["last_result"] == "RED"):
        return "ROTTEN", None
    if not h["green_ever"]:
        return "PENDING", None                # ran recently, not chronically failing, but never passed yet
    return "HEALTHY", None


def _age_str(last_ts, now):
    dt = _parse_ts(last_ts)
    if dt is None:
        return "-"
    sec = (now - dt).total_seconds()
    if sec < 0:
        return "just now"                     # clock skew / future timestamp
    if sec < 90:
        return f"{int(sec)}s ago"
    if sec < 5400:
        return f"{int(sec // 60)}m ago"
    if sec < 172800:
        return f"{int(sec // 3600)}h ago"
    return f"{int(sec // 86400)}d ago"


def main(argv) -> int:
    ap = argparse.ArgumentParser(prog="loopprint-ls.py", description="Repo-local loop health view (rot radar).")
    ap.add_argument("--dir", action="append", default=[], help="extra root to scan (repeatable)")
    ap.add_argument("--stale-days", type=int, default=14, help="STALE if no run in > N days (default 14)")
    ap.add_argument("--rot-streak", type=int, default=3, help="ROTTEN at >= K trailing RED runs (default 3)")
    ap.add_argument("--running-grace", type=int, default=120, help="recent-write window (s) treated as RUNNING")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--rotten", action="store_true", help="show only ROTTEN + STALE loops")
    ap.add_argument("--exit-nonzero-if-rotten", action="store_true", help="exit 1 if any loop is ROTTEN (CI hook)")
    args = ap.parse_args(argv[1:])

    cwd = Path.cwd()
    script_dir = Path(__file__).resolve().parent
    now = datetime.now(timezone.utc)

    roots, marker_tmpl = _scan_roots(script_dir, cwd, args.dir)
    loops = _find_loops(roots, cwd)

    rows = []
    for slug in sorted(loops):
        loop_dir = loops[slug]
        h, reason = _health(loop_dir, marker_tmpl, slug, cwd)
        running_lock = (loop_dir / ".running").is_file()
        status, why = _classify(h, reason, now, args.stale_days, args.rot_streak,
                                args.running_grace, running_lock)
        hh = h or {}
        rows.append({
            "slug": slug,
            "status": status,
            "reason": why,
            "last_run": hh.get("last_ts"),
            "iters": hh.get("iters", 0),
            "red_streak": hh.get("red_streak", 0),
            "last_result": hh.get("last_result"),
            "source": hh.get("source"),
            "dir": str(loop_dir),
        })

    if args.rotten:
        rows = [r for r in rows if r["status"] in ("ROTTEN", "STALE")]

    any_rotten = any(r["status"] == "ROTTEN" for r in rows)

    if args.json:
        print(json.dumps({"scanned_roots": roots, "loops": rows}, indent=2))
    else:
        if not rows:
            print(f"No loops found (scanned: {', '.join(roots)}).")
        else:
            print(f"{'SLUG':<24} {'STATUS':<21} {'LAST RUN':<11} {'ITERS':>5} {'RED-STREAK':>10}  SOURCE")
            for r in rows:
                tag = r["status"] + (f"({r['reason']})" if r["reason"] else "")
                print(f"{r['slug']:<24} {tag:<21} {_age_str(r['last_run'], now):<11} "
                      f"{r['iters']:>5} {r['red_streak']:>10}  {r['source'] or '-'}")
            rotten = [r['slug'] for r in rows if r['status'] == 'ROTTEN']
            stale = [r['slug'] for r in rows if r['status'] == 'STALE']
            if rotten:
                print(f"\n⚠  ROTTEN (failing repeatedly): {', '.join(rotten)}", file=sys.stderr)
            if stale:
                print(f"⏸  STALE (no recent run): {', '.join(stale)}", file=sys.stderr)

    return 1 if (args.exit_nonzero_if_rotten and any_rotten) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
