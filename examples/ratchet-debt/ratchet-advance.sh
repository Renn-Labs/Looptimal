#!/usr/bin/env bash
# ratchet-advance.sh — tighten the baseline after an accepted GREEN iteration.
# Called by the runner post-accept ONLY; the runner is the only caller.
# Deterministic, no external tool required.
# Only writes baseline when the current count is strictly better; idempotent otherwise.
set -euo pipefail

c=$(grep -c . findings.txt || true)   # grep exits 1 on an empty file; keep 0 under set -e
b=$(cat baseline)
if [ "$c" -lt "$b" ]; then
    printf '%s\n' "$c" > baseline
fi
