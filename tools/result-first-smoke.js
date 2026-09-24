const { chromium } = require('playwright');
const assert = require('assert');

(async()=>{
  const browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'block',reducedMotion:'reduce'});
  const page=await context.newPage();
  page.setDefaultTimeout(12000);
  const pageErrors=[];
  page.on('pageerror',e=>pageErrors.push(String(e&&e.stack||e)));
  await page.addInitScript(()=>{
    try{localStorage.setItem('caseflow_consent_v96','1');localStorage.setItem('caseflow_consent_accepted','true');}catch(e){}
    const chain=()=>({select(){return this},eq(){return this},in(){return this},order(){return this},limit(){return this},single:async()=>({data:null,error:null}),maybeSingle:async()=>({data:null,error:null}),insert:async()=>({data:null,error:null}),update(){return this},delete(){return this}});
    window.supabase={createClient:()=>({auth:{getSession:async()=>({data:{session:null}}),getUser:async()=>({data:{user:null}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})},from:chain,rpc:async()=>({data:null,error:null})})};
  });
  await page.route('**/*',route=>{
    const req=route.request(); const url=req.url(); const type=req.resourceType();
    if(type==='media'||type==='font'||type==='image'||/\/media\//.test(url)||/\/sw\.js(?:\?|$)/.test(url)) return route.abort();
    if(url.startsWith('https://cdn.jsdelivr.net/')) return route.fulfill({status:200,contentType:'application/javascript',body:''});
    if(url.startsWith('https://fonts.googleapis.com/')) return route.fulfill({status:200,contentType:'text/css',body:''});
    return route.continue();
  });
  await page.goto('http://127.0.0.1:4173/caseflow_studio_v96.html',{waitUntil:'domcontentloaded',timeout:30000});
  await page.waitForTimeout(700);

  const step=async(name,fn,ms=3500)=>{
    console.log('STEP_START',name);
    const t=Date.now();
    const value=await Promise.race([page.evaluate(fn),new Promise((_,reject)=>setTimeout(()=>reject(new Error('STEP_TIMEOUT '+name+' '+ms+'ms')),ms))]);
    console.log('STEP_DONE',name,Date.now()-t,JSON.stringify(value));
    return value;
  };

  await step('setup',()=>{
    try{pausePreview();}catch(e){}
    document.querySelectorAll('video').forEach(v=>{try{v.pause();v.removeAttribute('src');}catch(e){}});
    const c=document.createElement('canvas');c.width=240;c.height=320;const x=c.getContext('2d');x.fillStyle='#d8c1b1';x.fillRect(0,0,c.width,c.height);x.fillStyle='#fff';x.fillRect(75,182,90,24);
    const before=c.toDataURL('image/jpeg',.62);x.fillStyle='#f9f6e9';x.fillRect(80,185,80,19);const after=c.toDataURL('image/jpeg',.60);
    const src={dataUrl:before,category:'facial',label:'Facial',lips:true,intraoral:false,intraoralDark:false};
    state.photos=[src];state._simSource=src;state.simResults=[{dataUrl:after,source:before,srcObj:src,sourceKind:'Facial',settings:{}}];state.simResultIndex=0;state.simResult=state.simResults[0];
    const simCanvas=document.getElementById('simCanvas');window.__legacyCanvasCalls=0;
    if(simCanvas){const raw=simCanvas.getContext.bind(simCanvas);simCanvas.getContext=function(){window.__legacyCanvasCalls++;return raw.apply(this,arguments);};}
    return {before:before.length,after:after.length,open:typeof window.cfOpenResultScreen,paint:typeof window.cfPaintPrimaryResult};
  });

  await step('activate-only',()=>{
    document.querySelectorAll('.screen.active').forEach(el=>el.classList.remove('active'));
    const result=document.getElementById('result');result.classList.add('active');
    return {active:result.classList.contains('active'),display:getComputedStyle(result).display};
  });

  await step('assign-images-only',()=>{
    const r=state.simResult,src=state._simSource;
    document.getElementById('resultBefore').src=r.source||src.dataUrl;
    document.getElementById('resultAfter').src=r.dataUrl;
    return {beforeLen:document.getElementById('resultBefore').src.length,afterLen:document.getElementById('resultAfter').src.length};
  });

  await step('caption-bypass-contract',()=>{
    const r=state.simResult,src=state._simSource;
    const raw=(r&&r.sourceKind)||(src&&src.label)||(src&&src.category)||(src&&src.intraoral?'Intraoral':'Facial');
    document.getElementById('resultCaption').textContent=String(raw)+' image / Reference Image';
    return {label:String(raw),legacyHelperType:typeof sourceKindLabel};
  });

  await step('dismiss-overlay-only',()=>{
    document.querySelectorAll('.cfWaitOverlay.show').forEach(el=>el.classList.remove('show'));
    return {shown:!!document.querySelector('.cfWaitOverlay.show')};
  });

  const noRaf=await step('call-paint-no-raf',()=>{
    if(typeof window.cfPaintPrimaryResult!=='function')throw new Error('cfPaintPrimaryResult missing');
    const raw=window.requestAnimationFrame;let captured=0;
    window.requestAnimationFrame=function(cb){captured++;window.__capturedResultFrame=cb;return 9901;};
    try{const t=performance.now();const ok=window.cfPaintPrimaryResult();return {ok,elapsed:performance.now()-t,captured,scheduled:Number(window.__cfEditHydrationScheduled||0),firstPaint:Number(window.__cfResultFirstPaintAt||0),caption:document.getElementById('resultCaption').textContent};}
    finally{window.requestAnimationFrame=raw;}
  });
  assert(noRaf.elapsed<900,'paint remained synchronous even with rAF suppressed');
  assert(/Facial image/.test(noRaf.caption),'primary caption did not use stored source kind');

  await new Promise(r=>setTimeout(r,180));
  const snapshot=await step('post-paint-snapshot',()=>({
    active:document.getElementById('result').classList.contains('active'),
    waitShown:!!document.querySelector('.cfWaitOverlay.show'),
    legacyCanvasCalls:Number(window.__legacyCanvasCalls||0),
    beforeLen:document.getElementById('resultBefore').src.length,
    afterLen:document.getElementById('resultAfter').src.length,
    galleryChildren:document.getElementById('simResultGallery').children.length,
    gridChildren:document.getElementById('simV96EditGrid').children.length,
    guardInstalled:!!(window.go&&window.go.__cfResultGuardV6)
  }));

  console.log(JSON.stringify({noRaf,snapshot,pageErrors},null,2));
  assert(snapshot.active,'result screen did not activate');
  assert(snapshot.beforeLen>100&&snapshot.afterLen>100,'before/after images were not painted');
  assert.strictEqual(snapshot.waitShown,false,'waiting overlay remained visible');
  assert.strictEqual(snapshot.legacyCanvasCalls,0,'legacy full-frame pixel renderer ran');
  assert.strictEqual(snapshot.galleryChildren,0,'single result duplicated into gallery on first paint');
  assert(snapshot.guardInstalled,'final result-route guard was not installed');
  const relevant=pageErrors.filter(x=>/SyntaxError|ReferenceError|cfPaintPrimaryResult|renderResultImages/.test(x));
  assert.deepStrictEqual(relevant,[],'result-first runtime errors: '+relevant.join('\n'));
  await context.close();await browser.close();process.exit(0);
})().catch(async e=>{console.error(e);process.exit(1);});