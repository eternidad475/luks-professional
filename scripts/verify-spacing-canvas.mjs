import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const browserModule=await import(process.env.CF_PLAYWRIGHT_MODULE||'playwright');
const {chromium}=browserModule.default||browserModule;
const html=await readFile(new URL('../caseflow_studio_v96.html',import.meta.url),'utf8');
const script=html.match(/<script id="cf-v96-simulation-studio">([\s\S]*?)<\/script>/)[1];
function region(start,end){const i=script.indexOf(start),j=script.indexOf(end,i+start.length);assert.ok(i>=0&&j>i,start);return script.slice(i,j);}
const browser=await chromium.launch({executablePath:process.env.CF_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
try{
  const page=await browser.newPage();let network=0;await page.route('**/*',route=>{network++;route.abort();});
  await page.setContent('<html><body><h1>Caseflow synthetic canvas regression</h1><div id="fixtures"></div></body></html>');
  await page.addScriptTag({content:`
    const state=window.state={simV82:{concept:'prosthetic',targets:{space:true},targetOrder:['space']},simV96:{shade:50,toothShape:50,alignment:0,scallop:0,smileFrame:0,bioBlend:50}};
    const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)));
    function smoothstep(a,b,x){const t=clamp((x-a)/(b-a),0,1);return t*t*(3-2*t);}
    function pickSource(){return state._simSource;}
    function sourceKind(){return 'Focus';}
    function drawBadge(){} // disable only annotation for exact protected-pixel checks
    function cfSimROIConfig(){return {};}
    function aiEndpoint(){return 'https://synthetic.invalid';}
    function toastFn(){}
    ${region('  function loadImage(src){','  function rr(')}
    ${region('  const CF_ORTHO_KEYS=','  // Composite ONLY the mouth region')}
    ${region('  function toneMatchToOriginal(','  // ===== Automated pre-generation PROBLEM LIST')}
    ${region('  function applyIntraoralBioBlend(', '  // ── Sim Studio landmark-aware')}
    ${region('  async function finalizeAIImage(','  // Transient backend/upstream')}
    ${region('  function buildSimulationPayload(','  // AI is used whenever')}
    window.tests={finalizeAIImage,spacingEnamelMaskCanvas,generateViaAI,buildSimulationPayload};
  `});
  const results=await page.evaluate(async()=>{
    const W=480,H=320;
    function fixture(closed=false){const c=document.createElement('canvas');c.width=W;c.height=H;const x=c.getContext('2d');const bg=x.createImageData(W,H);for(let i=0;i<W*H;i++){const k=i*4;bg.data[k]=148+(i*17%35);bg.data[k+1]=39+(i*13%23);bg.data[k+2]=53+(i*7%15);bg.data[k+3]=255;}x.putImageData(bg,0,0);x.fillStyle='rgb(22,20,20)';x.fillRect(0,240,W,80);x.fillStyle='rgb(219,204,175)';x.fillRect(150,80,82,130);x.fillRect(248,80,82,130);x.fillStyle=closed?'rgb(219,204,175)':'rgb(22,20,20)';x.fillRect(232,80,16,130);return c;}
    const before=fixture(),after=fixture(true), ax=after.getContext('2d');ax.fillStyle='#fff';ax.fillRect(150,220,180,60);ax.fillRect(150,20,180,40);
    const afterHigh=document.createElement('canvas');afterHigh.width=W*2;afterHigh.height=H*2;const hx=afterHigh.getContext('2d');hx.imageSmoothingEnabled=false;hx.drawImage(after,0,0,W*2,H*2);
    const src={category:'focus',intraoral:true,intraoralDark:false,lips:false,dataUrl:before.toDataURL(),problemList:[]};state._simSource=src;
    let requests=0,consumed=0,refunded=0,captured=null;
    window.cfConsumeToken=async()=>{consumed++;return {ok:true,ledgerId:'synthetic-ledger'};};
    window.cfRefundGeneration=()=>{refunded++;};
    window.fetchSimWithRetry=async(_ep,body)=>{requests++;captured=JSON.parse(body);return {json:async()=>({image:afterHigh.toDataURL()})};};
    // Capture the exact canvas before JPEG; production encode is exercised as well.
    let raw,maskPixels,sourcePixels;const originalSpacingMask=spacingEnamelMaskCanvas;window.spacingEnamelMaskCanvas=function(ox,aix,w,h){const m=originalSpacingMask(ox,aix,w,h);maskPixels=m.getContext('2d').getImageData(0,0,w,h).data;sourcePixels=ox.getImageData(0,0,w,h).data;return m;};const originalToDataURL=HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL=function(type,...args){if(type==='image/jpeg')raw=new Uint8ClampedArray(this.getContext('2d').getImageData(0,0,W,H).data);return originalToDataURL.call(this,type,...args);};
    state.simV96.bioBlend=85; // exercise real non-neutral finish BEFORE protected alpha
    const output=await tests.generateViaAI(src);
    const pix=(x,y)=>Array.from(raw.slice((y*W+x)*4,(y*W+x)*4+3));
    const values={gap:pix(240,130),gum:pix(240,30),beyondIncisal:pix(240,225),background:pix(240,265),requests,consumed,refunded,prompt:captured.prompt,outputType:output.slice(0,23)};
    const originalPix=(x,y)=>Array.from(sourcePixels.slice((y*W+x)*4,(y*W+x)*4+3));values.gumOriginal=originalPix(240,30);values.incisalOriginal=originalPix(240,225);values.excludedPixels=0;values.changedExcludedPixels=0;for(let i=0;i<raw.length;i+=4){if(maskPixels[i+3]===0){values.excludedPixels++;if(raw[i]!==sourcePixels[i]||raw[i+1]!==sourcePixels[i+1]||raw[i+2]!==sourcePixels[i+2])values.changedExcludedPixels++;}}
    for(const [name,c]of [['Before (synthetic)',before],['Mock AI (synthetic)',after]]){const label=document.createElement('p');label.textContent=name;document.getElementById('fixtures').append(label,c);}
    const img=new Image();img.src=output;const label=document.createElement('p');label.textContent='Final protected composite (synthetic)';document.getElementById('fixtures').append(label,img);
    // Error/refund path does not expose raw generated output.
    const realFinalize=finalizeAIImage;window.finalizeAIImage=async()=>{throw new Error('synthetic composite failure');};
    let failed=false;try{await tests.generateViaAI(src);}catch(e){failed=true;}
    window.finalizeAIImage=realFinalize;values.failedClosed=failed;values.refundedAfterFailure=refunded;
    delete window.cfConsumeToken;let denied=false;try{await tests.generateViaAI(src);}catch(e){denied=!!e.cfNoTokens;}
    values.authStillRequired=denied;values.requestsAfterAuthDenial=requests;
    return values;
  });
  assert.ok(results.gap[0]>150,JSON.stringify(results));
  assert.deepEqual(results.gum,results.gumOriginal);assert.deepEqual(results.beyondIncisal,results.incisalOriginal);assert.ok(results.excludedPixels>480*320*.7);assert.equal(results.changedExcludedPixels,0,'all excluded noisy-tissue pixels must remain exact before JPEG');assert.deepEqual(results.background,[22,20,20]);
  assert.equal(results.requests,1);assert.equal(results.consumed,1);assert.equal(results.refunded,0);
  assert.match(results.prompt,/SELECTED SPACING COMPLAINT/);assert.equal(results.outputType,'data:image/jpeg;base64,');
  assert.equal(results.failedClosed,true);assert.equal(results.refundedAfterFailure,1);assert.equal(results.authStillRequired,true);assert.equal(results.requestsAfterAuthDenial,2);assert.equal(network,0);
  if(process.env.CF_CANVAS_SCREENSHOT)await page.screenshot({path:process.env.CF_CANVAS_SCREENSHOT,fullPage:true});
  console.log('PASS actual Chromium Canvas destination-in retains closure and exact protected pixels');
  console.log('PASS actual generateViaAI payload, response finalization, token gate, refund and failure paths');
  console.log('PASS 2x-resolution AI output is downsampled before protected composition');
  console.log('PASS all excluded noisy-tissue pixels remain identical before JPEG');
  console.log('PASS zero external network calls; synthetic images only');
}finally{await browser.close();}
