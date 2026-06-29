#!/usr/bin/env bash
# verify.sh — external gate (READ-ONLY): GREEN if count <= baseline.
# Does NOT write baseline; that role belongs exclusively to ratchet-advance.sh.
set -euo pipefail

# grep -c exits 1 when the file is empty (0 matches); keep count=0, don't abort under set -e.
count=$(grep -c . findings.txt || true)
base=$(cat baseline)
if [ "$count" -le "$base" ]; then
    printf 'verify: %s findings, baseline %s — GREEN\n' "$count" "$base"
    exit 0
else
    printf 'verify: %s findings, baseline %s — RED (count exceeds baseline)\n' "$count" "$base"
    exit 1
fi
