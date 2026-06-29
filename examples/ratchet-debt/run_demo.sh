#!/usr/bin/env bash
# run_demo.sh — non-mutating demo for the ratchet-debt loop.
# Copies committed fixtures into a fresh tmpdir and runs run-this-loop.sh there.
# The committed findings.txt and baseline are NEVER modified.
#
# Runs under plain bash + coreutils — OMC, plugins, and AI tools are all optional.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RUNNER="${REPO_ROOT}/templates/run-this-loop.sh"

D=$(mktemp -d)
trap 'rm -rf "$D"' EXIT INT TERM

# Copy committed fixtures to tmpdir — never touch the originals.
cp "${SCRIPT_DIR}/findings.txt" \
   "${SCRIPT_DIR}/baseline" \
   "${SCRIPT_DIR}/verify.sh" \
   "${SCRIPT_DIR}/maker.sh" \
   "${SCRIPT_DIR}/ratchet-advance.sh" \
   "$D/"

chmod +x "$D/verify.sh" "$D/maker.sh" "$D/ratchet-advance.sh"

printf 'before: baseline=%s\n' "$(cat "$D/baseline")"

cd "$D" || exit 1

VERIFIER_SHAPE=ratchet \
RATCHET_ADVANCE=ratchet-advance.sh \
BUDGET_MIN=1 \
MAX_ITERS=20 \
AUTONOMY=full \
bash "$RUNNER" || true

printf 'after:  baseline=%s\n' "$(cat baseline)"
