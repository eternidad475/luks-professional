const { chromium } = require('playwright');
const assert = require('assert');

(async()=>{
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:390,height:844}});
  await page.addInitScript(()=>{
    try{localStorage.setItem('caseflow_consent_v96','1');}catch(e){}
    window.supabase={createClient:()=>({
      auth:{getSession:async()=>({data:{session:null}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}}),signInWithPassword:async()=>({data:{},error:null}),signUp:async()=>({data:{},error:null})},
      from:()=>({select(){return this},eq(){return this},order(){return this},limit(){return this},single:async()=>({data:null,error:null}),maybeSingle:async()=>({data:null,error:null}),insert:async()=>({data:null,error:null}),update(){return this},delete(){return this}}),
      rpc:async()=>({data:null,error:null})
    })};
  });
  await page.route('https://cdn.jsdelivr.net/**',route=>route.fulfill({status:200,contentType:'application/javascript',body:''}));
  await page.route('**/simulate',async route=>{await new Promise(r=>setTimeout(r,30000));try{await route.abort();}catch(e){}});
  await page.goto('http://127.0.0.1:4173/caseflow_studio_v96.html',{waitUntil:'domcontentloaded',timeout:30000});
  await page.waitForFunction(()=>typeof window.caseflowProduceSimImage==='function',{timeout:15000});
  const result=await page.evaluate(async()=>{
    let localCalls=0,meshCalls=0,refunds=0;
    window.cfConsumeToken=async()=>({ok:true,ledgerId:'smoke-ledger'});
    window.cfRefundGeneration=()=>{refunds++;};
    window.caseflowLocalAnalyze=()=>{localCalls++;return new Promise(()=>{});};
    window.cfEnsureFaceMesh=()=>{meshCalls++;return new Promise(()=>{});};
    const c=document.createElement('canvas');c.width=640;c.height=800;const x=c.getContext('2d');x.fillStyle='#b8d7ec';x.fillRect(0,0,c.width,c.height);x.fillStyle='#f4d4c3';x.beginPath();x.arc(320,350,220,0,Math.PI*2);x.fill();x.fillStyle='#fff';x.fillRect(245,430,150,45);
    const src={dataUrl:c.toDataURL('image/jpeg',.82),category:'facial',lips:true,intraoral:false,intraoralDark:false};
    const start=performance.now();
    const url=await window.caseflowProduceSimImage(src);
    const elapsed=performance.now()-start;
    await new Promise(r=>setTimeout(r,150));
    return {elapsed,urlPrefix:String(url).slice(0,24),mode:window.__caseflowPrimaryResultMode,localCalls,meshCalls,refunds,overlayShown:!!document.querySelector('.cfWaitOverlay.show'),morphText:document.body.textContent.includes('Preparing morphing sequence')||document.body.textContent.includes('モーフィングシークエンスを準備中')};
  });
  console.log(JSON.stringify(result,null,2));
  assert(result.elapsed<19500,'primary result exceeded 19.5 seconds');
  assert(result.elapsed>=14500,'stall test returned before expected deadline');
  assert(result.urlPrefix.startsWith('data:image/'),'no usable image result');
  assert.strictEqual(result.mode,'quick');
  assert.strictEqual(result.localCalls,0,'local analysis ran on primary critical path');
  assert.strictEqual(result.meshCalls,0,'face mesh ran on primary critical path');
  assert.strictEqual(result.overlayShown,false,'waiting overlay remained visible');
  assert.strictEqual(result.morphText,false,'morphing status leaked into simulation wait UI');
  await browser.close();
})().catch(err=>{console.error(err);process.exit(1);});
