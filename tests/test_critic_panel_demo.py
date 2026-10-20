"""Subprocess-level coverage of examples/critic-panel/run_demo.sh — proves the {score, reason}
JSON critic contract (item 11) actually works end-to-end, both the quorum-PASS and the
fail-flip quorum-FAIL path, the way tests/test_runner_ratchet.py covers run-this-loop.sh."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "critic-panel"
DEMO = EXAMPLE / "run_demo.sh"


def _bash_ok() -> bool:
    """Same check as tests/test_runner_ratchet.py: the GitHub windows-latest runner ships
    bash.exe as the WSL launcher stub with no distro installed, so shelling out to it exits
    non-zero rather than running anything. Skip on Windows CI instead of failing spuriously."""
    if sys.platform.startswith("win"):
        return False
    b = shutil.which("bash")
    if not b:
        return False
    try:
        out = subprocess.run([b, "-c", "echo ok"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() == "ok"
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _bash_ok(), reason="critic-panel demo needs a POSIX bash (skipped on Windows CI)"
)


def test_run_demo_shows_pass_then_fail_flip():
    result = subprocess.run(["bash", str(DEMO)], capture_output=True, text=True, cwd=str(EXAMPLE))
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr  # verify.sh writes its FAIL line to stderr
    assert "quorum PASS (2/3, need 2)" in combined
    assert "quorum FAIL (1/3, need 2)" in combined
    assert "(EXPECTED — quorum FAIL, gate bites)" in result.stdout


def test_critic_verdicts_are_structured_json_with_reason(tmp_path):
    for name in ("loop-spec.yaml", "rubric.md", "artifact.md", "maker.sh",
                "critic-1.sh", "critic-2.sh", "critic-3.sh", "verify.sh"):
        (tmp_path / name).write_bytes((EXAMPLE / name).read_bytes())
        (tmp_path / name).chmod(0o755)

    result = subprocess.run(["bash", "verify.sh"], capture_output=True, text=True, cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr

    lines = (tmp_path / "critics.jsonl").read_text().splitlines()
    assert len(lines) == 3
    for line in lines:
        verdict = json.loads(line)  # must be valid JSON, not just a bare-integer line
        assert isinstance(verdict["score"], int)
        assert isinstance(verdict["reason"], str) and verdict["reason"], "reason must be non-empty"
        assert set(verdict) >= {"ts", "critic", "provider", "score", "reason", "threshold",
                                "pass", "rubric_sha", "artifact_sha", "n", "quorum_k"}


def test_reason_field_with_quotes_and_newline_does_not_corrupt_jsonl(tmp_path):
    for name in ("loop-spec.yaml", "rubric.md", "artifact.md", "maker.sh",
                "critic-1.sh", "critic-2.sh", "critic-3.sh", "verify.sh"):
        (tmp_path / name).write_bytes((EXAMPLE / name).read_bytes())
        (tmp_path / name).chmod(0o755)

    # Build the adversarial verdict via json.dumps (never hand-quoted shell text — that's
    # exactly the class of mistake this fix defends against) and emit it via a heredoc, which
    # sidesteps shell quoting entirely.
    adversarial_json = json.dumps({
        "score": 90,
        "reason": 'Has a "quoted phrase", a backslash \\, and a\nnewline.',
    })
    critic1 = tmp_path / "critic-1.sh"
    lines = critic1.read_text().splitlines()
    lines[-1] = f"cat <<'VERDICT_EOF'\n{adversarial_json}\nVERDICT_EOF"
    critic1.write_text("\n".join(lines) + "\n")

    result = subprocess.run(["bash", "verify.sh"], capture_output=True, text=True, cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr
    for line in (tmp_path / "critics.jsonl").read_text().splitlines():
        json.loads(line)  # raises if any line was corrupted by the adversarial reason text


def _panel_copy(tmp_path: Path) -> Path:
    work = tmp_path / "panel"
    shutil.copytree(EXAMPLE, work)
    return work


def _run_verify(work: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [shutil.which("bash"), "verify.sh"],
        cwd=work, capture_output=True, text=True, timeout=60,
    )


def test_isolated_critics_pass_and_leave_no_canary(tmp_path):
    work = _panel_copy(tmp_path)
    result = _run_verify(work)
    assert result.returncode == 0, result.stderr
    assert "quorum PASS" in result.stdout
    # The canary is scaffolding, not an artifact — it must not survive the run.
    assert not (work / ".critic-canary").exists()


def test_a_critic_that_reads_the_canary_voids_the_panel(tmp_path):
    """The whole point of the canary: a critic that can read files it was never given
    invalidates every score it produced, including a passing one."""
    work = _panel_copy(tmp_path)
    # critic-2 leaks: it scores high AND echoes a file nobody handed it.
    (work / "critic-2.sh").write_text(
        "#!/usr/bin/env bash\n"
        "# PROVIDER=leaky\n"
        "set -euo pipefail\n"
        'leak=$(cat .critic-canary 2>/dev/null | head -1 || true)\n'
        'printf \'{"score": 95, "reason": "%s"}\\n\' "$leak"\n'
    )
    result = _run_verify(work)
    assert result.returncode == 3, f"expected VOID(3), got {result.returncode}: {result.stderr}"
    assert "VOID" in result.stderr
    assert "quorum PASS" not in result.stdout, "a leaky panel must never report a pass"
