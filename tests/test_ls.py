"""Tests for loopprint-ls.py (repo-local loop health / rot radar)."""
import json
import subprocess
import sys
import importlib.util
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LS = REPO / "scripts" / "loopprint-ls.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("loopprint_ls", LS)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ls = _load_module()


# ---- fixtures ---------------------------------------------------------------
def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _rec(i, res, dt):
    return json.dumps({"iter": i, "ts": _iso(dt), "wall_ms": 5,
                       "verifier_result": res, "accepted": res == "GREEN"})


def _mk_loop(root: Path, slug: str, lines=None, spec=True, fname="metrics.jsonl", running=False):
    d = root / "loops" / slug
    d.mkdir(parents=True)
    if spec:
        (d / "loop-spec.yaml").write_text(f"slug: {slug}\n")
    if lines is not None:
        (d / fname).write_text("\n".join(lines) + "\n")
    if running:
        (d / ".running").write_text("")          # the lock the runner holds while a run is live
    return d


def _run(cwd: Path, *args):
    p = subprocess.run([sys.executable, str(LS), *args], cwd=cwd,
                       capture_output=True, text=True)
    return p


def _statuses(cwd: Path, *args):
    p = _run(cwd, "--json", *args)
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    return {r["slug"]: (r["status"], r["reason"]) for r in data["loops"]}


# ---- the five health states -------------------------------------------------
def test_all_states_classified(tmp_path):
    now = datetime.now(timezone.utc)
    _mk_loop(tmp_path, "healthy", [_rec(1, "RED", now - timedelta(minutes=10)),
                                   _rec(2, "GREEN", now - timedelta(minutes=9))])
    _mk_loop(tmp_path, "rotten", [_rec(i, "RED", now - timedelta(hours=4 - i)) for i in range(1, 4)])
    _mk_loop(tmp_path, "stale", [_rec(1, "GREEN", now - timedelta(days=30))])
    _mk_loop(tmp_path, "running", [_rec(1, "RED", now - timedelta(hours=1)),
                                   _rec(2, "RED", now - timedelta(hours=1)),
                                   _rec(3, "RED", now - timedelta(seconds=5))], running=True)
    _mk_loop(tmp_path, "never", None)
    st = _statuses(tmp_path)
    assert st["healthy"][0] == "HEALTHY"
    assert st["rotten"][0] == "ROTTEN"
    assert st["stale"][0] == "STALE"
    assert st["running"][0] == "RUNNING"          # live run holds the .running lock
    assert st["never"] == ("UNKNOWN", "never_run")


def test_running_requires_lock_else_rotten(tmp_path):
    """A recent RED streak is RUNNING only while the runner holds the .running lock. A TERMINAL RED loop
    (no lock) MUST reach ROTTEN — otherwise --exit-nonzero-if-rotten silently misses a fast-failing loop."""
    now = datetime.now(timezone.utc)
    reds = [_rec(1, "RED", now), _rec(2, "RED", now), _rec(3, "RED", now)]
    _mk_loop(tmp_path, "live", reds, running=True)
    _mk_loop(tmp_path, "dead", reds, running=False)      # finished failing — no lock
    st = _statuses(tmp_path)
    assert st["live"][0] == "RUNNING"
    assert st["dead"][0] == "ROTTEN"
    assert _run(tmp_path, "--exit-nonzero-if-rotten").returncode == 1   # the terminal one trips CI


def test_pending_when_never_green(tmp_path):
    """A recent loop that has never gone GREEN and isn't chronically failing is PENDING, not HEALTHY."""
    now = datetime.now(timezone.utc)
    _mk_loop(tmp_path, "newish", [_rec(1, "RED", now - timedelta(minutes=5)),
                                  _rec(2, "RED", now - timedelta(minutes=4))])
    assert _statuses(tmp_path)["newish"][0] == "PENDING"


def test_skip_only_is_no_verdict(tmp_path):
    now = datetime.now(timezone.utc)
    d = tmp_path / "loops" / "dry"
    d.mkdir(parents=True)
    (d / "loop-spec.yaml").write_text("slug: dry\n")
    (d / "metrics.jsonl").write_text(json.dumps({"iter": 1, "ts": _iso(now), "verifier_result": "SKIP"}) + "\n")
    assert _statuses(tmp_path)["dry"] == ("UNKNOWN", "no_verdict")


def test_corrupt_metrics_falls_through_to_state(tmp_path):
    """A corrupt metrics.jsonl must not stop the ladder — a valid state.jsonl still classifies the loop."""
    now = datetime.now(timezone.utc)
    d = tmp_path / "loops" / "ladder"
    d.mkdir(parents=True)
    (d / "metrics.jsonl").write_text("{corrupt\n")
    (d / "state.jsonl").write_text(_rec(1, "GREEN", now - timedelta(minutes=1)) + "\n")
    assert _statuses(tmp_path)["ladder"][0] == "HEALTHY"


def test_missing_timestamp_is_unknown(tmp_path):
    d = tmp_path / "loops" / "nots"
    d.mkdir(parents=True)
    (d / "metrics.jsonl").write_text(json.dumps({"iter": 1, "verifier_result": "RED", "ts": None}) + "\n")
    assert _statuses(tmp_path)["nots"] == ("UNKNOWN", "no_timestamp")


def test_resolve_marker_is_exact_not_substring(tmp_path):
    """The verifier marker must match this slug exactly — a substring glob would pick another loop's marker."""
    (tmp_path / ".omc" / "state").mkdir(parents=True)
    (tmp_path / ".omc" / "state" / "pricing-verifier.json").write_text('{"result":"RED"}')
    tmpl = ".omc/state/<mode>-verifier.json"
    assert ls._resolve_marker(tmpl, "ci", tmp_path) is None          # 'ci' must NOT match 'pricing-...'
    (tmp_path / ".omc" / "state" / "ci-verifier.json").write_text('{"result":"GREEN"}')
    assert ls._resolve_marker(tmpl, "ci", tmp_path) is not None      # exact slug match resolves


# ---- malformed tolerance ----------------------------------------------------
def test_malformed_lines_are_parse_error(tmp_path):
    d = tmp_path / "loops" / "borked"
    d.mkdir(parents=True)
    (d / "loop-spec.yaml").write_text("slug: borked\n")
    (d / "metrics.jsonl").write_text("{not json\n%%%\n")
    assert _statuses(tmp_path)["borked"] == ("UNKNOWN", "parse_error")


def test_blank_and_mixed_lines_tolerated(tmp_path):
    now = datetime.now(timezone.utc)
    _mk_loop(tmp_path, "mixed", ["", "{bad", _rec(1, "GREEN", now - timedelta(minutes=1)), ""])
    assert _statuses(tmp_path)["mixed"][0] == "HEALTHY"


# ---- exit codes -------------------------------------------------------------
def test_exit_nonzero_if_rotten(tmp_path):
    now = datetime.now(timezone.utc)
    _mk_loop(tmp_path, "rotten", [_rec(i, "RED", now - timedelta(hours=4 - i)) for i in range(1, 4)])
    assert _run(tmp_path, "--exit-nonzero-if-rotten").returncode == 1


def test_exit_zero_when_no_rotten(tmp_path):
    now = datetime.now(timezone.utc)
    _mk_loop(tmp_path, "ok", [_rec(1, "GREEN", now - timedelta(minutes=1))])
    _mk_loop(tmp_path, "stale", [_rec(1, "GREEN", now - timedelta(days=30))])  # STALE is not ROTTEN
    assert _run(tmp_path, "--exit-nonzero-if-rotten").returncode == 0


# ---- custom dir / state_dir -------------------------------------------------
def test_custom_dir_scanned(tmp_path):
    now = datetime.now(timezone.utc)
    d = tmp_path / "work" / "myloop"
    d.mkdir(parents=True)
    (d / "metrics.jsonl").write_text(_rec(1, "GREEN", now - timedelta(minutes=1)) + "\n")
    st = _statuses(tmp_path, "--dir", "work")
    assert st["myloop"][0] == "HEALTHY"


# ---- panel must-fix: streak by APPEND ORDER, never ts-sort -------------------
def test_red_streak_is_append_order_not_timestamp():
    now = datetime.now(timezone.utc)
    # File order ends in 2 REDs; their ts are EARLIER than the GREEN (clock skew / backfill).
    results = [("GREEN", _iso(now)), ("RED", _iso(now - timedelta(hours=2))),
               ("RED", _iso(now - timedelta(hours=3)))]
    h = ls._from_results(results, "metrics.jsonl")
    assert h["red_streak"] == 2          # trailing REDs by file order, not by sorting ts


def test_root_from_state_dir_strips_slug():
    assert ls._root_from_state_dir("loops/<slug>") == "loops"
    assert ls._root_from_state_dir(".omc/loops/<slug>") == ".omc/loops"
    assert ls._root_from_state_dir("loops\\<slug>") == "loops"        # Windows backslash separator
    assert ls._root_from_state_dir("") is None


def test_parse_ts_handles_z_suffix():
    dt = ls._parse_ts("2026-06-26T12:00:00Z")
    assert dt is not None and dt.tzinfo is not None
    assert ls._parse_ts(None) is None
    assert ls._parse_ts("garbage") is None
