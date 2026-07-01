#!/usr/bin/env bash
# check_calibration.sh — a bounded smoke test: does JUDGE agree with a small, human-labeled
# golden set often enough to be trusted in a real loop? Catches a broken/lazy judge (e.g. one
# that always scores 90 regardless of input, or ignores the rubric) BEFORE it's wired into a
# real verify.sh — it does NOT prove fine-grained scoring accuracy; 3-5 examples is a directional
# smoke test, not a statistically rigorous calibration. See templates/verifier-library.yaml's
# judge-calibration-check recipe for the copy-paste version.
set -euo pipefail

JUDGE="${JUDGE:-$(dirname "$0")/judge_under_test.sh}"
GOLDEN_DIR="$(dirname "$0")/golden"
MANIFEST="$GOLDEN_DIR/expected.txt"
THRESHOLD="${THRESHOLD:-80}"
MIN_AGREEMENT="${MIN_AGREEMENT:-1.0}"  # 1.0 = every golden example must agree, for a set this small

total=0
correct=0
mismatches=()

while read -r filename expected; do
  [ -z "$filename" ] && continue
  case "$filename" in \#*) continue ;; esac
  artifact="$GOLDEN_DIR/$filename"
  [ -f "$artifact" ] || { echo "check_calibration: golden artifact missing: $artifact" >&2; exit 1; }

  raw=$(bash "$JUDGE" "$artifact") || raw='{"score": 0, "reason": "judge script exited non-zero"}'
  actual=$(RAW="$raw" THRESHOLD="$THRESHOLD" python3 -c '
import json, os
try:
    v = json.loads(os.environ["RAW"]); score = int(v.get("score", 0))
except (json.JSONDecodeError, ValueError, TypeError, KeyError):
    score = 0
print("pass" if score >= int(os.environ["THRESHOLD"]) else "fail")
')

  total=$((total + 1))
  if [ "$actual" = "$expected" ]; then
    correct=$((correct + 1))
  else
    mismatches+=("$filename: expected=$expected actual=$actual")
  fi
done < "$MANIFEST"

if [ "$total" -eq 0 ]; then
  echo "check_calibration: empty golden set ($MANIFEST) — nothing to check" >&2
  exit 1
fi

agreement=$(python3 -c "print($correct / $total)")
ok=$(python3 -c "print(1 if $agreement >= $MIN_AGREEMENT else 0)")

echo "check_calibration: $correct/$total agree with the golden set (agreement=$agreement, need >= $MIN_AGREEMENT)"
if [ "$ok" != "1" ]; then
  echo "check_calibration: FAIL — judge disagreed with the golden set:" >&2
  printf '  %s\n' "${mismatches[@]}" >&2
  exit 1
fi
echo "check_calibration: GREEN"
exit 0
