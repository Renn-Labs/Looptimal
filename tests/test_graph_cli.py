import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "looptimal-graph.py"
STARTERS = REPO / "scripts" / "graph_starters"


def _load_graph_cli():
    spec = importlib.util.spec_from_file_location("looptimal_graph", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


graph_cli = _load_graph_cli()


def _starter(slug: str = "verified-code-change"):
    return json.loads((STARTERS / slug / "graph.json").read_text(encoding="utf-8"))


def test_all_packaged_starters_are_structurally_green():
    slugs = sorted(path.name for path in STARTERS.iterdir() if path.is_dir())
    assert slugs == [
        "customer-signal-roadmap",
        "gtm-lightning-pmf",
        "product-development-system",
        "reviewed-content-publish",
        "verified-code-change",
    ]

    for slug in slugs:
        graph = _starter(slug)
        errors, order = graph_cli.validate_graph(graph)
        assert errors == [], f"{slug}: {errors}"
        assert len(order) == len(graph["nodes"])


def test_cycle_fails_closed():
    graph = _starter()
    graph["edges"].append(
        {"from": "verify-change", "to": "reproduce-defect", "on": "success"}
    )

    errors, order = graph_cli.validate_graph(graph)

    assert order == []
    assert any("acyclic and connected" in error for error in errors)


def test_self_grading_verifier_fails_closed():
    graph = _starter()
    graph["nodes"][0]["contract"]["verifier"] = {
        "kind": "reviewer",
        "reviewer": "self-review",
        "green_means": "The reproduction is accepted.",
    }

    errors, _ = graph_cli.validate_graph(graph)

    assert any("self-grading verifier is forbidden" in error for error in errors)


@pytest.mark.parametrize("scope", ["acceptance", "node"])
def test_self_grading_green_means_fails_closed(scope):
    graph = _starter()
    if scope == "acceptance":
        verifier = graph["acceptance"]["verifier"]
    else:
        verifier = graph["nodes"][0]["contract"]["verifier"]
    verifier["green_means"] = "The maker says it looks good."

    errors, _ = graph_cli.validate_graph(graph)

    assert any("self-grading claim is forbidden" in error for error in errors)


@pytest.mark.parametrize("command", ["true", "echo accepted", "python3 -c 'print(1)'"])
def test_noop_or_inline_verifier_command_fails_closed(command):
    graph = _starter()
    graph["nodes"][0]["contract"]["verifier"] = {
        "kind": "command",
        "command": command,
        "green_means": "The configured external check proves the reproduction.",
    }

    errors, _ = graph_cli.validate_graph(graph)

    assert any("no-op or inline-eval verifier is forbidden" in error for error in errors)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside/state.jsonl",
        r"..\outside\state.jsonl",
        r"C:\temp\state.jsonl",
        "C:temp/state.jsonl",
        r"\\server\share\state.jsonl",
    ],
)
def test_cross_platform_unsafe_paths_fail_closed(unsafe_path):
    graph = _starter()
    graph["state"]["path"] = unsafe_path

    errors, _ = graph_cli.validate_graph(graph)

    assert any("must stay inside the graph workspace" in error for error in errors)


def test_h1_loop_without_matching_gate_fails_closed():
    graph = _starter()
    graph["nodes"][0]["authority"] = "H1"

    errors, _ = graph_cli.validate_graph(graph)

    assert any("H1 loop requires an inbound approval edge" in error for error in errors)


def test_verified_trust_without_evidence_fails_closed():
    graph = _starter()
    graph["trust_tier"] = "verified"
    graph["evidence_refs"] = []

    errors, _ = graph_cli.validate_graph(graph)

    assert "evidence_refs: requires at least one item" in errors


def test_duplicate_edge_is_reported_without_corrupting_order():
    graph = _starter()
    graph["edges"].append(copy.deepcopy(graph["edges"][0]))

    errors, order = graph_cli.validate_graph(graph)

    assert any("duplicate edge" in error for error in errors)
    assert order == ["reproduce-defect", "implement-change", "verify-change"]


def test_starters_json_lists_packaged_patterns(capsys):
    exit_code = graph_cli.main(["looptimal-graph", "starters", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "GREEN"
    assert payload["errors"] == []
    assert {row["slug"] for row in payload["starters"]} == {
        "verified-code-change",
        "customer-signal-roadmap",
        "reviewed-content-publish",
        "product-development-system",
        "gtm-lightning-pmf",
    }
    assert all(row["trust_tier"] == "starter" for row in payload["starters"])


def test_init_copies_a_valid_starter(tmp_path, capsys):
    destination = tmp_path / "my-graph"

    exit_code = graph_cli.main(
        [
            "looptimal-graph",
            "init",
            str(destination),
            "--starter",
            "customer-signal-roadmap",
        ]
    )

    assert exit_code == 0
    assert (destination / "README.md").is_file()
    graph = json.loads((destination / "graph.json").read_text(encoding="utf-8"))
    errors, _ = graph_cli.validate_graph(graph)
    assert errors == []
    assert "next: looptimal graph inspect" in capsys.readouterr().out


def test_init_refuses_a_file_destination(tmp_path, capsys):
    destination = tmp_path / "occupied"
    destination.write_text("do not overwrite", encoding="utf-8")

    exit_code = graph_cli.main(["looptimal-graph", "init", str(destination)])

    assert exit_code == 1
    assert destination.read_text(encoding="utf-8") == "do not overwrite"
    assert "destination is not a directory" in capsys.readouterr().err


def test_init_rejects_starter_path_traversal(tmp_path, capsys):
    exit_code = graph_cli.main(
        ["looptimal-graph", "init", str(tmp_path / "graph"), "--starter", "../outside"]
    )

    assert exit_code == 2
    assert "unknown starter" in capsys.readouterr().err


def test_starters_fails_closed_when_package_assets_are_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(graph_cli, "STARTERS_DIR", tmp_path)

    exit_code = graph_cli.main(["looptimal-graph", "starters", "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "RED"
    assert payload["starters"] == []
    assert len(payload["errors"]) == 5


def test_inspect_returns_deterministic_order_and_gate(capsys):
    graph_path = STARTERS / "reviewed-content-publish" / "graph.json"

    exit_code = graph_cli.main(
        ["looptimal-graph", "inspect", str(graph_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [node["id"] for node in payload["order"]] == [
        "source-claims",
        "draft-article",
        "audience-review",
        "publish-approval",
        "publish-content",
    ]
    assert payload["human_gates"] == [
        {"id": "publish-approval", "authority": "H1", "approver": "Chairman"}
    ]
    assert payload["execution_mode"] == "disabled"


def test_render_requires_green_and_preserves_authority(capsys):
    graph_path = STARTERS / "reviewed-content-publish" / "graph.json"

    exit_code = graph_cli.main(["looptimal-graph", "render", str(graph_path)])

    assert exit_code == 0
    rendered = capsys.readouterr().out
    assert rendered.startswith("flowchart TD\n")
    assert 'n_publish_approval{"Approve public publication<br/>human_gate | H1"}' in rendered
    assert "n_publish_approval -->|approval| n_publish_content" in rendered


def test_render_refuses_overwrite_without_force(tmp_path, capsys):
    graph_path = STARTERS / "verified-code-change" / "graph.json"
    output = tmp_path / "graph.mmd"
    output.write_text("preserve me", encoding="utf-8")

    refused = graph_cli.main(
        ["looptimal-graph", "render", str(graph_path), "--output", str(output)]
    )

    assert refused == 1
    assert output.read_text(encoding="utf-8") == "preserve me"
    assert "refusing to overwrite" in capsys.readouterr().err

    forced = graph_cli.main(
        [
            "looptimal-graph",
            "render",
            str(graph_path),
            "--output",
            str(output),
            "--force",
        ]
    )

    assert forced == 0
    assert output.read_text(encoding="utf-8").startswith("flowchart TD\n")


def test_graph_schema_doc_names_the_executable_contract():
    text = (REPO / "references" / "graph-schema.md").read_text(encoding="utf-8")

    assert "scripts/looptimal-graph.py" in text
    assert "execution.mode" in text
    assert "must be `disabled`" in text.lower()
