const fs=require('fs');
const path='caseflow_studio_v96.html';
let s=fs.readFileSync(path,'utf8');
const startToken='  function cfPaintPrimaryResult(){';
const endToken='  window.cfPaintPrimaryResult=cfPaintPrimaryResult;';
const start=s.indexOf(startToken);
if(start<0)throw new Error('cfPaintPrimaryResult start not found');
const end=s.indexOf(endToken,start);
if(end<0)throw new Error('cfPaintPrimaryResult end not found');
const replacement=`  function cfPaintPrimaryResult(){
    const seq=++__cfResultPaintSeq;
    const r=cfResultRecord();
    const src=state._simSource||(r&&r.srcObj)||(Array.isArray(state.photos)?state.photos[0]:null);
    if(!r||!src)return false;
    const resultEl=document.getElementById('result');
    document.querySelectorAll('.screen.active').forEach(function(el){if(el!==resultEl)el.classList.remove('active');});
    if(resultEl)resultEl.classList.add('active');
    cfDismissWaitVisualOnly();
    window.__cfResultFirstPaintAt=performance.now();
    window.__cfEditHydrationScheduled=seq;
    setTimeout(function(){
      if(seq!==__cfResultPaintSeq)return;
      try{
        const before=document.getElementById('resultBefore');
        const after=document.getElementById('resultAfter');
        const beforeSrc=r.source||(r.srcObj&&r.srcObj.dataUrl)||src.dataUrl;
        if(before){before.decoding='async';if(before.getAttribute('src')!==beforeSrc)before.setAttribute('src',beforeSrc);}
        if(after){after.decoding='async';if(after.getAttribute('src')!==r.dataUrl)after.setAttribute('src',r.dataUrl);}
      }catch(e){console.error('[CaseFlow result image paint]',e);}
    },0);
    setTimeout(function(){cfRunIdle(function(){if(seq!==__cfResultPaintSeq)return;try{const el=document.getElementById('simulationCompareSlider');if(el&&typeof setupCompareSlider==='function')setupCompareSlider(el);}catch(e){console.warn('[CaseFlow compare hydrate]',e);}},1800);},800);
    setTimeout(function(){cfRunIdle(function(){if(seq!==__cfResultPaintSeq)return;try{buildEditGrid();window.__cfEditHydratedSeq=seq;}catch(e){console.warn('[CaseFlow edit hydrate]',e);}},2400);},1100);
    setTimeout(function(){cfRunIdle(function(){if(seq!==__cfResultPaintSeq)return;try{renderSimGallery();}catch(e){console.warn('[CaseFlow gallery hydrate]',e);}},2200);},1400);
    setTimeout(function(){cfRunIdle(function(){try{if(window.cfWait)window.cfWait.hideAll();}catch(e){}try{pausePreview();}catch(e){}},2200);},1700);
    setTimeout(function(){cfRunIdle(function(){try{if(window.__cfPendingGallerySync&&typeof window.renderUpload==='function'){window.__cfPendingGallerySync=false;window.renderUpload();}if(window.cfPersist&&window.cfPersist.schedule)window.cfPersist.schedule(900);}catch(e){console.warn('[CaseFlow deferred sync]',e);}},2800);},2100);
    return true;
  }
`;
s=s.slice(0,start)+replacement+s.slice(end);
fs.writeFileSync(path,s);
console.log('replaced primary result painter with async shell-first router');
