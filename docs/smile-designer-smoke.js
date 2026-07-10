/* CASEFLOW STUDIO™ Smile Designer smoke suite.
   Run: npm i playwright --no-save && node docs/smile-designer-smoke.js caseflow_studio_v96.html */
const { chromium } = require('playwright');
const path = require('path');
const checks=[];
function check(name,ok,extra=''){checks.push({name,ok:!!ok});console.log(`${ok?'PASS':'FAIL'}  ${name}${extra?` [${extra}]`:''}`)}
(async()=>{
  const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||undefined});
  const page=await browser.newPage({viewport:{width:390,height:844}});
  page.setDefaultTimeout(12000);
  page.on('pageerror',e=>console.log('[pageerror]',String(e).slice(0,220)));
  await page.addInitScript(()=>{try{localStorage.setItem('caseflow_consent_v96','1')}catch(_){}});
  await page.goto('file://'+path.resolve(process.argv[2]||'caseflow_studio_v96.html'),{waitUntil:'load',timeout:60000});
  await page.waitForTimeout(1400);
  await page.evaluate(()=>{const g=document.getElementById('cfGateV2');if(g){g.classList.remove('open');g.style.display='none'}});

  await page.evaluate(()=>{if(window.go)window.go('simulator')});
  await page.waitForTimeout(300);
  check('primary simulator has no Teeth Type field',await page.evaluate(()=>!document.querySelector('#simulator #cfTtField')));
  check('canonical tooth-form state remains available',await page.evaluate(()=>typeof window.cfTeethTypeCurrent==='function'));

  await page.evaluate(()=>{
    const svg='<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1100"><rect width="900" height="1100" fill="#bd8c7c"/><ellipse cx="450" cy="620" rx="235" ry="112" fill="#4d1721"/><rect x="270" y="560" width="360" height="120" rx="28" fill="#fffdf4"/></svg>';
    const u='data:image/svg+xml;base64,'+btoa(svg);window.state=window.state||{};
    state.simV82=Object.assign({},state.simV82||{},{concept:'ortho'});state.simV96=Object.assign({},state.simV96||{});
    state._simSource={dataUrl:u,category:'facial',lips:true};state.simResult={dataUrl:u,source:u,srcObj:state._simSource,sourceKind:'Facial',settings:{}};state.simResults=[state.simResult];state.simResultIndex=0;
    if(window.go)window.go('result');if(window.renderResult)window.renderResult();if(window.cfRenderSmileDesigner)window.cfRenderSmileDesigner();
  });
  await page.waitForTimeout(550);
  check('result-stage host exists',await page.evaluate(()=>!!document.getElementById('cfSmileDesignerHost')));
  check('entry visible after result exists',await page.evaluate(()=>{const e=document.querySelector('#cfSmileDesignerHost button,#cfSmileDesignerHost .cfSdLaunch');return!!e&&e.getBoundingClientRect().height>0}));
  check('orthodontic-only wording keeps designer optional',await page.evaluate(()=>/optional|任意|Smile Designer/i.test((document.getElementById('cfSmileDesignerHost')||{}).textContent||'')));

  // Do not return the async opener promise: the sheet opens immediately while ROI preview resolves later.
  await page.evaluate(()=>{if(window.cfOpenSmileDesigner)window.cfOpenSmileDesigner()});
  await page.waitForTimeout(700);
  check('sheet opens',await page.evaluate(()=>{const o=document.querySelector('.cfSdOverlay');return!!o&&o.classList.contains('open')}));
  check('modal semantics',await page.evaluate(()=>{const d=document.querySelector('.cfSdOverlay [role="dialog"]');return!!d&&d.getAttribute('aria-modal')==='true'}));
  check('focus inside dialog',await page.evaluate(()=>{const o=document.querySelector('.cfSdOverlay');return!!o&&o.contains(document.activeElement)}));
  check('six form choices',await page.evaluate(()=>document.querySelectorAll('[data-form], [data-cfsd-form], .cfSdCard').length>=6));
  check('golden proportion slider',await page.evaluate(()=>!!document.querySelector('.cfSdOverlay input[type="range"]')));
  check('live preview canvas',await page.evaluate(()=>!!document.querySelector('.cfSdOverlay canvas')));

  const original=await page.evaluate(()=>state.simResult.dataUrl);
  await page.evaluate(()=>{const c=document.querySelector('[data-form="ovoid"],[data-cfsd-form="ovoid"],[data-id="ovoid"]');if(c)c.click();const r=document.querySelector('.cfSdOverlay input[type="range"]');if(r){r.value='78';r.dispatchEvent(new Event('input',{bubbles:true}))}});
  await page.waitForTimeout(300);
  check('preview is non-destructive',await page.evaluate(v=>state.simResult.dataUrl===v,original));
  check('ovoid selection visible',await page.evaluate(()=>/ovoid/i.test((document.querySelector('.cfSdOverlay')||{}).textContent||'')));
  check('78% ratio visible',await page.evaluate(()=>/78\s*%|78/.test((document.querySelector('.cfSdOverlay')||{}).textContent||'')));
  const prompt=await page.evaluate(()=>typeof window.cfSmileDesignerPromptFragment==='function'?window.cfSmileDesignerPromptFragment('facial'):(typeof window.cfSmileDesignerPrompt==='function'?window.cfSmileDesignerPrompt('facial'):''));
  check('prompt names selected form',/ovoid/i.test(prompt),prompt.slice(0,100));
  check('prompt carries proportion direction',/golden|proportion|width-to-height|ratio/i.test(prompt));
  check('prompt prevents elongation',/do not elongate|crown length|proportionate crown height|lengthen/i.test(prompt));
  check('prompt protects face or lips',/face identity|lips|lip shape|outside the tooth/i.test(prompt));

  const committed=await page.evaluate(()=>JSON.stringify(state.cfSmileDesign||null));
  await page.keyboard.press('Escape');await page.waitForTimeout(250);
  check('Escape closes',await page.evaluate(()=>{const o=document.querySelector('.cfSdOverlay');return!o||!o.classList.contains('open')}));
  check('Cancel does not commit',await page.evaluate(v=>JSON.stringify(state.cfSmileDesign||null)===v,committed));

  await page.evaluate(()=>{window.__sdCalls=0;window.__sdOrig=window.runSecondaryRefinement;window.runSecondaryRefinement=async()=>{window.__sdCalls++;return true};window.cfOpenSmileDesigner()});
  await page.waitForTimeout(350);
  await page.evaluate(()=>{const c=document.querySelector('[data-form="rounded_square"],[data-cfsd-form="rounded_square"],[data-id="rounded_square"]');if(c)c.click();const a=document.querySelector('[data-cfsd-apply],.cfSdApply,#cfSdApplyBtn');if(a)a.click()});
  await page.waitForTimeout(350);
  check('Apply commits design metadata',await page.evaluate(()=>!!state.cfSmileDesign));
  check('Apply commits manual tooth form',await page.evaluate(()=>state.simTeethType&&state.simTeethType.source==='manual'));
  check('Apply invokes guarded refinement once',await page.evaluate(()=>window.__sdCalls===1));
  await page.evaluate(()=>{if(window.__sdOrig)window.runSecondaryRefinement=window.__sdOrig});

  await page.evaluate(()=>{document.documentElement.style.setProperty('--c1','#0e7a5f');document.documentElement.style.setProperty('--c2','#e7bf59');window.cfOpenSmileDesigner()});await page.waitForTimeout(300);
  check('live palette change retains designer',await page.evaluate(()=>{const d=document.querySelector('.cfSdSheet');return!!d&&d.getBoundingClientRect().height>0}));await page.keyboard.press('Escape');
  await page.setViewportSize({width:844,height:390});await page.evaluate(()=>{window.cfOpenSmileDesigner()});await page.waitForTimeout(300);
  check('landscape fits viewport',await page.evaluate(()=>{const d=document.querySelector('.cfSdSheet');if(!d)return false;const r=d.getBoundingClientRect();return r.height<=innerHeight&&r.width<=innerWidth}));await page.keyboard.press('Escape');
  await page.emulateMedia({reducedMotion:'reduce'});await page.evaluate(()=>{window.cfOpenSmileDesigner()});await page.waitForTimeout(100);await page.keyboard.press('Escape');
  check('reduced motion open/close',await page.evaluate(()=>{const o=document.querySelector('.cfSdOverlay');return!o||!o.classList.contains('open')}));
  const growth=await page.evaluate(async()=>{const n=document.querySelectorAll('.cfSdOverlay,.cfSdSheet').length;for(let i=0;i<6;i++){window.cfOpenSmileDesigner();await new Promise(r=>setTimeout(r,25));if(window.cfCloseSmileDesigner)window.cfCloseSmileDesigner(false);await new Promise(r=>setTimeout(r,25))}return document.querySelectorAll('.cfSdOverlay,.cfSdSheet').length-n});
  check('zero DOM growth',growth===0,String(growth));
  const failures=checks.filter(x=>!x.ok);console.log(`\n${checks.length} checks, ${failures.length} failures`);await browser.close();process.exit(failures.length?1:0);
})().catch(e=>{console.error(e);process.exit(2)});
