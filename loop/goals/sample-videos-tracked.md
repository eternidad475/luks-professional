predicate: test -n "$(cd "$(git rev-parse --show-toplevel)" && git ls-files 'media/*.mp4')"
born: 2026-07-10
source: .gitignore law "sample morph videos served by the app must be tracked"
status: satisfied
last-pass: 2026-07-10
on-violation: wake me. Do not auto-fix.
retire-when: the app stops serving sample videos from media/. Retirement is a human decision, logged.
