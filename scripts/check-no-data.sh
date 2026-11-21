#!/usr/bin/env bash
# Fails if any demo data, document or secret is tracked by git.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

bad=$(git ls-files | grep -E '^local/|\.(pdf|xml|csv|jsonl|xlsx)$|(^|/)\.env$' || true)
if [[ -n "$bad" ]]; then
  echo "check-no-data: these files must not be committed:" >&2
  echo "$bad" >&2
  exit 1
fi
echo "check-no-data: ok"
