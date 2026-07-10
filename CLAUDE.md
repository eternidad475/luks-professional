# CLAUDE.md

## NEVER (laws; exceptions require asking first)
- Never exceed 200 changed lines in one commit without asking.
- Never touch api/stripe/, supabase/migrations/, sw.js, app/service-worker.js,
  app-v3/service-worker.js, or vercel.json unattended. (Billing, schema, and
  the privacy-critical service workers that must never cache case images.)
- Never report work as done from your own assessment. Done = the check passed.
- Never invent a secret, an endpoint, or a convention. Stop and ask.
- Never add a dependency to package.json or requirements.txt. Propose it in
  loop/memory/STATE.md and stop.
- Never exceed effort high inside any loop, except the conductor seat, which
  runs xhigh. xhigh is otherwise for one-shot reviews only.
- Never edit or delete a test to make it pass. That is a fail, always.
- Never echo, transcribe, or explain your internal reasoning in response
  text. (Official: triggers reasoning_extraction refusals on Fable 5.)
- When a /goal condition passes, write loop/goals/<name>.md with the condition
  as its predicate before reporting success.

## DISPATCH (route every task; first match wins; log to loop/memory/dispatch.tsv)
| model           | marginal    | appetite | intelligence | taste |
|-----------------|-------------|----------|--------------|-------|
| claude-fable-5  | 2 (credits) | 3        | 10           | 10    |
| claude-opus-4-8 | 7 (sub)     | 6        | 8            | 9     |
| claude-sonnet-5 | 9 (sub)     | 8        | 7            | 7     |
| codex (2nd sub) | 9           | 10       | 9            | 5     |
1. Decision (plan/review/route/standoff) -> fable-5, effort high, read-only.
2. Reads >50k tokens (logs/PDFs/screenshots) -> codex. Never fable.
3. Ships to users (UI/API/copy) -> taste >= 8 gets final pass.
4. Spec complete -> sonnet-5, effort medium.
5. Else sonnet-5; escalate one rung on a miss without asking.

## WORDS
- "intelligence" = hardest problem handled unsupervised
- "taste" = UI/UX, code quality, API design, copy
- "done" = the predicate passes; nothing else
- "small" = under 50 changed lines; "quick" = under 10 minutes of your time
- "cleanup" = behavior identical, loop/guardrails/verify.sh green before and after

## DONE
- Every task has a machine-checkable done_when before work starts.
- A fresh-context agent that saw neither plan nor draft verifies against it.
- loop/guardrails/verify.sh has the final vote.
- Deviations: conservative option, log to IMPLEMENTATION.md, continue.
- Maker and checker disagree twice -> stop, queue for a human.
