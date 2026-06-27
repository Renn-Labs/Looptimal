#!/usr/bin/env bash
# verify.sh — external gate for the spec-driven-remediation loop.
# GREEN (exit 0) only when every derived spec case passes.
set -euo pipefail

pytest tests/spec -q

echo "verify: spec suite GREEN"
