#!/usr/bin/env python3
"""loopprint-report — roll up loop runner metrics into cost-per-accepted-change.

Reads append-only metrics.jsonl emitted by a loop runner. Each line is one iteration:

    {"iter": 1, "ts": "...", "wall_ms": 1200, "verifier_result": "GREEN",
     "accepted": true, "tokens": 4000, "cost_usd": 0.02}

Tokens and cost_usd are optional — inject them via a per-harness adapter hook. The
north-star metric is cost_per_accepted_change = total_cost_usd / accepted_count.

Usage:
    loopprint-report.py <metrics.jsonl>       # human-readable table
    loopprint-report.py <metrics.jsonl> --json

Exit code: 0 on success, 2 if no metrics path is given. Blank or malformed lines are
skipped (count reported). Stdlib-only (json, argparse, datetime).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

NA_COST_MSG = "n/a (inject tokens/cost via a harness adapter)"


def _format_wall_ms(total_ms: int) -> str:
    if total_ms < 0:
        total_ms = 0
    total_s, ms_rem = divmod(total_ms, 1000)
    if total_s >= 3600:
        hours, rem = divmod(total_s, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{hours}h{minutes}m{seconds}s"
    if total_s >= 60:
        minutes, seconds = divmod(total_s, 60)
        return f"{minutes}m{seconds}s"
    if total_s > 0:
        return f"{total_s}s"
    if ms_rem > 0:
        return f"{ms_rem}ms"
    return "0s"


def _parse_record(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        wall_ms = int(raw["wall_ms"])
    except (KeyError, TypeError, ValueError):
        return None
    accepted = raw.get("accepted")
    if not isinstance(accepted, bool):
        return None
    return {
        "iter": raw.get("iter"),
        "ts": raw.get("ts"),
        "wall_ms": wall_ms,
        "verifier_result": raw.get("verifier_result"),
        "accepted": accepted,
        "tokens": raw.get("tokens"),
        "cost_usd": raw.get("cost_usd"),
    }


def _load_metrics(path: Path) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    skipped = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                skipped += 1
                continue
            try:
                raw = json.loads(stripped)
            except json.JSONDecodeError:
                skipped += 1
                continue
            record = _parse_record(raw)
            if record is None:
                skipped += 1
                continue
            records.append(record)
    return records, skipped


def _sum_optional_numeric(
    records: list[dict[str, Any]], field: str
) -> float | int | None:
    total = 0.0
    seen = False
    for record in records:
        value = record.get(field)
        if value is None:
            continue
        try:
            total += float(value)
            seen = True
        except (TypeError, ValueError):
            continue
    if not seen:
        return None
    if field == "tokens" and total.is_integer():
        return int(total)
    return total


def _acceptance_rate_pct(total_iterations: int, accepted_count: int) -> float | None:
    if total_iterations == 0:
        return None
    return (accepted_count / total_iterations) * 100.0


def _cost_per_accepted(total_cost_usd: float | None, accepted_count: int) -> float | None:
    if total_cost_usd is None or accepted_count == 0:
        return None
    return total_cost_usd / accepted_count


def _format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}%"


def _format_tokens(value: float | int | None) -> str:
    if value is None:
        return NA_COST_MSG
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value:,}"


def _format_cost(value: float | None) -> str:
    if value is None:
        return NA_COST_MSG
    return f"${value:,.6f}".rstrip("0").rstrip(".")


def _format_cost_metric(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.6f}".rstrip("0").rstrip(".")


def summarize(records: list[dict[str, Any]], skipped_lines: int) -> dict[str, Any]:
    total_iterations = len(records)
    accepted_count = sum(1 for record in records if record["accepted"])
    total_wall_ms = sum(record["wall_ms"] for record in records)
    total_tokens = _sum_optional_numeric(records, "tokens")
    total_cost_usd = _sum_optional_numeric(records, "cost_usd")
    acceptance_rate_pct = _acceptance_rate_pct(total_iterations, accepted_count)
    cost_per_accepted_change = _cost_per_accepted(total_cost_usd, accepted_count)

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total_iterations": total_iterations,
        "accepted_count": accepted_count,
        "acceptance_rate_pct": acceptance_rate_pct,
        "total_wall_clock": _format_wall_ms(total_wall_ms),
        "total_wall_ms": total_wall_ms,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost_usd,
        "cost_per_accepted_change": cost_per_accepted_change,
        "skipped_lines": skipped_lines,
    }


def _print_human(summary: dict[str, Any], path: Path) -> None:
    rows = [
        ("total iterations", str(summary["total_iterations"])),
        ("accepted count", str(summary["accepted_count"])),
        ("acceptance rate", _format_pct(summary["acceptance_rate_pct"])),
        ("total wall-clock", summary["total_wall_clock"]),
        ("total tokens", _format_tokens(summary["total_tokens"])),
        ("total cost_usd", _format_cost(summary["total_cost_usd"])),
        ("cost_per_accepted_change", _format_cost_metric(summary["cost_per_accepted_change"])),
        ("skipped lines", str(summary["skipped_lines"])),
    ]
    label_width = max(len(label) for label, _ in rows)
    print(f"loopprint-report: {path}")
    print()
    for label, value in rows:
        print(f"  {label:<{label_width}}  {value}")


def _print_json(summary: dict[str, Any], path: Path) -> None:
    payload = {
        "source": str(path),
        "generated_at": summary["generated_at"],
        "total_iterations": summary["total_iterations"],
        "accepted_count": summary["accepted_count"],
        "acceptance_rate_pct": summary["acceptance_rate_pct"],
        "total_wall_clock": summary["total_wall_clock"],
        "total_wall_ms": summary["total_wall_ms"],
        "total_tokens": summary["total_tokens"]
        if summary["total_tokens"] is not None
        else NA_COST_MSG,
        "total_cost_usd": summary["total_cost_usd"]
        if summary["total_cost_usd"] is not None
        else NA_COST_MSG,
        "cost_per_accepted_change": summary["cost_per_accepted_change"]
        if summary["cost_per_accepted_change"] is not None
        else "n/a",
        "skipped_lines": summary["skipped_lines"],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="loopprint-report.py",
        description="Roll up loop runner metrics.jsonl into cost-per-accepted-change.",
    )
    parser.add_argument(
        "metrics_path",
        nargs="?",
        help="Path to metrics.jsonl (one JSON object per line).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON summary.",
    )
    args = parser.parse_args(argv)

    if not args.metrics_path:
        parser.print_usage(sys.stderr)
        return 2

    path = Path(args.metrics_path)
    records, skipped = _load_metrics(path) if path.is_file() else ([], 0)
    summary = summarize(records, skipped)

    if args.json:
        _print_json(summary, path)
    else:
        _print_human(summary, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
