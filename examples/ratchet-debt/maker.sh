#!/usr/bin/env bash
# maker.sh — deterministic demo: resolve ONE finding by deleting the first line.
#
# real use: swap this for any dispatch — your own tool, a fix script, a model call:
#   your-tool --fix-next-finding
#   (no tool is required; this demo is purely deterministic)
#
# The runner calls maker.sh as a SEPARATE PROCESS (maker != checker is enforced structurally).
# This script MUST NOT write baseline; only ratchet-advance.sh may tighten it.
set -euo pipefail

# Portable in-place delete of line 1: -i.bak works on both GNU and BSD sed.
sed -i.bak '1d' findings.txt
rm -f findings.txt.bak
