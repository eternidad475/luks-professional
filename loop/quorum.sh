#!/usr/bin/env bash
# OPTIONAL (BUILD 7). Install condition: memory/dispatch.tsv shows Fable
# wake-ups that produced action: stop. Three cheap models vote; the
# conductor wakes only on 2 of 3. Voters never see each other's answers.
set -euo pipefail
cd "$(dirname "$0")"
SIGNALS="${1:-/tmp/signals.txt}"
V=0
for m in deepseek/deepseek-v4-flash qwen/qwen-3.6 moonshotai/kimi-k2.6; do
  llm -m "openrouter/$m" -s "$(cat triage.md)" < "$SIGNALS" \
    | grep -q "status: actionable" && V=$((V+1))
done
[ "$V" -ge 2 ] && exec ./loop.sh || echo "quorum: quiet ($V/3)"
