#!/usr/bin/env python3
"""tool_trajectory_check.py — reference implementation for oracle #15 "Sealed Tool-Trajectory
Match" (references/oracle-library.md). Verifies an Execute-stage agent's tool-call PROCESS, not
just its final output: did it stay inside an allowed capability surface, avoid a denied one, and
(optionally) respect a declared call order?

Deliberately generic: this repo ships ONE reference implementation, not a per-harness transcript
adapter for every supported harness (Claude Code, OpenCode, Hermes, etc. all log tool calls
differently). A framer normalizes their harness's actual transcript into the JSON-lines shape
this script expects — one JSON object per line, each with at least a "tool" key — before running
this check. The matching logic itself (allow/deny/order) does not change per harness.

Transcript line shape (JSON-lines, one call per line):
  {"tool": "Read", "args_summary": "config.yaml"}

Spec shape (JSON or this repo's tiny-YAML subset — see _common.py::load_config):
  allow: [Read, Grep, Bash]          # OPTIONAL — if set, any tool NOT in this list is forbidden
  deny: [Write]                      # OPTIONAL — always forbidden, even if also in allow
  order: [Read, Bash]                # OPTIONAL — a sequence that must appear, per order_mode
  order_mode: strict                 # strict (exact prefix-free subsequence, contiguous) |
                                      # subset (order among only the named tools, others may
                                      # interleave) | unordered (order is not checked)

Stdlib-only. Never eval()'s anything from the transcript or spec — both are parsed as data.

Usage: tool_trajectory_check.py --transcript <path> --spec <path>
Exit 0 = compliant (GREEN), 1 = a forbidden call or an order violation was found (RED).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _common import TinyYamlError, as_list, load_config  # noqa: E402


def load_transcript(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"transcript line {lineno} is not valid JSON: {exc}") from exc
        if not isinstance(event, dict) or "tool" not in event:
            raise ValueError(f"transcript line {lineno} must be an object with a 'tool' key")
        events.append(event)
    return events


def check(events: list[dict[str, Any]], spec: dict[str, Any]) -> list[str]:
    """Returns a list of violation strings — empty means compliant."""
    violations: list[str] = []
    allow = set(as_list(spec.get("allow"))) or None
    deny = set(as_list(spec.get("deny")))
    order = [str(t) for t in as_list(spec.get("order"))]
    order_mode = str(spec.get("order_mode") or "unordered").strip().lower()

    for i, event in enumerate(events):
        tool = str(event.get("tool") or "")
        if tool in deny:
            violations.append(f"call {i}: tool {tool!r} is on the deny-list")
        elif allow is not None and tool not in allow:
            violations.append(f"call {i}: tool {tool!r} is not on the allow-list {sorted(allow)}")

    if order and order_mode != "unordered":
        called = [str(e.get("tool") or "") for e in events]
        if order_mode == "strict":
            # `order` must appear as a contiguous subsequence somewhere in the transcript.
            found = any(called[j:j + len(order)] == order for j in range(len(called) - len(order) + 1))
            if not found:
                violations.append(f"order (strict) not satisfied — expected {order} to appear "
                                  f"contiguously; got {called}")
        elif order_mode == "subset":
            # among only the calls that ARE in `order`, they must appear in the declared sequence.
            filtered = [t for t in called if t in order]
            found = filtered == order
            if not found:
                violations.append(f"order (subset) not satisfied — among calls to {order}, "
                                  f"expected sequence {order}; got {filtered}")
        else:
            violations.append(f"unknown order_mode {order_mode!r} — must be strict, subset, or unordered")

    return violations


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify a tool-call transcript against a sealed allow/deny/order spec.")
    ap.add_argument("--transcript", required=True, help="path to a JSON-lines tool-call transcript")
    ap.add_argument("--spec", required=True, help="path to the allow/deny/order spec (JSON or tiny-YAML)")
    args = ap.parse_args(argv)

    try:
        events = load_transcript(Path(args.transcript))
    except (OSError, ValueError) as exc:
        print(f"tool_trajectory_check: cannot load transcript: {exc}", file=sys.stderr)
        return 1
    try:
        spec = load_config(Path(args.spec))
    except (TinyYamlError, OSError) as exc:
        print(f"tool_trajectory_check: cannot load spec: {exc}", file=sys.stderr)
        return 1
    if not isinstance(spec, dict):
        print("tool_trajectory_check: spec must be a mapping", file=sys.stderr)
        return 1

    violations = check(events, spec)
    if violations:
        print(f"tool_trajectory_check: RED ({len(violations)} violation(s))", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print(f"tool_trajectory_check: GREEN ({len(events)} calls, all compliant)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
