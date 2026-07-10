tick:            ; ./loop/loop.sh
queue:           ; @grep -E "review:|queued:|FAILED:|rerouted|refusal:" loop/memory/STATE.md || echo empty
trust:           ; @./loop/scripts/trust-log.sh --render
audit:           ; @./loop/scripts/cost-check.sh --report
goals:           ; @./loop/verify-goals.sh
verify:          ; @./loop/guardrails/verify.sh
clean-worktrees: ; @git worktree list | awk '/wt-/{print $$1}' | xargs -rn1 git worktree remove --force
.PHONY: tick queue trust audit goals verify clean-worktrees
