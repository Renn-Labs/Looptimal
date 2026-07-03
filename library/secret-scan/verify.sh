#!/usr/bin/env bash
# verify.sh — external gate for the secret-scan loop.
# GREEN (exit 0) = no committed secrets in tracked/regular files.
# RED (exit 1) = at least one secret pattern detected (file:line printed).
# READ-ONLY: git + coreutils only; no network; never modifies files.
set -euo pipefail

FINDINGS=0
LOOP_VERIFY_REL=""
LOOP_MAKER_REL=""

init_loop_skip_paths() {
  local script="${BASH_SOURCE[0]}"
  local root
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    root=$(git rev-parse --show-toplevel)
  else
    root=$(pwd -P)
  fi
  local script_dir abs_root
  script_dir=$(cd "$(dirname "$script")" && pwd -P)
  abs_root=$(cd "$root" && pwd -P)
  local rel_dir="${script_dir#$abs_root/}"
  LOOP_VERIFY_REL="${rel_dir}/$(basename "$script")"
  LOOP_MAKER_REL="${rel_dir}/maker.sh"
}

should_skip() {
  local relpath="$1"
  if [[ -n "$LOOP_VERIFY_REL" && "$relpath" == "$LOOP_VERIFY_REL" ]]; then
    return 0
  fi
  if [[ -n "$LOOP_MAKER_REL" && "$relpath" == "$LOOP_MAKER_REL" ]]; then
    return 0
  fi
  case "$relpath" in
    package-lock.json|yarn.lock|pnpm-lock.yaml|Cargo.lock|go.sum)
      return 0
      ;;
    *.cast|*.png|*.jpg|*.jpeg|*.gif|*.webp|*.ico|*.woff|*.woff2|*.ttf|*.eot|*.pdf|*.zip|*.gz|*.tar|*.br)
      return 0
      ;;
  esac
  return 1
}

is_false_positive() {
  local value="$1"

  # Hex digests, hashes, and placeholder demo material (matched value only).
  if printf '%s' "$value" | grep -qE '(sha256|stdout_sha|artifact_sha|rubric_sha|receipt_sha|contract_hash|sealed_inputs_hash|"sha256")'; then
    return 0
  fi
  if printf '%s' "$value" | grep -qE '^[0-9a-fA-F]{40,}$'; then
    return 0
  fi
  if printf '%s' "$value" | grep -qE '^0+$'; then
    return 0
  fi

  # URLs and VCS refs — not secrets.
  if printf '%s' "$value" | grep -qE '(https?://|git\+https|github\.com)'; then
    return 0
  fi

  # SSH public keys (not private-key PEM blocks).
  if printf '%s' "$value" | grep -qE 'ssh-(ed25519|rsa)[[:space:]]'; then
    return 0
  fi

  return 1
}

emit_hit() {
  local line="$1"
  local high_confidence="$2"
  local pattern="$3"

  if [[ "$high_confidence" == "1" ]]; then
    printf '%s\n' "$line"
    FINDINGS=1
    return
  fi

  local content="${line#*:*:}"
  local matched
  matched=$(printf '%s' "$content" | grep -oE "$pattern" 2>/dev/null | head -1 || true)
  [[ -z "$matched" ]] && matched="$content"
  is_false_positive "$matched" && return 0
  printf '%s\n' "$line"
  FINDINGS=1
}

record_hits() {
  local pattern="$1"
  local file="$2"
  local high_confidence="${3:-0}"
  local hits
  hits=$(grep -nIH -E "$pattern" "$file" 2>/dev/null || true)
  if [[ -n "$hits" ]]; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      emit_hit "$line" "$high_confidence" "$pattern"
    done <<< "$hits"
  fi
}

scan_file() {
  local file="$1"
  [[ -f "$file" && -r "$file" ]] || return 0
  should_skip "$file" && return 0

  # AWS access key IDs (AKIA + 16 uppercase alphanumeric).
  record_hits 'AKIA[0-9A-Z]{16}' "$file" 1

  # PEM / private key headers.
  record_hits '-----BEGIN[[:space:]]+.*PRIVATE[[:space:]]+KEY-----' "$file" 1

  # Common credential assignment patterns (api_key, secret, password, token + long value).
  record_hits '(api[_-]?key|client[_-]?secret|secret[_-]?key|password|passwd|auth[_-]?token|access[_-]?token|token)[[:space:]]*[=:][[:space:]]*['\''"]?[A-Za-z0-9_./+=-]{16,}['\''"]?' "$file" 0
}

collect_files() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git ls-files -z
  else
    find . -type f ! -path './.git/*' -print0 2>/dev/null || true
  fi
}

main() {
  init_loop_skip_paths

  local -a files=()
  while IFS= read -r -d '' path; do
    [[ -n "$path" ]] && files+=("$path")
  done < <(collect_files)

  if [[ ${#files[@]} -eq 0 ]]; then
    echo "verify: secret-scan GREEN (no files to scan)" >&2
    exit 0
  fi

  for file in "${files[@]}"; do
    scan_file "$file"
  done

  if [[ "$FINDINGS" -ne 0 ]]; then
    echo "verify: secret-scan RED — committed secrets detected (remove and rotate)" >&2
    exit 1
  fi

  echo "verify: secret-scan GREEN"
  exit 0
}

main "$@"