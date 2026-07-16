const fs=require('fs');
const path='caseflow_studio_v96.html';
let s=fs.readFileSync(path,'utf8');
if(s.includes('cf-fast-result-shell-v9')){console.log('fast result shell already installed');process.exit(0);}
const block=String.raw`
<style id="cf-fast-result-shell-v9-style">
.cfFastResultShell{position:absolute;inset:0;z-index:8200;display:none;overflow:auto;-webkit-overflow-scrolling:touch;padding:calc(14px + env(safe-area-inset-top)) 16px calc(28px + env(safe-area-inset-bottom));color:var(--ink,#201b35);background:linear-gradient(145deg,color-mix(in srgb,var(--c1) 22%,#fbf8ff),color-mix(in srgb,var(--c2) 18%,#fbf8ff));contain:layout paint style}
.cfFastResultShell.open{display:block}
.cfFastResultTop{display:flex;align-items:center;gap:12px;min-height:44px;margin-bottom:12px}
.cfFastResultTop button{width:42px;height:42px;border:1px solid rgba(255,255,255,.8);border-radius:999px;background:rgba(255,255,255,.88);color:var(--ink,#201b35);font-size:24px;box-shadow:0 8px 24px rgba(32,27,53,.10)}
.cfFastResultHead{flex:1;min-width:0}.cfFastResultHead b{display:block;font-size:18px;letter-spacing:-.03em}.cfFastResultHead span{display:block;margin-top:3px;font:700 9px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.06em;text-transform:uppercase;opacity:.58}
.cfFastResultCard{padding:10px;border:1px solid rgba(255,255,255,.82);border-radius:24px;background:rgba(255,255,255,.76);box-shadow:0 18px 48px rgba(32,27,53,.14)}
.cfFastCompare{position:relative;width:100%;height:min(62dvh,620px);min-height:320px;overflow:hidden;border-radius:18px;background:#111;touch-action:none;--cf-fast-split:50%}
.cfFastCompare img{position:absolute;inset:0;width:100%;height:100%;display:block;object-fit:contain;background:#111}
.cfFastCompare .cfFastAfter{clip-path:inset(0 calc(100% - var(--cf-fast-split)) 0 0)}
.cfFastDivider{position:absolute;top:0;bottom:0;left:var(--cf-fast-split);width:2px;transform:translateX(-1px);background:rgba(255,255,255,.92);box-shadow:0 0 18px rgba(255,255,255,.72);pointer-events:none}
.cfFastDivider:after{content:'↔';position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);display:grid;place-items:center;width:38px;height:38px;border-radius:50%;background:rgba(255,255,255,.94);color:#201b35;font-size:16px;box-shadow:0 8px 24px rgba(0,0,0,.24)}
.cfFastLabels{position:absolute;inset:12px 12px auto;display:flex;justify-content:space-between;pointer-events:none}.cfFastLabels span{padding:5px 8px;border-radius:999px;background:rgba(0,0,0,.42);color:#fff;font:800 9px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.06em}
.cfFastRange{width:100%;height:36px;margin:8px 0 0;accent-color:var(--c1,#7c5cff)}
.cfFastMeta{margin:8px 4px 2px;font:700 9px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.035em;opacity:.62}
.cfFastActions{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}.cfFastActions button{min-height:50px;border:1px solid rgba(255,255,255,.82);border-radius:16px;padding:8px;background:rgba(255,255,255,.82);color:var(--ink,#201b35);font-size:12px;font-weight:850;box-shadow:0 8px 22px rgba(32,27,53,.08)}
.cfFastActions .cfFastPrimary{grid-column:1/-1;background:linear-gradient(135deg,var(--c1,#7c5cff),var(--c2,#ff9fd6));color:#fff;border-color:transparent}
.cfFastActions button:disabled{display:none}
.cfFastDisclaimer{margin:12px 5px 0;font-size:10px;line-height:1.55;font-weight:650;opacity:.58}
@media(min-width:700px){.cfFastResultShell{left:50%;right:auto;width:min(720px,100vw);transform:translateX(-50%)}.cfFastCompare{height:min(68dvh,680px)}}
@media(prefers-reduced-motion:reduce){.cfFastResultShell *{scroll-behavior:auto!important;transition:none!important}}
</style>
<script id="cf-fast-result-shell-v9">
(function(){
  var rawGo=window.go, shell=null, seq=0;
  function record(){var arr=Array.isArray(window.state&&state.simResults)?state.simResults:[];return (window.state&&state.simResult)||arr[(window.state&&state.simResultIndex)||0]||null;}
  function sourceFor(r){return (window.state&&state._simSource)||(r&&r.srcObj)||((window.state&&Array.isArray(state.photos))?state.photos[0]:null);}
  function hideWait(){try{if(window.cfWait)window.cfWait.hideAll();}catch(e){}try{document.querySelectorAll('.cfWaitOverlay.show,.cfWaitOverlay.active').forEach(function(el){el.classList.remove('show','active');el.setAttribute('aria-hidden','true');});}catch(e){}}
  function ensure(){
    if(shell&&shell.isConnected)return shell;
    shell=document.createElement('section');shell.id='cfFastResultShell';shell.className='cfFastResultShell';shell.setAttribute('aria-hidden','true');
    shell.innerHTML='<div class="cfFastResultTop"><button type="button" data-cf-fast="back" aria-label="Back">‹</button><div class="cfFastResultHead"><b>Simulation Result</b><span>Primary visual result / 一次生成結果</span></div></div><div class="cfFastResultCard"><div class="cfFastCompare" id="cfFastCompare"><img class="cfFastBefore" id="cfFastBefore" alt="Before"><img class="cfFastAfter" id="cfFastAfter" alt="After"><div class="cfFastDivider"></div><div class="cfFastLabels"><span>Before</span><span>After</span></div></div><input class="cfFastRange" id="cfFastRange" type="range" min="0" max="100" value="50" aria-label="Before and after comparison"><p class="cfFastMeta" id="cfFastMeta">Reference image / 治療結果を保証するものではありません。</p></div><div class="cfFastActions"><button type="button" class="cfFastPrimary" data-cf-fast="smile">Smile Designer / 歯冠形態</button><button type="button" data-cf-fast="again">Regenerate / 再生成</button><button type="button" data-cf-fast="refine">Refine / 精密生成</button><button type="button" data-cf-fast="library">Library</button><button type="button" data-cf-fast="advanced">Advanced controls / 詳細調整</button></div><p class="cfFastDisclaimer">Clinical visualization support only. This image is not a diagnosis or a guarantee of treatment outcome.</p>';
    var app=document.querySelector('.app')||document.body;app.appendChild(shell);
    var range=shell.querySelector('#cfFastRange'),compare=shell.querySelector('#cfFastCompare');
    range.addEventListener('input',function(){compare.style.setProperty('--cf-fast-split',range.value+'%');});
    shell.addEventListener('click',function(e){var btn=e.target.closest('[data-cf-fast]');if(!btn)return;var action=btn.getAttribute('data-cf-fast');
      if(action==='back'){close();if(typeof rawGo==='function')rawGo('simulator');}
      else if(action==='again'){close();if(typeof window.generateSimulation==='function')window.generateSimulation();}
      else if(action==='smile'){if(typeof window.cfOpenSmileDesigner==='function')window.cfOpenSmileDesigner();}
      else if(action==='refine'){if(typeof window.runSecondaryRefinement==='function')window.runSecondaryRefinement();}
      else if(action==='library'){close();if(typeof rawGo==='function')rawGo('library');}
      else if(action==='advanced'){openLegacy();}
    });
    return shell;
  }
  function close(){if(!shell)return;shell.classList.remove('open');shell.setAttribute('aria-hidden','true');}
  function openLegacy(){close();setTimeout(function(){try{document.querySelectorAll('.screen.active').forEach(function(el){el.classList.remove('active');});var r=document.getElementById('result');if(r)r.classList.add('active');if(typeof window.renderResultImages==='function')window.renderResultImages();}catch(e){console.error('[CaseFlow advanced result]',e);}},0);}
  function paint(){
    var r=record(),src=sourceFor(r);if(!r||!src)return typeof rawGo==='function'?rawGo('simulator'):false;
    var token=++seq,el=ensure();hideWait();el.classList.add('open');el.setAttribute('aria-hidden','false');window.__cfFastResultOpenedAt=performance.now();
    var refine=el.querySelector('[data-cf-fast="refine"]');if(refine)refine.disabled=typeof window.runSecondaryRefinement!=='function';
    setTimeout(function(){if(token!==seq)return;try{var before=el.querySelector('#cfFastBefore'),after=el.querySelector('#cfFastAfter');var beforeSrc=r.source||(r.srcObj&&r.srcObj.dataUrl)||src.dataUrl;before.decoding='async';after.decoding='async';before.src=beforeSrc;after.src=r.dataUrl;var meta=el.querySelector('#cfFastMeta');var kind=(r.sourceKind||src.label||src.category||(src.intraoral?'Intraoral':'Facial'));if(meta)meta.textContent=kind+' image / Reference Image — 説明用の参考イメージであり、治療結果の保証ではありません。';window.__cfFastResultPaintedAt=performance.now();hideWait();}catch(e){console.error('[CaseFlow fast result paint]',e);}},0);
    setTimeout(function(){hideWait();try{if(typeof window.pausePreview==='function')window.pausePreview();}catch(e){}},180);
    return true;
  }
  function guarded(id){if(id==='result')return paint();if(id!=='result')close();return typeof rawGo==='function'?rawGo.apply(this,arguments):false;}
  guarded.__cfFastResultV9=true;guarded.__cfRaw=rawGo;window.__cfFastResultV9=true;
  window.cfCloseFastResult=close;window.cfOpenLegacyResultV9=openLegacy;window.cfOpenResultScreen=paint;window.cfPaintPrimaryResult=paint;window.go=guarded;
})();
</script>`;
s=s.replace('</body>',block+'\n</body>');
fs.writeFileSync(path,s);
if(fs.existsSync('sw.js')){let x=fs.readFileSync('sw.js','utf8');x=x.replace(/var VERSION = '[^']+';/,"var VERSION = 'cfsw-v7-fast-result-shell';");fs.writeFileSync('sw.js',x);}
console.log('installed fast result shell v9',s.length);
