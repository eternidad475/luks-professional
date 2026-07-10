---
name: triage-issues
description: Label and summarize new GitHub issues; no code changes
when: open issues exist without labels
---
## steps
1. Read the issue. Reproduce claims only by reading code, not running it.
2. Apply labels (bug/feature/question, area: app/api/morph/billing).
3. One-paragraph summary comment ONLY if the report is unclear.

## never
- Never close an issue.
- Never touch code in this skill.
- Never comment on billing/auth issues; queue them (contract-sensitive).

## done_when
- Every open issue has at least one label.
- Zero files changed in the repo.
