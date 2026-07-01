#!/usr/bin/env bash
# critic-1.sh — deterministic stub critic (cross-provider: codex).
# Real use: swap the echo for a live dispatch, e.g.:
#   codex exec 'Score artifact.md against rubric.md 0-100. Output JSON only: {"score": N, "reason": "..."}'
# PROVIDER=codex
set -euo pipefail

RUBRIC="rubric.md"
ARTIFACT="artifact.md"
while [ $# -gt 0 ]; do
  case "$1" in
    --rubric)   RUBRIC="$2";   shift 2 ;;
    --artifact) ARTIFACT="$2"; shift 2 ;;
    *)          shift ;;
  esac
done

[ -f "$RUBRIC" ]   || { echo "critic-1: rubric not found: $RUBRIC" >&2; exit 1; }
[ -f "$ARTIFACT" ] || { echo "critic-1: artifact not found: $ARTIFACT" >&2; exit 1; }

# Deterministic stub verdict — replace with live LLM dispatch for real judging.
echo '{"score": 90, "reason": "Clear, complete, accurate, and concise against every rubric dimension."}'
