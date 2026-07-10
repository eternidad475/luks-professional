#!/usr/bin/env bash
# Deterministic gate. Final vote on every change. No LLM anywhere in here.
# Stack: static HTML + Vercel serverless JS + Python morph-video library.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# Python: every tracked .py must compile
git ls-files '*.py' | while read -r f; do
  python3 -m py_compile "$f"
done

# Node: every tracked .js must parse
git ls-files '*.js' | while read -r f; do
  node --check "$f" >/dev/null
done

# JSON: manifests and config must be valid
git ls-files '*.json' '*.webmanifest' | while read -r f; do
  jq -e . "$f" >/dev/null
done

# Privacy invariant: service workers must never gain case-image caching.
# They may cache only the static shell; any fetch-handler caching of
# blob:/data: or /api/ responses is a hard fail.
for swf in sw.js app/service-worker.js app-v3/service-worker.js; do
  [ -f "$swf" ] || continue
  if grep -nE 'cache\.(put|add|addAll)\([^)]*(blob:|data:|/api/)' "$swf"; then
    echo "FAIL: $swf caches dynamic/case data" >&2
    exit 1
  fi
done

echo "verify.sh: green"
