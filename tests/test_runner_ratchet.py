from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "templates" / "run-this-loop.sh"


def _bash_ok() -> bool:
    """Return True only when a real POSIX bash is available.

    The GitHub ``windows-latest`` runner ships ``bash.exe`` as the WSL launcher
    stub with no distro installed, so shelling out to it exits non-zero. These
    tests exec ``run-this-loop.sh`` via bash, so skip the whole module wherever
    no working POSIX bash exists (Windows CI) rather than fail spuriously.
    """
    if sys.platform.startswith("win"):
        return False
    b = shutil.which("bash")
    if not b:
        return False
    try:
        out = subprocess.run(
            [b, "-c", "echo ok"], capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() == "ok"
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _bash_ok(), reason="runner tests need a POSIX bash (skipped on Windows CI)"
)


def _setup(tmp: Path) -> None:
    shutil.copy(RUNNER, tmp / "run-this-loop.sh")


def _write_sh(tmp: Path, name: str, body: str) -> None:
    p = tmp / name
    p.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}\n")


def _run(
    tmp: Path,
    args: list[str] | None = None,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    env = {**os.environ, "AUTONOMY": "full"}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", "run-this-loop.sh"] + (args or []),
        cwd=str(tmp),
        env=env,
        capture_output=True,
        text=True,
    )


def _metrics(tmp: Path) -> list[dict]:
    p = tmp / "metrics.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


# ===========================================================================
# Group A — GATE REGRESSION (must PASS now against unedited runner)
# ===========================================================================


def test_gate_already_green():
    """Gate: verify.sh GREEN on entry → exit 0, iter=0 metrics row, maker never called."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _setup(tmp)
        _write_sh(tmp, "verify.sh", "exit 0")
        _write_sh(tmp, "maker.sh", "touch maker_ran.flag")

        r = _run(tmp)

        assert r.returncode == 0, f"exit {r.returncode}\nstderr={r.stderr}"
        rows = _metrics(tmp)
        assert len(rows) == 1, f"expected 1 metrics row, got {rows}"
        assert rows[0]["iter"] == 0
        assert rows[0]["verifier_result"] == "GREEN"
        assert rows[0]["accepted"] is True
        assert not (tmp / "maker_ran.flag").exists(), "maker.sh must not run when already green"


def test_gate_green_after_one_maker():
    """Gate: verify.sh RED until maker.sh runs → exit 0 at iter 1, single accepted row."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _setup(tmp)
        _write_sh(tmp, "verify.sh", "[ -f done.flag ]")
        _write_sh(tmp, "maker.sh", "touch done.flag")

        r = _run(tmp)

        assert r.returncode == 0, f"exit {r.returncode}\nstderr={r.stderr}"
        rows = _metrics(tmp)
        assert len(rows) == 1, f"expected 1 metrics row, got {rows}"
        assert rows[0]["iter"] == 1
        assert rows[0]["verifier_result"] == "GREEN"
        assert rows[0]["accepted"] is True


# ===========================================================================
# Group B — RATCHET BEHAVIOR (Step 2 landed — these now pass)
# ===========================================================================


def test_ratchet_no_early_exit_on_first_green():
    """Ratchet: always-GREEN verify does NOT exit at first GREEN; runs MAX_ITERS=3 iters, exit 2."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _setup(tmp)
        _write_sh(tmp, "verify.sh", "exit 0")
        _write_sh(tmp, "maker.sh", "exit 0")

        r = _run(tmp, env_extra={"VERIFIER_SHAPE": "ratchet", "MAX_ITERS": "3"})

        assert r.returncode == 2, f"expected exit 2 (max-iters), got {r.returncode}\nstderr={r.stderr}"
        loop_rows = [row for row in _metrics(tmp) if row["iter"] >= 1]
        assert len(loop_rows) == 3, f"expected 3 loop rows, got {loop_rows}"


def test_ratchet_pre_loop_green_does_not_early_exit():
    """Ratchet: pre-loop GREEN does not exit early; proceeds into loop and hits max-iters (exit 2)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _setup(tmp)
        _write_sh(tmp, "verify.sh", "exit 0")
        _write_sh(tmp, "maker.sh", "exit 0")

        r = _run(tmp, env_extra={"VERIFIER_SHAPE": "ratchet", "MAX_ITERS": "1"})

        # Must NOT exit 0 (gate early-exit); must hit max-iters (exit 2) after 1 loop iteration
        assert r.returncode == 2, f"expected exit 2, got {r.returncode}\nstderr={r.stderr}"


def test_ratchet_stops_on_budget():
    """Ratchet: BUDGET_MIN=0 triggers wall-clock budget stop (exit 6) before any iteration."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _setup(tmp)
        _write_sh(tmp, "verify.sh", "exit 0")
        _write_sh(tmp, "maker.sh", "exit 0")

        r = _run(tmp, env_extra={"VERIFIER_SHAPE": "ratchet", "BUDGET_MIN": "0", "MAX_ITERS": "100"})

        assert r.returncode == 6, f"expected exit 6 (budget), got {r.returncode}\nstderr={r.stderr}"


def test_ratchet_advance_invoked_on_accept():
    """Ratchet: GREEN accepted iter → advance script called (sentinel appears); metrics row accepted=true."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _setup(tmp)
        _write_sh(tmp, "verify.sh", "exit 0")
        _write_sh(tmp, "maker.sh", "exit 0")
        _write_sh(tmp, "ratchet-advance.sh", "touch advance_ran.flag")

        _run(tmp, env_extra={
            "VERIFIER_SHAPE": "ratchet",
            "RATCHET_ADVANCE": "ratchet-advance.sh",
            "MAX_ITERS": "1",
        })

        assert (tmp / "advance_ran.flag").exists(), "ratchet-advance.sh was not invoked"
        loop_rows = [row for row in _metrics(tmp) if row["iter"] >= 1]
        assert len(loop_rows) >= 1, f"no loop metrics rows: {_metrics(tmp)}"
        assert loop_rows[0]["accepted"] is True


def test_ratchet_advance_failure_honest_audit():
    """Ratchet: advance exits non-zero → that iter's metrics row has accepted=false (honest audit)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _setup(tmp)
        _write_sh(tmp, "verify.sh", "exit 0")
        _write_sh(tmp, "maker.sh", "exit 0")
        _write_sh(tmp, "ratchet-advance.sh", "exit 1")

        _run(tmp, env_extra={
            "VERIFIER_SHAPE": "ratchet",
            "RATCHET_ADVANCE": "ratchet-advance.sh",
            "MAX_ITERS": "1",
        })

        rows = _metrics(tmp)
        loop_rows = [row for row in rows if row["iter"] >= 1]
        assert len(loop_rows) >= 1, f"no loop metrics rows: {rows}"
        assert loop_rows[0]["accepted"] is False, (
            f"expected accepted=false on advance failure, got {loop_rows[0]}"
        )


def test_ratchet_resume_elapsed_from_metrics_ts():
    """Ratchet --resume: elapsed from first metrics ts (not process start); 2-hour-old ts + BUDGET_MIN=1 → exit 6."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _setup(tmp)
        _write_sh(tmp, "verify.sh", "exit 0")
        _write_sh(tmp, "maker.sh", "exit 0")

        # Seed metrics.jsonl with a row timestamped 2 hours ago so elapsed >> BUDGET_MIN
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        seed = json.dumps({
            "iter": 1,
            "ts": old_ts,
            "wall_ms": 200,
            "verifier_result": "GREEN",
            "accepted": True,
            "tokens": None,
            "cost_usd": None,
        })
        (tmp / "metrics.jsonl").write_text(seed + "\n")

        r = _run(tmp, args=["--resume"], env_extra={
            "VERIFIER_SHAPE": "ratchet",
            "BUDGET_MIN": "1",    # 1 minute; 2-hour elapsed from seeded ts → immediate stop
            "MAX_ITERS": "100",
        })

        assert r.returncode == 6, (
            f"expected exit 6 (budget from resumed elapsed), got {r.returncode}\nstderr={r.stderr}"
        )


def test_ratchet_warns_when_advance_unset():
    """Ratchet shape with no RATCHET_ADVANCE wired → loud warning, not a silent no-op ratchet."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _setup(tmp)
        _write_sh(tmp, "verify.sh", "exit 0")
        _write_sh(tmp, "maker.sh", "exit 0")

        r = _run(tmp, env_extra={"VERIFIER_SHAPE": "ratchet", "MAX_ITERS": "1"})

        assert "RATCHET_ADVANCE is unset" in r.stderr, (
            f"expected a no-op-ratchet warning on stderr, got:\n{r.stderr}"
        )
