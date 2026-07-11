const { chromium } = require('playwright');
const assert = require('assert');

(async()=>{
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:390,height:844}});
  page.setDefaultTimeout(15000);
  const pageErrors=[];
  page.on('pageerror',e=>pageErrors.push(String(e&&e.stack||e)));
  await page.addInitScript(()=>{
    try{localStorage.setItem('caseflow_consent_v96','1');localStorage.setItem('caseflow_consent_accepted','true');}catch(e){}
    const chain=()=>({select(){return this},eq(){return this},in(){return this},order(){return this},limit(){return this},single:async()=>({data:null,error:null}),maybeSingle:async()=>({data:null,error:null}),insert:async()=>({data:null,error:null}),update(){return this},delete(){return this}});
    window.supabase={createClient:()=>({auth:{getSession:async()=>({data:{session:null}}),getUser:async()=>({data:{user:null}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})},from:chain,rpc:async()=>({data:null,error:null})})};
  });
  await page.route('https://cdn.jsdelivr.net/**',r=>r.fulfill({status:200,contentType:'application/javascript',body:''}));
  await page.route('https://fonts.googleapis.com/**',r=>r.fulfill({status:200,contentType:'text/css',body:''}));
  await page.goto('http://127.0.0.1:4173/caseflow_studio_v96.html',{waitUntil:'domcontentloaded',timeout:30000});
  await page.waitForTimeout(1800);
  const evalTask=page.evaluate(async()=>{
    const c=document.createElement('canvas');c.width=480;c.height=640;const x=c.getContext('2d');x.fillStyle='#d8c1b1';x.fillRect(0,0,c.width,c.height);x.fillStyle='#fff';x.fillRect(150,365,180,48);
    const before=c.toDataURL('image/jpeg',.76);x.fillStyle='#f9f6e9';x.fillRect(160,370,160,38);const after=c.toDataURL('image/jpeg',.74);
    const src={dataUrl:before,category:'facial',label:'Facial',lips:true,intraoral:false,intraoralDark:false};
    state.photos=[src];state._simSource=src;state.simResults=[{dataUrl:after,source:before,srcObj:src,sourceKind:'Facial',settings:{}}];state.simResultIndex=0;state.simResult=state.simResults[0];
    let legacyCanvasCalls=0;
    const simCanvas=document.getElementById('simCanvas');
    if(simCanvas){const raw=simCanvas.getContext.bind(simCanvas);simCanvas.getContext=function(){legacyCanvasCalls++;return raw.apply(this,arguments);};}
    if(window.cfWait)window.cfWait.show('test',0);
    const started=performance.now();
    go('result');
    await new Promise(r=>setTimeout(r,140));
    return {
      elapsed:performance.now()-started,
      active:document.getElementById('result').classList.contains('active'),
      beforeLen:document.getElementById('resultBefore').src.length,
      afterLen:document.getElementById('resultAfter').src.length,
      waitShown:!!document.querySelector('.cfWaitOverlay.show'),
      legacyCanvasCalls,
      galleryChildren:document.getElementById('simResultGallery').children.length,
      gridChildren:document.getElementById('simV96EditGrid').children.length,
      editHydrationScheduled:Number(window.__cfEditHydrationScheduled||0),
      firstPaintAt:Number(window.__cfResultFirstPaintAt||0)
    };
  });
  const result=await Promise.race([
    evalTask,
    new Promise((_,reject)=>setTimeout(()=>reject(new Error('result-first browser evaluation exceeded 12 seconds')),12000))
  ]);
  console.log(JSON.stringify({result,pageErrors},null,2));
  assert(result.active,'result screen did not activate');
  assert(result.elapsed<900,'first result paint was not immediate');
  assert(result.beforeLen>100&&result.afterLen>100,'before/after images were not painted');
  assert.strictEqual(result.waitShown,false,'waiting overlay remained visible');
  assert.strictEqual(result.legacyCanvasCalls,0,'legacy full-frame pixel renderer ran');
  assert.strictEqual(result.galleryChildren,0,'single result duplicated into gallery on first paint');
  assert(result.editHydrationScheduled>0,'edit controls were not scheduled for deferred hydration');
  assert(result.firstPaintAt>0,'first-paint timing marker missing');
  const relevant=pageErrors.filter(x=>/SyntaxError|ReferenceError|cfPaintPrimaryResult|renderResultImages/.test(x));
  assert.deepStrictEqual(relevant,[],'result-first runtime errors: '+relevant.join('\n'));
  await browser.close();
  process.exit(0);
})().catch(async e=>{console.error(e);process.exit(1);});