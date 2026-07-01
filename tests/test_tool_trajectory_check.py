"""Tests for templates/tool_trajectory_check.py — oracle #15 "Sealed Tool-Trajectory Match"'s
reference implementation."""
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "templates" / "tool_trajectory_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("tool_trajectory_check", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ttc = _load()


def _events(*tools):
    return [{"tool": t, "args_summary": ""} for t in tools]


def test_allowed_sequence_passes():
    events = _events("Read", "Grep", "Bash")
    spec = {"allow": ["Read", "Grep", "Bash"]}
    assert ttc.check(events, spec) == []


def test_forbidden_tool_via_deny_list_fails():
    events = _events("Read", "Write")
    spec = {"deny": ["Write"]}
    violations = ttc.check(events, spec)
    assert len(violations) == 1
    assert "Write" in violations[0] and "deny-list" in violations[0]


def test_tool_not_on_allow_list_fails():
    events = _events("Read", "Bash")
    spec = {"allow": ["Read"]}
    violations = ttc.check(events, spec)
    assert len(violations) == 1
    assert "Bash" in violations[0] and "allow-list" in violations[0]


def test_strict_order_requires_contiguous_subsequence():
    spec = {"order": ["Read", "Bash"], "order_mode": "strict"}
    assert ttc.check(_events("Grep", "Read", "Bash"), spec) == []  # contiguous somewhere — OK
    assert ttc.check(_events("Read", "Grep", "Bash"), spec) != []  # not contiguous — fails


def test_subset_order_ignores_interleaved_other_tools():
    spec = {"order": ["Read", "Bash"], "order_mode": "subset"}
    # Grep interleaved shouldn't matter — only relative order of Read/Bash is checked.
    assert ttc.check(_events("Read", "Grep", "Bash"), spec) == []
    assert ttc.check(_events("Bash", "Grep", "Read"), spec) != []  # wrong relative order


def test_unordered_mode_never_flags_order():
    spec = {"order": ["Read", "Bash"], "order_mode": "unordered"}
    assert ttc.check(_events("Bash", "Read"), spec) == []


def test_no_order_declared_never_checks_order():
    spec = {"allow": ["Read", "Bash"]}
    assert ttc.check(_events("Bash", "Read"), spec) == []


def test_main_exits_nonzero_and_reports_violations_on_stderr(tmp_path, capsys):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join(json.dumps(e) for e in _events("Read", "Write")) + "\n")
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({"deny": ["Write"]}))

    rc = ttc.main(["--transcript", str(transcript), "--spec", str(spec_path)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "RED" in captured.err
    assert "Write" in captured.err


def test_main_exits_zero_on_compliant_transcript(tmp_path, capsys):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join(json.dumps(e) for e in _events("Read", "Grep")) + "\n")
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({"allow": ["Read", "Grep"]}))

    rc = ttc.main(["--transcript", str(transcript), "--spec", str(spec_path)])
    assert rc == 0
    assert "GREEN" in capsys.readouterr().out


def test_malformed_transcript_line_is_a_clean_error(tmp_path, capsys):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("not json\n")
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({}))

    rc = ttc.main(["--transcript", str(transcript), "--spec", str(spec_path)])
    assert rc == 1
    assert "cannot load transcript" in capsys.readouterr().err
