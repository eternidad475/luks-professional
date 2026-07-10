// Run: npm i playwright --no-save && node docs/phase1-teeth-gallery-smoke.js caseflow_studio_v96.html <shot-dir>
// (set CHROMIUM_PATH if your Playwright build does not bundle a browser)
/* Headless smoke test for the Upper Anterior Teeth Shape Gallery.
   Drives the real caseflow_studio_v96.html in Chromium. Network calls to
   Supabase/backends fail silently offline; we exercise local UI + state. */
const { chromium } = require('playwright');
const path = require('path');

const results = [];
function check(name, ok, extra) {
  results.push({ name, ok: !!ok, extra: extra || '' });
  console.log((ok ? 'PASS' : 'FAIL') + '  ' + name + (extra ? '  [' + extra + ']' : ''));
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } }); // iPhone-ish portrait
  await page.addInitScript(() => { try { localStorage.setItem('caseflow_consent_v96', '1'); } catch (e) {} });
  page.on('pageerror', e => console.log('  [pageerror]', String(e).slice(0, 160)));

  const file = 'file://' + path.resolve(process.argv[2] || 'caseflow_studio_v96.html');
  await page.goto(file, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(1500); // let layered init scripts settle
  // Test harness only: the auth gate is a login wall for unauthenticated/offline
  // sessions; it is orthogonal to this feature and blocks synthetic pointer events.
  await page.evaluate(() => {
    var g = document.getElementById('cfGateV2');
    if (g) { g.classList.remove('open'); g.style.display = 'none'; }
  });

  // 1. simulator screen renders the Teeth Type field
  await page.evaluate(() => window.go('simulator'));
  await page.waitForTimeout(500);
  check('entry field present on simulator panel', await page.evaluate(() =>
    !!document.querySelector('#simFinishPanel #cfTtField')));
  check('patient context (sex/age) on panel BEFORE chief complaint cards', await page.evaluate(() => {
    const sex = document.querySelector('#simFinishPanel #cfTtSexSel');
    const complaints = document.querySelector('#simFinishPanel .simTargetGrid');
    return !!sex && !!complaints &&
      !!(sex.compareDocumentPosition(complaints) & Node.DOCUMENT_POSITION_FOLLOWING);
  }));
  check('context controls no longer inside the dialog', await page.evaluate(() => {
    window.cfOpenTeethTypeGallery();
    const inDialog = !!document.querySelector('#cfTtOverlay select, #cfTtOverlay [data-sex]');
    window.cfCloseTeethTypeGallery(false);
    return !inDialog;
  }));
  check('default field value is Auto', await page.evaluate(() =>
    document.getElementById('cfTtFieldValue').textContent.includes('Auto')));
  check('default state is auto', await page.evaluate(() =>
    window.state.simTeethType && window.state.simTeethType.id === 'auto'));

  // 2. baseline prompt (Auto, no context) contains no tooth-form fragment
  const basePrompt = await page.evaluate(() => window.cfTeethTypePromptFragment(false));
  check('Auto + no context emits empty fragment (production prompt unchanged)', basePrompt === '');

  // 3. open gallery
  await page.evaluate(() => window.cfOpenTeethTypeGallery());
  await page.waitForTimeout(400);
  check('overlay opens', await page.evaluate(() =>
    document.getElementById('cfTtOverlay').classList.contains('open')));
  check('dialog semantics', await page.evaluate(() => {
    const d = document.querySelector('#cfTtOverlay [role="dialog"]');
    return !!d && d.getAttribute('aria-modal') === 'true' && !!d.getAttribute('aria-labelledby');
  }));
  check('six radio cards', await page.evaluate(() =>
    document.querySelectorAll('#cfTtScroll [role="radio"]').length === 6));
  check('manual specimens use the opaline ceramic material', await page.evaluate(() => {
    const specimens = Array.from(document.querySelectorAll('#cfTtScroll .cfTtCard:not([data-id="auto"]) svg'));
    return specimens.length === 5 && specimens.every(s => s.getAttribute('data-specimen-material') === 'opaline-ceramic-v2')
      && !!document.getElementById('cfTtDefs')
      && document.getElementById('cfTtDefs').innerHTML.includes('cfTtEnamelGrain')
      && document.getElementById('cfTtDefs').innerHTML.includes('cfTtIncisalOpal');
  }));
  check('all five manual crown outlines are distinct', await page.evaluate(() => {
    const firstPaths = Array.from(document.querySelectorAll('#cfTtScroll .cfTtCard:not([data-id="auto"]) svg [data-crown-outline="left"]'));
    return firstPaths.length === 5 && new Set(firstPaths.map(p => p.getAttribute('d'))).size === 5;
  }));
  check('focus moved inside dialog', await page.evaluate(() =>
    document.getElementById('cfTtOverlay').contains(document.activeElement)));
  await page.screenshot({ path: process.argv[3] + '/gallery-open.png' });

  // 4. select rounded_square, set optional context, apply
  await page.click('.cfTtCard[data-id="rounded_square"]');
  await page.waitForTimeout(250);
  check('card aria-checked updates', await page.evaluate(() =>
    document.querySelector('.cfTtCard[data-id="rounded_square"]').getAttribute('aria-checked') === 'true'));
  await page.screenshot({ path: process.argv[3] + '/gallery-selected.png' });
  await page.click('#cfTtApplyBtn');
  await page.waitForTimeout(350);
  await page.selectOption('#cfTtSexSel', 'female');
  await page.selectOption('#cfTtAgeSel', '40代');
  await page.screenshot({ path: process.argv[3] + '/panel-context.png' });
  await page.evaluate(() => window.cfOpenTeethTypeGallery());
  await page.waitForTimeout(250);
  await page.click('#cfTtApplyBtn');
  await page.waitForTimeout(400);
  check('apply commits canonical state', await page.evaluate(() => {
    const t = window.state.simTeethType;
    return t.id === 'rounded_square' && t.source === 'manual' && !!t.selected_at
      && t.optional_context.sex === 'female' && t.optional_context.age === '40代';
  }));
  check('overlay closed after apply', await page.evaluate(() =>
    !document.getElementById('cfTtOverlay').classList.contains('open')));
  check('field summary shows selection', await page.evaluate(() =>
    document.getElementById('cfTtFieldValue').textContent.includes('Rounded Square')));
  check('focus restored to opener field', await page.evaluate(() =>
    document.activeElement && document.activeElement.id === 'cfTtField'));
  await page.screenshot({ path: process.argv[3] + '/field-applied.png' });

  // 5. prompt integration — standard and intraoral paths
  const frag = await page.evaluate(() => window.cfTeethTypePromptFragment(false));
  check('fragment is a MANDATORY requested change', frag.includes('REQUESTED CHANGE — UPPER ANTERIOR TOOTH FORM')
    && frag.includes('MANDATORY') && frag.includes('CENTRAL INCISORS first and foremost'));
  check('fragment supersedes keep-own-form guidance', frag.includes('SUPERSEDES'));
  check('fragment demands a visible outline change', frag.includes('CLEARLY VISIBLE'));
  check('fragment carries modifier', frag.includes('Combine structural width'));
  check('fragment states subordination to clinician instruction', frag.includes('OUTRANKS'));
  check('fragment forbids stereotyped sex mapping', frag.includes('masculine/feminine'));
  check('fragment forbids compensatory central-incisor elongation',
    frag.includes('Do not lengthen or enlarge the maxillary central incisors'));
  check('fragment enforces a continuous harmonious incisal curve',
    frag.includes('continuous, harmonious maxillary incisal curve') && frag.includes('never a conspicuous two-tooth downward step'));
  check('fragment includes a final morphology quality verification',
    frag.includes('Before finalizing, verify all three conditions'));
  const ovoidFrag = await page.evaluate(() => {
    const saved = JSON.parse(JSON.stringify(window.state.simTeethType));
    window.state.simTeethType = { id:'ovoid', source:'manual', selected_at:new Date().toISOString(), optional_context:{sex:null,age:null} };
    const f = window.cfTeethTypePromptFragment(false);
    window.state.simTeethType = saved;
    return f;
  });
  check('Ovoid is expressed through outline rather than crown length',
    ovoidFrag.includes('softly convex mesial and distal contours')
      && ovoidFrag.includes('do not lengthen the central incisors to signal an ovoid form'));
  check('manual family outranks the generic Tooth Shape slider family',
    ovoidFrag.includes('generic Tooth Shape slider') && ovoidFrag.includes('must not replace the selected family'));
  check('prompt version records incisal-harmony calibration',
    (await page.evaluate(() => window.cfTeethTypeMeta().prompt_version)) === 'cf-teeth-p1-v2-incisal-harmony');
  const autoFacialFrag = await page.evaluate(() => {
    const saved = JSON.parse(JSON.stringify(window.state.simTeethType));
    window.state.simTeethType = { id:'auto', source:'auto', selected_at:null, optional_context:{sex:null,age:null} };
    window.state._simSource = { dataUrl:'data:image/png;base64,iVBORw0KGgo=', category:'facial', lips:true };
    const f = window.cfTeethTypePromptFragment(false);
    window.state.simTeethType = saved; window.state._simSource = null;
    return f;
  });
  check('Auto + facial source: generator-side facial-type guidance (fallback)',
    autoFacialFrag.includes('facial-type matched') && autoFacialFrag.includes('brachyfacial')
    && autoFacialFrag.includes('dolichofacial') && autoFacialFrag.includes('not a diagnosis'));
  const autoRecFrag = await page.evaluate(() => {
    const saved = JSON.parse(JSON.stringify(window.state.simTeethType));
    window.state.simTeethType = { id:'auto', source:'auto', selected_at:null,
      optional_context:{sex:null,age:null}, auto_recommendation:{ id:'tapered', facial:'dolicho', basis:'facial-landmarks' } };
    const f = window.cfTeethTypePromptFragment(false);
    const label = document.getElementById('cfTtFieldValue') ? (window.cfRenderTeethTypeField(), document.getElementById('cfTtFieldValue').textContent) : '';
    window.state.simTeethType = saved; window.cfRenderTeethTypeField();
    return { f, label };
  });
  check('Auto + landmark recommendation reaches prompt and field label',
    autoRecFrag.f.includes('TAPERED') && autoRecFrag.f.includes('長顔型')
    && autoRecFrag.label.includes('推奨 Tapered'));
  const fullPrompt = await page.evaluate(() => {
    window.state._simSource = { dataUrl: 'data:image/png;base64,iVBORw0KGgo=', category: 'facial', lips: true };
    return window.caseflowBuildSimPrompt();
  });
  check('buildClinicalPrompt (facial path) includes fragment',
    fullPrompt.includes('REQUESTED CHANGE — UPPER ANTERIOR TOOTH FORM'));
  const intraPrompt = await page.evaluate(() => {
    window.state._simSource = { dataUrl: 'data:image/png;base64,iVBORw0KGgo=', category: 'focus', intraoral: true };
    return window.caseflowBuildSimPrompt();
  });
  check('buildClinicalPrompt (intraoral path) includes fragment',
    intraPrompt.includes('REQUESTED CHANGE — UPPER ANTERIOR TOOTH FORM'));
  check('intraoral fragment defers to absolute shot rules',
    intraPrompt.includes('absolute framing/incisal-edge rules'));

  // 6. payload metadata
  const payload = await page.evaluate(() =>
    window.buildSimulationPayload({ dataUrl: 'data:image/png;base64,iVBORw0KGgo=', category: 'facial', lips: true }));
  check('payload.teeth_type additive field', payload.teeth_type
    && payload.teeth_type.id === 'rounded_square' && payload.teeth_type.source === 'manual'
    && payload.teeth_type.optional_sex === 'female' && payload.teeth_type.optional_age === '40代'
    && !!payload.teeth_type.prompt_version);
  check('existing payload fields intact', typeof payload.denoising_strength === 'number'
    && typeof payload.prompt === 'string' && payload.concept);

  // 7. cancel restores prior selection
  await page.evaluate(() => window.cfOpenTeethTypeGallery());
  await page.waitForTimeout(250);
  await page.click('.cfTtCard[data-id="square"]');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  check('Escape cancels without committing', await page.evaluate(() =>
    window.state.simTeethType.id === 'rounded_square'));

  // 8. backdrop cancel
  await page.evaluate(() => window.cfOpenTeethTypeGallery());
  await page.waitForTimeout(250);
  await page.evaluate(() => document.querySelector('.cfTtBackdrop').click());
  await page.waitForTimeout(300);
  check('backdrop click cancels', await page.evaluate(() =>
    window.state.simTeethType.id === 'rounded_square'
    && !document.getElementById('cfTtOverlay').classList.contains('open')));

  // 9. Auto reset inside dialog
  await page.evaluate(() => window.cfOpenTeethTypeGallery());
  await page.waitForTimeout(250);
  await page.click('#cfTtAutoBtn');
  await page.click('#cfTtApplyBtn');
  await page.waitForTimeout(300);
  check('Auto reset restores Auto but preserves panel-owned sex/age', await page.evaluate(() => {
    const t = window.state.simTeethType;
    return t.id === 'auto' && t.optional_context.sex === 'female' && t.optional_context.age === '40代';
  }));

  // 10. settings snapshot stamping via pushSimResult path (simulated result record)
  await page.evaluate(() => {
    window.state.simTeethType = { id: 'ovoid', source: 'manual', selected_at: new Date().toISOString(), optional_context: { sex: null, age: null } };
  });
  const stamped = await page.evaluate(() => {
    // exercise the real stamping site through the public gallery api
    const r = { dataUrl: 'data:image/png;base64,iVBORw0KGgo=', settings: JSON.parse(JSON.stringify(window.state.simV96 || {})) };
    // pushSimResult is module-scoped; cfAutoSaveTempSim side effects are try/caught offline.
    // We reach it through the regenerate/generate path indirectly — instead assert via
    // cfTeethTypeMeta which is the single stamp source, then verify selectSimResult restore.
    return window.cfTeethTypeMeta();
  });
  check('cfTeethTypeMeta reflects canonical state', stamped.id === 'ovoid' && stamped.source === 'manual');
  const restored = await page.evaluate(() => {
    window.state.simResults = [{ dataUrl: 'data:image/png;base64,iVBORw0KGgo=', settings: Object.assign({}, window.state.simV96 || {}, { teethType: { id: 'tapered', source: 'manual', optional_sex: null, optional_age: null } }) }];
    window.state.simTeethType = { id: 'auto', source: 'auto', selected_at: null, optional_context: { sex: null, age: null } };
    window.cfSelectSimResult(0);
    return { id: window.state.simTeethType.id, leaked: 'teethType' in (window.state.simV96 || {}) };
  });
  check('selectSimResult restores variation tooth form', restored.id === 'tapered');
  check('no teethType key leaks into simV96', restored.leaked === false);

  // 11. new-case reset via clearPhotos
  await page.evaluate(() => window.clearPhotos());
  await page.waitForTimeout(200);
  check('clearPhotos resets to Auto', await page.evaluate(() =>
    window.state.simTeethType.id === 'auto'));

  // 12. no localStorage writes from the module
  check('no teeth keys in localStorage', await page.evaluate(() =>
    !Object.keys(localStorage).some(k => /teeth/i.test(k))));

  // 13. session meta carries simTeethType (cfPersist)
  await page.evaluate(() => {
    window.state.simTeethType = { id: 'square', source: 'manual', selected_at: new Date().toISOString(), optional_context: { sex: null, age: null } };
    return window.cfPersist.save();
  });
  await page.waitForTimeout(300);
  check('sessionStorage session meta persists selection', await page.evaluate(() => {
    const m = JSON.parse(sessionStorage.getItem('cf_session_meta_v96') || '{}');
    return m.simTeethType && m.simTeethType.id === 'square';
  }));

  // 14. reduced motion mode still opens/closes
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.evaluate(() => window.cfOpenTeethTypeGallery());
  await page.waitForTimeout(150);
  const rmOpen = await page.evaluate(() => document.getElementById('cfTtOverlay').classList.contains('open'));
  await page.keyboard.press('Escape');
  await page.waitForTimeout(150);
  const rmClosed = await page.evaluate(() => !document.getElementById('cfTtOverlay').classList.contains('open'));
  check('reduced-motion open/close', rmOpen && rmClosed);
  await page.emulateMedia({ reducedMotion: null });

  // 15. palette change while popup open restyles live (CSS var driven)
  await page.evaluate(() => {
    document.documentElement.style.setProperty('--c1', '#0e7a5f');
    document.documentElement.style.setProperty('--c2', '#f2c14e');
    window.cfOpenTeethTypeGallery();
  });
  await page.waitForTimeout(400);
  await page.screenshot({ path: process.argv[3] + '/gallery-alt-palette.png' });
  await page.keyboard.press('Escape');

  // 16. landscape orientation with popup open
  await page.setViewportSize({ width: 844, height: 390 });
  await page.evaluate(() => window.cfOpenTeethTypeGallery());
  await page.waitForTimeout(400);
  const landOk = await page.evaluate(() => {
    const s = document.querySelector('.cfTtSheet').getBoundingClientRect();
    return s.height <= window.innerHeight && s.height > 200;
  });
  check('landscape: sheet fits viewport', landOk);
  await page.screenshot({ path: process.argv[3] + '/gallery-landscape.png' });
  await page.keyboard.press('Escape');

  // 17. repeated open/close cycles do not accumulate DOM
  const domGrowth = await page.evaluate(async () => {
    const before = document.querySelectorAll('.cfTtOverlay, .cfTtCard').length;
    for (let i = 0; i < 12; i++) {
      window.cfOpenTeethTypeGallery();
      await new Promise(r => setTimeout(r, 30));
      window.cfCloseTeethTypeGallery(false);
      await new Promise(r => setTimeout(r, 30));
    }
    return document.querySelectorAll('.cfTtOverlay, .cfTtCard').length - before;
  });
  check('12 open/close cycles: zero DOM growth', domGrowth === 0);

  const fails = results.filter(r => !r.ok);
  console.log('\n' + results.length + ' checks, ' + fails.length + ' failures');
  await browser.close();
  process.exit(fails.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
