(() => {
  if (window.__caseflowPaletteSwapFixInstalled) return;
  window.__caseflowPaletteSwapFixInstalled = true;

  const STYLE_ID = 'caseflow-palette-swap-fix-style';
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      [data-cf-palette-swap-fix]{min-width:44px!important;min-height:44px!important;touch-action:manipulation;cursor:pointer;-webkit-tap-highlight-color:transparent;}
      [data-cf-palette-swap-fix] .cf-swap-icon{width:18px;height:18px;display:block;position:relative;color:currentColor;transition:transform 260ms cubic-bezier(.22,.85,.24,1);}
      [data-cf-palette-swap-fix].cf-swapping .cf-swap-icon{transform:rotate(180deg);}
      [data-cf-palette-swap-fix] .cf-swap-icon:before,[data-cf-palette-swap-fix] .cf-swap-icon:after{content:"";position:absolute;left:1px;right:1px;height:2px;border-radius:999px;background:currentColor;opacity:.92;}
      [data-cf-palette-swap-fix] .cf-swap-icon:before{top:5px;}[data-cf-palette-swap-fix] .cf-swap-icon:after{bottom:5px;}
      [data-cf-palette-swap-fix] .cf-swap-icon i,[data-cf-palette-swap-fix] .cf-swap-icon b{position:absolute;width:5px;height:5px;border-top:2px solid currentColor;border-right:2px solid currentColor;}
      [data-cf-palette-swap-fix] .cf-swap-icon i{right:0;top:3px;transform:rotate(45deg);}
      [data-cf-palette-swap-fix] .cf-swap-icon b{left:0;bottom:3px;transform:rotate(225deg);}
    `;
    document.head.appendChild(style);
  }

  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const setCssVar = (name, value) => { if (value) document.documentElement.style.setProperty(name, value); };
  const fire = (el) => {
    if (!el) return;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };

  function findRangeByLabel(pattern) {
    const nodes = Array.from(document.querySelectorAll('label,.row,.range-row,.slider-row,div,section'));
    for (const el of nodes) {
      const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
      if (!pattern.test(text)) continue;
      const own = el.querySelector && el.querySelector('input[type="range"]');
      if (own) return own;
      let parent = el.parentElement;
      for (let i = 0; parent && i < 4; i += 1, parent = parent.parentElement) {
        const input = parent.querySelector && parent.querySelector('input[type="range"]');
        if (input) return input;
      }
    }
    return null;
  }

  function setValueText(input, valueText) {
    const row = input && input.closest('.row,.range-row,.slider-row,div');
    if (!row) return;
    const nodes = Array.from(row.querySelectorAll('output,span,strong,b,em,div'));
    for (let i = nodes.length - 1; i >= 0; i -= 1) {
      const text = (nodes[i].textContent || '').trim();
      if (/^\d+°?$/.test(text) || /^\d+\s*\/\s*\d+$/.test(text)) {
        nodes[i].textContent = valueText;
        return;
      }
    }
  }

  function swapHueControls() {
    const h1 = findRangeByLabel(/Color\s*1\s*Hue/i);
    const h2 = findRangeByLabel(/Color\s*2\s*Hue/i);
    if (!h1 || !h2) return false;
    const v1 = h1.value;
    const v2 = h2.value;
    h1.value = v2;
    h2.value = v1;
    setValueText(h1, `${Math.round(Number(v2))}°`);
    setValueText(h2, `${Math.round(Number(v1))}°`);
    fire(h1); fire(h2);
    return true;
  }

  function swapBlendRatio() {
    const input = findRangeByLabel(/BLEND\s*RATIO|Blend\s*Ratio/i);
    if (!input) return;
    const min = Number(input.min || 0);
    const max = Number(input.max || 100);
    const current = Number(input.value);
    if (!Number.isFinite(current)) return;
    const next = Math.max(min, Math.min(max, max - (current - min)));
    input.value = String(next);
    setValueText(input, `${Math.round(next)} / ${Math.round(max - next)}`);
    fire(input);
  }

  function runSwap(btn) {
    btn && btn.classList.add('cf-swapping');
    setTimeout(() => btn && btn.classList.remove('cf-swapping'), 280);
    try { if (navigator.vibrate) navigator.vibrate(10); } catch (_) {}

    const changedInputs = swapHueControls();
    swapBlendRatio();

    if (!changedInputs) {
      const c1 = cssVar('--c1');
      const c2 = cssVar('--c2');
      setCssVar('--c1', c2);
      setCssVar('--c2', c1);
    }

    ['cfApplyBrandAccent','applyBrandAccent','renderGradientPalette','updateGradientPaletteUI','updatePalette','applyPalette'].forEach((name) => {
      try { if (typeof window[name] === 'function') window[name](); } catch (_) {}
    });
    document.dispatchEvent(new CustomEvent('caseflow:palette-swap', { bubbles: true }));
  }

  function enhance(root = document) {
    const nodes = Array.from(root.querySelectorAll ? root.querySelectorAll('button,[role="button"],.iconbtn,div') : []);
    nodes.forEach((btn) => {
      if (!btn || btn.dataset.cfPaletteSwapFix) return;
      const text = (btn.textContent || '').replace(/\s+/g, ' ').trim();
      if (text !== '⇄' && text !== '↔') return;
      let parent = btn.parentElement;
      let context = '';
      for (let i = 0; parent && i < 5; i += 1, parent = parent.parentElement) context += ' ' + (parent.textContent || '');
      if (!/Color\s*1|Color\s*2|Hue|Palette/i.test(context)) return;
      btn.dataset.cfPaletteSwapFix = '1';
      btn.setAttribute('aria-label', 'Color 1 and Color 2 を入れ替える');
      if (btn.tagName !== 'BUTTON') btn.setAttribute('role', 'button');
      btn.textContent = '';
      const icon = document.createElement('span');
      icon.className = 'cf-swap-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.innerHTML = '<i></i><b></b>';
      btn.appendChild(icon);
    });
  }

  document.addEventListener('click', (event) => {
    const btn = event.target && event.target.closest && event.target.closest('[data-cf-palette-swap-fix]');
    if (!btn) return;
    event.preventDefault();
    event.stopPropagation();
    runSwap(btn);
  }, true);

  const observer = new MutationObserver((mutations) => {
    mutations.forEach((m) => Array.from(m.addedNodes || []).forEach((node) => node.nodeType === 1 && enhance(node)));
    enhance(document);
  });

  const start = () => {
    enhance(document);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    setTimeout(() => enhance(document), 300);
    setTimeout(() => enhance(document), 1200);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
