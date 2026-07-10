---
name: bump-deps
description: Patch/minor version bumps for existing dependencies
when: a security advisory or stale lockfile is flagged as actionable
---
## steps
1. Bump ONE dependency, patch or minor only, in package.json or requirements.txt.
2. Run loop/guardrails/verify.sh.
3. Note the changelog link in IMPLEMENTATION.md.

## never
- Never add a NEW dependency (CLAUDE.md law: propose in STATE.md and stop).
- Never bump a major version unattended.
- Never bump stripe or @supabase/supabase-js unattended (billing/auth surface).

## done_when
- Exactly one dependency line changed.
- loop/guardrails/verify.sh exits 0.
