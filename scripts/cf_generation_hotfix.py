from pathlib import Path
import re, subprocess, tempfile, traceback

P=Path('caseflow_studio_v96.html')
LOG=Path('docs/generation-hotfix-result.txt')

try:
    s=P.read_text(encoding='utf-8')
    marker='/* CF_IOS_GENERATION_HARDENING_V1 */'
    if marker not in s:
        start='  async function fetchSimWithRetry(ep, body, maxAttempts){'
        end='\n  // ── buildSimulationPayload'
        a=s.find(start); b=s.find(end,a)
        if a<0 or b<0: raise RuntimeError(f'fetch block missing a={a} b={b}')
        replacement=r'''  /* CF_IOS_GENERATION_HARDENING_V1 */
  async function cfPrepareGenerationImage(dataUrl,maxEdge,quality){
    maxEdge=maxEdge||1800; quality=quality||0.88;
    if(!dataUrl || typeof dataUrl!=='string' || !dataUrl.startsWith('data:image/')) return dataUrl;
    try{
      const img=await loadImage(dataUrl);
      const iw=img.naturalWidth||img.width, ih=img.naturalHeight||img.height;
      const longest=Math.max(iw,ih);
      if(longest<=maxEdge && dataUrl.length<5500000) return dataUrl;
      const scale=Math.min(1,maxEdge/longest);
      const w=Math.max(1,Math.round(iw*scale)), h=Math.max(1,Math.round(ih*scale));
      const c=document.createElement('canvas'); c.width=w; c.height=h;
      const x=c.getContext('2d'); x.imageSmoothingEnabled=true; x.imageSmoothingQuality='high';
      x.drawImage(img,0,0,w,h);
      const out=c.toDataURL('image/jpeg',quality);
      c.width=1; c.height=1;
      return out;
    }catch(e){ console.warn('[CaseFlow] generation image optimization skipped',e); return dataUrl; }
  }
  window.cfPrepareGenerationImage=cfPrepareGenerationImage;

  async function fetchSimWithRetry(ep, body, maxAttempts){
    maxAttempts=maxAttempts||2;
    let lastErr=null;
    for(let attempt=1; attempt<=maxAttempts; attempt++){
      let ctrl=null, tid=null;
      try{
        ctrl=new AbortController();
        window.__cfGenerationAbort=function(){ try{ ctrl.abort(); }catch(e){} };
        tid=setTimeout(function(){ try{ ctrl.abort(); }catch(e){} },60000);
        const res=await fetch(ep,{method:'POST',headers:{'Content-Type':'application/json'},body:body,signal:ctrl.signal});
        clearTimeout(tid); tid=null; window.__cfGenerationAbort=null;
        if(res.ok) return res;
        let t=''; try{ t=await res.text(); }catch(e){}
        const err=new Error('HTTP '+res.status+' '+t.slice(0,400));
        if(RETRY_STATUS[res.status] && attempt<maxAttempts) lastErr=err; else throw err;
      }catch(e){
        if(tid) clearTimeout(tid); window.__cfGenerationAbort=null;
        if(e && e.name==='AbortError') e=new Error('生成処理がタイムアウトしました。通信状態を確認して再試行してください。');
        if(/^HTTP \d/.test(e&&e.message||'') && !RETRY_STATUS[parseInt((e.message.match(/HTTP (\d+)/)||[])[1],10)]) throw e;
        lastErr=e; if(attempt>=maxAttempts) break;
      }
      const wait=Math.pow(2,attempt-1)*900 + Math.floor(Math.random()*300);
      try{ const q=document.querySelector('.cfWaitOverlay .cfWaitSub'); if(q) q.textContent='サーバー応答を待っています… 再試行 '+attempt+'/'+(maxAttempts-1); }catch(e){}
      await sleep(wait);
    }
    throw lastErr || new Error('生成リクエストに失敗しました');
  }
'''
        s=s[:a]+replacement+s[b:]

        old='      const res=await fetchSimWithRetry(ep, JSON.stringify(buildSimulationPayload(source)));'
        new="      const _payload=buildSimulationPayload(source);\n      _payload.image=await cfPrepareGenerationImage(_payload.image,1800,0.88);\n      const res=await fetchSimWithRetry(ep, JSON.stringify(_payload),2);"
        if old not in s: raise RuntimeError('generate request line missing')
        s=s.replace(old,new,1)

        old="      try{ return await finalizeAIImage(source.dataUrl, out, kind, {intraoral:!!(source&&source.intraoral), lips:!!(source&&source.lips)}); }\n      catch(e){ console.warn('finalize failed, using raw AI image', e); return out; }"
        new="      try{ return await Promise.race([finalizeAIImage(source.dataUrl, out, kind, {intraoral:!!(source&&source.intraoral), lips:!!(source&&source.lips)}),new Promise((_,rej)=>setTimeout(()=>rej(new Error('画像仕上げ処理がタイムアウトしました')),28000))]); }\n      catch(e){ console.warn('finalize failed or timed out, using raw AI image', e); return out; }"
        if old not in s: raise RuntimeError('finalize line missing')
        s=s.replace(old,new,1)

        required_wait=[
          ('  var el, sub, showTimer, depth=0;','  var el, sub, showTimer, watchdogTimer, depth=0;'),
          ("      '<div class=\"cfWaitSub\"></div></div>';","      '<div class=\"cfWaitSub\"></div><button type=\"button\" class=\"cfWaitCancel\" style=\"margin-top:14px;min-width:112px;min-height:40px;border:1px solid rgba(32,27,53,.14);border-radius:999px;background:rgba(255,255,255,.72);color:#201b35;font-weight:850;font-size:12px\">処理を中止</button></div>';"),
          ("    sub=el.querySelector('.cfWaitSub');\n    return el;","    sub=el.querySelector('.cfWaitSub');\n    var cancel=el.querySelector('.cfWaitCancel');\n    if(cancel) cancel.addEventListener('click',function(){ try{ if(window.__cfGenerationAbort) window.__cfGenerationAbort(); }catch(e){} hideAll(); try{ if(typeof toastFn==='function') toastFn('生成処理を中止しました'); }catch(e){} });\n    return el;"),
          ("    showTimer=setTimeout(function(){ if(el) el.classList.add('show'); }, delay==null?0:delay);","    showTimer=setTimeout(function(){ if(el) el.classList.add('show'); }, delay==null?0:delay);\n    clearTimeout(watchdogTimer);\n    watchdogTimer=setTimeout(function(){ try{ if(window.__cfGenerationAbort) window.__cfGenerationAbort(); }catch(e){} hideAll(); try{ if(typeof toastFn==='function') toastFn('生成処理が長時間応答しなかったため停止しました。再試行してください。'); }catch(e){} },125000);"),
          ("    clearTimeout(showTimer);\n    if(el) el.classList.remove('show');","    clearTimeout(showTimer); clearTimeout(watchdogTimer);\n    if(el) el.classList.remove('show');"),
          ("  function hideAll(){ depth=0; clearTimeout(showTimer); if(el) el.classList.remove('show'); }","  function hideAll(){ depth=0; clearTimeout(showTimer); clearTimeout(watchdogTimer); if(el) el.classList.remove('show'); }")]
        for old,new in required_wait:
            if old not in s: raise RuntimeError('wait lifecycle pattern missing: '+old[:45])
            s=s.replace(old,new,1)

        recovery='''\n<script id="cf-ios-recovery-v1">\n(function(){function recover(){try{if(window.cfWait)window.cfWait.hideAll();}catch(e){}try{document.documentElement.style.removeProperty('overflow');document.body.style.removeProperty('overflow');}catch(e){}try{var a=document.querySelector('.app');if(a){a.style.visibility='visible';a.style.opacity='1';}}catch(e){}}window.addEventListener('pageshow',function(e){if(e.persisted)setTimeout(recover,40);});window.addEventListener('unhandledrejection',function(){setTimeout(function(){try{if(window.cfWait)window.cfWait.hideAll();}catch(e){}},0);});window.addEventListener('error',function(){setTimeout(function(){try{if(window.cfWait)window.cfWait.hideAll();}catch(e){}},0);});})();\n</script>\n'''
        if '</body>' not in s: raise RuntimeError('body end missing')
        s=s.replace('</body>',recovery+'</body>',1)
        P.write_text(s,encoding='utf-8')

    s=P.read_text(encoding='utf-8')
    required=['CF_IOS_GENERATION_HARDENING_V1','cfPrepareGenerationImage','cfWaitCancel','cf-ios-recovery-v1']
    if not all(x in s for x in required): raise RuntimeError('required markers missing')
    scripts=re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',s,re.S|re.I)
    failures=[]
    for i,code in enumerate(scripts):
        if not code.strip(): continue
        q=Path(tempfile.gettempdir())/f'cf-ios-{i}.js'; q.write_text(code,encoding='utf-8')
        r=subprocess.run(['node','--check',str(q)],capture_output=True,text=True)
        if r.returncode: failures.append((i,r.stderr[-800:]))
    if failures: raise RuntimeError('JS parse failures: '+repr(failures))
    LOG.write_text('SUCCESS\ninline_scripts='+str(len(scripts))+'\n',encoding='utf-8')
except Exception:
    LOG.parent.mkdir(parents=True,exist_ok=True)
    LOG.write_text('FAILED\n'+traceback.format_exc(),encoding='utf-8')
