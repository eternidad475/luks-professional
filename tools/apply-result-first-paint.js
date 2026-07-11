const fs=require('fs');
const path='caseflow_studio_v96.html';
let s=fs.readFileSync(path,'utf8');
function replaceOnce(label,before,after){
  const i=s.indexOf(before);
  if(i<0)throw new Error('anchor not found: '+label);
  s=s.slice(0,i)+after+s.slice(i+before.length);
  console.log('patched',label);
}
replaceOnce('legacy go result routing',
"function go(id){pausePreview();document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));$(id).classList.add('active');document.querySelectorAll('.nav').forEach(n=>n.classList.remove('on'));if(id==='export'){document.querySelectorAll('.nav')[3]?.classList.add('on')}else if(id==='preview'||id==='align'){document.querySelectorAll('.nav')[2]?.classList.add('on')}else if(id==='upload'){document.querySelectorAll('.nav')[1]?.classList.add('on')}else if(id==='start'||id==='home'||id==='simulator'){document.querySelectorAll('.nav')[0]?.classList.add('on')}if(id==='upload')renderUpload();if(id==='align')renderAlign();if(id==='preview')renderPreview();if(id==='simulator')renderSimulator();if(id==='result')renderResult()}",
"function go(id){if(id!=='result')pausePreview();document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));const target=$(id);if(target)target.classList.add('active');document.querySelectorAll('.nav').forEach(n=>n.classList.remove('on'));if(id==='export'){document.querySelectorAll('.nav')[3]?.classList.add('on')}else if(id==='preview'||id==='align'){document.querySelectorAll('.nav')[2]?.classList.add('on')}else if(id==='upload'){document.querySelectorAll('.nav')[1]?.classList.add('on')}else if(id==='start'||id==='home'||id==='simulator'){document.querySelectorAll('.nav')[0]?.classList.add('on')}if(id==='upload')renderUpload();if(id==='align')renderAlign();if(id==='preview')renderPreview();if(id==='simulator')renderSimulator();if(id==='result'&&typeof window.cfPaintPrimaryResult!=='function')setTimeout(function(){try{renderResult();}catch(e){console.error('[CaseFlow result fallback]',e);}},0)}"
);
replaceOnce('deferred autosave helper insertion',
"  window.cfAutoSaveTempSim=cfAutoSaveTempSim;\n  window.cfPersistLib=cfPersistLib;\n  function pushSimResult(r){",
"  window.cfAutoSaveTempSim=cfAutoSaveTempSim;\n  window.cfPersistLib=cfPersistLib;\n  function cfRunIdle(job,timeout){\n    try{if('requestIdleCallback' in window)return requestIdleCallback(job,{timeout:timeout||1800});}catch(e){}\n    return setTimeout(job,Math.min(timeout||600,700));\n  }\n  function cfScheduleTempSimSave(r,opts){setTimeout(function(){cfRunIdle(function(){try{cfAutoSaveTempSim(r,opts||{});}catch(e){console.error('[CaseFlow deferred autosave]',e);}},2400);},1600);}\n  window.cfScheduleTempSimSave=cfScheduleTempSimSave;\n  function pushSimResult(r){"
);
replaceOnce('push result sync autosave',
"    // Generation just completed → save to Library and surface a truthful success/failure toast.\n    cfAutoSaveTempSim(r, {toast:true});",
"    // Paint the result first; compress/persist only after the browser has rendered it.\n    cfScheduleTempSimSave(r,{toast:true});"
);
replaceOnce('result renderer',
`  function renderResultImages(){
    // Seed the gallery from a legacy single simResult (e.g. loaded project).
    if((!Array.isArray(state.simResults)||!state.simResults.length) && state.simResult && state.simResult.dataUrl){
      state.simResults=[state.simResult]; state.simResultIndex=0;
    }
    const arr=Array.isArray(state.simResults)?state.simResults:[];
    const r=state.simResult || arr[state.simResultIndex||0], src=state._simSource||pickSource();
    if(!r||!src){ renderSimGallery(); return; }
    const before=$id('resultBefore'), after=$id('resultAfter');
    // ⑤ ALWAYS pair the before image with THIS result's OWN source (never the global
    // _simSource, which is stale when switching between variations generated from different
    // uploads). r.source / r.srcObj are stored per-result in pushSimResult/regenerate.
    const beforeSrc=(r.source) || (r.srcObj && r.srcObj.dataUrl) || src.dataUrl;
    if(before) before.src=beforeSrc;
    if(after)  after.src=r.dataUrl;
    const cap=$id('resultCaption');
    if(cap) cap.textContent=\`${sourceKindLabel(src)} image / Reference Image — 説明用の参考イメージであり、治療結果の保証ではありません。\`;
    if(typeof setupCompareSlider==='function'){ const el=$id('simulationCompareSlider'); if(el) setupCompareSlider(el); }
    renderSimGallery();
  }`,
`  let __cfResultPaintSeq=0;
  function cfResultRecord(){
    if((!Array.isArray(state.simResults)||!state.simResults.length)&&state.simResult&&state.simResult.dataUrl){state.simResults=[state.simResult];state.simResultIndex=0;}
    const arr=Array.isArray(state.simResults)?state.simResults:[];
    return state.simResult||arr[state.simResultIndex||0]||null;
  }
  function cfDismissWaitVisualOnly(){
    try{document.querySelectorAll('.cfWaitOverlay.show').forEach(function(el){el.classList.remove('show');el.setAttribute('aria-hidden','true');});}catch(e){}
  }
  function cfResultKindLabel(r,src){
    const raw=(r&&r.sourceKind)||(src&&src.label)||(src&&src.category)||'';
    if(raw)return String(raw);
    return src&&src.intraoral?'Intraoral':'Facial';
  }
  function cfPaintPrimaryResult(){
    const seq=++__cfResultPaintSeq;
    const r=cfResultRecord(),src=state._simSource||pickSource();
    if(!r||!src)return false;
    const resultEl=$id('result');
    if(resultEl&&!resultEl.classList.contains('active')){document.querySelectorAll('.screen.active').forEach(function(el){el.classList.remove('active');});resultEl.classList.add('active');}
    const before=$id('resultBefore'),after=$id('resultAfter');
    const beforeSrc=r.source||(r.srcObj&&r.srcObj.dataUrl)||src.dataUrl;
    if(before&&before.src!==beforeSrc)before.src=beforeSrc;
    if(after&&after.src!==r.dataUrl)after.src=r.dataUrl;
    const cap=$id('resultCaption');
    if(cap)cap.textContent=cfResultKindLabel(r,src)+' image / Reference Image — 説明用の参考イメージであり、治療結果の保証ではありません。';
    cfDismissWaitVisualOnly();
    window.__cfResultFirstPaintAt=performance.now();
    window.__cfEditHydrationScheduled=seq;
    requestAnimationFrame(function(){
      if(seq!==__cfResultPaintSeq)return;
      setTimeout(function(){
        cfRunIdle(function(){if(seq!==__cfResultPaintSeq)return;try{const el=$id('simulationCompareSlider');if(el&&typeof setupCompareSlider==='function')setupCompareSlider(el);}catch(e){console.warn('[CaseFlow compare hydrate]',e);}},1600);
      },700);
      setTimeout(function(){
        cfRunIdle(function(){if(seq!==__cfResultPaintSeq)return;try{buildEditGrid();window.__cfEditHydratedSeq=seq;}catch(e){console.warn('[CaseFlow edit hydrate]',e);}},2200);
      },900);
      setTimeout(function(){
        cfRunIdle(function(){if(seq!==__cfResultPaintSeq)return;try{renderSimGallery();}catch(e){console.warn('[CaseFlow gallery hydrate]',e);}},1800);
      },1200);
      setTimeout(function(){
        cfRunIdle(function(){try{if(window.cfWait)window.cfWait.hideAll();}catch(e){}try{pausePreview();}catch(e){}},1800);
      },1400);
      setTimeout(function(){
        cfRunIdle(function(){try{if(window.__cfPendingGallerySync&&typeof window.renderUpload==='function'){window.__cfPendingGallerySync=false;window.renderUpload();}if(window.cfPersist&&window.cfPersist.schedule)window.cfPersist.schedule(900);}catch(e){console.warn('[CaseFlow deferred sync]',e);}},2400);
      },1800);
    });
    return true;
  }
  window.cfPaintPrimaryResult=cfPaintPrimaryResult;
  function renderResultImages(){return cfPaintPrimaryResult();}`
);
replaceOnce('late adoption heavy sync',
"          if(state.simResultIndex===i || state.simResult===rec){\n            state.simResult=rec;\n            try{ renderResultImages(); }catch(e){}\n            try{ renderSimGallery(); }catch(e){}\n          }\n          try{ cfAutoSaveTempSim(rec,{toast:false}); }catch(e){}\n          try{ if(window.cfPersist&&cfPersist.schedule) cfPersist.schedule(700); }catch(e){}",
"          if(state.simResultIndex===i || state.simResult===rec){state.simResult=rec;try{cfPaintPrimaryResult();}catch(e){}}\n          try{cfScheduleTempSimSave(rec,{toast:false});}catch(e){}\n          setTimeout(function(){cfRunIdle(function(){try{if(window.cfPersist&&cfPersist.schedule)cfPersist.schedule(700);}catch(e){}},1800);},1400);"
);
replaceOnce('regen sync save order',
"      cfAutoSaveTempSim(r);   // ① keep the 48h temp Library copy in sync with slider edits\n      renderResultImages();\n      // Persist the new result immediately so a reload won't lose it\n      try{ if(window.cfPersist) cfPersist.schedule(1000); }catch(e){}",
"      cfPaintPrimaryResult();\n      cfScheduleTempSimSave(r);\n      setTimeout(function(){cfRunIdle(function(){try{if(window.cfPersist)cfPersist.schedule(1000);}catch(e){}},1800);},1300);"
);
replaceOnce('pre-generation gallery sync',
"          state.photos.push(src);\n          if(typeof window.renderUpload==='function') window.renderUpload();\n          if(typeof window.cfPersist!=='undefined' && window.cfPersist && window.cfPersist.schedule) try{ window.cfPersist.schedule(800); }catch(e){}",
"          state.photos.push(src);\n          window.__cfPendingGallerySync=true;"
);
replaceOnce('generation route duplicate renders',
`      if(typeof go==='function') go('result');
      // After an orthodontic generation, recentre the alignment slider so the NEXT
      // regeneration applies a further, incremental correction on top of this result.
      if(_ortho){ state.simV96.alignment=50; window._cfExtractWarned=false; }
      setTimeout(()=>{ renderResultImages(); buildEditGrid(); }, 60);
      setTimeout(()=>{ renderResultImages(); buildEditGrid(); }, 220);`,
`      if(typeof window.cfOpenResultScreen==='function')window.cfOpenResultScreen();else cfPaintPrimaryResult();
      if(_ortho){state.simV96.alignment=50;window._cfExtractWarned=false;}`
);
replaceOnce('legacy render wrapper',
`  /* ---- keep the result edit grid in sync whenever the result page renders ---- */
  const prevRenderResult = window.renderResult;
  window.renderResult = function(){
    const r = (typeof prevRenderResult==='function') ? prevRenderResult.apply(this,arguments) : undefined;
    setTimeout(()=>{ renderResultImages(); buildEditGrid(); }, 40);
    setTimeout(buildEditGrid, 180);
    return r;
  };

  const prevGo = window.go;
  if(typeof prevGo==='function' && !window.__v96GoWrapped){
    window.__v96GoWrapped=true;
    window.go=function(id){
      const r=prevGo.apply(this,arguments);
      if(id==='result') setTimeout(()=>{ renderResultImages(); buildEditGrid(); }, 70);
      return r;
    };
  }

  window.addEventListener('DOMContentLoaded', ()=>{ setTimeout(buildEditGrid, 200); });`,
`  /* Result route: bypass every legacy renderer/wrapper when a generated result exists. */
  const prevRenderResult=window.renderResult;
  window.renderResult=function(){
    if(cfResultRecord())return cfPaintPrimaryResult();
    return (typeof prevRenderResult==='function')?prevRenderResult.apply(this,arguments):undefined;
  };
  function cfOpenResultScreen(){
    document.querySelectorAll('.screen.active').forEach(function(el){el.classList.remove('active');});
    const resultEl=$id('result');if(resultEl)resultEl.classList.add('active');
    return cfPaintPrimaryResult();
  }
  window.cfOpenResultScreen=cfOpenResultScreen;
  const prevGo=window.go;
  if(typeof prevGo==='function'&&!window.__v96GoWrapped){
    window.__v96GoWrapped=true;
    window.go=function(id){if(id==='result'&&cfResultRecord())return cfOpenResultScreen();return prevGo.apply(this,arguments);};
  }
  window.addEventListener('DOMContentLoaded',function(){if(document.querySelector('#result.active'))cfPaintPrimaryResult();});`
);
if(!s.includes('cf-result-route-guard-v6')){
  s=s.replace('</body>',`<script id="cf-result-route-guard-v6">
+(function(){
+  var raw=window.go;
+  if(typeof raw!=='function'||raw.__cfResultGuardV6)return;
+  function guarded(id){
+    if(id==='result'&&typeof window.cfOpenResultScreen==='function')return window.cfOpenResultScreen();
+    return raw.apply(this,arguments);
+  }
+  guarded.__cfResultGuardV6=true;guarded.__cfRaw=raw;window.go=guarded;
+})();
+</script>
+</body>`);
}
fs.writeFileSync(path,s);
if(fs.existsSync('sw.js')){
  let x=fs.readFileSync('sw.js','utf8');
  x=x.replace(/var VERSION = '[^']+';/,"var VERSION = 'cfsw-v6-result-first-paint';");
  fs.writeFileSync('sw.js',x);
}
console.log('done',s.length);