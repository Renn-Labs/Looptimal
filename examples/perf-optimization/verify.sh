#!/usr/bin/env bash
# verify.sh — external gate for the perf-optimization loop.
# GREEN (exit 0) only when p95 is at target AND the correctness suite passes.
set -euo pipefail

TARGET_P95_MS=200
PROFILE="${LOAD_PROFILE:-standard}"

# Gate 1: measure p95 under the standard load profile.
P95_MS="$(python scripts/bench_search.py --profile "$PROFILE" --metric p95 --format value)"
if ! [[ "$P95_MS" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
  echo "verify: bench_search.py returned non-numeric p95: $P95_MS" >&2
  exit 1
fi
if awk -v p95="$P95_MS" -v target="$TARGET_P95_MS" 'BEGIN { exit !(p95 <= target) }'; then
  :
else
  echo "verify: p95 ${P95_MS}ms exceeds target ${TARGET_P95_MS}ms" >&2
  exit 1
fi

# Gate 2: correctness — no functional regression.
pytest tests/integration -q

echo "verify: p95 ${P95_MS}ms <= ${TARGET_P95_MS}ms and correctness GREEN"
