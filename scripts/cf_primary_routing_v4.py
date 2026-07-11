from pathlib import Path
import re, subprocess, tempfile, traceback

H=Path('caseflow_studio_v96.html'); SW=Path('sw.js'); LOG=Path('docs/primary-routing-v4-result.txt')
try:
    s=H.read_text(encoding='utf-8')
    if 'CF_PRIMARY_ROUTING_ISOLATION_V4' not in s:
        # Replace the misleading global wait poem.
        s=re.sub(r"\s*\{en:'Preparing morphing sequence', ja:'モーフィングシークエンスを準備中'.*?ko:'모핑 시퀀스 준비 중'\}\s*",
                 "\n  {en:'Finalizing clinical preview', ja:'臨床プレビューを仕上げ中', pt:'Finalizando a prévia clínica', it:'Finalizzazione dell’anteprima clinica', ar:'إنهاء المعاينة السريرية', zh:'正在完成临床预览', ko:'임상 미리보기 마무리 중'}\n",s,count=1,flags=re.S)

        # Make late AI work cancellable after the first-result deadline.
        sig='  async function generateViaAI(source){'
        if sig not in s: raise RuntimeError('generateViaAI signature missing')
        s=s.replace(sig,"""  /* CF_PRIMARY_ROUTING_ISOLATION_V4 */
  function cfPrimaryCancelled(ctx){return !!(ctx&&ctx.cancelled);}
  function cfPrimaryCancelError(){const e=new Error('primary generation cancelled after deadline');e.name='AbortError';e.cfPrimaryCancelled=true;return e;}
  function cfCheckPrimaryRun(ctx){if(cfPrimaryCancelled(ctx))throw cfPrimaryCancelError();}
  async function generateViaAI(source,runCtx){""",1)
        s=s.replace("      _ledgerId=(_tk&&_tk.ledgerId)||null;\n    }\n    try{","      _ledgerId=(_tk&&_tk.ledgerId)||null;\n      cfCheckPrimaryRun(runCtx);\n    }\n    try{\n      cfCheckPrimaryRun(runCtx);",1)
        s=s.replace("      const _payload=buildSimulationPayload(source);","      cfCheckPrimaryRun(runCtx);\n      const _payload=buildSimulationPayload(source);",1)
        s=s.replace("      _payload.image=await cfPrepareGenerationImage(_payload.image,_cfImageEdge,0.84);","      const _cfFastPrimary=!!(runCtx&&runCtx.primary);\n      const _cfSendEdge=_cfFastPrimary?((source&&source.intraoral)?1280:1024):_cfImageEdge;\n      _payload.image=await cfPrepareGenerationImage(_payload.image,_cfSendEdge,_cfFastPrimary?0.80:0.84);\n      cfCheckPrimaryRun(runCtx);",1)
        s=s.replace("      const res=await fetchSimWithRetry(ep, JSON.stringify(_payload),1);","      const res=await fetchSimWithRetry(ep, JSON.stringify(_payload),1);\n      cfCheckPrimaryRun(runCtx);",1)
        s=s.replace("      const j=await res.json();","      const j=await res.json();\n      cfCheckPrimaryRun(runCtx);",1)
        s=s.replace("      const kind=(typeof sourceKind==='function') ? sourceKind(source) : 'Image';","      cfCheckPrimaryRun(runCtx);\n      const kind=(typeof sourceKind==='function') ? sourceKind(source) : 'Image';",1)

        # Replace V3 primary orchestration from its deadline constant through the exported function.
        a=s.find('  const CF_PRIMARY_RESULT_DEADLINE_MS=18000;'); b=s.find('\n  window.caseflowProduceSimImage=produceImage;',a)
        if a<0 or b<0: raise RuntimeError('V3 primary block missing')
        b+=len('\n  window.caseflowProduceSimImage=produceImage;')
        s=s[:a]+Path('scripts/v4_produce_block.txt').read_text(encoding='utf-8')+s[b:]

        # Defer image shrinking / JSON persistence / Library rendering until after result paint.
        anchor='  function pushSimResult(r){'; i=s.find(anchor)
        if i<0: raise RuntimeError('pushSimResult missing')
        helper="""  function cfScheduleTempSimSave(r,opts){
    const job=function(){try{cfAutoSaveTempSim(r,opts||{});}catch(e){console.error('[CaseFlow deferred autosave]',e);}};
    try{if('requestIdleCallback' in window)requestIdleCallback(job,{timeout:2600});else setTimeout(job,650);}catch(e){setTimeout(job,650);}
  }
  window.cfScheduleTempSimSave=cfScheduleTempSimSave;
"""
        s=s[:i]+helper+s[i:]
        s=s.replace("    // Generation just completed → save to Library and surface a truthful success/failure toast.\n    cfAutoSaveTempSim(r, {toast:true});","    // Result paint is the priority; persistence runs after navigation.\n    cfScheduleTempSimSave(r,{toast:true});",1)
        s=s.replace("      cfAutoSaveTempSim(r);   // ① keep the 48h temp Library copy in sync with slider edits","      cfScheduleTempSimSave(r);   // defer persistence so result editing remains responsive",1)

        old="""          state.photos.push(src);
          if(typeof window.renderUpload==='function') window.renderUpload();
          if(typeof window.cfPersist!=='undefined' && window.cfPersist && window.cfPersist.schedule) try{ window.cfPersist.schedule(800); }catch(e){}"""
        if old not in s: raise RuntimeError('pre-generation Gallery sync missing')
        s=s.replace(old,"""          state.photos.push(src);
          window.__cfPendingGallerySync=true;""",1)

        # Replace the success path from produceImage through the two delayed render calls.
        start=s.find('      const url = await produceImage(_genSrc);')
        end_token="      setTimeout(()=>{ renderResultImages(); buildEditGrid(); }, 220);"
        end=s.find(end_token,start)
        if start<0 or end<0: raise RuntimeError('generation success block missing')
        end+=len(end_token)
        s=s[:start]+Path('scripts/v4_transition_block.txt').read_text(encoding='utf-8')+s[end:]

        s=s.replace('</body>',Path('scripts/v4_isolation_guard.txt').read_text(encoding='utf-8')+'</body>',1)
        H.write_text(s,encoding='utf-8')

    sw=SW.read_text(encoding='utf-8')
    sw=re.sub(r"var VERSION = '[^']+';","var VERSION = 'cfsw-v4-primary-routing';",sw,count=1)
    SW.write_text(sw,encoding='utf-8')

    s=H.read_text(encoding='utf-8')
    required=['CF_PRIMARY_ROUTING_ISOLATION_V4','CF_PRIMARY_RESULT_DEADLINE_MS=16000','cfScheduleTempSimSave','cf-primary-routing-isolation-v4','Finalizing clinical preview','window.__cfPendingGallerySync']
    if not all(x in s for x in required): raise RuntimeError('V4 marker missing')
    if 'Preparing morphing sequence' in s or 'モーフィングシークエンスを準備中' in s: raise RuntimeError('morph wait poem remains')
    p=s[s.find('async function produceImage(src)'):s.find('window.caseflowProduceSimImage=produceImage;')]
    if any(x in p for x in ['ensureProblemList(','ensureIntraoralFlag(','createSimulationImageV96(']): raise RuntimeError('heavy primary work remains')
    scripts=re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',s,re.S|re.I); bad=[]
    for n,code in enumerate(scripts):
        if not code.strip(): continue
        f=Path(tempfile.gettempdir())/f'cfv4-{n}.js'; f.write_text(code,encoding='utf-8')
        r=subprocess.run(['node','--check',str(f)],capture_output=True,text=True)
        if r.returncode: bad.append((n,r.stderr[-1200:]))
    if bad: raise RuntimeError('inline JS parse failure '+repr(bad))
    subprocess.run(['node','--check','sw.js'],check=True,capture_output=True,text=True)
    LOG.write_text(f'SUCCESS_V4\ninline_scripts={len(scripts)}\nhard_deadline_ms=16000\nservice_worker=cfsw-v4-primary-routing\n',encoding='utf-8')
except Exception:
    LOG.parent.mkdir(parents=True,exist_ok=True); LOG.write_text('FAILED_V4\n'+traceback.format_exc(),encoding='utf-8'); raise
