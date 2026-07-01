#!/usr/bin/env bash
# verify.sh — critic-panel fan-out gate for the critic-panel example.
# Derived from the critic-panel recipe in templates/verifier-library.yaml.
# EXIT 0 (GREEN) iff >= QUORUM_K critics score ARTIFACT >= THRESHOLD.
# Emits critics.jsonl (one JSON line per critic, {score, reason} + provenance) in the working
# directory. Each critic-N.sh prints a JSON verdict {"score": N, "reason": "..."} on stdout —
# parsed via python3 -c (never eval'd as shell) and re-serialized through json.dumps so a
# reason containing quotes/newlines can't corrupt the jsonl line. READ-ONLY: rubric.md and
# artifact.md are never modified.
set -euo pipefail

RUBRIC="rubric.md"
ARTIFACT="artifact.md"
N=3
QUORUM_K=2
THRESHOLD=80

sha() {
  local f="$1"
  (sha256sum "$f" 2>/dev/null || shasum -a 256 "$f") | awk '{print $1}'
}

rsha=$(sha "$RUBRIC")
asha=$(sha "$ARTIFACT")
pass=0

for i in $(seq 1 "$N"); do
  script="./critic-${i}.sh"
  raw=$(bash "$script" --rubric "$RUBRIC" --artifact "$ARTIFACT") || raw='{"score": 0, "reason": "critic script exited non-zero"}'
  provider=$(grep -m1 -oE 'PROVIDER=[A-Za-z0-9_-]+' "$script" | cut -d= -f2 || true)
  ok=$(RAW="$raw" TS="$(date -u +%FT%TZ)" CRITIC="critic-$i" PROVIDER="${provider:-unknown}" \
       THRESHOLD="$THRESHOLD" RSHA="$rsha" ASHA="$asha" NN="$N" QK="$QUORUM_K" python3 -c '
import json, os

try:
    verdict = json.loads(os.environ["RAW"])
    score = int(verdict.get("score", 0))
    reason = str(verdict.get("reason", ""))
except (json.JSONDecodeError, ValueError, TypeError, KeyError):
    score, reason = 0, "critic verdict was not valid JSON {score, reason}"

threshold = int(os.environ["THRESHOLD"])
ok = score >= threshold
line = {
    "ts": os.environ["TS"], "critic": os.environ["CRITIC"], "provider": os.environ["PROVIDER"],
    "score": score, "reason": reason, "threshold": threshold, "pass": ok,
    "rubric_sha": os.environ["RSHA"], "artifact_sha": os.environ["ASHA"],
    "n": int(os.environ["NN"]), "quorum_k": int(os.environ["QK"]),
}
with open("critics.jsonl", "a") as f:
    f.write(json.dumps(line) + "\n")
print("1" if ok else "0")
')
  [ "$ok" = "1" ] && pass=$((pass + 1))
done

if [ "$pass" -ge "$QUORUM_K" ]; then
  echo "critic-panel: quorum PASS ($pass/$N, need $QUORUM_K)"
  exit 0
else
  echo "critic-panel: quorum FAIL ($pass/$N, need $QUORUM_K)" >&2
  exit 1
fi
