#!/usr/bin/env bash
# Re-verify every standing goal. A goal you only verify once is an
# assumption with a timestamp. Detection only; fixes go through the pipeline.
set -uo pipefail
cd "$(dirname "$0")"
LEDGER="memory/goal-ledger.tsv"; VIOLATIONS=0
for g in goals/*.md; do
  [ -e "$g" ] || continue
  grep -q '^status: retired' "$g" && continue
  pred=$(grep '^predicate:' "$g" | cut -d' ' -f2-); name=$(basename "$g" .md)
  start=$(date +%s%3N)
  if timeout 60 bash -c "$pred" >/dev/null 2>&1; then r=pass
    sed -i "s/^status:.*/status: satisfied/; s/^last-pass:.*/last-pass: $(date +%F)/" "$g"
  else r=FAIL; VIOLATIONS=$((VIOLATIONS+1)); sed -i "s/^status:.*/status: VIOLATED/" "$g"; fi
  echo -e "$(date -Is)\t$name\t$r\t$(( $(date +%s%3N) - start ))" >> "$LEDGER"
done
[ "$VIOLATIONS" -gt 0 ] && { grep -l '^status: VIOLATED' goals/*.md; exit 1; }
echo "all standing goals hold"
