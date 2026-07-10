from pathlib import Path
import re, subprocess, tempfile, traceback

# Workflow trigger: primary hard-deadline v3
HTML = Path('caseflow_studio_v96.html')
SW = Path('sw.js')
LOG = Path('docs/primary-generation-v3-result.txt')

try:
    s = HTML.read_text(encoding='utf-8')
    marker = '/* CF_PRIMARY_HARD_DEADLINE_V3 */'
    if marker not in s:
        start = s.find('  async function ensureIntraoralFlag(src){')
        end_marker = '\n  window.caseflowEnsureIntraoral=ensureIntraoralFlag;'
        end = s.find(end_marker, start)
        if start < 0 or end < 0:
            raise RuntimeError(f'ensureIntraoralFlag block missing start={start} end={end}')
        end += len(end_marker)
        bounded_flag = r'''  /* CF_PRIMARY_HARD_DEADLINE_V3 */
  async function ensureIntraoralFlag(src){
    if(!src || !src.dataUrl) return false;
    const resolveLips=()=>{
      if(typeof src.lips!=='boolean') src.lips=(((src.category||'').toLowerCase()==='facial') && !src.intraoral);
    };
    if(typeof src.intraoral==='boolean' && typeof src.intraoralDark==='boolean'){ resolveLips(); return src.intraoral; }
    try{
      if(window.caseflowLocalAnalyze){
        const timeoutToken={cfTimeout:true};
        const a=await Promise.race([
          window.caseflowLocalAnalyze(src.dataUrl,src.category||null),
          new Promise(resolve=>setTimeout(()=>resolve(timeoutToken),650))
        ]);
        if(a!==timeoutToken){
          src.intraoral=!!(a&&a.intraoral); src.intraoralDark=!!(a&&a.intraoralDark);
          resolveLips(); return src.intraoral;
        }
      }
    }catch(e){}
    if(typeof src.intraoral!=='boolean') src.intraoral=((src.category||'').toLowerCase()==='intraoral');
    if(typeof src.intraoralDark!=='boolean') src.intraoralDark=false;
    resolveLips(); return src.intraoral;
  }
  window.caseflowEnsureIntraoral=ensureIntraoralFlag;'''
        s = s[:start] + bounded_flag + s[end:]

        pstart = s.find('  async function produceImage(src){')
        pend_marker = '\n  window.caseflowProduceSimImage=produceImage;'
        pend = s.find(pend_marker, pstart)
        if pstart < 0 or pend < 0:
            raise RuntimeError(f'produceImage block missing start={pstart} end={pend}')
        pend += len(pend_marker)
        orchestration = r'''  const CF_PRIMARY_RESULT_DEADLINE_MS=18000;
  const CF_PRIMARY_PREFLIGHT_MS=700;
  async function cfFastPrimaryPreview(src,raw){
    if(!src||!src.dataUrl) return null;
    try{
      const img=await Promise.race([
        loadImage(src.dataUrl),
        new Promise((_,reject)=>setTimeout(()=>reject(new Error('quick preview decode timeout')),1800))
      ]);
      const iw=img.naturalWidth||img.width,ih=img.naturalHeight||img.height;
      if(!iw||!ih) return src.dataUrl;
      const maxEdge=960,scale=Math.min(1,maxEdge/Math.max(iw,ih));
      const w=Math.max(1,Math.round(iw*scale)),h=Math.max(1,Math.round(ih*scale));
      const c=document.createElement('canvas');c.width=w;c.height=h;
      const x=c.getContext('2d',{alpha:false});x.imageSmoothingEnabled=true;x.imageSmoothingQuality='high';x.drawImage(img,0,0,w,h);
      const facial=((src.category||'').toLowerCase()==='facial')||(!src.intraoral&&src.lips!==false);
      const rx=facial?w*.31:w*.12, ry=facial?h*.50:h*.18, rw=facial?w*.38:w*.76, rh=facial?h*.23:h*.55;
      const tmp=document.createElement('canvas');tmp.width=w;tmp.height=h;
      const tx=tmp.getContext('2d');
      const shade=((raw&&raw.shade)!=null?raw.shade:50); const bright=1+Math.max(0,shade-50)/50*.07;
      tx.filter='brightness('+bright.toFixed(3)+') saturate(.92) contrast(1.025)';tx.drawImage(img,0,0,w,h);tx.filter='none';
      x.save();x.beginPath();x.ellipse(rx+rw/2,ry+rh/2,rw/2,rh/2,0,0,Math.PI*2);x.clip();x.globalAlpha=.74;x.drawImage(tmp,0,0);x.restore();
      try{drawBadge(x,w,h);}catch(e){}
      const out=c.toDataURL('image/jpeg',.82);c.width=c.height=1;tmp.width=tmp.height=1;return out;
    }catch(e){ console.warn('[CaseFlow] quick preview fallback uses source',e); return src.dataUrl; }
  }
  window.cfFastPrimaryPreview=cfFastPrimaryPreview;
  async function produceImage(src){
    const started=performance.now();
    let progressTimer=null, deadlineTimer=null;
    window.__caseflowQuickPreviewUsed=false;
    try{sessionStorage.setItem('cf_primary_generation_guard_v3',JSON.stringify({startedAt:Date.now()}));}catch(e){}
    try{if(window.cfWait)cfWait.show('AIシミュレーション中',0);}catch(e){}
    const quickTask=cfFastPrimaryPreview(src,state.simV96||{});
    try{
      await Promise.allSettled([
        Promise.race([ensureIntraoralFlag(src),new Promise(resolve=>setTimeout(resolve,CF_PRIMARY_PREFLIGHT_MS))]),
        Promise.race([ensureProblemList(src),new Promise(resolve=>setTimeout(resolve,CF_PRIMARY_PREFLIGHT_MS))])
      ]);
    }catch(e){}
    const preflightMs=Math.round(performance.now()-started);
    const aiOn=aiEnabled();
    if(aiOn){
      const msgs=['画像を最適化中…','AIシミュレーション生成中…','臨床デザインを確認中…'];let mi=0;
      const tick=()=>{try{const q=document.querySelector('.cfWaitOverlay .cfWaitSub');if(q)q.textContent=msgs[mi++%msgs.length];}catch(e){}};
      tick();progressTimer=setInterval(tick,2200);
    }
    try{
      if(aiOn){
        const aiTask=generateViaAI(src).then(url=>({kind:'ai',url})).catch(err=>({kind:'error',err}));
        const remaining=Math.max(2500,CF_PRIMARY_RESULT_DEADLINE_MS-(performance.now()-started));
        const deadlineTask=new Promise(resolve=>{deadlineTimer=setTimeout(()=>resolve({kind:'deadline'}),remaining);});
        const result=await Promise.race([aiTask,deadlineTask]);
        if(result&&result.kind==='ai'&&result.url){
          window.__caseflowPrimaryResultMode='ai';return result.url;
        }
        if(result&&result.kind==='error'&&result.err&&result.err.cfNoTokens) throw result.err;
        if(result&&result.kind==='deadline'){try{if(window.__cfGenerationAbort)window.__cfGenerationAbort();}catch(e){}}
        if(result&&result.kind==='error') window.__caseflowLastAIError=String((result.err&&result.err.message)||result.err||'AI error');
      }
      let quick=null;
      try{quick=await Promise.race([quickTask,new Promise(resolve=>setTimeout(()=>resolve(src&&src.dataUrl||null),1200))]);}catch(e){quick=src&&src.dataUrl||null;}
      if(!quick) throw new Error('一次プレビューを作成できませんでした');
      window.__caseflowQuickPreviewUsed=true;window.__caseflowPrimaryResultMode='quick';
      setTimeout(()=>{try{toastFn('通信が時間内に完了しなかったため、軽量プレビューを表示しました。精密生成は結果画面から再実行できます。');}catch(e){}},80);
      return quick;
    } finally {
      clearInterval(progressTimer);clearTimeout(deadlineTimer);
      const totalMs=Math.round(performance.now()-started);
      window.__caseflowGenerationTiming={preflight_ms:preflightMs,total_ms:totalMs,mode:window.__caseflowPrimaryResultMode||'unknown',hard_deadline_ms:CF_PRIMARY_RESULT_DEADLINE_MS,completed_at:new Date().toISOString()};
      try{if(typeof window.cfLogEvent==='function')window.cfLogEvent('generation_timing','visual-simulation',window.__caseflowGenerationTiming);}catch(e){}
      try{sessionStorage.removeItem('cf_primary_generation_guard_v3');}catch(e){}
      try{if(window.cfWait)cfWait.hideAll();}catch(e){}
    }
  }
  window.caseflowProduceSimImage=produceImage;'''
        s = s[:pstart] + orchestration + s[pend:]
        s = s.replace("},32000);", "},24000);", 1)
        recovery = r'''
<script id="cf-primary-recovery-v3">
(function(){
  function recover(){
    try{if(window.cfWait)window.cfWait.hideAll();}catch(e){}
    try{document.documentElement.style.removeProperty('overflow');document.body.style.removeProperty('overflow');}catch(e){}
    try{var app=document.querySelector('.app');if(app){app.style.visibility='visible';app.style.opacity='1';app.style.display='block';}}catch(e){}
    try{
      if(!document.querySelector('.screen.active')){
        var target=(window.state&&state.simResult&&document.getElementById('result'))?'result':'simulator';
        if(typeof window.go==='function'&&document.getElementById(target))window.go(target);
        else{var el=document.getElementById(target)||document.querySelector('.screen');if(el)el.classList.add('active');}
      }
    }catch(e){}
    try{sessionStorage.removeItem('cf_primary_generation_guard_v3');}catch(e){}
  }
  window.cfRecoverPrimaryGenerationV3=recover;
  window.addEventListener('pageshow',function(){setTimeout(recover,30);});
  window.addEventListener('DOMContentLoaded',function(){
    var stale=false;try{var g=JSON.parse(sessionStorage.getItem('cf_primary_generation_guard_v3')||'null');stale=!!g;}catch(e){}
    if(stale||!document.querySelector('.screen.active'))setTimeout(recover,60);
  });
  document.addEventListener('visibilitychange',function(){if(!document.hidden)setTimeout(recover,50);});
})();
</script>
'''
        if '</body>' not in s: raise RuntimeError('body end missing')
        s=s.replace('</body>',recovery+'</body>',1)
        HTML.write_text(s,encoding='utf-8')
    sw=SW.read_text(encoding='utf-8')
    sw=sw.replace("var VERSION = 'cfsw-v1';","var VERSION = 'cfsw-v3-primary-deadline';")
    SW.write_text(sw,encoding='utf-8')
    s=HTML.read_text(encoding='utf-8')
    required=['CF_PRIMARY_HARD_DEADLINE_V3','CF_PRIMARY_RESULT_DEADLINE_MS=18000','cfFastPrimaryPreview','cf-primary-recovery-v3','window.__caseflowQuickPreviewUsed']
    if not all(k in s for k in required): raise RuntimeError('required V3 markers missing')
    if 'return await createSimulationImageV96(src, state.simV96);' in s[s.find('async function produceImage'):s.find('window.caseflowProduceSimImage')]:
        raise RuntimeError('heavy fallback remains in primary AI orchestration')
    scripts=re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',s,re.S|re.I)
    failures=[]
    for i,code in enumerate(scripts):
        if not code.strip():continue
        q=Path(tempfile.gettempdir())/f'cf-v3-{i}.js';q.write_text(code,encoding='utf-8')
        r=subprocess.run(['node','--check',str(q)],capture_output=True,text=True)
        if r.returncode:failures.append((i,r.stderr[-1000:]))
    if failures:raise RuntimeError('inline JS parse failures '+repr(failures))
    subprocess.run(['node','--check','sw.js'],check=True,capture_output=True,text=True)
    LOG.write_text('SUCCESS_V3\ninline_scripts='+str(len(scripts))+'\nhard_deadline_ms=18000\nservice_worker=cfsw-v3-primary-deadline\n',encoding='utf-8')
except Exception:
    LOG.parent.mkdir(parents=True,exist_ok=True)
    LOG.write_text('FAILED_V3\n'+traceback.format_exc(),encoding='utf-8')
    raise
