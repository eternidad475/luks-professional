from pathlib import Path

src = Path('caseflow_studio_v96.html').read_text(encoding='utf-8')
lines = src.splitlines()
terms = [
    'function ensureIntraoralFlag',
    'async function ensureIntraoralFlag',
    'function ensureProblemList',
    'async function ensureProblemList',
    'async function produceImage',
    'async function generateViaAI',
    'async function fetchSimWithRetry',
    'async function createSimulationImageV96',
    'window.cfWait =',
    'function showScreen',
    'serviceWorker.register',
    'visibility =',
    "style.visibility",
    'classList.remove(\'active\')',
]

out = []
for term in terms:
    hits = [i for i, line in enumerate(lines) if term in line]
    out.append(f'\n===== {term} hits={[i+1 for i in hits]} =====')
    for i in hits[:12]:
        lo = max(0, i - 45)
        hi = min(len(lines), i + 180)
        out.extend(f'{n+1:05d}: {lines[n]}' for n in range(lo, hi))

Path('docs/primary-generation-v3-diagnostics.txt').write_text('\n'.join(out), encoding='utf-8')
print('wrote diagnostics', len(out))
