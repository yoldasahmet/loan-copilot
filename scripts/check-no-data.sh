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
# API keys (Anthropic, OpenAI, OpenRouter) anywhere in tracked files, e.g. pasted into .env.example
keys=$(git grep -l -I -E 'sk-(ant|proj|or-v1)-[A-Za-z0-9_-]{20,}' -- . || true)
if [[ -n "$keys" ]]; then
  echo "check-no-data: these tracked files contain an API key:" >&2
  echo "$keys" >&2
  exit 1
fi
echo "check-no-data: ok"
