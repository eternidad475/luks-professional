const fs=require('fs');
const path='caseflow_studio_v96.html';
let s=fs.readFileSync(path,'utf8');
const start=s.indexOf('<script id="cf-result-route-guard-v6">');
if(start<0)throw new Error('v6 result route guard not found');
const end=s.indexOf('</script>',start);
if(end<0)throw new Error('v6 result route guard end not found');
const block=`<script id="cf-result-route-guard-v8">
(function(){
  var rawGo=window.go;
  var paintSeq=0;
  function record(){
    var arr=Array.isArray(window.state&&state.simResults)?state.simResults:[];
    return (window.state&&state.simResult)||arr[(window.state&&state.simResultIndex)||0]||null;
  }
  function sourceFor(r){
    return (window.state&&state._simSource)||(r&&r.srcObj)||((window.state&&Array.isArray(state.photos))?state.photos[0]:null);
  }
  function hideWait(){
    try{document.querySelectorAll('.cfWaitOverlay.show').forEach(function(el){el.classList.remove('show');el.setAttribute('aria-hidden','true');});}catch(e){}
  }
  function openResult(){
    var r=record(),src=sourceFor(r);
    if(!r||!src){return typeof rawGo==='function'?rawGo.apply(this,arguments):false;}
    var seq=++paintSeq;
    var result=document.getElementById('result');
    document.querySelectorAll('.screen.active').forEach(function(el){if(el!==result)el.classList.remove('active');});
    if(result)result.classList.add('active');
    hideWait();
    window.__cfResultFirstPaintAt=performance.now();
    window.__cfEditHydrationScheduled=seq;
    setTimeout(function(){
      if(seq!==paintSeq)return;
      try{
        var before=document.getElementById('resultBefore');
        var after=document.getElementById('resultAfter');
        var beforeSrc=r.source||(r.srcObj&&r.srcObj.dataUrl)||src.dataUrl;
        if(before){before.decoding='async';before.setAttribute('src',beforeSrc);}
        if(after){after.decoding='async';after.setAttribute('src',r.dataUrl);}
      }catch(e){console.error('[CaseFlow result image paint v8]',e);}
    },0);
    setTimeout(function(){try{var el=document.getElementById('simulationCompareSlider');if(el&&typeof window.setupCompareSlider==='function')window.setupCompareSlider(el);}catch(e){console.warn('[CaseFlow compare hydrate v8]',e);}},900);
    setTimeout(function(){try{if(typeof window.buildEditGrid==='function')window.buildEditGrid();}catch(e){console.warn('[CaseFlow edit hydrate v8]',e);}},1200);
    setTimeout(function(){try{if(typeof window.renderSimGallery==='function')window.renderSimGallery();}catch(e){console.warn('[CaseFlow gallery hydrate v8]',e);}},1500);
    setTimeout(function(){try{if(window.cfWait)window.cfWait.hideAll();}catch(e){}try{if(typeof window.pausePreview==='function')window.pausePreview();}catch(e){}},1700);
    return true;
  }
  function guarded(id){if(id==='result')return openResult();return typeof rawGo==='function'?rawGo.apply(this,arguments):false;}
  guarded.__cfResultGuardV8=true;
  guarded.__cfResultGuardV6=true;
  guarded.__cfRaw=rawGo;
  window.cfOpenResultScreen=openResult;
  window.cfPaintPrimaryResult=openResult;
  window.go=guarded;
})();
</script>`;
s=s.slice(0,start)+block+s.slice(end+'</script>'.length);
s=s.replace(/try\{cfPaintPrimaryResult\(\);\}/g,'try{window.cfOpenResultScreen();}');
s=s.replace(/\n\s*cfPaintPrimaryResult\(\);\n\s*cfScheduleTempSimSave/g,'\n      window.cfOpenResultScreen();\n      cfScheduleTempSimSave');
fs.writeFileSync(path,s);
console.log('installed final result route v8');
