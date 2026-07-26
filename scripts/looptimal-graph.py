#!/usr/bin/env python3
"""Create, validate, inspect, and render governed Looptimal graph manifests.

Graph v1 is intentionally non-authoritative: it composes immutable loop references and human
gates, but it does not execute nodes, clear authority gates, or manufacture evidence. The CLI is
stdlib-only and accepts JSON or the repository's portable YAML subset.
"""
from __future__ import annotations

import argparse
import heapq
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    TinyYamlError,
    as_dict,
    as_list,
    is_noop_command,
    is_traversing_ref,
    load_config,
)

SCHEMA_VERSION = 1
STARTERS_DIR = Path(__file__).resolve().parent / "graph_starters"
EXPECTED_STARTERS = (
    "customer-signal-roadmap",
    "gtm-lightning-pmf",
    "product-development-system",
    "reviewed-content-publish",
    "verified-code-change",
)
VALID_NODE_KINDS = {"loop", "human_gate"}
VALID_EDGE_EVENTS = {"success", "approval", "data"}
VALID_AUTHORITIES = {"tier-a", "H1", "H2", "custom"}
VALID_TRUST_TIERS = {"idea", "starter", "runnable", "verified", "receipted"}
VALID_VERIFIER_KINDS = {"command", "reviewer", "rubric"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
LOOP_REF_RE = re.compile(r"^loop://[a-z0-9][a-z0-9-]{1,62}@\d+\.\d+\.\d+$")
SELF_GRADE_RE = re.compile(
    r"\b(self[-\s]?(grade|review|check|verify)|looks? good|seems? fine|trust me|"
    r"the (agent|maker|model) says)\b",
    re.I,
)
PLACEHOLDER_RE = re.compile(r"<[^>]+>|\b(todo|tbd|replace this)\b", re.I)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _portable_path_error(value: Any) -> str | None:
    raw = _text(value)
    if not raw:
        return "must be a non-empty relative path"
    normalized = raw.replace("\\", "/")
    if (
        is_traversing_ref(normalized)
        or normalized.startswith("//")
        or re.match(r"^[A-Za-z]:", normalized)
    ):
        return "must stay inside the graph workspace (absolute paths and '..' are forbidden)"
    return None


def _string_list_errors(prefix: str, value: Any, *, required: bool = True) -> list[str]:
    rows = as_list(value)
    errors: list[str] = []
    if required and not rows:
        return [f"{prefix}: requires at least one item"]
    for index, item in enumerate(rows):
        if not _text(item):
            errors.append(f"{prefix}[{index}]: must be a non-empty string")
    return errors


def _verifier_errors(prefix: str, value: Any) -> list[str]:
    verifier = as_dict(value)
    errors: list[str] = []
    kind = _text(verifier.get("kind"))
    if kind not in VALID_VERIFIER_KINDS:
        errors.append(f"{prefix}.kind: must be one of {sorted(VALID_VERIFIER_KINDS)}")

    if kind == "command":
        identity = _text(verifier.get("command"))
        field = "command"
    else:
        identity = _text(verifier.get("reviewer"))
        field = "reviewer"
    if not identity:
        errors.append(f"{prefix}.{field}: required for verifier kind {kind!r}")
    elif SELF_GRADE_RE.search(identity) or PLACEHOLDER_RE.search(identity):
        errors.append(f"{prefix}.{field}: placeholder or self-grading verifier is forbidden")
    elif kind == "command" and is_noop_command(identity):
        errors.append(f"{prefix}.command: no-op or inline-eval verifier is forbidden")

    green_means = _text(verifier.get("green_means"))
    if not green_means:
        errors.append(f"{prefix}.green_means: must state what a pass proves")
    elif SELF_GRADE_RE.search(green_means) or PLACEHOLDER_RE.search(green_means):
        errors.append(f"{prefix}.green_means: placeholder or self-grading claim is forbidden")
    return errors


def _loop_node_errors(index: int, node: dict[str, Any]) -> list[str]:
    prefix = f"nodes[{index}]"
    errors: list[str] = []
    uses = _text(node.get("uses"))
    if not LOOP_REF_RE.fullmatch(uses):
        errors.append(f"{prefix}.uses: expected immutable loop://slug@x.y.z reference")

    actors = as_dict(node.get("actors"))
    maker = _text(actors.get("maker"))
    checker = _text(actors.get("checker"))
    if not maker or not checker:
        errors.append(f"{prefix}.actors: maker and checker are required")
    elif maker.casefold() == checker.casefold():
        errors.append(f"{prefix}.actors: maker and checker must differ")

    contract = as_dict(node.get("contract"))
    if not _text(contract.get("goal")):
        errors.append(f"{prefix}.contract.goal: required")
    path_error = _portable_path_error(contract.get("state"))
    if path_error:
        errors.append(f"{prefix}.contract.state: {path_error}")
    errors.extend(_verifier_errors(f"{prefix}.contract.verifier", contract.get("verifier")))

    stop = as_dict(contract.get("stop"))
    if not _text(stop.get("success")):
        errors.append(f"{prefix}.contract.stop.success: required")
    if not _positive_int(stop.get("max_iterations")):
        errors.append(f"{prefix}.contract.stop.max_iterations: must be a positive integer")

    errors.extend(_string_list_errors(f"{prefix}.evidence", node.get("evidence")))
    return errors


def _human_gate_errors(index: int, node: dict[str, Any]) -> list[str]:
    prefix = f"nodes[{index}]"
    errors: list[str] = []
    authority = _text(node.get("authority"))
    if authority not in {"H1", "H2", "custom"}:
        errors.append(f"{prefix}.authority: human gates require H1, H2, or custom")
    if not _text(node.get("approver")):
        errors.append(f"{prefix}.approver: named human role is required")
    errors.extend(_string_list_errors(f"{prefix}.evidence", node.get("evidence")))
    return errors


def validate_graph(graph: Any) -> tuple[list[str], list[str]]:
    """Return (blocking errors, deterministic topological order)."""
    if not isinstance(graph, dict):
        return ["root: graph manifest must be an object"], []

    errors: list[str] = []
    if graph.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version: expected {SCHEMA_VERSION}")

    graph_id = _text(graph.get("id"))
    if not ID_RE.fullmatch(graph_id):
        errors.append("id: expected lowercase kebab-case identifier")
    if not SEMVER_RE.fullmatch(_text(graph.get("version"))):
        errors.append("version: expected semantic version x.y.z")
    if not _text(graph.get("name")):
        errors.append("name: required")
    if not _text(graph.get("outcome")):
        errors.append("outcome: required")

    trust_tier = _text(graph.get("trust_tier"))
    if trust_tier not in VALID_TRUST_TIERS:
        errors.append(f"trust_tier: must be one of {sorted(VALID_TRUST_TIERS)}")
    evidence_refs = as_list(graph.get("evidence_refs"))
    if trust_tier in {"verified", "receipted"}:
        errors.extend(_string_list_errors("evidence_refs", evidence_refs))
    elif any(not _text(item) for item in evidence_refs):
        errors.append("evidence_refs: every present reference must be a non-empty string")
    if trust_tier == "receipted":
        receipt_error = _portable_path_error(graph.get("receipt_path"))
        if receipt_error:
            errors.append(f"receipt_path: {receipt_error}")

    execution = as_dict(graph.get("execution"))
    if execution.get("mode") != "disabled":
        errors.append("execution.mode: graph v1 must be 'disabled' (this kit is not a runtime)")

    state = as_dict(graph.get("state"))
    state_error = _portable_path_error(state.get("path"))
    if state_error:
        errors.append(f"state.path: {state_error}")

    default_authority = _text(as_dict(graph.get("authority")).get("default"))
    if default_authority not in VALID_AUTHORITIES:
        errors.append(f"authority.default: must be one of {sorted(VALID_AUTHORITIES)}")

    acceptance = as_dict(graph.get("acceptance"))
    errors.extend(_verifier_errors("acceptance.verifier", acceptance.get("verifier")))
    errors.extend(_string_list_errors("acceptance.evidence", acceptance.get("evidence")))

    graph_stop = as_dict(graph.get("stop"))
    if not _text(graph_stop.get("success")):
        errors.append("stop.success: required")
    if not _positive_int(graph_stop.get("max_transitions")):
        errors.append("stop.max_transitions: must be a positive integer")
    if not _positive_int(graph_stop.get("wall_clock_minutes")):
        errors.append("stop.wall_clock_minutes: must be a positive integer")

    node_rows = as_list(graph.get("nodes"))
    if not node_rows:
        errors.append("nodes: requires at least one node")
        return errors, []

    nodes: dict[str, dict[str, Any]] = {}
    for index, raw_node in enumerate(node_rows):
        node = as_dict(raw_node)
        if not node:
            errors.append(f"nodes[{index}]: must be an object")
            continue
        node_id = _text(node.get("id"))
        if not ID_RE.fullmatch(node_id):
            errors.append(f"nodes[{index}].id: expected lowercase kebab-case identifier")
            continue
        if node_id in nodes:
            errors.append(f"nodes[{index}].id: duplicate node {node_id!r}")
            continue
        nodes[node_id] = node
        kind = _text(node.get("kind"))
        if kind not in VALID_NODE_KINDS:
            errors.append(f"nodes[{index}].kind: must be one of {sorted(VALID_NODE_KINDS)}")
        if not _text(node.get("name")):
            errors.append(f"nodes[{index}].name: required")
        if not _text(node.get("outcome")):
            errors.append(f"nodes[{index}].outcome: required")
        authority = _text(node.get("authority"))
        if authority not in VALID_AUTHORITIES:
            errors.append(f"nodes[{index}].authority: must be one of {sorted(VALID_AUTHORITIES)}")
        if kind == "loop":
            errors.extend(_loop_node_errors(index, node))
        elif kind == "human_gate":
            errors.extend(_human_gate_errors(index, node))

    indegree = {node_id: 0 for node_id in nodes}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    valid_edges: list[tuple[str, str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for index, raw_edge in enumerate(as_list(graph.get("edges"))):
        edge = as_dict(raw_edge)
        source = _text(edge.get("from"))
        target = _text(edge.get("to"))
        event = _text(edge.get("on"))
        if source not in nodes:
            errors.append(f"edges[{index}].from: unknown node {source!r}")
        if target not in nodes:
            errors.append(f"edges[{index}].to: unknown node {target!r}")
        if source and source == target:
            errors.append(f"edges[{index}]: self-edge is forbidden")
        if event not in VALID_EDGE_EVENTS:
            errors.append(f"edges[{index}].on: must be one of {sorted(VALID_EDGE_EVENTS)}")
        key = (source, target, event)
        duplicate = key in seen_edges
        if duplicate:
            errors.append(f"edges[{index}]: duplicate edge {source!r}->{target!r} on {event!r}")
        seen_edges.add(key)
        if (
            not duplicate
            and source in nodes
            and target in nodes
            and source != target
            and event in VALID_EDGE_EVENTS
        ):
            valid_edges.append(key)
            indegree[target] += 1
            outgoing[source].append(target)

    roots = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    if len(roots) != 1:
        errors.append(f"topology: expected exactly one root node, found {len(roots)} ({roots})")

    queue = roots[:]
    heapq.heapify(queue)
    remaining = dict(indegree)
    order: list[str] = []
    while queue:
        node_id = heapq.heappop(queue)
        order.append(node_id)
        for target in sorted(outgoing[node_id]):
            remaining[target] -= 1
            if remaining[target] == 0:
                heapq.heappush(queue, target)
    if len(order) != len(nodes):
        blocked = sorted(set(nodes) - set(order))
        errors.append(f"topology: graph must be acyclic and connected; blocked nodes: {blocked}")

    for node_id, node in nodes.items():
        kind = _text(node.get("kind"))
        authority = _text(node.get("authority"))
        if kind == "human_gate":
            if not any(source == node_id and event == "approval" for source, _, event in valid_edges):
                errors.append(f"nodes.{node_id}: human gate requires an outgoing approval edge")
        if kind == "loop" and authority in {"H1", "H2"}:
            approved = any(
                target == node_id
                and event == "approval"
                and _text(nodes[source].get("kind")) == "human_gate"
                and _text(nodes[source].get("authority")) == authority
                for source, target, event in valid_edges
            )
            if not approved:
                errors.append(
                    f"nodes.{node_id}: {authority} loop requires an inbound approval edge "
                    f"from a matching human gate"
                )

    return errors, order


def _graph_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_dir():
        for name in ("graph.json", "graph.yaml", "graph.yml"):
            candidate = path / name
            if candidate.is_file():
                return candidate
        raise FileNotFoundError(f"no graph.json, graph.yaml, or graph.yml under {path}")
    return path


def _load_graph(raw: str | Path) -> tuple[Path, dict[str, Any]]:
    path = _graph_path(raw).resolve()
    data = load_config(path)
    if not isinstance(data, dict):
        raise TinyYamlError(f"graph root must be an object: {path}")
    return path, data


def _starter_rows() -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    if not STARTERS_DIR.is_dir():
        return rows, [f"packaged starter directory is missing: {STARTERS_DIR}"]
    for slug in EXPECTED_STARTERS:
        directory = STARTERS_DIR / slug
        graph_path = directory / "graph.json"
        if not graph_path.is_file():
            errors.append(f"packaged starter is missing: {slug}/graph.json")
            continue
        try:
            graph = load_config(graph_path)
        except (OSError, TinyYamlError) as exc:
            errors.append(f"packaged starter could not be loaded: {slug}: {exc}")
            continue
        validation_errors, _ = validate_graph(graph)
        if validation_errors:
            errors.append(
                f"packaged starter is RED: {slug}: {'; '.join(validation_errors)}"
            )
            continue
        rows.append(
            {
                "slug": slug,
                "name": _text(graph.get("name")),
                "outcome": _text(graph.get("outcome")),
                "trust_tier": _text(graph.get("trust_tier")),
            }
        )
    return rows, errors


def _summary(graph: dict[str, Any], order: list[str]) -> dict[str, Any]:
    nodes = {str(node["id"]): node for node in as_list(graph.get("nodes"))}
    terminals = sorted(set(nodes) - {str(edge.get("from")) for edge in as_list(graph.get("edges"))})
    return {
        "id": graph["id"],
        "version": graph["version"],
        "name": graph["name"],
        "outcome": graph["outcome"],
        "trust_tier": graph["trust_tier"],
        "execution_mode": as_dict(graph.get("execution")).get("mode"),
        "order": [
            {
                "id": node_id,
                "name": nodes[node_id]["name"],
                "kind": nodes[node_id]["kind"],
                "authority": nodes[node_id]["authority"],
            }
            for node_id in order
        ],
        "human_gates": [
            {
                "id": node_id,
                "authority": nodes[node_id]["authority"],
                "approver": nodes[node_id].get("approver"),
            }
            for node_id in order
            if nodes[node_id]["kind"] == "human_gate"
        ],
        "terminals": terminals,
        "acceptance": graph["acceptance"],
        "stop": graph["stop"],
        "notice": "Non-authoritative graph projection; execution is disabled.",
    }


def _mermaid(graph: dict[str, Any]) -> str:
    def label(value: Any) -> str:
        return " ".join(str(value).replace('"', "'").replace("[", "(").replace("]", ")").split())

    lines = [
        "flowchart TD",
        f'  %% {label(graph["name"])} - non-authoritative; execution disabled',
    ]
    for node in as_list(graph.get("nodes")):
        node_id = f'n_{str(node["id"]).replace("-", "_")}'
        body = f'{label(node["name"])}<br/>{node["kind"]} | {node["authority"]}'
        if node["kind"] == "human_gate":
            lines.append(f'  {node_id}{{"{body}"}}')
        else:
            lines.append(f'  {node_id}["{body}"]')
    for edge in as_list(graph.get("edges")):
        source = f'n_{str(edge["from"]).replace("-", "_")}'
        target = f'n_{str(edge["to"]).replace("-", "_")}'
        lines.append(f'  {source} -->|{label(edge["on"])}| {target}')
    return "\n".join(lines) + "\n"


def _cmd_starters(args: argparse.Namespace) -> int:
    rows, errors = _starter_rows()
    if args.json:
        print(
            json.dumps(
                {
                    "verdict": "RED" if errors else "GREEN",
                    "starters": rows,
                    "errors": errors,
                },
                indent=2,
            )
        )
    else:
        if errors:
            print("looptimal graph starters: RED", file=sys.stderr)
            for error in errors:
                print(f"  RED  {error}", file=sys.stderr)
            return 1
        print("Looptimal graph starters (structure only; execution disabled)")
        for row in rows:
            print(f"- {row['slug']}: {row['name']} - {row['outcome']}")
    return 1 if errors else 0


def _cmd_init(args: argparse.Namespace) -> int:
    starter = _text(args.starter)
    if starter not in EXPECTED_STARTERS or not ID_RE.fullmatch(starter):
        print(f"graph init: unknown starter {args.starter!r}", file=sys.stderr)
        return 2
    source = STARTERS_DIR / starter
    if not (source / "graph.json").is_file():
        print(f"graph init: unknown starter {args.starter!r}", file=sys.stderr)
        return 2

    try:
        source_path, source_graph = _load_graph(source)
    except (OSError, TinyYamlError, ValueError) as exc:
        print(f"graph init: packaged starter could not be loaded: {exc}", file=sys.stderr)
        return 1
    source_errors, _ = validate_graph(source_graph)
    if source_errors:
        print(f"graph init: packaged starter is RED: {source_path}", file=sys.stderr)
        for error in source_errors:
            print(f"  RED  {error}", file=sys.stderr)
        return 1

    destination = Path(args.destination).resolve()
    if destination.exists():
        if not destination.is_dir():
            print(f"graph init: destination is not a directory: {destination}", file=sys.stderr)
            return 1
        if any(destination.iterdir()):
            print(f"graph init: refusing to overwrite non-empty {destination}", file=sys.stderr)
            return 1
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_file():
            shutil.copy2(item, target)
    path, graph = _load_graph(destination)
    errors, _ = validate_graph(graph)
    if errors:
        print("graph init: packaged starter failed validation", file=sys.stderr)
        for error in errors:
            print(f"  RED  {error}", file=sys.stderr)
        return 1
    print(f"graph init: wrote {path}")
    print(f"next: looptimal graph inspect {path}")
    return 0


def _validated(raw: str) -> tuple[Path | None, dict[str, Any] | None, list[str], list[str]]:
    try:
        path, graph = _load_graph(raw)
    except (OSError, TinyYamlError, ValueError) as exc:
        return None, None, [str(exc)], []
    errors, order = validate_graph(graph)
    return path, graph, errors, order


def _cmd_validate(args: argparse.Namespace) -> int:
    path, graph, errors, order = _validated(args.graph)
    report = {
        "verdict": "RED" if errors else "GREEN",
        "path": str(path) if path else str(args.graph),
        "errors": errors,
        "order": order,
        "execution_mode": as_dict(graph.get("execution")).get("mode") if graph else None,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    elif errors:
        print(f"graph validate: RED — {len(errors)} blocking issue(s)", file=sys.stderr)
        for error in errors:
            print(f"  RED  {error}", file=sys.stderr)
    else:
        print(
            f"graph validate: GREEN — {graph['id']}@{graph['version']} "
            f"({len(order)} nodes; execution disabled)"
        )
    return 1 if errors else 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    _, graph, errors, order = _validated(args.graph)
    if errors or graph is None:
        print("graph inspect: manifest is RED; run `looptimal graph validate`", file=sys.stderr)
        for error in errors:
            print(f"  RED  {error}", file=sys.stderr)
        return 1
    summary = _summary(graph, order)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"{summary['name']} ({summary['id']}@{summary['version']})")
        print("NON-AUTHORITATIVE · execution disabled")
        print(f"Outcome: {summary['outcome']}")
        for index, node in enumerate(summary["order"], start=1):
            print(
                f"{index}. {node['name']} "
                f"[{node['kind']} · authority={node['authority']}]"
            )
        if summary["human_gates"]:
            print("Human gates:")
            for gate in summary["human_gates"]:
                print(f"- {gate['authority']}: {gate['id']} ({gate['approver']})")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    _, graph, errors, _ = _validated(args.graph)
    if errors or graph is None:
        print("graph render: manifest is RED; refusing to render", file=sys.stderr)
        for error in errors:
            print(f"  RED  {error}", file=sys.stderr)
        return 1
    rendered = _mermaid(graph)
    if args.output:
        output = Path(args.output)
        if output.exists():
            if output.is_dir():
                print(f"graph render: output is a directory: {output}", file=sys.stderr)
                return 1
            if not args.force:
                print(
                    f"graph render: refusing to overwrite existing {output}; use --force",
                    file=sys.stderr,
                )
                return 1
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"graph render: wrote {output}")
    else:
        sys.stdout.write(rendered)
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="looptimal graph",
        description="Create and inspect governed loop graphs. Graph v1 never executes nodes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    starters = sub.add_parser("starters", help="list packaged starter graphs")
    starters.add_argument("--json", action="store_true")
    starters.set_defaults(handler=_cmd_starters)

    init = sub.add_parser("init", help="copy a packaged starter into a new directory")
    init.add_argument("destination")
    init.add_argument("--starter", default="verified-code-change")
    init.set_defaults(handler=_cmd_init)

    validate = sub.add_parser("validate", help="fail-closed graph schema and topology validation")
    validate.add_argument("graph")
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(handler=_cmd_validate)

    inspect = sub.add_parser("inspect", help="show ordered nodes, authority, and human gates")
    inspect.add_argument("graph")
    inspect.add_argument("--json", action="store_true")
    inspect.set_defaults(handler=_cmd_inspect)

    render = sub.add_parser("render", help="render a validated graph as Mermaid")
    render.add_argument("graph")
    render.add_argument("--output", "-o")
    render.add_argument("--force", action="store_true")
    render.set_defaults(handler=_cmd_render)

    args = parser.parse_args(argv[1:])
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
