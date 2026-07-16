#!/usr/bin/env bash
# verify.sh — external gate for the first-30-minutes example.
#
# Without FIRST30_RUN_ROOT:
#   Structural readiness of the committed example package (install-level check).
#   Exit 0 = package complete. This is NOT an accepted outcome receipt.
#
# With FIRST30_RUN_ROOT=<run root>:
#   Re-check durable attempt lineage for that run (fail-closed).
#   Exit 0 = consistent ACCEPTED/EXHAUSTED; 1 = inconsistent/RED/non-terminal;
#   3 = BLOCKED terminal or bad pin.
#
# Never writes looptimal-receipt.json. Outcome receipts are solely the job of
# scripts/verify-outcome.py before an ACCEPTED terminal (see run_demo.sh).
#
# Governance: this is the demo package gate, not the independent product
# approval authority. Independent maker≠checker review happens outside.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

required=(
  "${SCRIPT_DIR}/README.md"
  "${SCRIPT_DIR}/loop-spec.yaml"
  "${SCRIPT_DIR}/state.md"
  "${SCRIPT_DIR}/verify.sh"
  "${SCRIPT_DIR}/run_demo.sh"
  "${SCRIPT_DIR}/stale-candidate.json"
)

for path in "${required[@]}"; do
  if [[ ! -f "$path" ]]; then
    printf 'verify: RED — missing required example file: %s\n' "$path" >&2
    exit 1
  fi
done

# Structural vocabulary guard: the committed copy must keep the four-term
# distinction that the teaching contract depends on.
if ! grep -q 'attempt-evidence' "${SCRIPT_DIR}/README.md"; then
  printf 'verify: RED — README must name attempt-evidence\n' >&2
  exit 1
fi
if ! grep -q 'looptimal-receipt' "${SCRIPT_DIR}/README.md"; then
  printf 'verify: RED — README must name the accepted outcome receipt\n' >&2
  exit 1
fi
if ! grep -q 'INSTRUCTIONAL' "${SCRIPT_DIR}/README.md" && ! grep -qi 'instructional' "${SCRIPT_DIR}/README.md"; then
  printf 'verify: RED — README must mark the example as instructional\n' >&2
  exit 1
fi
if ! grep -qi 'controlled' "${SCRIPT_DIR}/README.md"; then
  printf 'verify: RED — README must describe the demo as controlled (not independent field discovery)\n' >&2
  exit 1
fi
if ! grep -qi 'independent' "${SCRIPT_DIR}/README.md"; then
  printf 'verify: RED — README must state that independent review is outside the demo\n' >&2
  exit 1
fi

if [[ -z "${FIRST30_RUN_ROOT:-}" ]]; then
  printf 'verify: layer=smoke GREEN — example package complete (structural / install-level smoke only)\n'
  printf 'verify: note — smoke is not a verifier attempt result and not an accepted outcome receipt\n'
  exit 0
fi

RUN_ROOT="$(cd "${FIRST30_RUN_ROOT}" && pwd)"
export FIRST30_REPO_ROOT="${REPO_ROOT}"
export FIRST30_EXAMPLE_DIR="${SCRIPT_DIR}"

# Delegate lineage re-check to the same engine run_demo.sh embeds, in
# --verify-only mode so maker and checker stay distinct processes inside the
# demo (still not a claim of independent product approval).
exec bash "${SCRIPT_DIR}/run_demo.sh" --verify-only --root "${RUN_ROOT}"
