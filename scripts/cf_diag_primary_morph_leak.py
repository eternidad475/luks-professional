from pathlib import Path

src = Path('caseflow_studio_v96.html').read_text(encoding='utf-8')
lines = src.splitlines()
terms = [
    'Preparing morphing sequence',
    'モーフィングシークエンス',
    'cfWaitOverlay',
    'window.cfWait',
    'function produceImage',
    'async function produceImage',
    'produceImage(',
    "go('result')",
    'go("result")',
    'renderResult()',
    'renderResultImages()',
    'cfCapRefresh',
    'cfEnsureFaceMesh',
    'prepareMorph',
    'Morphing',
    'morphing',
    'MutationObserver',
    'prevGo=window.go',
    'var prevGo=window.go',
    'window.go=',
]

out=[]
for term in terms:
    hits=[i for i,l in enumerate(lines) if term in l]
    out.append(f'\n===== {term} hits={[i+1 for i in hits]} =====')
    for i in hits[:30]:
        lo=max(0,i-60); hi=min(len(lines),i+180)
        out.extend(f'{n+1:05d}: {lines[n]}' for n in range(lo,hi))

Path('docs/primary-morph-leak-diagnostics.txt').write_text('\n'.join(out),encoding='utf-8')
print('diagnostics lines',len(out))
