#!/usr/bin/env bash
# judge_under_test.sh — a deterministic, mildly content-aware stub judge (NOT a real LLM
# dispatch) used only to demonstrate the calibration mechanism. Scores an artifact by how many
# of three required section headers it contains — enough to distinguish the golden/pass-*.md
# fixtures from golden/fail-1.md without needing a live model call in this repo's tests.
#
# Real use: point this at your ACTUAL critic script (e.g. examples/critic-panel/critic-1.sh) —
# calibration doesn't care what's inside the judge, only whether its verdicts agree with a
# known-correct golden set.
set -euo pipefail

ARTIFACT="${1:?usage: judge_under_test.sh <artifact-path>}"
[ -f "$ARTIFACT" ] || { echo "judge_under_test: artifact not found: $ARTIFACT" >&2; exit 1; }

required=("## Summary" "## Risks" "## Rollback")
hits=0
for section in "${required[@]}"; do
  grep -qF "$section" "$ARTIFACT" && hits=$((hits + 1))
done

score=$((hits * 100 / ${#required[@]}))
reason="Found ${hits}/${#required[@]} required sections (${required[*]})."
SCORE="$score" REASON="$reason" python3 -c '
import json, os
print(json.dumps({"score": int(os.environ["SCORE"]), "reason": os.environ["REASON"]}))
'
