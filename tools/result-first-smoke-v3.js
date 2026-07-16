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
    const req=route.request(),url=req.url(),type=req.resourceType();
    if(type==='media'||type==='font'||type==='image'||/\/media\//.test(url)||/\/sw\.js(?:\?|$)/.test(url))return route.abort();
    if(url.startsWith('https://cdn.jsdelivr.net/'))return route.fulfill({status:200,contentType:'application/javascript',body:''});
    if(url.startsWith('https://fonts.googleapis.com/'))return route.fulfill({status:200,contentType:'text/css',body:''});
    return route.continue();
  });
  await page.goto('http://127.0.0.1:4173/caseflow_studio_v96.html',{waitUntil:'domcontentloaded',timeout:30000});
  await page.waitForTimeout(700);

  const immediate=await Promise.race([
    page.evaluate(()=>{
      try{pausePreview();}catch(e){}
      document.querySelectorAll('video').forEach(v=>{try{v.pause();v.removeAttribute('src');}catch(e){}});
      const c=document.createElement('canvas');c.width=240;c.height=320;const x=c.getContext('2d');x.fillStyle='#d8c1b1';x.fillRect(0,0,c.width,c.height);x.fillStyle='#fff';x.fillRect(75,182,90,24);
      const before=c.toDataURL('image/jpeg',.62);x.fillStyle='#f9f6e9';x.fillRect(80,185,80,19);const after=c.toDataURL('image/jpeg',.60);
      const src={dataUrl:before,category:'facial',label:'Facial',lips:true,intraoral:false,intraoralDark:false};
      state.photos=[src];state._simSource=src;state.simResults=[{dataUrl:after,source:before,srcObj:src,sourceKind:'Facial',settings:{}}];state.simResultIndex=0;state.simResult=state.simResults[0];
      const simCanvas=document.getElementById('simCanvas');window.__legacyCanvasCalls=0;
      if(simCanvas){const raw=simCanvas.getContext.bind(simCanvas);simCanvas.getContext=function(){window.__legacyCanvasCalls++;return raw.apply(this,arguments);};}
      if(window.cfWait)window.cfWait.show('test',0);
      const started=performance.now();
      if(typeof window.cfOpenResultScreen!=='function')throw new Error('cfOpenResultScreen missing');
      const ok=window.cfOpenResultScreen();
      return {
        ok,
        elapsed:performance.now()-started,
        active:document.getElementById('result').classList.contains('active'),
        waitShown:!!document.querySelector('.cfWaitOverlay.show'),
        editHydrationScheduled:Number(window.__cfEditHydrationScheduled||0),
        firstPaintAt:Number(window.__cfResultFirstPaintAt||0),
        guardInstalled:!!(window.go&&window.go.__cfResultGuardV6)
      };
    }),
    new Promise((_,reject)=>setTimeout(()=>reject(new Error('result shell activation exceeded 2 seconds')),2000))
  ]);

  assert.strictEqual(immediate.ok,true,'result painter returned false');
  assert(immediate.elapsed<250,'result shell activation was not immediate');
  assert(immediate.active,'result screen did not activate');
  assert.strictEqual(immediate.waitShown,false,'waiting overlay remained visible');
  assert(immediate.editHydrationScheduled>0,'deferred hydration was not scheduled');
  assert(immediate.firstPaintAt>0,'first-paint timing marker missing');
  assert(immediate.guardInstalled,'final result-route guard was not installed');

  await page.waitForTimeout(250);
  const settled=await Promise.race([
    page.evaluate(()=>({
      beforeLen:document.getElementById('resultBefore').src.length,
      afterLen:document.getElementById('resultAfter').src.length,
      legacyCanvasCalls:Number(window.__legacyCanvasCalls||0),
      galleryChildren:document.getElementById('simResultGallery').children.length,
      gridChildren:document.getElementById('simV96EditGrid').children.length
    })),
    new Promise((_,reject)=>setTimeout(()=>reject(new Error('result image assignment exceeded 2 seconds')),2000))
  ]);

  console.log(JSON.stringify({immediate,settled,pageErrors},null,2));
  assert(settled.beforeLen>100&&settled.afterLen>100,'before/after images were not assigned asynchronously');
  assert.strictEqual(settled.legacyCanvasCalls,0,'legacy full-frame pixel renderer ran');
  assert.strictEqual(settled.galleryChildren,0,'single result duplicated into gallery during first paint');
  assert.strictEqual(settled.gridChildren,0,'edit grid hydrated during first paint');
  const relevant=pageErrors.filter(x=>/SyntaxError|ReferenceError|cfPaintPrimaryResult|renderResultImages/.test(x));
  assert.deepStrictEqual(relevant,[],'result-first runtime errors: '+relevant.join('\n'));
  await context.close();await browser.close();process.exit(0);
})().catch(async e=>{console.error(e);process.exit(1);});
