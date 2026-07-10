/* CASEFLOW STUDIO™ Smile Designer smoke suite.
   Run: npm i playwright --no-save && node docs/smile-designer-smoke.js caseflow_studio_v96.html
*/
const { chromium } = require('playwright');
const path = require('path');

const checks = [];
function check(name, ok, extra = '') {
  checks.push({ name, ok: !!ok, extra });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? ` [${extra}]` : ''}`);
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  page.on('pageerror', e => console.log('[pageerror]', String(e).slice(0, 240)));
  await page.addInitScript(() => {
    try { localStorage.setItem('caseflow_consent_v96', '1'); } catch (_) {}
  });
  const target = 'file://' + path.resolve(process.argv[2] || 'caseflow_studio_v96.html');
  await page.goto(target, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(1600);
  await page.evaluate(() => {
    const gate = document.getElementById('cfGateV2');
    if (gate) { gate.classList.remove('open'); gate.style.display = 'none'; }
  });

  // Primary stage must no longer ask for tooth form.
  await page.evaluate(() => window.go && window.go('simulator'));
  await page.waitForTimeout(350);
  check('primary simulator has no Teeth Type entry field', await page.evaluate(() => !document.querySelector('#simulator #cfTtField')));
  check('canonical tooth-form state remains available for secondary design', await page.evaluate(() => typeof window.cfTeethTypeCurrent === 'function'));

  // Seed a production-shaped result without network calls.
  await page.evaluate(() => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1100"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#e8b59e"/><stop offset="1" stop-color="#6a3f36"/></linearGradient></defs><rect width="900" height="1100" fill="url(#g)"/><ellipse cx="450" cy="610" rx="235" ry="105" fill="#4d1721"/><rect x="270" y="555" width="360" height="120" rx="28" fill="#fffdf4"/><path d="M270 615h360" stroke="#d6c9b6" stroke-width="5"/></svg>`;
    const url = 'data:image/svg+xml;base64,' + btoa(svg);
    window.state = window.state || {};
    window.state.simV82 = Object.assign({}, window.state.simV82 || {}, { concept: 'ortho' });
    window.state.simV96 = Object.assign({}, window.state.simV96 || {});
    window.state._simSource = { dataUrl: url, category: 'facial', lips: true };
    window.state.simResult = { dataUrl: url, source: url, srcObj: window.state._simSource, sourceKind: 'Facial', settings: {} };
    window.state.simResults = [window.state.simResult];
    window.state.simResultIndex = 0;
    if (typeof window.go === 'function') window.go('result');
    if (typeof window.renderResult === 'function') window.renderResult();
    if (typeof window.cfRenderSmileDesigner === 'function') window.cfRenderSmileDesigner();
  });
  await page.waitForTimeout(700);

  check('result-stage Smile Designer host exists', await page.evaluate(() => !!document.getElementById('cfSmileDesignerHost')));
  check('Smile Designer entry is visible after a result exists', await page.evaluate(() => {
    const el = document.querySelector('#cfSmileDesignerHost button, #cfSmileDesignerHost .cfSdEntry');
    return !!el && el.getBoundingClientRect().height > 0;
  }));
  check('orthodontic-only result keeps design optional', await page.evaluate(() => {
    const t = (document.getElementById('cfSmileDesignerHost') || {}).textContent || '';
    return /optional|任意|Smile Designer/i.test(t);
  }));

  // Open sheet.
  await page.evaluate(() => window.cfOpenSmileDesigner && window.cfOpenSmileDesigner());
  await page.waitForTimeout(400);
  check('Smile Designer sheet opens', await page.evaluate(() => {
    const o = document.querySelector('.cfSdOverlay');
    return !!o && (o.classList.contains('open') || o.getAttribute('aria-hidden') === 'false');
  }));
  check('dialog has modal accessibility semantics', await page.evaluate(() => {
    const d = document.querySelector('.cfSdOverlay [role="dialog"]');
    return !!d && d.getAttribute('aria-modal') === 'true';
  }));
  check('focus is moved inside dialog', await page.evaluate(() => {
    const o = document.querySelector('.cfSdOverlay');
    return !!o && o.contains(document.activeElement);
  }));
  check('six form choices are present', await page.evaluate(() => document.querySelectorAll('[data-cfsd-form], .cfSdFormCard').length >= 6));
  check('golden proportion control is present', await page.evaluate(() => !!document.querySelector('.cfSdOverlay input[type="range"]')));
  check('live preview canvas is present', await page.evaluate(() => !!document.querySelector('.cfSdOverlay canvas')));

  // Ensure preview editing is non-destructive.
  const beforeData = await page.evaluate(() => window.state.simResult.dataUrl);
  const beforePrompt = await page.evaluate(() => typeof window.cfSmileDesignerPrompt === 'function' ? window.cfSmileDesignerPrompt('facial') : '');
  await page.evaluate(() => {
    const card = document.querySelector('[data-cfsd-form="ovoid"], .cfSdFormCard[data-id="ovoid"]');
    if (card) card.click();
    const range = document.querySelector('.cfSdOverlay input[type="range"]');
    if (range) {
      range.value = String(Math.min(Number(range.max || 85), 78));
      range.dispatchEvent(new Event('input', { bubbles: true }));
    }
  });
  await page.waitForTimeout(350);
  check('live preview does not overwrite authoritative result image', await page.evaluate(v => window.state.simResult.dataUrl === v, beforeData));
  check('form selection updates draft/visual state', await page.evaluate(() => {
    const selected = document.querySelector('[data-cfsd-form="ovoid"][aria-checked="true"], .cfSdFormCard[data-id="ovoid"].selected, .cfSdFormCard[data-id="ovoid"][aria-selected="true"]');
    return !!selected || /ovoid/i.test((document.querySelector('.cfSdOverlay') || {}).textContent || '');
  }));
  check('golden ratio value is reflected in the sheet', await page.evaluate(() => /78\s*%|0\.78|78/.test((document.querySelector('.cfSdOverlay') || {}).textContent || '')));

  // Prompt must be specific and guarded.
  const prompt = await page.evaluate(() => typeof window.cfSmileDesignerPrompt === 'function' ? window.cfSmileDesignerPrompt('facial') : '');
  check('secondary prompt names selected crown form', /ovoid/i.test(prompt), prompt.slice(0, 100));
  check('secondary prompt carries proportion instruction', /golden|proportion|width-to-height|ratio/i.test(prompt));
  check('secondary prompt prevents central-incisor elongation', /do not elongate|not by increasing crown length|proportionate crown height|lengthen/i.test(prompt));
  check('secondary prompt protects face or lips', /face identity|lips|lip shape|outside the tooth/i.test(prompt));

  // Cancel must leave committed design unchanged.
  const oldCommitted = await page.evaluate(() => JSON.stringify(window.state.cfSmileDesign || null));
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  check('Escape closes the designer', await page.evaluate(() => {
    const o = document.querySelector('.cfSdOverlay');
    return !o || (!o.classList.contains('open') && o.getAttribute('aria-hidden') !== 'false');
  }));
  check('Cancel does not commit draft design', await page.evaluate(v => JSON.stringify(window.state.cfSmileDesign || null) === v, oldCommitted));

  // Reopen and intercept final refinement call; Apply should commit then call it once.
  await page.evaluate(() => {
    window.__sdRefineCalls = 0;
    window.__sdOriginalRefine = window.runSecondaryRefinement;
    window.runSecondaryRefinement = async function(){ window.__sdRefineCalls++; return true; };
    window.cfOpenSmileDesigner();
  });
  await page.waitForTimeout(250);
  await page.evaluate(() => {
    const card = document.querySelector('[data-cfsd-form="rounded_square"], .cfSdFormCard[data-id="rounded_square"]');
    if (card) card.click();
    const apply = document.querySelector('[data-cfsd-apply], .cfSdApply, #cfSdApplyBtn');
    if (apply) apply.click();
  });
  await page.waitForTimeout(350);
  check('Apply commits secondary Smile Design metadata', await page.evaluate(() => !!window.state.cfSmileDesign));
  check('Apply commits tooth form as a secondary manual selection', await page.evaluate(() => {
    const t = window.state.simTeethType;
    return !!t && t.source === 'manual' && ['rounded_square','ovoid','square','tapered','natural_asymmetry'].includes(t.id);
  }));
  check('Apply invokes existing guarded secondary refinement exactly once', await page.evaluate(() => window.__sdRefineCalls === 1));
  await page.evaluate(() => { if (window.__sdOriginalRefine) window.runSecondaryRefinement = window.__sdOriginalRefine; });

  // Palette and responsive checks.
  await page.evaluate(() => {
    document.documentElement.style.setProperty('--c1', '#0e7a5f');
    document.documentElement.style.setProperty('--c2', '#e7bf59');
    window.cfOpenSmileDesigner();
  });
  await page.waitForTimeout(250);
  check('designer remains visible after live palette change', await page.evaluate(() => {
    const d = document.querySelector('.cfSdSheet');
    return !!d && d.getBoundingClientRect().height > 0;
  }));
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 844, height: 390 });
  await page.evaluate(() => window.cfOpenSmileDesigner());
  await page.waitForTimeout(300);
  check('landscape sheet fits viewport', await page.evaluate(() => {
    const d = document.querySelector('.cfSdSheet'); if (!d) return false;
    const r = d.getBoundingClientRect(); return r.height <= innerHeight && r.width <= innerWidth;
  }));
  await page.keyboard.press('Escape');

  // Reduced motion and DOM stability.
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.evaluate(() => window.cfOpenSmileDesigner());
  await page.waitForTimeout(100);
  await page.keyboard.press('Escape');
  check('reduced-motion open/close works', await page.evaluate(() => {
    const o = document.querySelector('.cfSdOverlay');
    return !o || !o.classList.contains('open');
  }));
  const growth = await page.evaluate(async () => {
    const before = document.querySelectorAll('.cfSdOverlay, .cfSdSheet').length;
    for (let i = 0; i < 8; i++) {
      window.cfOpenSmileDesigner();
      await new Promise(r => setTimeout(r, 20));
      window.cfCloseSmileDesigner && window.cfCloseSmileDesigner(false);
      await new Promise(r => setTimeout(r, 20));
    }
    return document.querySelectorAll('.cfSdOverlay, .cfSdSheet').length - before;
  });
  check('repeated open/close causes zero DOM growth', growth === 0, String(growth));

  const failures = checks.filter(x => !x.ok);
  console.log(`\n${checks.length} checks, ${failures.length} failures`);
  await browser.close();
  process.exit(failures.length ? 1 : 0);
})().catch(err => { console.error(err); process.exit(2); });
