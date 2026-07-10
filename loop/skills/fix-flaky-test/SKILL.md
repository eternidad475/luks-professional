---
name: fix-flaky-test
description: Stabilize a check that passes and fails on identical code
when: goal-ledger.tsv shows the same goal alternating pass/FAIL with no merges between
---
## steps
1. Reproduce the flake: run the predicate 5 times, record outcomes.
2. Identify the nondeterminism (timing, network, ordering, tmp files).
3. Fix the CHECK's environment or the code's nondeterminism, never the assertion.

## never
- Never delete, skip, or weaken the check.
- Never add retries as the fix.
- Never mark a goal retired; that is a human decision.

## done_when
- The predicate passes 5 consecutive runs.
- The assertion is unchanged or strictly stronger.
