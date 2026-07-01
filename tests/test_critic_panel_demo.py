"""Subprocess-level coverage of examples/critic-panel/run_demo.sh — proves the {score, reason}
JSON critic contract (item 11) actually works end-to-end, both the quorum-PASS and the
fail-flip quorum-FAIL path, the way tests/test_runner_ratchet.py covers run-this-loop.sh."""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "critic-panel"
DEMO = EXAMPLE / "run_demo.sh"


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
