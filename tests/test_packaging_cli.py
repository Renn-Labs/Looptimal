import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "looptimal_cli",
        REPO / "looptimal_cli" / "__init__.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


looptimal_cli = _load_cli()


def test_grouped_loopprint_ls_dispatches_to_existing_script(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loopprint", "ls", "--json"])

    with pytest.raises(SystemExit) as exc:
        looptimal_cli.loopprint()

    assert exc.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["loops"] == []
    assert set(payload["scanned_roots"]) == {".omc/loops", "loops"}


def test_grouped_loopprint_library_dispatches_to_existing_script(monkeypatch, capsys):
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(sys, "argv", ["loopprint", "library", "search", "secret", "--json"])

    with pytest.raises(SystemExit) as exc:
        looptimal_cli.loopprint()

    assert exc.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert {row["slug"] for row in payload["loops"]} == {"secret-scan"}


def test_grouped_looptimal_library_dispatches_to_existing_script(monkeypatch, capsys):
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(sys, "argv", ["looptimal", "library", "search", "secret", "--json"])

    with pytest.raises(SystemExit) as exc:
        looptimal_cli.looptimal()

    assert exc.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert {row["slug"] for row in payload["loops"]} == {"secret-scan"}


def test_grouped_loopprint_help_lists_subcommands(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["loopprint", "--help"])

    with pytest.raises(SystemExit) as exc:
        looptimal_cli.loopprint()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage: loopprint <command> [args...]" in out
    assert "library" in out
    assert "ls" in out
    assert "lint" in out


def test_grouped_looptimal_help_lists_subcommands(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["looptimal", "--help"])

    with pytest.raises(SystemExit) as exc:
        looptimal_cli.looptimal()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage: looptimal <command> [args...]" in out
    assert "graph" in out
    assert "library" in out
    assert "verify-outcome" in out
    assert "doctor" in out


def test_grouped_looptimal_graph_dispatches_to_starter_cli(monkeypatch, capsys):
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(sys, "argv", ["looptimal", "graph", "starters", "--json"])

    with pytest.raises(SystemExit) as exc:
        looptimal_cli.looptimal()

    assert exc.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert {row["slug"] for row in payload["starters"]} == {
        "verified-code-change",
        "customer-signal-roadmap",
        "reviewed-content-publish",
    }


def test_grouped_loopprint_unknown_command_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["loopprint", "wat"])

    with pytest.raises(SystemExit) as exc:
        looptimal_cli.loopprint()

    assert exc.value.code == 2
    assert "unknown command 'wat'" in capsys.readouterr().err


def test_grouped_looptimal_unknown_command_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["looptimal", "wat"])

    with pytest.raises(SystemExit) as exc:
        looptimal_cli.looptimal()

    assert exc.value.code == 2
    assert "unknown command 'wat'" in capsys.readouterr().err
