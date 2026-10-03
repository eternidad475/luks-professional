import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
// All fixtures below are mathematically constructed colours/rectangles. They contain
// no patient image, pixel samples, photo coordinates, image IDs or remote requests.
const path=process.argv[2] || new URL('../caseflow_studio_v96.html',import.meta.url);
const html=await readFile(path,'utf8');
const start=html.indexOf('  function cfSpacingMaskPixels('),end=html.indexOf('  function spacingEnamelMaskCanvas(',start);
assert.ok(start>=0&&end>start);
const ctx=vm.createContext({clamp:(v,a,b)=>Math.max(a,Math.min(b,v)),smoothstep:(a,b,v)=>{const t=Math.max(0,Math.min(1,(v-a)/(b-a)));return t*t*(3-2*t);}});
vm.runInContext(html.slice(start,end),ctx);
let total=0;function test(name,fn){fn();total++;console.log('PASS '+name);}
const gum=[175,65,85,255],tooth=[224,211,180,255],shade=[170,135,90,255],shadow=[49,17,15,255],metal=[155,165,179,255],neutral=[176,170,166,255];
function make(scale=1,offset=0){
  const w=320*scale,h=220*scale,d=new Uint8ClampedArray(w*h*4);
  const fill=(a,x0,y0,x1,y1,c)=>{for(let y=y0*scale;y<y1*scale;y++)for(let x=x0*scale;x<x1*scale;x++)a.set(c,(y*w+x)*4);};
  fill(d,0,0,320,220,gum);fill(d,0,145,320,175,[15,12,12,255]);
  const cx=140+offset;fill(d,cx-60,50,cx-6,130,tooth);fill(d,cx+6,50,cx+60,130,tooth);
  fill(d,cx-6,50,cx+6,130,shade);fill(d,cx-3,50,cx+3,130,shadow);
  const a=new Uint8ClampedArray(d);fill(a,cx-6,50,cx+6,130,shade);
  const mask=(o=d,g=a)=>ctx.cfSpacingMaskPixels(o,g,w,h),alpha=(m,x,y)=>m[((y*scale)*w+x*scale)*4+3];
  return {w,h,scale,cx,o:d,a,fill,mask,alpha};
}
for(const scale of [1,2,3])for(const offset of [0,45])test(`warm shoulders and red-reflected dark core restore at scale ${scale}, translation ${offset}`,()=>{const f=make(scale,offset),m=f.mask();assert.equal(f.alpha(m,f.cx,80),255);assert.equal(f.alpha(m,f.cx-5,80),255);assert.equal(f.alpha(m,f.cx+5,100),255);});
test('geometry tolerates small neutral texture interruptions inside enamel anchors',()=>{const f=make();f.fill(f.o,f.cx-12,60,f.cx-10,120,neutral);const m=f.mask();assert.equal(f.alpha(m,f.cx,85),255);});
test('mildly varying dark core does not require a rectangular opening',()=>{const f=make();f.fill(f.o,f.cx-6,50,f.cx+6,130,shade);for(let y=50;y<130;y++){const half=2+Math.floor((y-50)/27);f.fill(f.o,f.cx-half,y,f.cx+half,y+1,shadow);}assert.equal(f.alpha(f.mask(),f.cx,85),255);});
test('unchanged warm shoulders do not fake restoration of an unchanged dark core',()=>{const f=make();assert.equal(f.alpha(f.mask(f.o,f.o),f.cx,85),0);});
test('minor model change below 70 percent of original dark core is rejected',()=>{const f=make();const a=new Uint8ClampedArray(f.o);f.fill(a,f.cx-3,65,f.cx+3,90,shade);assert.equal(f.alpha(f.mask(f.o,a),f.cx,75),0);});
test('the model must supply enamel rather than a red or blue replacement',()=>{for(const c of [gum,metal,[200,100,125,255]]){const f=make();f.fill(f.a,f.cx-6,50,f.cx+6,130,c);assert.equal(f.alpha(f.mask(),f.cx,85),0);}});
test('a pink gingival shoulder blocks the corridor despite model whitening',()=>{const f=make();f.fill(f.o,f.cx-6,50,f.cx-3,130,gum);assert.equal(f.alpha(f.mask(),f.cx,85),0);});
test('a pale-pink papilla is not admitted as shadowed enamel',()=>{const f=make();f.fill(f.o,f.cx-6,50,f.cx-3,130,[222,181,178,255]);assert.equal(f.alpha(f.mask(),f.cx,85),0);});
test('wide low-value missing-tooth span cannot create a tooth',()=>{const f=make();f.fill(f.o,f.cx-18,50,f.cx+18,130,shadow);f.fill(f.a,f.cx-18,50,f.cx+18,130,tooth);assert.equal(f.alpha(f.mask(),f.cx,85),0);});
test('a short dark pit cannot become a new tooth contact',()=>{const f=make();f.fill(f.o,f.cx-6,50,f.cx+6,130,tooth);f.fill(f.o,f.cx-3,85,f.cx+3,88,shadow);assert.equal(f.alpha(f.mask(),f.cx,86),0);});
test('long triangular gingival embrasure remains protected',()=>{const f=make();f.fill(f.o,f.cx-6,50,f.cx+6,130,tooth);for(let y=50;y<100;y++){const half=Math.max(1,Math.ceil((100-y)/9));f.fill(f.o,f.cx-half,y,f.cx+half,y+1,shadow);}assert.equal(f.alpha(f.mask(),f.cx,60),0);});
test('incisal background extension has no same-row original anchors',()=>{const f=make();f.fill(f.a,f.cx-60,130,f.cx+60,170,tooth);assert.equal(f.alpha(f.mask(),f.cx,140),0);assert.equal(f.alpha(f.mask(),f.cx,160),0);});
test('a horizontal bite opening remains protected even with enamel on both arches',()=>{const f=make();f.fill(f.o,f.cx-60,90,f.cx+60,105,shadow);f.fill(f.a,f.cx-60,90,f.cx+60,105,tooth);assert.equal(f.alpha(f.mask(),f.cx,95),0);});
test('a single-sided tooth never supplies two anchors',()=>{const f=make();f.fill(f.o,f.cx+6,50,f.cx+60,130,gum);assert.equal(f.alpha(f.mask(),f.cx,85),0);});
test('metal retractors cannot supply the missing second enamel anchor',()=>{const f=make();f.fill(f.o,f.cx+6,50,f.cx+60,130,metal);assert.equal(f.alpha(f.mask(),f.cx,85),0);});
test('new dark seam across an original crown is not composited',()=>{const f=make();f.fill(f.a,f.cx-50,80,f.cx-10,83,shadow);assert.equal(f.alpha(f.mask(),f.cx-30,81),0);});
test('model cannot duplicate an incisal edge by splitting original enamel',()=>{const f=make();f.fill(f.a,f.cx-60,112,f.cx-6,116,[20,18,18,255]);assert.equal(f.alpha(f.mask(),f.cx-30,114),0);});
test('whole-mouth model repaint cannot alter gum, lips, retractor or external background',()=>{const f=make();f.fill(f.o,15,30,30,165,metal);f.fill(f.a,0,0,320,220,tooth);const m=f.mask();for(const [x,y] of [[140,25],[140,190],[20,80],[280,160]])assert.equal(f.alpha(m,x,y),0);});
test('direct alpha composite reproduces model pixels only where permitted and locks every excluded pixel',()=>{const f=make(),m=f.mask();let excluded=0,restored=0;for(let at=0;at<f.w*f.h;at++){const i=at*4,a=m[i+3]/255;for(let k=0;k<3;k++){const out=Math.round(f.a[i+k]*a+f.o[i+k]*(1-a));if(a===0){assert.equal(out,f.o[i+k]);excluded++;}if(a===1){assert.equal(out,f.a[i+k]);restored++;}}}assert.ok(excluded>f.w*f.h);assert.ok(restored>0);});
test('mask evaluation never mutates source or model buffers',()=>{const f=make(),o=new Uint8ClampedArray(f.o),a=new Uint8ClampedArray(f.a);f.mask();assert.deepEqual(f.o,o);assert.deepEqual(f.a,a);});
test('all inline classic scripts parse after isolated mask replacement',()=>{let count=0;for(const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)){const type=m[1].match(/\btype\s*=\s*["']([^"']+)["']/i)?.[1];if(type&&!/^(text|application)\/(java|ecma)script$/.test(type))continue;if(!m[2].trim())continue;new vm.Script(m[2]);count++;}assert.ok(count>=80);});
for(const scale of [1,2,3])for(const inverted of [false,true])for(const color of [[22,20,20,255],[105,50,45,255]])test(`cervical tapered notch stays protected at scale ${scale}, inverted ${inverted}, red ${color[0]>100}`,()=>{
  const f=make(scale),left=f.cx-45,right=f.cx+45;f.fill(f.o,0,0,320,220,gum);f.fill(f.o,left,40,right,105,tooth);f.a.set(f.o);
  for(let y=40;y<75;y++){const half=Math.max(2,Math.ceil(5-(y-40)*3/35)),yy=inverted?144-y:y;f.fill(f.o,f.cx-half,yy,f.cx+half,yy+1,color);}
  const m=f.mask();for(let y=40;y<75;y++){const yy=inverted?144-y:y;assert.equal(f.alpha(m,f.cx,yy),0);}
});
for(const scale of [1,2,3])for(const inverted of [false,true])test(`short dark red cervical notch stays protected at scale ${scale}, inverted ${inverted}`,()=>{
  const f=make(scale);f.fill(f.o,0,0,320,220,gum);f.fill(f.o,f.cx-45,40,f.cx+45,105,tooth);f.a.set(f.o);f.fill(f.o,f.cx-4,inverted?87:40,f.cx+4,inverted?105:58,[105,50,45,255]);const m=f.mask();assert.equal(f.alpha(m,f.cx,inverted?96:49),0);
});

for(const scale of [1,2,3])for(const inverted of [false,true])test(`full coronal gap survives apposed opposing-arch enamel at scale ${scale}, inverted ${inverted}`,()=>{
  const f=make(scale);f.fill(f.o,0,0,320,220,gum);f.fill(f.o,f.cx-45,40,f.cx+45,145,tooth);
  f.fill(f.o,f.cx-4,inverted?80:40,f.cx+4,inverted?145:105,shadow);f.a.set(f.o);
  f.fill(f.a,f.cx-4,inverted?80:40,f.cx+4,inverted?145:105,shade);
  assert.equal(f.alpha(f.mask(),f.cx,inverted?115:75),255);
});
console.log(`${total} spacing-mask repair checks passed (fully synthetic, no network)`);
