from pathlib import Path

src=Path('caseflow_studio_v96.html').read_text(encoding='utf-8')
lines=src.splitlines()
terms=[
  'produceImage(',
  'caseflowProduceSimImage',
  'Reference Image 作成',
  'Reference Image',
  'cfWait.show',
  'cfWait.hide',
  'cfWait.hideAll',
  'window.cfWait=',
  'window.cfWait =',
  'const cfWait',
  'var cfWait',
  'function renderResult',
  "go('result')",
  'go("result")',
  'cfCapRefresh',
  'cfEnsureFaceMesh',
  'POEMS',
]
out=[]
for term in terms:
  hits=[i for i,l in enumerate(lines) if term in l]
  out.append(f'\n===== {term} hits={[i+1 for i in hits]} =====')
  for i in hits:
    lo=max(0,i-24); hi=min(len(lines),i+45)
    out.extend(f'{n+1:05d}: {lines[n]}' for n in range(lo,hi))
Path('docs/primary-flow-compact.txt').write_text('\n'.join(out),encoding='utf-8')
print('lines',len(out))
