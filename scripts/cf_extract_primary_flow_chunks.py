from pathlib import Path

p=Path('caseflow_studio_v96.html')
s=p.read_text(encoding='utf-8')
lines=s.splitlines()

def chunk(name,lo,hi):
    Path('docs/'+name).write_text('\n'.join(f'{i+1:05d}: {lines[i]}' for i in range(max(0,lo-1),min(len(lines),hi))),encoding='utf-8')

def around(name,needle,before=80,after=180,occ=0):
    hits=[i for i,l in enumerate(lines) if needle in l]
    if not hits:
        Path('docs/'+name).write_text('NO HIT '+needle,encoding='utf-8');return
    i=hits[min(occ,len(hits)-1)]
    chunk(name,i-before+1,i+after+1)

chunk('diag-primary-callsite.txt',20870,21080)
chunk('diag-cfwait-core.txt',21720,21840)
chunk('diag-cfwait-i18n-wrapper.txt',28110,28190)
around('diag-wait-overlay.txt','window.cfWait',120,260)
around('diag-wait-overlay-markup.txt','cfWaitOverlay',80,180)
around('diag-poems.txt','var POEMS',30,90)
around('diag-go-wrapper.txt','var prevGo=window.go',80,180)
# Collect morph-related call lines only, with tight contexts.
out=[]
for needle in ['cfCapRefresh','cfEnsureFaceMesh','prepareMorph','Preparing morphing sequence','モーフィングシークエンス']:
    hits=[i for i,l in enumerate(lines) if needle in l]
    out.append(f'===== {needle}: {[i+1 for i in hits]} =====')
    for i in hits:
        lo=max(0,i-18);hi=min(len(lines),i+30)
        out.extend(f'{n+1:05d}: {lines[n]}' for n in range(lo,hi))
Path('docs/diag-morph-hooks.txt').write_text('\n'.join(out),encoding='utf-8')
# All wait-related line numbers, then context around the last likely definition occurrence.
wait_hits=[i for i,l in enumerate(lines) if 'cfWait' in l]
Path('docs/diag-cfwait-lines.txt').write_text('\n'.join(f'{i+1:05d}: {lines[i]}' for i in wait_hits),encoding='utf-8')
# Definitions often appear near hideAll/show methods; capture every object-like definition candidate.
def_candidates=[i for i,l in enumerate(lines) if ('hideAll' in l or 'function show(' in l or 'const cfWait' in l or 'var cfWait' in l or 'window.cfWait=' in l or 'window.cfWait =' in l)]
out2=[]
for i in def_candidates:
    out2.append(f'===== candidate line {i+1} =====')
    lo=max(0,i-80);hi=min(len(lines),i+180)
    out2.extend(f'{n+1:05d}: {lines[n]}' for n in range(lo,hi))
Path('docs/diag-cfwait-definitions.txt').write_text('\n'.join(out2),encoding='utf-8')
print('done')
