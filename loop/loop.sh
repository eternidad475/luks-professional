#!/usr/bin/env bash
# The heartbeat. Exit map: 0 quiet/done, 1 iteration cap, 2 reroute, 3 budget.
set -euo pipefail
cd "$(dirname "$0")"
MAX_ITERS="${MAX_ITERS:-10}"
DAILY_BUDGET_USD="${DAILY_BUDGET_USD:-5}"
CHEAP="${CHEAP:-openrouter/deepseek/deepseek-v4-flash}"
WORKER="${WORKER:-openrouter/moonshotai/kimi-k2.6}"

./scripts/cost-check.sh --budget "$DAILY_BUDGET_USD" || exit 3

for ((i=1; i<=MAX_ITERS; i++)); do
  # 1 TRIAGE: quiet-tick gate, ~$0.01
  { git log --oneline -20; gh issue list --limit 20 2>/dev/null || true; \
    gh run list --limit 10 2>/dev/null || true; } \
    | llm -m "$CHEAP" -s "$(cat triage.md)" >> memory/STATE.md
  ./scripts/log-cost.sh triage 0.01
  grep -q "status: actionable" memory/STATE.md || { echo quiet; exit 0; }

  # 2 CONDUCT: Fable, xhigh, fresh context, read-only, JSON out
  claude -p "$(cat conductor.md)
STATE: $(cat memory/STATE.md)
TRUST: $(./scripts/trust-log.sh --render)
CONTRACT: $(cat contract.md)" \
    --model claude-fable-5 --effort xhigh --allowedTools "Read" \
    --output-format json > /tmp/c.json
  ./scripts/log-cost.sh conductor 0.35

  # 2a ROUTE-TOLERANCE: never iterate on a model you didn't choose
  SERVED=$(jq -r '.modelUsage | keys[0] // "claude-fable-5"' /tmp/c.json)
  [[ "$SERVED" != *fable* ]] && { echo "rerouted" >> memory/STATE.md; exit 2; }
  # Refusals are HTTP 200: check the stop reason, not the exit code
  STOPR=$(jq -r '.stop_reason // empty' /tmp/c.json)
  [[ "$STOPR" == "refusal" ]] && { echo "refusal: conductor" >> memory/STATE.md; exit 2; }

  jq -r '.result' /tmp/c.json > work-order.json
  SKILL=$(jq -r .skill work-order.json); ACTION=$(jq -r .action work-order.json)
  [[ "$ACTION" == stop  ]] && exit 0
  [[ "$ACTION" == queue ]] && { echo "queued: $SKILL" >> memory/STATE.md; continue; }

  # 3 EXECUTE: cheap worker, isolated worktree
  WT="../wt-$i"; git worktree add "$WT" -b "loop/$SKILL-$i" >/dev/null
  ( cd "$WT" && llm -m "$WORKER" -s "$(cat "$OLDPWD/workers/implement.md")" \
      "$(cat "$OLDPWD/work-order.json")" > IMPLEMENTATION.md )
  ./scripts/log-cost.sh worker 0.10

  # 4 VERIFY: fresh Fable, no tools, sees only spec + diff
  V=$(claude -p "$(cat workers/verify.md)
SPEC: $(jq -r .spec work-order.json)
DIFF: $(cd "$WT" && git diff)" \
    --model claude-fable-5 --effort high --allowedTools "" \
    --output-format json | jq -r .result)
  ./scripts/log-cost.sh verifier 0.40

  # 5 GATE: deterministic; then ledger; ship only at auto tier
  if [[ "$V" == PASS* ]] && ( cd "$WT" && "$OLDPWD/guardrails/verify.sh" ); then
    ./scripts/trust-log.sh "$SKILL" pass
    if [[ "$(./scripts/trust-log.sh --tier "$SKILL")" == auto ]]; then
      ( cd "$WT" && git add -A && git commit -qm "loop: $SKILL" && gh pr create --fill || true )
      echo "- shipped: $SKILL" >> memory/STATE.md
    else
      echo "- review: $SKILL in $WT" >> memory/STATE.md
    fi
  else
    ./scripts/trust-log.sh "$SKILL" fail
    echo "- FAILED: $SKILL in $WT" >> memory/STATE.md
  fi
  ./scripts/cost-check.sh --budget "$DAILY_BUDGET_USD" || exit 3
done
exit 1   # iteration cap without stop: check STATE.md
