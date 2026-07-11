from pathlib import Path

src=Path('caseflow_studio_v96.html').read_text(encoding='utf-8')
lines=src.splitlines()

def write_around(filename, needles, before=50, after=140):
    out=[]
    for needle in needles:
        hits=[i for i,l in enumerate(lines) if needle in l]
        out.append(f'===== {needle}: {[i+1 for i in hits]} =====')
        for i in hits:
            lo=max(0,i-before);hi=min(len(lines),i+after)
            out.extend(f'{n+1:05d}: {lines[n]}' for n in range(lo,hi))
    Path('docs/'+filename).write_text('\n'.join(out),encoding='utf-8')

write_around('diag-primary-analysis.txt',['function ensureProblemList','async function ensureProblemList','caseflowLocalAnalyze','window.caseflowLocalAnalyze'],45,150)
write_around('diag-primary-result-save.txt',['function pushSimResult','const pushSimResult','function cfAutoSaveTempSim','window.cfAutoSaveTempSim','cfAutoSaveTempSim(','function renderResultImages'],45,150)
write_around('diag-primary-go-morph.txt',['cfCapRefresh','cfEnsureFaceMesh','var prevGo=window.go','const prevGo=window.go','window.go=function'],30,80)
print('done')
