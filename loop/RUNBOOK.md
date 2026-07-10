# Runbook

## Daily ops
- `make tick`   — run one heartbeat by hand (Week 1: daily, read everything)
- `make queue`  — what's waiting for you (with coffee)
- `make trust`  — the trust ledger, rendered
- `make audit`  — 7-day spend by stage vs. the formula
- `make goals`  — re-verify every standing goal now
- `make clean-worktrees` — remove loop worktrees after review

## Cron (install when Week 2 starts, on the machine that runs the loop)
```
0 7 * * 1-5  cd <repo>/loop && ./loop.sh >> memory/cron.log 2>&1
30 7 * * *   cd <repo>/loop && ./verify-goals.sh >> memory/cron.log 2>&1
```

## Exit map (loop.sh)
0 quiet/done · 1 iteration cap (check STATE.md) · 2 reroute/refusal · 3 budget

## Alarms
| Signal | Meaning | Action |
|---|---|---|
| exit 2 (reroute) | safeguard router swapped models mid-run | read the checkpoint; re-run item tomorrow; never iterate on the swapped output |
| stop_reason: refusal | safety classifier declined (HTTP 200, not an error) | fall back to claude-opus-4-8; if it recurs on one skill, audit that skill for reasoning-echo or cyber/bio-adjacent phrasing |
| exit 3 (budget) | daily spend hit the line | `make audit`; find which stage grew; fix the effort map, not the budget |
| ALERT demoted | an established skill dropped below 90% | read its last 3 fails; usually the spec pattern, not the worker |
| goal VIOLATED | something finished stopped being true | sentinel gives suspects; fix goes through the normal pipeline |
| maker/checker standoff x2 | neither is presumed right | you decide, or run a third fresh reviewer that judges evidence and may not split the difference |
| verify-goals timeout | predicate too expensive | that is a violation; cheapen the predicate |

## Goal sentinel (detection only; fixes go through the pipeline)
```
/loop 1d Run ./verify-goals.sh. If non-zero: for each violated goal, read its
last-pass date and list what merged since (git log --oneline --since=<date>).
Report goal, suspects, on-violation policy. Do not fix anything.
```

## Optional loops — install ONLY when the condition appears
- **Quorum** (`quorum.sh`, present but not cronned): install when
  memory/dispatch.tsv shows Fable wake-ups that produced `action: stop`.
- **Ratchet**: install when one number matters. Monotonic improvement or
  self-revert; the metric may not be gamed; the finished floor becomes a
  standing goal in goals/.
- **Sparring**: install when this repo ships code daily. Builder and breaker,
  opposed; breaker writes ONE failing test/day under tests/sparring/ tagged
  @sparring; builder fixes CODE only; disputes queue for a human.
- **Compost** (weekly, install always once the loop has a week of exhaust):
  read FAILED lines in STATE.md, fails in trust.tsv, FAILs in goal-ledger.tsv,
  PRs closed unmerged; propose AT MOST 3 changes (a CLAUDE.md law quoting
  incidents, a skill fix, or a missing standing goal). Propose only;
  human signature required.

## 30-day trust schedule (do not skip graduations)
| Week | Level | You do | Graduate when |
|---|---|---|---|
| 1 | L1 report | `make tick` by hand daily; read everything | 3 consecutive runs route exactly as you would have |
| 2 | L2 draft | cron on; `make queue` with coffee | 2 skills cross 20 logged runs |
| 3 | L3 ship | `make audit` vs the formula; best skill goes unattended | 1 week, zero interventions |
| 4 | L4 grow | compost sign-offs; approve 1 proposed skill; run the delete pass | you removed something and nothing broke |

## Cost model
daily = ticks × triage(0.01) + hits × (conductor 0.35 + worker 0.10 + verifier 0.40).
Cadence is a cost decision: halving the interval doubles the floor. The quiet
tick must cost cents. Effort never above high in loops except the conductor.

## Prereqs on the loop machine
claude CLI (Fable 5 access, usage-credits cap set) · llm CLI + OpenRouter key
(`llm install llm-openrouter`) · jq · gh · git · make · cron
