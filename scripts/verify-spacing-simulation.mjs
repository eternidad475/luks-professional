import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

// Executes production functions against synthetic state/pixels; no account, image API,
// patient data, generation tokens, network or extra dependencies.
const html=await readFile(new URL('../caseflow_studio_v96.html',import.meta.url),'utf8');
const script=html.match(/<script id="cf-v96-simulation-studio">([\s\S]*?)<\/script>/)[1];
function region(start,end){const i=script.indexOf(start),j=script.indexOf(end,i+start.length);assert.ok(i>=0&&j>i,start);return script.slice(i,j);}
const source=region('  const CF_ORTHO_KEYS=', '  // Composite ONLY the mouth region')
  +region('  function cfDeriveFindingsView(', '  window.cfDeriveFindingsView')
  +region('  function requestedStrength(){','  // Build a feathered ENAMEL')
  +region('  function cfSpacingMaskPixels(', '  function spacingEnamelMaskCanvas(');
const ctx=vm.createContext({console,state:{},window:{},
  clamp:(v,a,b)=>Math.max(a,Math.min(b,Number(v))),
  smoothstep:(a,b,x)=>{const t=Math.max(0,Math.min(1,(x-a)/(b-a)));return t*t*(3-2*t);},
  pickSource:()=>ctx.state._simSource,
  sourceKind:s=>s.category==='facial'?'Facial':'Focus'
});
vm.runInContext(source,ctx);
let total=0;function test(name,fn){fn();total++;console.log('PASS '+name);}
function setup({order=['space'],selected=true,dark=false,concept='prosthetic',scope='combined',findings=[]}={}){
  ctx.state={simV82:{concept,targets:{space:selected,shade:false},...(order?{targetOrder:order}:{})},
    simV96:{shade:50,toothShape:50,alignment:0,scallop:0,smileFrame:0,bioBlend:50},simCorrectionScope:scope,
    _simSource:{category:'focus',intraoral:true,intraoralDark:dark,lips:false,problemList:findings}};
}
for(const order of [['space'],['shade','space'],null,['space','space','shade']])for(const dark of [false,true]){
  test(`prosthetic closure survives rank/order ${JSON.stringify(order)}, contraster=${dark}`,()=>{
    setup({order,dark});ctx.state.simV82.targets.shade=!!order?.includes('shade');
    const p=ctx.buildClinicalPrompt();
    assert.match(p,/SELECTED SPACING COMPLAINT/);assert.match(p,/Proximal outlines MAY expand/);
    assert.doesNotMatch(p,/EXACT current pixel position|Keep every tooth's own outline, size and position|Return the teeth essentially unchanged|with ONLY the tooth enamel adjusted/);
    assert.doesNotMatch(p,/gently level the incisal edges and upright the tooth axes/);
    assert.match(p,/Do NOT move, tip or rotate teeth/);assert.match(p,/Preserve original crown height/);
    assert.equal(ctx.requestedStrength(),.4);
  });
}
test('stale deselected order does not request spacing or activate neutral result',()=>{setup({selected:false});assert.equal(ctx.cfSpacingRequested(),false);assert.equal(ctx.requestedStrength(),0);assert.doesNotMatch(ctx.buildClinicalPrompt(),/SELECTED SPACING COMPLAINT/);});
test('active tap order deduplicates and appends legacy cards',()=>{setup({order:['shade','space','space','missing']});ctx.state.simV82.targets.shade=true;assert.deepEqual(Array.from(ctx.cfActiveComplaintOrder()),['shade','space']);});
for(const scope of ['shade','gingiva','preserve','alignment'])test(`prosthetic explicit ${scope} scope is respected`,()=>{setup({scope});assert.equal(ctx.cfSpacingRequested(),false);});
test('prosthetic shape scope permits contact restoration',()=>{setup({scope:'shape'});assert.equal(ctx.cfSpacingRequested(),true);});
test('screened spacing does not demand orthodontic movement in prosthetic',()=>{setup({findings:[{en:'spacing / diastema'}]});assert.doesNotMatch(ctx.buildClinicalPrompt(),/these must be expressed as tooth POSITION/);});
for(const concept of ['ortho','hybrid'])test(`${concept} receives concept-appropriate closure`,()=>{setup({concept});const p=ctx.buildClinicalPrompt();assert.match(p,/SELECTED SPACING COMPLAINT/);assert.match(p,/orthodontic alignment/);});
test('facial route retains facial identity constraints',()=>{setup();ctx.state._simSource={category:'facial',intraoral:false};const p=ctx.buildClinicalPrompt();assert.match(p,/SELECTED SPACING COMPLAINT/);assert.match(p,/IDENTITY/);});
const W=240,H=160, gum=[165,50,60,255],tooth=[219,204,175,255],dark=[22,20,20,255],blue=[160,180,210,255];
function fill(d,x0,y0,x1,y1,c){for(let y=y0;y<y1;y++)for(let x=x0;x<x1;x++)d.set(c,(y*W+x)*4);}
function pixels(){const d=new Uint8ClampedArray(W*H*4);fill(d,0,0,W,H,gum);fill(d,0,120,W,H,dark);return d;}
function fixture(gap=8,center=120){const o=pixels();fill(o,center-45,40,center-gap/2,105,tooth);fill(o,center+gap/2,40,center+45,105,tooth);fill(o,center-gap/2,40,center+gap/2,105,dark);const a=new Uint8ClampedArray(o);fill(a,center-gap/2,40,center+gap/2,105,tooth);return {o,a};}
const mask=(o,a)=>ctx.cfSpacingMaskPixels(o,a,W,H),alpha=(m,x,y)=>m[(y*W+x)*4+3];
test('model-produced narrow coronal closure is fully admitted',()=>{const {o,a}=fixture(),m=mask(o,a);assert.equal(alpha(m,120,65),255);assert.equal(alpha(m,118,90),255);});
test('off-center narrow closure is admitted without recentering anatomy',()=>{const {o,a}=fixture(8,85),m=mask(o,a);assert.equal(alpha(m,85,65),255);assert.equal(alpha(m,180,65),0);});
test('unchanged generated gap is not locally painted or warped closed',()=>{const {o}=fixture(),m=mask(o,o);assert.equal(alpha(m,120,65),0);});
test('red gingiva is locked even when AI paints it white',()=>{const {o,a}=fixture();fill(a,60,15,180,35,tooth);const m=mask(o,a);assert.equal(alpha(m,120,25),0);});
test('black contraster below original incisal boundary is locked',()=>{const {o,a}=fixture();fill(a,75,105,165,150,tooth);const m=mask(o,a);assert.equal(alpha(m,120,115),0);assert.equal(alpha(m,120,130),0);});
test('broad missing-tooth span is locked',()=>{const {o,a}=fixture(36),m=mask(o,a);assert.equal(alpha(m,120,65),0);});
test('single-row dark shadow cannot become a closure corridor',()=>{const {o,a}=fixture();fill(o,116,40,124,105,tooth);fill(o,116,70,124,71,dark);assert.equal(alpha(mask(o,a),120,70),0);});
test('triangular gingival embrasure is not a coronal gap',()=>{const {o,a}=fixture();fill(o,116,40,124,105,tooth);for(let y=40;y<65;y++){const half=Math.max(1,Math.ceil((65-y)/5));fill(o,120-half,y,120+half,y+1,dark);}assert.equal(alpha(mask(o,a),120,45),0);});
test('blue/silver retractor does not become an enamel anchor',()=>{const {o,a}=fixture();fill(o,20,20,40,100,blue);fill(a,20,20,40,100,tooth);assert.equal(alpha(mask(o,a),30,60),0);});
test('horizontal bite opening is not filled',()=>{const {o,a}=fixture();fill(o,70,85,170,95,dark);fill(a,70,85,170,95,tooth);assert.equal(alpha(mask(o,a),120,90),0);});
test('every excluded pixel retains original channels under alpha compositing',()=>{const {o,a}=fixture();fill(a,0,0,W,30,tooth);const m=mask(o,a);let protectedCount=0;for(let p=0;p<W*H;p++){const i=p*4,al=m[i+3]/255;if(!al){protectedCount++;for(let k=0;k<3;k++)assert.equal(Math.round(a[i+k]*al+o[i+k]*(1-al)),o[i+k]);}}assert.ok(protectedCount>W*H*.7);});
test('actual finalizer uses scoped mask only for intraoral prosthetic selected-space',()=>{assert.match(script,/opts && opts.intraoral[\s\S]{0,200}cfSpacingRequested\(\) && \(state.simV82\|\|\{\}\).concept==='prosthetic'[\s\S]{0,100}spacingEnamelMaskCanvas/);});
test('selected intraoral spacing cannot silently return cosmetic fallback after AI error',()=>{const p=region('  async function produceImage(src){','  window.caseflowProduceSimImage');assert.match(p,/cfSpacingUnavailable=true; throw err/);assert.ok(p.indexOf('throw err')<p.indexOf('return await createSimulationImageV96'));});
test('scoped finalization errors cannot expose raw unprotected output',()=>{assert.match(script,/if\(source && source.intraoral && cfSpacingRequested\(\)\) throw e;/);});
test('neutral silver and pale pink cannot be repainted as enamel',()=>{for(const color of [[180,180,180,255],[220,190,185,255],[210,180,180,255]]){const {o,a}=fixture();fill(o,20,20,40,100,color);fill(a,20,20,40,100,tooth);assert.equal(alpha(mask(o,a),30,60),0);}});
test('actual screening view cannot negate selected gap with crowding-only classification',()=>{setup({findings:[{en:'crowding / rotation',ja:'叢生'}]});const p=ctx.buildClinicalPrompt();assert.doesNotMatch(p,/NO clearly open interdental space is present/);assert.match(p,/Screening did not confirm a gap/);});
test('actual screening view does not force spacing closure in shade-only scope',()=>{setup({scope:'shade',findings:[{en:'spacing / diastema',ja:'歯間離開'}]});assert.doesNotMatch(ctx.buildClinicalPrompt(),/MUST be COMPLETELY CLOSED|SELECTED SPACING COMPLAINT/);});
test('contraster orthodontic space does not become a restorative crown-width request',()=>{setup({concept:'ortho',dark:true});const p=ctx.buildClinicalPrompt();assert.doesNotMatch(p,/proximal crown contours may extend HORIZONTALLY|do not.*move tooth axes/);assert.match(p,/horizontal tooth alignment is allowed/);});
console.log(`${total} spacing simulation checks passed (synthetic only)`);
