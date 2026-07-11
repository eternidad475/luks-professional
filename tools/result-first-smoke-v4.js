const {chromium}=require('playwright');
const assert=require('assert');
(async()=>{
  const browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'block',reducedMotion:'reduce'});
  const page=await context.newPage();page.setDefaultTimeout(12000);
  const errors=[];page.on('pageerror',e=>errors.push(String(e&&e.stack||e)));
  await page.addInitScript(()=>{try{localStorage.setItem('caseflow_consent_v96','1');localStorage.setItem('caseflow_consent_accepted','true');}catch(e){}const chain=()=>({select(){return this},eq(){return this},in(){return this},order(){return this},limit(){return this},single:async()=>({data:null,error:null}),maybeSingle:async()=>({data:null,error:null}),insert:async()=>({data:null,error:null}),update(){return this},delete(){return this}});window.supabase={createClient:()=>({auth:{getSession:async()=>({data:{session:null}}),getUser:async()=>({data:{user:null}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})},from:chain,rpc:async()=>({data:null,error:null})})};});
  await page.route('**/*',route=>{const req=route.request(),u=req.url(),t=req.resourceType();if(t==='media'||t==='font'||/\/media\//.test(u)||/\/sw\.js(?:\?|$)/.test(u))return route.abort();if(u.startsWith('https://cdn.jsdelivr.net/'))return route.fulfill({status:200,contentType:'application/javascript',body:''});if(u.startsWith('https://fonts.googleapis.com/'))return route.fulfill({status:200,contentType:'text/css',body:''});return route.continue();});
  await page.goto('http://127.0.0.1:4173/caseflow_studio_v96.html',{waitUntil:'domcontentloaded',timeout:30000});await page.waitForTimeout(700);
  const result=await page.evaluate(async()=>{
    try{pausePreview();}catch(e){}document.querySelectorAll('video').forEach(v=>{try{v.pause();v.removeAttribute('src');}catch(e){}});
    const c=document.createElement('canvas');c.width=240;c.height=320;const x=c.getContext('2d');x.fillStyle='#d8c1b1';x.fillRect(0,0,c.width,c.height);x.fillStyle='#fff';x.fillRect(75,182,90,24);const before=c.toDataURL('image/jpeg',.62);x.fillStyle='#f9f6e9';x.fillRect(80,185,80,19);const after=c.toDataURL('image/jpeg',.60);
    const src={dataUrl:before,category:'facial',label:'Facial',lips:true,intraoral:false,intraoralDark:false};state.photos=[src];state._simSource=src;state.simResults=[{dataUrl:after,source:before,srcObj:src,sourceKind:'Facial',settings:{}}];state.simResultIndex=0;state.simResult=state.simResults[0];
    if(window.cfWait)window.cfWait.show('test',0);const t=performance.now();const ok=window.cfOpenResultScreen();const returned=performance.now()-t;await new Promise(r=>setTimeout(r,120));
    const shell=document.getElementById('cfFastResultShell'),compare=document.getElementById('cfFastCompare'),range=document.getElementById('cfFastRange');range.value='72';range.dispatchEvent(new Event('input',{bubbles:true}));
    return {ok,returned,open:!!shell&&shell.classList.contains('open'),aria:shell&&shell.getAttribute('aria-hidden'),before:(document.getElementById('cfFastBefore')||{}).src?.length||0,after:(document.getElementById('cfFastAfter')||{}).src?.length||0,split:compare&&compare.style.getPropertyValue('--cf-fast-split'),legacyActive:document.getElementById('result').classList.contains('active'),wait:!!document.querySelector('.cfWaitOverlay.show,.cfWaitOverlay.active'),v9:window.__cfFastResultV9===true,opened:Number(window.__cfFastResultOpenedAt||0),painted:Number(window.__cfFastResultPaintedAt||0)};
  });
  console.log(JSON.stringify({result,errors},null,2));
  assert(result.ok,'fast result route returned false');assert(result.returned<300,'fast result route did not return immediately');assert(result.open,'fast result shell did not open');assert.strictEqual(result.aria,'false');assert(result.before>100&&result.after>100,'images were not painted');assert.strictEqual(result.split,'72%');assert.strictEqual(result.legacyActive,false,'heavy legacy result screen activated');assert.strictEqual(result.wait,false,'waiting overlay remained');assert(result.v9,'v9 route marker missing');assert(result.opened>0&&result.painted>0,'timing markers missing');
  const relevant=errors.filter(x=>/SyntaxError|ReferenceError|cfFastResult|fast result/i.test(x));assert.deepStrictEqual(relevant,[],'runtime errors: '+relevant.join('\n'));
  await context.close();await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
