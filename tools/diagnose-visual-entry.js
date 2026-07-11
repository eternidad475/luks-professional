const fs = require('fs');
const vm = require('vm');

const file = 'caseflow_studio_v96.html';
const html = fs.readFileSync(file, 'utf8');
const lines = html.split(/\r?\n/);

function printContext(label, needle, before = 18, after = 55) {
  const idx = lines.findIndex((line) => line.includes(needle));
  console.log(`\n===== ${label} :: ${needle} :: line ${idx + 1} =====`);
  if (idx < 0) {
    console.log('NOT FOUND');
    return;
  }
  const start = Math.max(0, idx - before);
  const end = Math.min(lines.length, idx + after + 1);
  for (let i = start; i < end; i += 1) {
    console.log(`${String(i + 1).padStart(6, ' ')} | ${lines[i]}`);
  }
}

const markers = [
  ['result markup', 'id="result"'],
  ['navigation', 'function go('],
  ['result renderer', 'function renderResultImages('],
  ['result gallery', 'function renderSimGallery('],
  ['edit grid', 'function buildEditGrid('],
  ['push result', 'function pushSimResult('],
  ['autosave', 'function cfAutoSaveTempSim('],
  ['generation entry', 'window.runSimulation = async function'],
  ['result route', "go('result')"],
  ['late adoption', 'function cfArmLateAdoption('],
  ['wait overlay', 'watchdogTimer=setTimeout']
];

for (const [label, needle] of markers) printContext(label, needle);

const scriptRe = /<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi;
let match;
let scriptIndex = 0;
let syntaxFailures = 0;
while ((match = scriptRe.exec(html))) {
  scriptIndex += 1;
  const code = match[1];
  if (!code.trim()) continue;
  try {
    new vm.Script(code, { filename: `${file}:inline-${scriptIndex}` });
  } catch (error) {
    syntaxFailures += 1;
    console.error(`INLINE SCRIPT ${scriptIndex} SYNTAX ERROR`);
    console.error(error && error.stack ? error.stack : error);
  }
}

const resultRouteCount = (html.match(/go\(['"]result['"]\)/g) || []).length;
const syncAutosaveNearPush = /function pushSimResult\([\s\S]{0,2200}?cfAutoSaveTempSim\(/.test(html);
const directBase64Gallery = /function renderSimGallery\([\s\S]{0,4000}?<img src=["']\+r\.dataUrl/.test(html);
const doubleHeavyPaint = /go\(['"]result['"]\)[\s\S]{0,1800}?renderResultImages\(\)[\s\S]{0,500}?buildEditGrid\(\)/.test(html);

console.log('\n===== SUMMARY =====');
console.log(JSON.stringify({
  bytes: Buffer.byteLength(html),
  lines: lines.length,
  inlineScripts: scriptIndex,
  syntaxFailures,
  resultRouteCount,
  syncAutosaveNearPush,
  directBase64Gallery,
  doubleHeavyPaint
}, null, 2));

if (syntaxFailures) process.exitCode = 1;
