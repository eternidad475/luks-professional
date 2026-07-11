const fs=require('fs');
const path='caseflow_studio_v96.html';
let s=fs.readFileSync(path,'utf8');
const scriptStart=s.indexOf('/* Secondary-stage Smile Designer');
if(scriptStart<0) throw new Error('Smile Designer script not found');
const scriptEnd=s.indexOf('</script>',scriptStart);
if(scriptEnd<0) throw new Error('Smile Designer script end not found');

// Make mount() idempotent. Replacing host.innerHTML on every mutation caused the
// body-wide MutationObserver to observe its own write and enter an endless loop.
const mountStart=s.indexOf('  function mount(){',scriptStart);
const mountEnd=s.indexOf('  function removePrimaryField(){',mountStart);
if(mountStart<0||mountEnd<0||mountEnd>scriptEnd) throw new Error('Smile Designer mount block not found');
const assignAt=s.indexOf('    host.innerHTML=',mountStart);
if(assignAt<0||assignAt>mountEnd) throw new Error('Smile Designer host assignment not found');
const guard=[
  "    var mountKey=c+'|'+id+'|'+s.ratio;",
  "    if(host.dataset.cfSdMountKey===mountKey && host.querySelector('#cfSdLaunch')){removePrimaryField();return;}",
  "    host.dataset.cfSdMountKey=mountKey;",
  ''
].join('\n');
s=s.slice(0,assignAt)+guard+s.slice(assignAt);

// Expose an explicit mount hook for the dedicated result route.
const removeMarker='  function removePrimaryField(){';
const updatedRemoveAt=s.indexOf(removeMarker,mountStart);
if(updatedRemoveAt<0) throw new Error('removePrimaryField marker missing after mount patch');
s=s.slice(0,updatedRemoveAt)+'  window.cfMountSmileDesigner=mount;\n'+s.slice(updatedRemoveAt);

// Replace the self-observing body MutationObserver with a guarded, coalesced
// observer. It can still repair the launch control after legacy DOM rewrites,
// but never rewrites an already-mounted launch button.
const oldObserver="  var mo=new MutationObserver(function(){removePrimaryField();if(document.querySelector('#result.active'))mount()});mo.observe(document.body,{childList:true,subtree:true});";
const newObserver=[
  '  var moQueued=false;',
  '  var mo=new MutationObserver(function(){',
  '    removePrimaryField();',
  "    if(!document.querySelector('#result.active'))return;",
  "    var host=document.getElementById('cfSmileDesignerHost');",
  "    if(host&&host.querySelector('#cfSdLaunch'))return;",
  '    if(moQueued)return;',
  '    moQueued=true;',
  '    requestAnimationFrame(function(){moQueued=false;mount();});',
  '  });',
  '  mo.observe(document.body,{childList:true,subtree:true});'
].join('\n');
const oi=s.indexOf(oldObserver,scriptStart);
if(oi<0||oi>scriptEnd+guard.length+40) throw new Error('Smile Designer observer anchor not found');
s=s.slice(0,oi)+newObserver+s.slice(oi+oldObserver.length);

// The result-first route bypasses legacy go() wrappers. Mount Smile Designer only
// after the primary image is visible, without making it part of first paint.
const hydrateNeedle="        try{const el=$id('simulationCompareSlider');if(el&&typeof setupCompareSlider==='function')setupCompareSlider(el);}catch(e){console.warn('[CaseFlow compare hydrate]',e);}";
const hydrateAt=s.indexOf(hydrateNeedle);
if(hydrateAt<0) throw new Error('Result hydration anchor not found');
const hydrateAfter=hydrateAt+hydrateNeedle.length;
const mountSchedule="\n        setTimeout(function(){try{if(window.cfMountSmileDesigner)window.cfMountSmileDesigner();}catch(e){console.warn('[CaseFlow Smile Designer mount]',e);}},180);";
s=s.slice(0,hydrateAfter)+mountSchedule+s.slice(hydrateAfter);

fs.writeFileSync(path,s);
console.log('patched Smile Designer observer loop');
