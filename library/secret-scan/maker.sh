#!/usr/bin/env bash
# maker.sh — remediation guide for secret-scan findings (maker ≠ checker).
# READ-ONLY: prints guidance only; never edits files.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

main() {
  local output status
  set +e
  output=$(bash "$SCRIPT_DIR/verify.sh" 2>&1)
  status=$?
  set -e

  if [[ "$status" -eq 0 ]]; then
    echo "maker: no secret-scan findings — verifier is GREEN; nothing to remediate."
    exit 0
  fi

  echo "maker: secret-scan verifier is RED. For each finding below:"
  echo "  1. Remove the secret from the file (and from git history if it was committed)."
  echo "  2. Rotate/revoke the credential at the provider — removal alone is not enough."
  echo "  3. Re-run: bash verify.sh"
  echo ""
  echo "Findings (file:line):"
  echo "$output" | grep -E '^[^:]+:[0-9]+:' || true
  exit 0
}

main "$@"