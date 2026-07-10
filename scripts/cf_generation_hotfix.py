from pathlib import Path
import re, subprocess, tempfile, traceback

P=Path('caseflow_studio_v96.html')
LOG=Path('docs/generation-hotfix-result.txt')

try:
    s=P.read_text(encoding='utf-8')
    marker='/* CF_GENERATION_SPEED_V2 */'
    if marker not in s:
        required=[
            ('  /* CF_IOS_GENERATION_HARDENING_V1 */','  /* CF_IOS_GENERATION_HARDENING_V1 */\n  /* CF_GENERATION_SPEED_V2 */'),
            ('maxEdge=maxEdge||1800; quality=quality||0.88;','maxEdge=maxEdge||1280; quality=quality||0.84;'),
            ('longest<=maxEdge && dataUrl.length<5500000','longest<=maxEdge && dataUrl.length<2800000'),
            ('maxAttempts=maxAttempts||2;','maxAttempts=maxAttempts||1;'),
            ("},60000);","},20000);"),
            ("_payload.image=await cfPrepareGenerationImage(_payload.image,1800,0.88);","const _cfImageEdge=(source&&source.intraoral)?1536:1280;\n      _payload.image=await cfPrepareGenerationImage(_payload.image,_cfImageEdge,0.84);"),
            ("fetchSimWithRetry(ep, JSON.stringify(_payload),2)","fetchSimWithRetry(ep, JSON.stringify(_payload),1)"),
            ("setTimeout(()=>rej(new Error('画像仕上げ処理がタイムアウトしました')),28000)","setTimeout(()=>rej(new Error('画像仕上げ処理がタイムアウトしました')),5000)"),
            ('},125000);','},32000);')
        ]
        for old,new in required:
            if old not in s:
                raise RuntimeError('speed patch pattern missing: '+old[:90])
            s=s.replace(old,new,1)

        old="""    try{ await ensureIntraoralFlag(src); }catch(e){}
    try{ await ensureProblemList(src); }catch(e){}
    const _aiOn=aiEnabled();"""
        new="""    const _cfPreflightStart=performance.now();
    try{
      await Promise.allSettled([
        ensureIntraoralFlag(src),
        Promise.race([ensureProblemList(src),new Promise(function(resolve){setTimeout(resolve,1500);})])
      ]);
    }catch(e){}
    const _cfPreflightMs=Math.round(performance.now()-_cfPreflightStart);
    const _aiOn=aiEnabled();"""
        if old not in s: raise RuntimeError('preflight block missing')
        s=s.replace(old,new,1)

        old="""    try{
      if(_aiOn){"""
        new="""    const _cfGenerationStart=performance.now();
    try{
      if(_aiOn){"""
        if old not in s: raise RuntimeError('produceImage timing start missing')
        s=s.replace(old,new,1)

        old="""      clearInterval(_progressTimer);
      try{ if(window.cfWait) cfWait.hide(); }catch(e){}
    }
  }"""
        new="""      clearInterval(_progressTimer);
      const _cfTotalMs=Math.round(performance.now()-_cfGenerationStart);
      window.__caseflowGenerationTiming={preflight_ms:_cfPreflightMs,total_ms:_cfTotalMs,completed_at:new Date().toISOString()};
      try{ if(typeof window.cfLogEvent==='function') window.cfLogEvent('generation_timing','visual-simulation',window.__caseflowGenerationTiming); }catch(e){}
      console.log('[CaseFlow Generation Timing]',window.__caseflowGenerationTiming);
      try{ if(window.cfWait) cfWait.hideAll(); }catch(e){}
    }
  }"""
        if old not in s: raise RuntimeError('produceImage finally block missing')
        s=s.replace(old,new,1)

        old="""      const _payload=buildSimulationPayload(source);
      const _cfImageEdge=(source&&source.intraoral)?1536:1280;
      _payload.image=await cfPrepareGenerationImage(_payload.image,_cfImageEdge,0.84);
      const res=await fetchSimWithRetry(ep, JSON.stringify(_payload),1);"""
        new="""      const _payload=buildSimulationPayload(source);
      const _cfImageEdge=(source&&source.intraoral)?1536:1280;
      const _cfPrepStart=performance.now();
      _payload.image=await cfPrepareGenerationImage(_payload.image,_cfImageEdge,0.84);
      const _cfPayloadBytes=JSON.stringify(_payload).length;
      const _cfRequestStart=performance.now();
      const res=await fetchSimWithRetry(ep, JSON.stringify(_payload),1);
      window.__caseflowLastRequestTiming={prepare_ms:Math.round(_cfRequestStart-_cfPrepStart),request_ms:Math.round(performance.now()-_cfRequestStart),payload_bytes:_cfPayloadBytes};"""
        if old not in s: raise RuntimeError('request timing block missing')
        s=s.replace(old,new,1)

        P.write_text(s,encoding='utf-8')

    s=P.read_text(encoding='utf-8')
    checks=[
      'CF_GENERATION_SPEED_V2','_cfImageEdge=(source&&source.intraoral)?1536:1280',
      'fetchSimWithRetry(ep, JSON.stringify(_payload),1)','setTimeout(resolve,1500)',
      'window.__caseflowGenerationTiming','payload_bytes:_cfPayloadBytes'
    ]
    if not all(x in s for x in checks): raise RuntimeError('speed markers missing')
    scripts=re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',s,re.S|re.I)
    failures=[]
    for i,code in enumerate(scripts):
        if not code.strip(): continue
        q=Path(tempfile.gettempdir())/f'cf-speed-{i}.js'; q.write_text(code,encoding='utf-8')
        r=subprocess.run(['node','--check',str(q)],capture_output=True,text=True)
        if r.returncode: failures.append((i,r.stderr[-1000:]))
    if failures: raise RuntimeError('JS parse failures: '+repr(failures))
    LOG.write_text('SUCCESS_V2\ninline_scripts='+str(len(scripts))+'\ntarget_seconds=20-30\n',encoding='utf-8')
except Exception:
    LOG.parent.mkdir(parents=True,exist_ok=True)
    LOG.write_text('FAILED_V2\n'+traceback.format_exc(),encoding='utf-8')
