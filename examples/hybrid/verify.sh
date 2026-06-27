#!/usr/bin/env bash
# verify.sh — external gate for the hybrid loop.
# GREEN (exit 0) only when repro, spec, and benchmark gates all pass.
set -euo pipefail

TARGET_P95_MS=5000
FIXTURE="${EXPORT_FIXTURE:-fixtures/export_10k_rows.json}"

# Gate 1: reproduction — the reported timeout must be fixed.
pytest tests/repro/test_export_timeout.py -q

# Gate 2: spec — behavior must match the written export contract.
pytest tests/spec/test_export_spec.py -q

# Gate 3: benchmark — p95 must stay within budget after the fix.
P95_MS="$(python scripts/bench_export.py --fixture "$FIXTURE" --metric p95 --format value)"
if ! [[ "$P95_MS" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
  echo "verify: bench_export.py returned non-numeric p95: $P95_MS" >&2
  exit 1
fi
if awk -v p95="$P95_MS" -v target="$TARGET_P95_MS" 'BEGIN { exit !(p95 <= target) }'; then
  :
else
  echo "verify: p95 ${P95_MS}ms exceeds target ${TARGET_P95_MS}ms" >&2
  exit 1
fi

echo "verify: repro GREEN, spec GREEN, p95 ${P95_MS}ms <= ${TARGET_P95_MS}ms"
