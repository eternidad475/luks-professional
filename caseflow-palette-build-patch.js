const fs = require('fs');
const path = require('path');

const htmlPath = path.join(__dirname, 'caseflow_studio_v96.html');
const patchTag = '<script src="/caseflow-palette-swap-fix.js" defer></script>';

if (!fs.existsSync(htmlPath)) {
  console.warn('[caseflow] caseflow_studio_v96.html not found. Palette patch skipped.');
  process.exit(0);
}

let html = fs.readFileSync(htmlPath, 'utf8');

if (html.includes('caseflow-palette-swap-fix.js')) {
  console.log('[caseflow] Palette swap patch already present.');
  process.exit(0);
}

if (html.includes('</body>')) {
  html = html.replace('</body>', `${patchTag}\n</body>`);
} else {
  html += `\n${patchTag}\n`;
}

fs.writeFileSync(htmlPath, html, 'utf8');
console.log('[caseflow] Palette swap patch injected.');
