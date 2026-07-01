#!/usr/bin/env bash
# critic-3.sh — deterministic stub critic (cross-provider: gemini).
# Real use: swap the echo for a live dispatch, e.g.:
#   gemini 'Score artifact.md against rubric.md 0-100. Output JSON only: {"score": N, "reason": "..."}'
# PROVIDER=gemini
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

[ -f "$RUBRIC" ]   || { echo "critic-3: rubric not found: $RUBRIC" >&2; exit 1; }
[ -f "$ARTIFACT" ] || { echo "critic-3: artifact not found: $ARTIFACT" >&2; exit 1; }

# Deterministic stub verdict — replace with live LLM dispatch for real judging.
echo '{"score": 70, "reason": "Below threshold: Completeness dimension is missing the rollback-plan subsection."}'
