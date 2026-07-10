---
name: fix-lint-debt
description: Fix syntax/parse debt surfaced by guardrails/verify.sh
when: verify.sh reports a compile/parse/JSON failure on the default branch
---
## steps
1. Run loop/guardrails/verify.sh; take the FIRST failing file only.
2. Fix that one file. Behavior identical; formatting-only where possible.
3. Re-run verify.sh until that file passes.

## never
- Never touch a second file in the same run.
- Never change behavior to silence a checker.
- Never edit verify.sh itself.

## done_when
- loop/guardrails/verify.sh exits 0.
- git diff touches exactly one file.
