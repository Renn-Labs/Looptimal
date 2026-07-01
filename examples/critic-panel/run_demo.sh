#!/usr/bin/env bash
# run_demo.sh — run the critic-panel example in a tmpdir; never mutates tracked files.
# Demonstrates quorum PASS (normal) and quorum FAIL (fail-flip with critic-2 → 50).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── DEMO 1: quorum PASS (critic scores: 90/85/70 → 2 of 3 >= 80) ─────────────
echo "=== DEMO 1: quorum PASS (scores 90/85/70, quorum 2-of-3 >= 80) ==="
D=$(mktemp -d)
cp "$SCRIPT_DIR/loop-spec.yaml" \
   "$SCRIPT_DIR/rubric.md" \
   "$SCRIPT_DIR/artifact.md" \
   "$SCRIPT_DIR/maker.sh" \
   "$SCRIPT_DIR/critic-1.sh" \
   "$SCRIPT_DIR/critic-2.sh" \
   "$SCRIPT_DIR/critic-3.sh" \
   "$SCRIPT_DIR/verify.sh" \
   "$D"/

if (cd "$D" && bash verify.sh); then
  echo "exit=0"
else
  echo "exit=$?  (UNEXPECTED)"
fi

echo "--- critics.jsonl (first line) ---"
head -1 "$D/critics.jsonl"

# ── DEMO 2: fail-flip (critic-2 → 50 → only 1 of 3 pass → quorum FAIL) ───────
echo ""
echo "=== DEMO 2: fail-flip (critic-2 score 50 → only 1/3 pass, gate bites) ==="
D2=$(mktemp -d)
cp "$SCRIPT_DIR/loop-spec.yaml" \
   "$SCRIPT_DIR/rubric.md" \
   "$SCRIPT_DIR/artifact.md" \
   "$SCRIPT_DIR/maker.sh" \
   "$SCRIPT_DIR/critic-1.sh" \
   "$SCRIPT_DIR/critic-2.sh" \
   "$SCRIPT_DIR/critic-3.sh" \
   "$SCRIPT_DIR/verify.sh" \
   "$D2"/

sed -i 's/"score": 85/"score": 50/' "$D2/critic-2.sh"

if (cd "$D2" && bash verify.sh); then
  echo "exit=0  (UNEXPECTED — panel should have failed)"
else
  echo "exit=1  (EXPECTED — quorum FAIL, gate bites)"
fi
