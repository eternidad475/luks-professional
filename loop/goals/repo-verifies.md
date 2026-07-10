predicate: cd "$(git rev-parse --show-toplevel)" && ./loop/guardrails/verify.sh
born: 2026-07-10
source: BUILD 2 (every tracked .py compiles, every .js parses, every JSON valid, service workers cache only the static shell)
status: satisfied
last-pass: 2026-07-10
on-violation: wake me. Do not auto-fix.
retire-when: never (this is the gate itself). Retirement is a human decision, logged.
